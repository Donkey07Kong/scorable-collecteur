import csv
import json
import os
import sys
import threading
import time
import traceback
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

import prediction_engine
import ml_ensemble
import value_bets
import odds_matrix
import collect_cotes
import auto_collect
from ml_features import build_features_live
import requests

_ml_models = None
_ml_trained = False
_historique_cache = None
_historique_cache_time = 0
_last_auto_train_time = "jamais"
_last_auto_train_round = 0

def get_historique():
    global _historique_cache, _historique_cache_time
    now = time.time()
    if _historique_cache is None or (now - _historique_cache_time > STATS_REFRESH_INTERVAL):
        _historique_cache = prediction_engine.charger_historique()
        _historique_cache_time = now
    return _historique_cache

def get_ml_models():
    global _ml_models, _ml_trained
    if _ml_models is None and not _ml_trained:
        _ml_models = ml_ensemble.load_models()
        _ml_trained = True
    return _ml_models

def train_ml_models():
    global _ml_models, _ml_trained
    historique = get_historique()
    stats = get_stats()
    max_round_csv = 0
    for h in historique:
        r = h.get("round", 0)
        if r > max_round_csv:
            max_round_csv = r
    max_train_round = max_round_csv - 10 if max_round_csv > 10 else None
    print("  [Train] max_train_round=%s (excluant rounds %d-%d)" % (max_train_round, (max_train_round or 0)+1, max_round_csv))
    models, cv = ml_ensemble.train_ensemble(
        historique, stats["team_stats"], stats["elo_ratings"],
        stats["h2h_stats"], stats["tendances"], max_train_round=max_train_round
    )
    if models:
        ml_ensemble.save_models(models)
        _ml_models = models
        _ml_trained = True
    return models, cv

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

_predict_cache = None
_predict_cache_time = 0
_predict_cache_round = 0
_enriching = False
_enrich_lock = threading.Lock()
_current_round_detected = 0
_current_round_time = 0
_current_cycle = 0
_last_cycle_increment_time = 0

CYCLE_LENGTH = 46
ROUND_DURATION_SEC = 120

def _log_enrich(msg):
    try:
        with open("server_err.log", "a", encoding="utf-8") as f:
            f.write("[ENRICH] %s\n" % msg)
    except Exception:
        pass
_stats = None
_last_refresh = 0
STATS_REFRESH_INTERVAL = 300
HISTORY_FILE = "historique_predictions.json"
MANUAL_ROUNDS_FILE = "rounds_manuels.json"
PLAYOUT_CACHE = {}
PLAYOUT_CACHE_TTL = {}
_history_enriched_cache = None
_history_enriched_time = 0
_HISTORY_ENRICHED_TTL = 30
_save_lock = threading.RLock()

PLAYOUT_URL = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues/round/{round}/playout?eventCategoryId=156008&parentEventCategoryId=8060"
FUTURS_CACHE_DURATION = 120
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "fr",
    "app-version": "34283",
    "referer": "https://bet261.mg/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
}

def get_stats():
    global _stats, _last_refresh
    now = time.time()
    if _stats is None or (now - _last_refresh > STATS_REFRESH_INTERVAL):
        historique = get_historique()
        _stats = prediction_engine.calculer_stats(historique)
        _last_refresh = now
    return _stats

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                for i in range(len(content) - 1, 0, -1):
                    if content[i] == '}':
                        try:
                            candidate = content[:i+1]
                            if not candidate.lstrip().startswith('['):
                                continue
                            data = json.loads(candidate + '\n]')
                            return data
                        except:
                            continue
            except Exception:
                pass
            return []
    return []

def save_history(history):
    with _save_lock:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False)

def _atomic_modify_history(fn):
    with _save_lock:
        history = load_history()
        result = fn(history)
        if result is not None:
            history = result
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False)
        return history

def _save_snapshot_merge(round_num, new_snap):
    def _do_merge(history):
        for entry in history:
            if entry.get("round") == round_num:
                pred_keys = set("%s|%s" % (p.get("home_team",""), p.get("away_team","")) for p in entry.get("predictions",[]))
                old_snap = entry.get("playout_snapshot", {})
                for k, v in new_snap.items():
                    if v.get("_resolved") and k in pred_keys:
                        old_snap[k] = v
                old_snap = {k: v for k, v in old_snap.items() if k in pred_keys}
                entry["playout_snapshot"] = old_snap
                break
    _atomic_modify_history(_do_merge)

def compute_calibration_data():
    history = load_history()
    all_samples = []

    for entry in history:
        preds = entry.get("predictions", [])
        snap = entry.get("playout_snapshot", {})
        for p in preds:
            team_key = "%s|%s" % (p.get("home_team", ""), p.get("away_team", ""))
            result = snap.get(team_key, {})
            if not result.get("_resolved"):
                continue

            sd = result.get("score_dom", 0)
            se = result.get("score_ext", 0)
            total = sd + se
            if sd > se:
                actual = "1"
            elif se > sd:
                actual = "2"
            else:
                actual = "X"
            actual_ou25 = "Over" if total > 2.5 else "Under"
            actual_ou35 = "Over" if total > 3.5 else "Under"
            actual_pair = "Pair" if total % 2 == 0 else "Impair"
            actual_dc_1X = actual in ("1", "X")
            actual_dc_X2 = actual in ("X", "2")
            actual_dc_12 = actual in ("1", "2")

            sample = {
                "round": p.get("round", entry.get("round", 0)),
                "home": p.get("home_team", ""),
                "away": p.get("away_team", ""),
                "actual_result": actual,
                "actual_ou25": actual_ou25,
                "actual_ou35": actual_ou35,
                "actual_pair": actual_pair,
                "actual_dc_1X": actual_dc_1X,
                "actual_dc_X2": actual_dc_X2,
                "actual_dc_12": actual_dc_12,
                "actual_score": "%d-%d" % (sd, se),
                "prob_dom": p.get("prob_dom", 33.3),
                "prob_nul": p.get("prob_nul", 33.3),
                "prob_ext": p.get("prob_ext", 33.3),
                "prob_over_25": p.get("prob_over_25", 50),
                "prob_over_35": p.get("prob_over_35", 35),
                "prob_pair": p.get("prob_pair", 50),
                "prob_dc_1X": p.get("prob_dc_1X", 66),
                "prob_dc_X2": p.get("prob_dc_X2", 66),
                "prob_dc_12": p.get("prob_dc_12", 66),
                "dc_pred": p.get("dc_pred", ""),
                "confidence": p.get("confidence", 50),
                "res_code": p.get("res_code", "?"),
                "ml_confidence": p.get("ml_confidence", 0),
                "ml_pred_1x2": p.get("ml_pred_1x2", "?"),
                "tabpfn_conf": p.get("tabpfn_conf", 0),
            }
            all_samples.append(sample)

    if not all_samples:
        return {"total": 0, "bins": {}, "metrics": {}, "samples": []}

    def make_bins(key, actual_key, positive_val, n_bins=10):
        bins = {}
        for i in range(n_bins):
            lo = i * (100.0 / n_bins)
            hi = (i + 1) * (100.0 / n_bins)
            label = "%.0f-%.0f%%" % (lo, hi)
            correct = 0
            total = 0
            for s in all_samples:
                prob = s.get(key, 50)
                if lo <= prob < hi:
                    total += 1
                    if s.get(actual_key) == positive_val:
                        correct += 1
            if total > 0:
                bins[label] = {
                    "bin_center": round((lo + hi) / 2, 1),
                    "predicted": round((lo + hi) / 2, 1),
                    "actual": round(correct / total * 100, 1),
                    "count": total,
                    "correct": correct,
                }
        return bins

    bins_1x2_home = make_bins("prob_dom", "actual_result", "1")
    bins_1x2_draw = make_bins("prob_nul", "actual_result", "X")
    bins_1x2_away = make_bins("prob_ext", "actual_result", "2")
    bins_ou25 = make_bins("prob_over_25", "actual_ou25", "Over")
    bins_ou35 = make_bins("prob_over_35", "actual_ou35", "Over")

    def brier_score(key, actual_key, positive_val):
        n = 0
        sse = 0.0
        for s in all_samples:
            prob = s.get(key, 50) / 100.0
            actual_val = 1.0 if s.get(actual_key) == positive_val else 0.0
            sse += (prob - actual_val) ** 2
            n += 1
        return round(sse / n, 4) if n > 0 else 0

    def accuracy(key, actual_key):
        correct = sum(1 for s in all_samples if s.get("res_code") == s.get(actual_key))
        return round(correct / len(all_samples) * 100, 1) if all_samples else 0

    metrics = {
        "total_samples": len(all_samples),
        "brier_home": brier_score("prob_dom", "actual_result", "1"),
        "brier_draw": brier_score("prob_nul", "actual_result", "X"),
        "brier_away": brier_score("prob_ext", "actual_result", "2"),
        "brier_ou25": brier_score("prob_over_25", "actual_ou25", "Over"),
        "accuracy_1x2": accuracy("res_code", "actual_result"),
        "accuracy_ou25": round(sum(1 for s in all_samples if (s.get("prob_over_25", 50) > 50 and s.get("actual_ou25") == "Over") or (s.get("prob_over_25", 50) <= 50 and s.get("actual_ou25") == "Under")) / len(all_samples) * 100, 1),
        "avg_confidence": round(sum(s.get("confidence", 50) for s in all_samples) / len(all_samples), 1),
        "distribution": {
            "home": sum(1 for s in all_samples if s.get("actual_result") == "1"),
            "draw": sum(1 for s in all_samples if s.get("actual_result") == "X"),
            "away": sum(1 for s in all_samples if s.get("actual_result") == "2"),
            "over25": sum(1 for s in all_samples if s.get("actual_ou25") == "Over"),
            "under25": sum(1 for s in all_samples if s.get("actual_ou25") == "Under"),
        },
        "high_conf_accuracy": {},
    }

    for thr in [60, 70, 75, 80, 85, 90]:
        high = [s for s in all_samples if s.get("confidence", 0) >= thr]
        if high:
            correct = sum(1 for s in high if s.get("res_code") == s.get("actual_result"))
            metrics["high_conf_accuracy"][str(thr)] = {
                "n": len(high),
                "accuracy": round(correct / len(high) * 100, 1),
            }

    rounds_list = sorted(set(s.get("round", 0) for s in all_samples))
    recent = [s for s in all_samples if s.get("round", 0) in rounds_list[-5:]] if len(rounds_list) > 5 else all_samples
    metrics["recent_5r"] = {
        "total": len(recent),
        "accuracy_1x2": round(sum(1 for s in recent if s.get("res_code") == s.get("actual_result")) / len(recent) * 100, 1) if recent else 0,
    }

    return {
        "total": len(all_samples),
        "rounds": rounds_list,
        "bins": {
            "home_1x2": bins_1x2_home,
            "draw_1x2": bins_1x2_draw,
            "away_1x2": bins_1x2_away,
            "over_ou25": bins_ou25,
            "over_ou35": bins_ou35,
        },
        "metrics": metrics,
        "last_50": all_samples[-50:] if len(all_samples) > 50 else all_samples,
    }

def load_manual_rounds():
    if os.path.exists(MANUAL_ROUNDS_FILE):
        with open(MANUAL_ROUNDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_manual_rounds(rounds):
    with open(MANUAL_ROUNDS_FILE, "w", encoding="utf-8") as f:
        json.dump(rounds, f, ensure_ascii=False)

def get_all_teams():
    stats = get_stats()
    return sorted(stats.get("team_stats", {}).keys())

def lookup_teams_from_history(match_id):
    """Recherche les noms d'equipes pour un match_id dans l'historique des predictions"""
    history = load_history()
    for entry in history:
        for pred in entry.get("predictions", []):
            if pred.get("match_id") == match_id:
                return {"home_team": pred.get("home_team", "?"), "away_team": pred.get("away_team", "?")}
    return {}

def lookup_teams_from_history_bulk(round_num):
    """Construit un dict match_id -> {home_team, away_team} pour un round depuis l'historique"""
    history = load_history()
    result = {}
    for entry in history:
        if entry.get("round") == round_num:
            for pred in entry.get("predictions", []):
                mid = pred.get("match_id")
                if mid:
                    result[mid] = {"home_team": pred.get("home_team", "?"), "away_team": pred.get("away_team", "?")}
            break
    return result

def fix_csv_question_marks():
    """Corriger les lignes avec ? dans donnees_equipes.csv en utilisant l'historique"""
    file_path = "donnees_equipes.csv"
    if not os.path.exists(file_path):
        return 0

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    fixed = 0
    rounds_to_fix = set()
    for row in rows:
        if row.get("home_team") == "?" or row.get("away_team") == "?":
            rounds_to_fix.add(int(row.get("round", 0)))

    for rnd in rounds_to_fix:
        team_map = lookup_teams_from_history_bulk(rnd)
        if not team_map:
            continue

        team_list = [(p.get("home_team", "?"), p.get("away_team", "?"))
                     for entry in load_history() if entry.get("round") == rnd
                     for p in entry.get("predictions", [])]
        if not team_list:
            continue

        round_rows = [row for row in rows if int(row.get("round", 0)) == rnd]

        if len(round_rows) == len(team_list):
            for i, row in enumerate(round_rows):
                if (row.get("home_team") == "?" or row.get("away_team") == "?") and i < len(team_list):
                    row["home_team"] = team_list[i][0]
                    row["away_team"] = team_list[i][1]
                    fixed += 1

        for row in round_rows:
            if row.get("home_team") == "?" or row.get("away_team") == "?":
                mid = int(row.get("match_id", 0))
                if mid and mid in team_map:
                    row["home_team"] = team_map[mid]["home_team"]
                    row["away_team"] = team_map[mid]["away_team"]
                    fixed += 1

    if fixed > 0:
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return fixed

def sauvegarder_resultat_round(round_num, matchs_data):
    """Sauvegarde les resultats d'un round dans donnees_equipes.csv"""
    file_path = "donnees_equipes.csv"
    file_exists = os.path.exists(file_path) and os.path.getsize(file_path) > 10

    rows = []
    if file_exists:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

    existing_pairs = set()
    for row in rows:
        if int(row.get("round", 0)) == round_num:
            existing_pairs.add((row.get("home_team", ""), row.get("away_team", "")))

    new_pairs = set((m["home_team"], m["away_team"]) for m in matchs_data)
    all_new = new_pairs.issubset(existing_pairs)

    if all_new:
        return False

    fieldnames = ["round", "match_id", "home_team", "away_team", "score_final_dom", "score_final_ext",
                  "nb_buts_total", "nb_buts_dom", "nb_buts_ext", "minutes_buts", "nb_evenements",
                  "premier_but_minute", "premier_but_equipe", "intervalle_moyen", "intervalle_max",
                  "intervalle_min", "victoire", "cycle"]

    cycle_num = 1
    try:
        state_path = "auto_collect_state.json"
        if os.path.exists(state_path):
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
                cycle_num = state.get("cycle", 1)
    except:
        pass

    with open(file_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for m in matchs_data:
            sd, se = m["score_dom"], m["score_ext"]
            total = sd + se
            victoire = "dom" if sd > se else "ext" if se > sd else "nul"
            writer.writerow({
                "round": round_num,
                "match_id": m.get("match_id", 0),
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "score_final_dom": sd,
                "score_final_ext": se,
                "nb_buts_total": total,
                "nb_buts_dom": sd,
                "nb_buts_ext": se,
                "minutes_buts": "",
                "nb_evenements": 0,
                "premier_but_minute": "",
                "premier_but_equipe": "",
                "intervalle_moyen": 0,
                "intervalle_max": 0,
                "intervalle_min": 0,
                "victoire": victoire,
                "cycle": str(cycle_num),
            })
    return True

def _try_resolve_all(rounds_list):
    """Essaie de resoudre les rounds non-resolus par matching par ID, puis par playout_id_map."""
    global _stats, _last_refresh
    history = load_history()
    updated_any = False
    round_updates = {}
    for rnd in rounds_list:
        entry = None
        for h in history:
            if h.get("round") == rnd and h.get("cycle", _current_cycle) == _current_cycle:
                entry = h
                break
        if not entry:
            continue

        preds = entry.get("predictions", [])
        snap = entry.get("playout_snapshot", {})
        playout_id_map = entry.get("playout_id_map", {})
        if not preds:
            continue

        results_by_id, ordered_ids, ordered_results = fetch_playout_with_ids(rnd)

        resolved_count = 0
        unresolved_preds = []
        for pred in preds:
            team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
            if snap.get(team_key, {}).get("_resolved"):
                continue
            mid = pred.get("match_id", 0)
            if mid and mid in results_by_id:
                pr = dict(results_by_id[mid])
                pr["home_team"] = pred.get("home_team", "")
                pr["away_team"] = pred.get("away_team", "")
                pr["_resolved"] = True
                snap[team_key] = pr
                playout_id_map[team_key] = mid
                resolved_count += 1
            else:
                unresolved_preds.append(pred)

        if unresolved_preds and playout_id_map:
            for pred in unresolved_preds:
                team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
                saved_pid = playout_id_map.get(team_key)
                if saved_pid and saved_pid in results_by_id:
                    pr = dict(results_by_id[saved_pid])
                    pr["home_team"] = pred.get("home_team", "")
                    pr["away_team"] = pred.get("away_team", "")
                    pr["_resolved"] = True
                    snap[team_key] = pr
                    resolved_count += 1

        if unresolved_preds and len(ordered_ids) == len(preds):
            for idx, pred in enumerate(preds):
                team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
                if snap.get(team_key, {}).get("_resolved"):
                    continue
                if idx < len(ordered_results):
                    pr = dict(ordered_results[idx])
                    pr["home_team"] = pred.get("home_team", "")
                    pr["away_team"] = pred.get("away_team", "")
                    pr["_resolved"] = True
                    snap[team_key] = pr
                    playout_id_map[team_key] = ordered_ids[idx]
                    resolved_count += 1
            entry["playout_id_map"] = playout_id_map
            print("  [Collecteur] Round %d: built playout_id_map from position match (%d)" % (rnd, resolved_count))

        if resolved_count > 0:
            round_updates[rnd] = {"snap": snap, "id_map": dict(playout_id_map)}
            updated_any = True
            print("  [Collecteur] Round %d: resolu %d matchs" % (rnd, resolved_count))

    if updated_any:
        def _persist_resolve(history):
            for rnd_u, upd in round_updates.items():
                for h in history:
                    if h.get("round") == rnd_u:
                        h.setdefault("playout_snapshot", {}).update(
                            {k: v for k, v in upd["snap"].items() if v.get("_resolved")}
                        )
                        if upd["id_map"]:
                            h["playout_id_map"] = upd["id_map"]
                        break
        _atomic_modify_history(_persist_resolve)
        _stats = None
        _last_refresh = time.time()


def _process_completed_round(completed_round):
    """Traite un round termine: met a jour le snapshot et sauvegarde dans le CSV."""
    global _stats, _last_refresh
    history = load_history()
    entry = None
    for h in history:
        if h.get("round") == completed_round and h.get("cycle", _current_cycle) == _current_cycle:
            entry = h
            break
    if not entry:
        return

    preds = entry.get("predictions", [])
    snap = entry.get("playout_snapshot", {})
    playout_id_map = entry.get("playout_id_map", {})

    results_by_id, ordered_ids, ordered_results = fetch_playout_with_ids(completed_round)

    unresolved_preds = []
    updated = 0
    for pred in preds:
        team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
        if snap.get(team_key, {}).get("_resolved"):
            continue
        mid = pred.get("match_id", 0)

        if mid and mid in results_by_id:
            pr = dict(results_by_id[mid])
            pr["home_team"] = pred.get("home_team", "")
            pr["away_team"] = pred.get("away_team", "")
            pr["_resolved"] = True
            snap[team_key] = pr
            playout_id_map[team_key] = mid
            updated += 1
        else:
            unresolved_preds.append(pred)

    if unresolved_preds and playout_id_map:
        for pred in unresolved_preds:
            team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
            saved_pid = playout_id_map.get(team_key)
            if saved_pid and saved_pid in results_by_id:
                pr = dict(results_by_id[saved_pid])
                pr["home_team"] = pred.get("home_team", "")
                pr["away_team"] = pred.get("away_team", "")
                pr["_resolved"] = True
                snap[team_key] = pr
                updated += 1
                unresolved_preds.remove(pred)

    if unresolved_preds and len(ordered_ids) == len(preds):
        for idx, pred in enumerate(preds):
            team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
            if snap.get(team_key, {}).get("_resolved"):
                continue
            if idx < len(ordered_results):
                pr = dict(ordered_results[idx])
                pr["home_team"] = pred.get("home_team", "")
                pr["away_team"] = pred.get("away_team", "")
                pr["_resolved"] = True
                snap[team_key] = pr
                playout_id_map[team_key] = ordered_ids[idx]
                updated += 1
        entry["playout_id_map"] = playout_id_map
        if updated:
            print("  [Collecteur] Round %d: built playout_id_map from position match" % completed_round)

    if updated > 0:
        def _persist_completed(history):
            for h in history:
                if h.get("round") == completed_round:
                    h.setdefault("playout_snapshot", {}).update(
                        {k: v for k, v in snap.items() if v.get("_resolved")}
                    )
                    if playout_id_map:
                        h["playout_id_map"] = playout_id_map
                    resolved_snap = h.get("playout_snapshot", {})
                    preds_in_entry = h.get("predictions", [])
                    all_resolved = True
                    for p in preds_in_entry:
                        tk = "%s|%s" % (p.get("home_team",""), p.get("away_team",""))
                        s = resolved_snap.get(tk, {})
                        if s.get("_resolved") and not p.get("has_result"):
                            p["actual_score_dom"] = s.get("score_dom", 0)
                            p["actual_score_ext"] = s.get("score_ext", 0)
                            p["actual_total"] = s.get("total", 0)
                            p["has_result"] = True
                            p["result_source"] = "playout_id"
                        if not p.get("has_result"):
                            all_resolved = False
                    if preds_in_entry and all_resolved:
                        h["has_result"] = True
                    break
        _atomic_modify_history(_persist_completed)
        print("  [Collecteur] Round %d: %d resolves (completed)" % (completed_round, updated))

    matchs_data = []
    for pred in preds:
        team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
        s = snap.get(team_key, {})
        if s.get("_resolved") or s.get("total", 0) > 0:
            matchs_data.append({
                "home_team": pred.get("home_team", "?"),
                "away_team": pred.get("away_team", "?"),
                "match_id": pred.get("match_id", 0),
                "score_dom": s.get("score_dom", 0),
                "score_ext": s.get("score_ext", 0),
            })

    if matchs_data and len(matchs_data) == len(preds):
        all_known = all(m.get("home_team", "?") != "?" for m in matchs_data)
        if all_known:
            saved = sauvegarder_resultat_round(completed_round, matchs_data)
            if saved:
                print("  [Collecteur] Round %d sauvegarde CSV (%d matchs)" % (completed_round, len(matchs_data)))
                _stats = None
                _last_refresh = time.time()
                threading.Thread(target=_auto_retrain, args=(completed_round,), daemon=True).start()


def _auto_retrain(round_num):
    global _ml_models, _ml_trained, _last_auto_train_time, _last_auto_train_round
    try:
        print("  [Auto-Train] Demarrage apres round %d..." % round_num)
        historique = prediction_engine.charger_historique()
        stats = prediction_engine.calculer_stats(historique)
        max_round_csv = max(int(d.get("round", 0)) for d in historique)
        max_train_round = max_round_csv - 10 if max_round_csv > 10 else None
        models, cv = ml_ensemble.train_ensemble_fast(
            historique, stats["team_stats"], stats["elo_ratings"],
            stats["h2h_stats"], stats["tendances"], max_train_round=max_train_round
        )
        if models:
            ml_ensemble.save_models(models)
            _ml_models = models
            _ml_trained = True
            _last_auto_train_time = time.strftime("%Y-%m-%d %H:%M:%S")
            _last_auto_train_round = round_num
            print("  [Auto-Train] OK! CV: rf_1x2=%.1f%% lgbm_ou25=%.1f%%" % (
                cv.get("rf_1x2", 0) * 100, cv.get("lgbm_ou25", 0) * 100))
    except Exception as e:
        print("  [Auto-Train] Erreur: %s" % e)


def collecteur_resultats():
    """Thread arriere-plan qui collecte automatiquement les resultats"""
    global _stats, _last_refresh, _current_round_detected, _current_round_time, _predict_cache, _predict_cache_round, _current_cycle

    def _clog(msg):
        try:
            with open("server_err.log", "a", encoding="utf-8") as f:
                f.write("[COLLECTEUR] %s\n" % msg)
                f.flush()
        except Exception:
            pass

    _clog("Demarrage collecteur, cycle=%d" % _current_cycle)
    try:
        history = load_history()
        if history:
            rounds_with_unresolved = []
            for h in history:
                snap = h.get("playout_snapshot", {})
                if snap and any(not v.get("_resolved") for v in snap.values()):
                    rounds_with_unresolved.append(h["round"])
            if rounds_with_unresolved:
                _clog("Rounds non-resolus: %s" % sorted(rounds_with_unresolved))
                _try_resolve_all(rounds_with_unresolved)
    except Exception as ex:
        _clog("Erreur resolve init: %s" % ex)
    _clog("Loop principal demarre")
    last_round_seen = None
    first_iteration = True
    while True:
        try:
            headers = prediction_engine.HEADERS
            r = requests.get(prediction_engine.MATCHES_URL, headers=headers, timeout=10)
            data = r.json()
            rounds = data.get("rounds", [])
            current_round = None
            current_matches = []
            for rnd in rounds:
                matches = rnd.get("matches", [])
                rn = rnd.get("roundNumber")
                if matches:
                    if current_round is None or rn > current_round:
                        current_round = rn
                        current_matches = matches

            if current_round:
                _current_round_detected = current_round
                _current_round_time = time.time()
                if current_round != _predict_cache_round:
                    _predict_cache = None
                    _predict_cache_round = current_round

                now = time.time()
                if last_round_seen is None and first_iteration:
                    _hist = load_history()
                    _max_hist_round = max((h.get("round", 0) for h in _hist), default=0)
                    if _max_hist_round > current_round:
                        _current_cycle += 1
                        _clog("Cycle %d detecte au demarrage (hist max=R%d, API R%d)" % (_current_cycle, _max_hist_round, current_round))
                elif last_round_seen and current_round < last_round_seen:
                    _current_cycle += 1
                    _clog("Cycle %d detecte! R%d -> %d" % (_current_cycle, last_round_seen, current_round))
                    _stats = None
                    _last_refresh = now

                if last_round_seen and current_round != last_round_seen:
                    _clog("Transition R%d -> R%d" % (last_round_seen, current_round))
                    if current_round > last_round_seen:
                        for cr in range(last_round_seen, current_round):
                            _process_completed_round(cr)
                    else:
                        for cr in range(last_round_seen, 47):
                            _process_completed_round(cr)
                        for cr in range(1, current_round):
                            _process_completed_round(cr)

                last_round_seen = current_round
                first_iteration = False

                history = load_history()
                entry_found = False
                for entry in history:
                    if entry.get("round") == current_round and entry.get("cycle", _current_cycle) == _current_cycle:
                        entry_found = True
                        break

                if not entry_found and current_matches:
                    _clog("Nouveau R%d, generation..." % current_round)
                    try:
                        stats = get_stats()
                        predictions, _ = prediction_engine.predire_tous(stats)
                        if predictions:
                            save_predictions(predictions, current_round)
                            _clog("R%d sauvegardee (%d matchs)" % (current_round, len(predictions)))
                    except Exception as ex:
                        _clog("Erreur save R%d: %s" % (current_round, ex))
            else:
                _clog("Pas de round actif")
        except Exception as ex:
            _clog("ERROR: %s" % str(ex))
        time.sleep(5)

def fetch_playout_with_ids(round_num):
    """Recupere le playout et retourne (results_by_id, ordered_ids, ordered_results).
    results_by_id: {playout_match_id: {score_dom, score_ext, total}}
    ordered_ids: [playout_match_id, ...] dans l'ordre de l'API
    ordered_results: [{score_dom, score_ext, total}, ...] dans l'ordre
    """
    url = PLAYOUT_URL.format(round=round_num)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        data = resp.json()
        matches = data.get("matches", [])
        results_by_id = {}
        ordered_ids = []
        ordered_results = []
        for ev in matches:
            mid = ev.get("id")
            goals = ev.get("goals", [])
            if goals:
                final = goals[-1]
                hs = int(final.get("homeScore", 0))
                aws = int(final.get("awayScore", 0))
            else:
                hs = 0
                aws = 0
            entry = {"score_dom": hs, "score_ext": aws, "total": hs + aws}
            results_by_id[mid] = entry
            ordered_ids.append(mid)
            ordered_results.append(entry)
        return results_by_id, ordered_ids, ordered_results
    except Exception:
        return {}, [], []


def save_predictions(predictions, round_num):
    playout_snapshot = {}
    playout_id_map = {}
    for pred in predictions:
        team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
        playout_snapshot[team_key] = {
            "score_dom": 0, "score_ext": 0, "total": 0,
            "home_team": pred.get("home_team", ""),
            "away_team": pred.get("away_team", ""),
            "_resolved": False,
        }

    accu_list = []
    try:
        accu_list = value_bets.generate_accumulators(predictions, favoris_only=False)
    except Exception:
        accu_list = []

    simples_list = []
    try:
        history_snapshot = load_history()
        simples_list = value_bets.generate_simples(predictions, max_simples=6, min_edge=0, history=history_snapshot)
    except Exception:
        simples_list = []

    pred_map = {}
    for p in predictions:
        pk = "%s|%s" % (p.get("home_team", ""), p.get("away_team", ""))
        pred_map[pk] = p

    for simp in simples_list:
        pk = "%s|%s" % (simp.get("home_team", ""), simp.get("away_team", ""))
        pred = pred_map.get(pk, {})
        simp["ou_pred"] = pred.get("ou_pred", "Under 2.5")
        simp["ou_confidence"] = pred.get("ou_confidence", 70)
        simp["prob_over_25"] = pred.get("prob_over_25", 28)
        simp["prob_under_25"] = pred.get("prob_under_25", 72)

    h2h_simples = []
    try:
        h2h_simples = value_bets.generate_h2h_simples(predictions, max_simples=8)
    except Exception:
        h2h_simples = []

    h2h_accu_list = []
    try:
        h2h_accu_list = value_bets.generate_h2h_accumulators(predictions, max_accus=5)
    except Exception:
        h2h_accu_list = []

    ou_h2h_simples = []
    try:
        ou_h2h_simples = value_bets.generate_ou_h2h_simples(predictions, max_simples=6)
    except Exception:
        ou_h2h_simples = []

    all_resolved = playout_snapshot and all(
        v.get("_resolved") for v in playout_snapshot.values()
    )

    entry = {
        "round": round_num,
        "cycle": _current_cycle,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "has_result": all_resolved if playout_snapshot else False,
        "predictions": predictions,
        "playout_snapshot": playout_snapshot,
        "playout_id_map": playout_id_map,
        "team_order": [(p.get("home_team", ""), p.get("away_team", "")) for p in predictions],
        "accumulators": accu_list,
        "simples": simples_list,
        "h2h_simples": h2h_simples,
        "h2h_accumulators": h2h_accu_list,
        "ou_h2h_simples": ou_h2h_simples,
    }

    def _insert_entry(history):
        existing_idx = None
        for i, h in enumerate(history):
            if h.get("round") == round_num and h.get("cycle", 0) == _current_cycle:
                existing_idx = i
                break
        pred_keys = set("%s|%s" % (p.get("home_team",""), p.get("away_team","")) for p in predictions)
        if existing_idx is not None:
            old_snap = history[existing_idx].get("playout_snapshot", {})
            for k, v in old_snap.items():
                if k not in playout_snapshot and k in pred_keys:
                    playout_snapshot[k] = v
            entry["playout_snapshot"] = {k: v for k, v in playout_snapshot.items() if k in pred_keys}
            history[existing_idx] = entry
        else:
            history.append(entry)
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    _atomic_modify_history(_insert_entry)

def fetch_playout_results(round_num):
    now = time.time()
    if round_num in PLAYOUT_CACHE:
        if now - PLAYOUT_CACHE_TTL.get(round_num, 0) < 300:
            return PLAYOUT_CACHE[round_num]
        else:
            del PLAYOUT_CACHE[round_num]

    url = PLAYOUT_URL.format(round=round_num)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=3)
        data = resp.json()
        matches = data.get("matches", [])
        results = {}
        for ev in matches:
            match_id = ev.get("id")
            goals = ev.get("goals", [])
            if goals:
                final = goals[-1]
                hs = int(final.get("homeScore", 0))
                aws = int(final.get("awayScore", 0))
            else:
                hs = 0
                aws = 0
            results[match_id] = {
                "score_dom": hs,
                "score_ext": aws,
                "total": hs + aws,
            }
        PLAYOUT_CACHE[round_num] = results
        PLAYOUT_CACHE_TTL[round_num] = time.time()
        return results
    except Exception:
        PLAYOUT_CACHE[round_num] = {}
        PLAYOUT_CACHE_TTL[round_num] = time.time()
        return {}

def charger_resultats_equipes():
    import csv
    data = {}
    if os.path.exists("donnees_equipes.csv"):
        with open("donnees_equipes.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rnd = int(row["round"])
                if rnd not in data:
                    data[rnd] = []
                data[rnd].append({
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "match_id": int(row.get("match_id", 0)),
                    "score_dom": int(row["score_final_dom"]),
                    "score_ext": int(row["score_final_ext"]),
                })
    return data

def fetch_playout_ordered(round_num):
    """Recupere les resultats du playout en ordre (pour matching par position)."""
    url = PLAYOUT_URL.format(round=round_num)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        data = resp.json()
        matches = data.get("matches", [])
        results = []
        for ev in matches:
            goals = ev.get("goals", [])
            if goals:
                final = goals[-1]
                hs = int(final.get("homeScore", 0))
                aws = int(final.get("awayScore", 0))
            else:
                hs = 0
                aws = 0
            results.append({
                "score_dom": hs,
                "score_ext": aws,
                "total": hs + aws,
            })
        return results
    except Exception:
        return []


FUTURS_ROUND_CACHE = {}
FUTURS_ROUND_TTL = {}

def fetch_rounds_from_main():
    """Fetch all rounds with matches from the main endpoint (includes odds)."""
    now = time.time()
    cache_key = "main"
    if cache_key in FUTURS_ROUND_CACHE and now - FUTURS_ROUND_TTL.get(cache_key, 0) < FUTURS_CACHE_DURATION:
        return FUTURS_ROUND_CACHE[cache_key]

    url = prediction_engine.MATCHES_URL
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        rounds = data.get("rounds", [])
        result_rounds = []
        for rnd in rounds:
            rn = rnd.get("roundNumber", 0)
            matches_raw = rnd.get("matches", [])
            if not matches_raw:
                continue
            matches = []
            for ev in matches_raw:
                home = ev.get("homeTeam", {}).get("name", "?")
                away = ev.get("awayTeam", {}).get("name", "?")
                mid = ev.get("id", 0)
                cotes = prediction_engine.extraire_cotes(ev)
                matches.append({
                    "match_id": mid,
                    "home_team": home,
                    "away_team": away,
                    "cotes": cotes,
                })
            result_rounds.append({
                "round": rn,
                "matches": matches,
                "n_matches": len(matches),
            })
        FUTURS_ROUND_CACHE[cache_key] = result_rounds
        FUTURS_ROUND_TTL[cache_key] = time.time()
        return result_rounds
    except Exception:
        return FUTURS_ROUND_CACHE.get(cache_key, [])


def predire_calendrier():
    stats = get_stats()
    historique = get_historique()
    ml_models = None
    try:
        ml_models = get_ml_models()
    except Exception:
        pass

    all_rounds = fetch_rounds_from_main()
    result_rounds = []

    for rnd in all_rounds:
        predicted_matches = []
        for m in rnd.get("matches", []):
            home = m["home_team"]
            away = m["away_team"]
            cotes = m.get("cotes", {})
            probas = prediction_engine.cotes_vers_proba(cotes) if cotes.get("cote_1") else {}
            pred = prediction_engine.predire_match(stats, probas, home, away)

            if ml_models:
                try:
                    feats = build_features_live(
                        home, away, rnd.get("round", 0),
                        historique, stats["team_stats"], stats["elo_ratings"],
                        stats["h2h_stats"], stats["tendances"]
                    )
                    if feats and feats[0] is not None:
                        ml_pred = ml_ensemble.predict_ensemble(ml_models, feats[0])
                        if ml_pred:
                            pred = ml_ensemble.hybrid_predict(pred, ml_pred)
                except Exception:
                    pass

            pred["cotes"] = cotes
            predicted_matches.append(pred)

        result_rounds.append({
            "round": rnd.get("round", 0),
            "matches": predicted_matches,
            "n_matches": len(predicted_matches),
        })

    return {"rounds": result_rounds, "n_rounds": len(result_rounds)}


def _enrich_from_snapshots(history):
    for entry in history:
        all_resolved = True
        for pred in entry.get("predictions", []):
            if pred.get("has_result"):
                continue
            team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
            snap = entry.get("playout_snapshot", {})
            if team_key in snap and snap[team_key].get("_resolved"):
                pr = snap[team_key]
                pred["actual_score_dom"] = pr["score_dom"]
                pred["actual_score_ext"] = pr["score_ext"]
                pred["actual_total"] = pr["total"]
                pred["has_result"] = True
                pred["result_source"] = "snapshot"
            else:
                all_resolved = False
        if entry.get("predictions") and entry.get("has_result") is None:
            entry["has_result"] = all_resolved


def charger_resultats_bet261():
    path = "bet261_real_results.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        lookup = {}
        for rnd_str, matches in data.items():
            for h, a, sd, se in matches:
                lookup[(h.lower(), a.lower(), int(rnd_str))] = (int(rnd_str), sd, se)
                lookup[(a.lower(), h.lower(), int(rnd_str))] = (int(rnd_str), se, sd)
        return lookup
    except Exception:
        return {}


def enrichir_resultats(history, skip_playout=False):
    resultats_equipes = charger_resultats_equipes()
    bet261_lookup = charger_resultats_bet261()

    for entry in history:
        rnd = entry["round"]

        snapshot = entry.get("playout_snapshot", {})
        playout_id_map = entry.get("playout_id_map", {})

        need_enrichment = not all(p.get("has_result") for p in entry["predictions"])

        if need_enrichment:
            playout_by_id = {}
            all_from_snapshot = all(
                snapshot.get("%s|%s" % (p.get("home_team", ""), p.get("away_team", "")), {}).get("_resolved")
                for p in entry["predictions"] if not p.get("has_result")
            )
            if not skip_playout and not all_from_snapshot and playout_id_map:
                try:
                    playout_by_id, _, _ = fetch_playout_with_ids(rnd)
                except Exception:
                    pass

            actuals_csv = resultats_equipes.get(rnd, [])
            csv_map = {(a["home_team"], a["away_team"]): a for a in actuals_csv if a.get("home_team") != "?"}
            csv_id_map = {a["match_id"]: a for a in actuals_csv if a.get("match_id") and a.get("home_team") != "?"}

            for pred in entry["predictions"]:
                if pred.get("has_result"):
                    continue

                match_id = pred.get("match_id", 0)
                team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))

                resolved = False

                bet_key = (pred["home_team"].lower(), pred["away_team"].lower(), rnd)
                bet_key_generic = (pred["home_team"].lower(), pred["away_team"].lower())
                if bet_key in bet261_lookup:
                    _, sd, se = bet261_lookup[bet_key]
                    pred["actual_score_dom"] = sd
                    pred["actual_score_ext"] = se
                    pred["actual_total"] = sd + se
                    pred["has_result"] = True
                    pred["result_source"] = "bet261_scrape"
                    resolved = True
                if not resolved:
                    key = (pred["home_team"], pred["away_team"])
                    if key in csv_map:
                        a = csv_map[key]
                        pred["actual_score_dom"] = a["score_dom"]
                        pred["actual_score_ext"] = a["score_ext"]
                        pred["actual_total"] = a["score_dom"] + a["score_ext"]
                        pred["has_result"] = True
                        pred["result_source"] = "csv"
                        resolved = True
                    elif match_id and match_id in csv_id_map:
                        a = csv_id_map[match_id]
                        pred["actual_score_dom"] = a["score_dom"]
                        pred["actual_score_ext"] = a["score_ext"]
                        pred["actual_total"] = a["score_dom"] + a["score_ext"]
                        pred["has_result"] = True
                        pred["result_source"] = "csv_id"
                        resolved = True
                if not resolved:
                    if playout_id_map.get(team_key) and playout_id_map[team_key] in playout_by_id:
                        pr = playout_by_id[playout_id_map[team_key]]
                        pred["actual_score_dom"] = pr["score_dom"]
                        pred["actual_score_ext"] = pr["score_ext"]
                        pred["actual_total"] = pr["total"]
                        pred["has_result"] = True
                        pred["result_source"] = "playout_id"
                        resolved = True
                if not resolved:
                    if team_key in snapshot and snapshot[team_key].get("_resolved"):
                        pr = snapshot[team_key]
                        pred["actual_score_dom"] = pr["score_dom"]
                        pred["actual_score_ext"] = pr["score_ext"]
                        pred["actual_total"] = pr["total"]
                        pred["has_result"] = True
                        pred["result_source"] = "snapshot"


        correct_result = 0
        correct_over_under = 0
        correct_total = 0
        correct_pair_impair = 0
        correct_dc_1X = 0
        correct_dc_X2 = 0
        correct_dc_12 = 0
        correct_dc_pred = 0
        correct_btts = 0
        total_dc_pred = 0
        total_btts_pred = 0
        total_matches = 0

        for pred in entry["predictions"]:
            if not pred.get("has_result"):
                continue

            sd = pred.get("actual_score_dom", 0)
            se = pred.get("actual_score_ext", 0)
            actual_total = sd + se

            actual_result = "1" if sd > se else "2" if se > sd else "X"
            if actual_result == pred.get("res_code"):
                correct_result += 1

            if actual_result in ("1", "X"):
                pred["actual_dc_1X"] = True
                correct_dc_1X += 1
            else:
                pred["actual_dc_1X"] = False
            if actual_result in ("X", "2"):
                pred["actual_dc_X2"] = True
                correct_dc_X2 += 1
            else:
                pred["actual_dc_X2"] = False
            if actual_result in ("1", "2"):
                pred["actual_dc_12"] = True
                correct_dc_12 += 1
            else:
                pred["actual_dc_12"] = False

            dc_pred = pred.get("dc_pred", "")
            if dc_pred:
                won = False
                if dc_pred == "1X" and actual_result in ("1", "X"):
                    won = True
                elif dc_pred == "X2" and actual_result in ("X", "2"):
                    won = True
                elif dc_pred == "12" and actual_result in ("1", "2"):
                    won = True
                pred["dc_correct"] = won
                total_dc_pred += 1
                if won:
                    correct_dc_pred += 1

            ou_pred = pred.get("ou_pred", "")
            if ou_pred:
                actual_ou = "Over 2.5" if actual_total > 2.5 else "Under 2.5"
                pred["ou_pred_correct"] = (ou_pred == actual_ou)
                pred["ou_actual"] = actual_ou

            btts_pred = pred.get("btts_pred", "")
            if btts_pred:
                actual_btts = "BTTS Oui" if sd > 0 and se > 0 else "BTTS Non"
                pred["btts_correct"] = (btts_pred == actual_btts)
                pred["btts_actual"] = actual_btts
                total_btts_pred += 1
                if pred["btts_correct"]:
                    correct_btts += 1

            pred_total = pred.get("total_buts", 0)
            pred_is_over = pred.get("prob_over_25", 50) > 50
            if pred_is_over == (actual_total > 2.5):
                correct_over_under += 1

            if abs(pred_total - actual_total) <= 1:
                correct_total += 1

            pred_is_pair = pred.get("prob_pair", 50) > 50
            if pred_is_pair == (actual_total % 2 == 0):
                correct_pair_impair += 1

            total_matches += 1

        total_preds = len(entry.get("predictions", []))
        if total_matches > 0:
            entry["has_result"] = True
            entry["accuracy_result"] = round(correct_result / total_matches * 100, 1)
            entry["accuracy_over_under"] = round(correct_over_under / total_matches * 100, 1)
            entry["accuracy_total"] = round(correct_total / total_matches * 100, 1)
            entry["accuracy_pair_impair"] = round(correct_pair_impair / total_matches * 100, 1)
            entry["accuracy_dc_1X"] = round(correct_dc_1X / total_matches * 100, 1)
            entry["accuracy_dc_X2"] = round(correct_dc_X2 / total_matches * 100, 1)
            entry["accuracy_dc_12"] = round(correct_dc_12 / total_matches * 100, 1)
            entry["accuracy_dc_pred"] = round(correct_dc_pred / total_dc_pred * 100, 1) if total_dc_pred > 0 else None
            entry["accuracy_btts"] = round(correct_btts / total_btts_pred * 100, 1) if total_btts_pred > 0 else None
            entry["total_matches_checked"] = total_matches
        elif total_preds > 0:
            entry["has_result"] = False
            entry["accuracy_result"] = None
            entry["accuracy_over_under"] = None
            entry["accuracy_total"] = None
            entry["accuracy_pair_impair"] = None
            entry["accuracy_dc_1X"] = None
            entry["accuracy_dc_X2"] = None
            entry["accuracy_dc_12"] = None
            entry["accuracy_dc_pred"] = None
            entry["accuracy_btts"] = None
            entry["total_matches_checked"] = 0
        else:
            entry["has_result"] = None
            entry["accuracy_result"] = None
            entry["accuracy_over_under"] = None
            entry["accuracy_total"] = None
            entry["accuracy_pair_impair"] = None
            entry["accuracy_dc_1X"] = None
            entry["accuracy_dc_X2"] = None
            entry["accuracy_dc_12"] = None
            entry["accuracy_dc_pred"] = None
            entry["accuracy_btts"] = None
            entry["total_matches_checked"] = 0

        for pred in entry["predictions"]:
            if pred.get("has_result") and "btts_correct" not in pred:
                sd = pred.get("actual_score_dom", 0)
                se = pred.get("actual_score_ext", 0)
                btts_pred = pred.get("btts_pred", "")
                if btts_pred:
                    actual_btts = "BTTS Oui" if sd > 0 and se > 0 else "BTTS Non"
                    pred["btts_correct"] = (btts_pred == actual_btts)
                    pred["btts_actual"] = actual_btts

        for pred in entry["predictions"]:
            if not pred.get("cotes_btts_oui") and pred.get("cotes_raw", {}).get("btts_oui"):
                pred["cotes_btts_oui"] = pred["cotes_raw"]["btts_oui"]
                pred["cotes_btts_non"] = pred["cotes_raw"].get("btts_non", 0)

        for pred in entry["predictions"]:
            if pred.get("has_result") and "ou_pred_correct" not in pred:
                sd = pred.get("actual_score_dom", 0)
                se = pred.get("actual_score_ext", 0)
                actual_total = sd + se
                ou_pred = pred.get("ou_pred", "")
                if ou_pred:
                    actual_ou = "Over 2.5" if actual_total > 2.5 else "Under 2.5"
                    pred["ou_pred_correct"] = (ou_pred == actual_ou)
                    pred["ou_actual"] = actual_ou

        accumulators = entry.get("accumulators", [])
        if accumulators:
            actual_map = {}
            for pred in entry["predictions"]:
                if not pred.get("has_result"):
                    continue
                team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
                sd = pred.get("actual_score_dom", 0)
                se = pred.get("actual_score_ext", 0)
                ar = "1" if sd > se else "2" if se > sd else "X"
                actual_map[team_key] = ar
                actual_map[pred.get("home_team", "")] = ar
                actual_map[pred.get("away_team", "")] = ar

            if not actual_map:
                for snap_key, snap_val in entry.get("playout_snapshot", {}).items():
                    if snap_val.get("_resolved"):
                        sd = snap_val.get("score_dom", 0)
                        se = snap_val.get("score_ext", 0)
                        ar = "1" if sd > se else "2" if se > sd else "X"
                        actual_map[snap_key] = ar
                        parts = snap_key.split("|")
                        if len(parts) == 2:
                            actual_map[parts[0]] = ar
                            actual_map[parts[1]] = ar

            for acc in accumulators:
                legs_won = 0
                legs_total = len(acc.get("legs", []))
                for leg in acc.get("legs", []):
                    home = leg.get("home", "")
                    away = leg.get("away", "")
                    pick = leg.get("dc_pick", "")
                    team_key = "%s|%s" % (home, away)
                    ar = actual_map.get(team_key, "")
                    if not ar:
                        ar = actual_map.get(home, "") or actual_map.get(away, "")
                    won = False
                    if pick == "1X" and ar in ("1", "X"):
                        won = True
                    elif pick == "X2" and ar in ("X", "2"):
                        won = True
                    elif pick == "12" and ar in ("1", "2"):
                        won = True
                    leg["actual_result"] = ar
                    leg["leg_won"] = won
                    if won:
                        legs_won += 1
                acc["legs_won"] = legs_won
                acc["legs_total"] = legs_total
                acc["accu_won"] = legs_won == legs_total and legs_total > 0

        simples = entry.get("simples", [])
        if simples:
            actual_map_simple = {}
            for pred in entry["predictions"]:
                if not pred.get("has_result"):
                    continue
                team_key = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
                sd = pred.get("actual_score_dom", 0)
                se = pred.get("actual_score_ext", 0)
                ar = "1" if sd > se else "2" if se > sd else "X"
                actual_map_simple[team_key] = ar
                actual_map_simple[pred.get("home_team", "")] = ar
                actual_map_simple[pred.get("away_team", "")] = ar

            if not actual_map_simple:
                for snap_key, snap_val in entry.get("playout_snapshot", {}).items():
                    if snap_val.get("_resolved"):
                        sd = snap_val.get("score_dom", 0)
                        se = snap_val.get("score_ext", 0)
                        ar = "1" if sd > se else "2" if se > sd else "X"
                        actual_map_simple[snap_key] = ar
                        parts = snap_key.split("|")
                        if len(parts) == 2:
                            actual_map_simple[parts[0]] = ar
                            actual_map_simple[parts[1]] = ar

            for simp in simples:
                home = simp.get("home_team", "")
                away = simp.get("away_team", "")
                pick = simp.get("dc_pick", "")
                team_key = "%s|%s" % (home, away)
                ar = actual_map_simple.get(team_key, "")
                if not ar:
                    ar = actual_map_simple.get(home, "") or actual_map_simple.get(away, "")
                won = None
                if ar:
                    won = False
                    if pick == "1X" and ar in ("1", "X"):
                        won = True
                    elif pick == "X2" and ar in ("X", "2"):
                        won = True
                    elif pick == "12" and ar in ("1", "2"):
                        won = True
                simp["actual_result"] = ar
                simp["simple_won"] = won

                ou_pred = simp.get("ou_pred", "")
                ou_won = None
                total_goals = None
                actual_ou = ""
                for snap_key, snap_val in entry.get("playout_snapshot", {}).items():
                    if not snap_val.get("_resolved"):
                        continue
                    sk_home = snap_val.get("home_team", "")
                    sk_away = snap_val.get("away_team", "")
                    if sk_home.lower() == home.lower() and sk_away.lower() == away.lower():
                        sd = snap_val.get("score_dom", 0) or snap_val.get("score_home", 0)
                        se = snap_val.get("score_ext", 0) or snap_val.get("score_away", 0)
                        total_goals = sd + se
                        actual_ou = "Over 2.5" if total_goals > 2.5 else "Under 2.5"
                        if ou_pred:
                            ou_won = (ou_pred == actual_ou)
                        break
                simp["ou_won"] = ou_won
                simp["ou_actual"] = actual_ou
                simp["ou_total_goals"] = total_goals

        if simples:
            pred_map_ou = {}
            for pred in entry.get("predictions", []):
                pk = "%s|%s" % (pred.get("home_team", ""), pred.get("away_team", ""))
                pred_map_ou[pk] = pred
            for simp in simples:
                if "ou_pred" not in simp:
                    pk = "%s|%s" % (simp.get("home_team", ""), simp.get("away_team", ""))
                    pred = pred_map_ou.get(pk, {})
                    simp["ou_pred"] = pred.get("ou_pred", "Under 2.5")
                    simp["ou_confidence"] = pred.get("ou_confidence", 70)
                    simp["prob_over_25"] = pred.get("prob_over_25", 28)
                    simp["prob_under_25"] = pred.get("prob_under_25", 72)

                    ou_pred = simp.get("ou_pred", "")
                    ou_won = None
                    total_goals = None
                    actual_ou = ""
                    for snap_key, snap_val in entry.get("playout_snapshot", {}).items():
                        if not snap_val.get("_resolved"):
                            continue
                        sk_home = snap_val.get("home_team", "")
                        sk_away = snap_val.get("away_team", "")
                        if sk_home.lower() == simp.get("home_team", "").lower() and sk_away.lower() == simp.get("away_team", "").lower():
                            sd2 = snap_val.get("score_dom", 0) or snap_val.get("score_home", 0)
                            se2 = snap_val.get("score_ext", 0) or snap_val.get("score_away", 0)
                            total_goals = sd2 + se2
                            actual_ou = "Over 2.5" if total_goals > 2.5 else "Under 2.5"
                            if ou_pred:
                                ou_won = (ou_pred == actual_ou)
                            break
                    simp["ou_won"] = ou_won
                    simp["ou_actual"] = actual_ou
                    simp["ou_total_goals"] = total_goals

        h2h_simples = entry.get("h2h_simples", [])
        if h2h_simples:
            for snap_key, snap_val in entry.get("playout_snapshot", {}).items():
                if not snap_val.get("_resolved"):
                    continue
                sk_home = snap_val.get("home_team", "")
                sk_away = snap_val.get("away_team", "")
                sd = snap_val.get("score_dom", 0) or snap_val.get("score_home", 0)
                se = snap_val.get("score_ext", 0) or snap_val.get("score_away", 0)
                total_goals = sd + se
                actual_result = "1" if sd > se else "2" if se > sd else "X"
                actual_ou = "Over 2.5" if total_goals > 2.5 else "Under 2.5"
                actual_btts = "Oui" if sd > 0 and se > 0 else "Non"
                for hsimp in h2h_simples:
                    if hsimp.get("home_team", "").lower() != sk_home.lower() or hsimp.get("away_team", "").lower() != sk_away.lower():
                        continue
                    pick = hsimp.get("h2h_pick", "")
                    won = None
                    if pick == "1X":
                        won = actual_result in ("1", "X")
                    elif pick == "X2":
                        won = actual_result in ("X", "2")
                    elif pick == "12":
                        won = actual_result in ("1", "2")
                    elif pick == "Under 2.5":
                        won = (actual_ou == "Under 2.5")
                    elif pick == "Under 1.5":
                        won = total_goals <= 1.5
                    elif pick == "BTTS Non":
                        won = (actual_btts == "Non")
                    elif pick == "BTTS Oui":
                        won = (actual_btts == "Oui")
                    elif pick == "X":
                        won = (actual_result == "X")
                    hsimp["h2h_won"] = won
                    hsimp["h2h_actual_result"] = actual_result
                    hsimp["h2h_actual_ou"] = actual_ou
                    hsimp["h2h_actual_btts"] = actual_btts
                    hsimp["h2h_total_goals"] = total_goals

        h2h_accus = entry.get("h2h_accumulators", [])
        if h2h_accus:
            for accu in h2h_accus:
                legs_won = 0
                for leg in accu.get("legs", []):
                    for snap_key, snap_val in entry.get("playout_snapshot", {}).items():
                        if not snap_val.get("_resolved"):
                            continue
                        sk_home = snap_val.get("home_team", "")
                        sk_away = snap_val.get("away_team", "")
                        if sk_home.lower() != leg["home"].lower() or sk_away.lower() != leg["away"].lower():
                            continue
                        sd = snap_val.get("score_dom", 0) or snap_val.get("score_home", 0)
                        se = snap_val.get("score_ext", 0) or snap_val.get("score_away", 0)
                        actual_result = "1" if sd > se else "2" if se > sd else "X"
                        pick = leg.get("dc_pick", "")
                        won = False
                        if pick == "1X":
                            won = actual_result in ("1", "X")
                        elif pick == "X2":
                            won = actual_result in ("X", "2")
                        elif pick == "12":
                            won = actual_result in ("1", "2")
                        leg["leg_won"] = won
                        leg["actual_result"] = actual_result
                        if won:
                            legs_won += 1
                        break
                accu["legs_won"] = legs_won
                accu["accu_won"] = legs_won == accu.get("n_legs", 2)

        ou_h2h_simples = entry.get("ou_h2h_simples", [])
        if ou_h2h_simples:
            for snap_key, snap_val in entry.get("playout_snapshot", {}).items():
                if not snap_val.get("_resolved"):
                    continue
                sk_home = snap_val.get("home_team", "")
                sk_away = snap_val.get("away_team", "")
                sd = snap_val.get("score_dom", 0) or snap_val.get("score_home", 0)
                se = snap_val.get("score_ext", 0) or snap_val.get("score_away", 0)
                total_goals = sd + se
                actual_ou = "Over 2.5" if total_goals > 2.5 else "Under 2.5"
                actual_btts = "Oui" if sd > 0 and se > 0 else "Non"
                for osimp in ou_h2h_simples:
                    if osimp.get("home_team", "").lower() != sk_home.lower() or osimp.get("away_team", "").lower() != sk_away.lower():
                        continue
                    pick = osimp.get("ou_pick", "")
                    won = None
                    if pick == "Under 2.5":
                        won = (actual_ou == "Under 2.5")
                    elif pick == "Under 1.5":
                        won = total_goals <= 1.5
                    elif pick == "BTTS Non":
                        won = (actual_btts == "Non")
                    elif pick == "BTTS Oui":
                        won = (actual_btts == "Oui")
                    osimp["ou_h2h_won"] = won
                    osimp["ou_h2h_actual_ou"] = actual_ou
                    osimp["ou_h2h_actual_btts"] = actual_btts
                    osimp["ou_h2h_total_goals"] = total_goals

    return history

def _resolve_pending_rounds_bg():
    """Background: resolve rounds with has_result=False via playout API."""
    try:
        current_live = _current_round_detected
        history = load_history()
        for entry in history:
            if entry.get("has_result"):
                continue
            rnd = entry.get("round")
            cycle = entry.get("cycle", _current_cycle)
            if rnd == current_live:
                continue
            snap = entry.get("playout_snapshot", {})
            if any(s.get("_resolved") for s in snap.values()):
                continue
            preds = entry.get("predictions", [])
            if not preds:
                continue
            try:
                _process_completed_round(rnd)
                _clog("RESOLVE-BG: round %d (C%d) resolved via background" % (rnd, cycle))
            except Exception as e:
                _clog("RESOLVE-BG: round %d (C%d) error: %s" % (rnd, cycle, str(e)))
    except Exception:
        pass

def _enrich_and_save():
    """Enrichir les resultats et sauvegarder. Rapide: pas de playout network call."""
    try:
        def _do_enrich(history):
            return enrichir_resultats(history, skip_playout=True)
        return _atomic_modify_history(_do_enrich)
    except Exception:
        return load_history()

class BetHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        try:
            with open("server_err.log", "a", encoding="utf-8") as f:
                f.write("[HTTP] %s - %s\n" % (self.address_string(), format % args))
        except Exception:
            pass

    def do_GET(self):
        try:
            return self._do_GET()
        except Exception as e:
            try:
                with open("server_err.log", "a", encoding="utf-8") as f:
                    import traceback
                    f.write("[CRASH do_GET] %s\n%s\n" % (self.path, traceback.format_exc()))
            except Exception:
                pass
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"error":"internal"}')
            except Exception:
                pass

    def _do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open("index.html", "r", encoding="utf-8") as f:
                self.wfile.write(f.read().encode("utf-8"))
            return

        if path == "/api/predict":
            global _predict_cache, _predict_cache_time, _predict_cache_round, _enriching, _current_round_detected, _current_round_time
            _tp = time.time()

            current_round_api = _current_round_detected
            if current_round_api == 0 or (time.time() - _current_round_time > 30):
                try:
                    rr = requests.get(prediction_engine.MATCHES_URL, headers=HEADERS, timeout=8)
                    rd = rr.json()
                    for rnd in rd.get("rounds", []):
                        if rnd.get("matches"):
                            rn = rnd.get("roundNumber", 0)
                            if rn > current_round_api:
                                current_round_api = rn
                                _current_round_detected = current_round_api
                                _current_round_time = time.time()
                except Exception:
                    pass

            if current_round_api == 0:
                current_round_api = 999

            same_round = (_predict_cache is not None and _predict_cache_round == current_round_api and time.time() - _predict_cache_time < 60)

            if same_round:
                _tp4 = time.time()
                try:
                    with open("server_err.log", "a", encoding="utf-8") as f:
                        f.write("[TIMING] predict=CACHED (round %d) total=%.3fs\n" % (current_round_api, _tp4 - _tp))
                except Exception:
                    pass
                self.send_json(_predict_cache)
                return

            stats = get_stats()
            historique = get_historique()

            predictions, err = prediction_engine.predire_tous(stats)
            _tp1 = time.time()
            ml_models = get_ml_models()
            _tp2 = time.time()

            if predictions and ml_models:
                _tp_feat = time.time()
                all_features = []
                for p in predictions:
                    try:
                        features = build_features_live(
                            p["home_team"], p["away_team"], p.get("round", 0),
                            historique, stats["team_stats"], stats["elo_ratings"],
                            stats["h2h_stats"], stats["tendances"]
                        )
                        if features:
                            all_features.append(features[0])
                        else:
                            all_features.append(None)
                    except Exception:
                        all_features.append(None)
                _tp_feat2 = time.time()

                valid_features = [f for f in all_features if f is not None]
                valid_indices = [i for i, f in enumerate(all_features) if f is not None]

                if valid_features:
                    try:
                        ml_batch = ml_ensemble.predict_ensemble_batch(ml_models, valid_features)
                        for idx, vi in enumerate(valid_indices):
                            if idx < len(ml_batch) and ml_batch[idx]:
                                predictions[vi] = ml_ensemble.hybrid_predict(predictions[vi], ml_batch[idx])
                    except Exception:
                        for i, p in enumerate(predictions):
                            try:
                                if all_features[i]:
                                    ml_pred = ml_ensemble.predict_ensemble(ml_models, all_features[i])
                                    p = ml_ensemble.hybrid_predict(p, ml_pred)
                            except Exception:
                                pass

                if valid_features:
                    def _run_tabpfn_bg(valid_feats, valid_idx, preds, ml_mods):
                        try:
                            tabpfn_results = ml_ensemble.predict_tabpfn_batch(ml_mods, valid_feats)
                            if tabpfn_results:
                                idx = 0
                                for vi in valid_idx:
                                    if idx < len(tabpfn_results):
                                        tr = tabpfn_results[idx]
                                        p = preds[vi]
                                        if "tabpfn_1x2_proba" in tr:
                                            proba = tr["tabpfn_1x2_proba"]
                                            if len(proba) >= 3:
                                                p["tabpfn_proba_1"] = proba[0]
                                                p["tabpfn_proba_X"] = proba[1]
                                                p["tabpfn_proba_2"] = proba[2]
                                                p["tabpfn_pred"] = tr["tabpfn_1x2_pred"]
                                                p["tabpfn_conf"] = tr["tabpfn_1x2_conf"]
                                                cur_best = p.get("confidence", 0)
                                                tp_conf = tr.get("tabpfn_1x2_conf", 0)
                                                if tp_conf > cur_best:
                                                    p["confidence"] = tp_conf
                                                    p["confidence_source"] = "tabpfn"
                                        if "tabpfn_ou25_over" in tr:
                                            p["tabpfn_ou25"] = tr["tabpfn_ou25_over"]
                                        idx += 1
                        except Exception:
                            pass
                    threading.Thread(target=_run_tabpfn_bg, args=(valid_features, valid_indices, predictions, ml_models), daemon=True).start()

            if predictions:
                _tp_odds = time.time()
                for p in predictions:
                    try:
                        cr = p.get("cotes_raw", {})
                        c1 = cr.get("cote_1", 2.0)
                        cx = cr.get("cote_X", 3.5)
                        c2 = cr.get("cote_2", 3.5)
                        if c1 and cx and c2:
                            ml_pred = p.get("ml_pred_1x2", None)
                            ml_conf = p.get("ml_confidence_1x2", None)
                            elo_h = p.get("home_elo", None)
                            elo_a = p.get("away_elo", None)
                            matrix_res = odds_matrix.analyze_match(
                                p["home_team"], p["away_team"],
                                c1, cx, c2,
                                ml_pred=ml_pred, ml_confidence=ml_conf,
                                elo_home=elo_h, elo_away=elo_a
                            )
                            p["odds_matrix"] = matrix_res
                            combined = odds_matrix.get_combined_prediction(matrix_res, p)
                            p["combined_prediction"] = combined
                            final = combined.get("final_pred", matrix_res.get("fav_side", "1"))
                            p["final_pred_1x2"] = final
                            tips = combined.get("tips", [])
                            if combined.get("agreement"):
                                p["final_reco"] = tips[-1] if tips else "Matrice+ML d'accord"
                            else:
                                p["final_reco"] = tips[-1] if tips else "Matrice/ML en desaccord"
                            p["final_confidence"] = combined.get("combined_confidence", "MOYENNE")
                    except Exception:
                        pass

                    try:
                        cr = p.get("cotes_raw", {})
                        dc_1X_odds = cr.get("dc_1X", 0)
                        dc_X2_odds = cr.get("dc_X2", 0)
                        dc_12_odds = cr.get("dc_12", 0)
                        if dc_1X_odds and dc_X2_odds and dc_12_odds:
                            p_dc_1X = p.get("prob_dc_1X", 0) / 100
                            p_dc_X2 = p.get("prob_dc_X2", 0) / 100
                            p_dc_12 = p.get("prob_dc_12", 0) / 100
                            dc_bets = []
                            for code, model_prob, odds in [("1X", p_dc_1X, dc_1X_odds), ("X2", p_dc_X2, dc_X2_odds), ("12", p_dc_12, dc_12_odds)]:
                                if model_prob > 0 and odds > 0:
                                    implied = 1 / odds
                                    edge = model_prob - implied
                                    ev = model_prob * odds - 1
                                    dc_bets.append({
                                        "code": code,
                                        "model_prob": round(model_prob * 100, 1),
                                        "site_odds": round(odds, 2),
                                        "implied_prob": round(implied * 100, 1),
                                        "edge": round(edge * 100, 1),
                                        "ev": round(ev * 100, 1),
                                        "value": edge > 0.03,
                                    })
                            p["dc_analysis"] = dc_bets
                    except Exception:
                        pass

            _tp_odds2 = time.time()
            _tp_core = time.time()

            vb_list = []
            accu_list = []
            simples_list = []
            h2h_simples = []
            h2h_accu_list = []
            ou_h2h_simples = []

            def _enrich_background(preds, hist):
                global _enriching, _predict_cache, _predict_cache_time, _predict_cache_round
                if _enriching:
                    return
                with _enrich_lock:
                    _enriching = True
                    try:
                        try:
                            import team_profiler
                            for p in preds:
                                cr = p.get("cotes_raw", {})
                                c1 = cr.get("cote_1", 0)
                                c2 = cr.get("cote_2", 0)
                                prof = team_profiler.evaluate_match(
                                    p.get("home_team", ""), p.get("away_team", ""),
                                    home_odds=c1, away_odds=c2,
                                )
                                p["profiler"] = prof
                                if prof["confidence_adjustment"] != 0:
                                    old_conf = p.get("confidence", 50)
                                    p["confidence"] = max(10, min(99, old_conf + prof["confidence_adjustment"]))
                                if prof["dc_boosts"]["1X"] > 0 or prof["dc_boosts"]["X2"] > 0 or prof["dc_boosts"]["12"] > 0:
                                    for dc in p.get("dc_analysis", []):
                                        code = dc.get("code", "")
                                        if code in prof["dc_boosts"] and prof["dc_boosts"][code] > 0:
                                            dc["model_prob"] = min(95, dc["model_prob"] + prof["dc_boosts"][code] * 100)
                                            dc["edge"] = dc["model_prob"] / 100 - (1 / dc["site_odds"] if dc["site_odds"] > 0 else 0)
                                            dc["profiler_boosted"] = True
                            _log_enrich("profiler OK: %d matches" % len(preds))
                        except Exception as ex:
                            _log_enrich("profiler FAILED: %s" % ex)

                        rnd_num = preds[0].get("round", 0) if preds else 0
                        if rnd_num:
                            save_predictions(preds, rnd_num)

                        try:
                            auto_collect.auto_collect()
                        except Exception:
                            pass

                        try:
                            threading.Thread(target=collect_cotes.collecter_cotes, daemon=True).start()
                        except Exception:
                            pass

                        accu_res = []
                        simples_res = []
                        h2h_s_res = []
                        h2h_a_res = []
                        ou_h2h_res = []
                        try:
                            accu_res = value_bets.generate_accumulators(preds, favoris_only=False)
                        except Exception as ex:
                            _log_enrich("accu FAILED: %s" % ex)
                            accu_res = []
                        else:
                            _log_enrich("accu OK: %d" % len(accu_res))
                        try:
                            simples_res = value_bets.generate_simples(preds, max_simples=6, min_edge=0, history=hist)
                        except Exception as ex:
                            _log_enrich("simples FAILED: %s" % ex)
                            simples_res = []
                        else:
                            _log_enrich("simples OK: %d" % len(simples_res))
                        try:
                            h2h_s_res = value_bets.generate_h2h_simples(preds, max_simples=8)
                        except Exception as ex:
                            _log_enrich("h2h_simples FAILED: %s" % ex)
                            h2h_s_res = []
                        else:
                            _log_enrich("h2h_simples OK: %d" % len(h2h_s_res))
                        try:
                            h2h_a_res = value_bets.generate_h2h_accumulators(preds, max_accus=5)
                        except Exception as ex:
                            _log_enrich("h2h_accus FAILED: %s" % ex)
                            h2h_a_res = []
                        else:
                            _log_enrich("h2h_accus OK: %d" % len(h2h_a_res))
                        try:
                            ou_h2h_res = value_bets.generate_ou_h2h_simples(preds, max_simples=6)
                        except Exception as ex:
                            _log_enrich("ou_h2h FAILED: %s" % ex)
                            ou_h2h_res = []
                        else:
                            _log_enrich("ou_h2h OK: %d" % len(ou_h2h_res))

                        for p in preds:
                            p.pop("cotes_raw", None)
                            p.pop("cotes_all", None)

                        enriched = {
                            "predictions": preds,
                            "error": None,
                            "ml_active": True,
                            "value_bets": value_bets.find_value_bets(preds, min_edge=0.02),
                            "accumulators": accu_res,
                            "simples": simples_res,
                            "h2h_simples": h2h_s_res,
                            "h2h_accumulators": h2h_a_res,
                            "ou_h2h_simples": ou_h2h_res,
                            "stats": {
                                "total_matchs": stats["total_matchs"],
                                "moy_buts": stats["moy_buts"],
                                "moy_dom": stats["moy_dom"],
                                "moy_ext": stats["moy_ext"],
                                "over_25": stats["over_25"],
                                "v_dom": stats["v_dom"],
                                "nuls": stats["nuls"],
                                "v_ext": stats["v_ext"],
                            }
                        }
                        _predict_cache = enriched
                        _predict_cache_time = time.time()
                        _predict_cache_round = preds[0].get("round", 0) if preds else 0
                    except Exception as e:
                        try:
                            with open("server_err.log", "a", encoding="utf-8") as f:
                                f.write("[ENRICH ERROR] %s\n" % str(e))
                        except Exception:
                            pass
                    finally:
                        _enriching = False

            for p in predictions:
                cr = p.get("cotes_raw", {})
                if cr.get("dc_1X"):
                    p["dc_odds_1X"] = cr["dc_1X"]
                if cr.get("dc_X2"):
                    p["dc_odds_X2"] = cr["dc_X2"]
                if cr.get("dc_12"):
                    p["dc_odds_12"] = cr["dc_12"]

            _hist_for_bg = load_history()
            _preds_for_bg = [dict(p) for p in predictions]
            threading.Thread(target=_enrich_background, args=(_preds_for_bg, _hist_for_bg), daemon=True).start()

            for p in predictions:
                p.pop("cotes_raw", None)
                p.pop("cotes_all", None)

            quick_response = {
                "predictions": predictions,
                "error": err,
                "ml_active": ml_models is not None,
                "value_bets": [],
                "accumulators": [],
                "simples": [],
                "stats": {
                    "total_matchs": stats["total_matchs"],
                    "moy_buts": stats["moy_buts"],
                    "moy_dom": stats["moy_dom"],
                    "moy_ext": stats["moy_ext"],
                    "over_25": stats["over_25"],
                    "v_dom": stats["v_dom"],
                    "nuls": stats["nuls"],
                    "v_ext": stats["v_ext"],
                }
            }

            _predict_cache = quick_response
            _predict_cache_time = time.time()
            _predict_cache_round = current_round_api

            self.send_json(quick_response)
            _tp4 = time.time()
            try:
                with open("server_err.log", "a", encoding="utf-8") as f:
                    f.write("[TIMING] predict=%.1fs ml=%.1fs feat=%.1fs odds=%.1fs core=%.1fs TOTAL=QUICK %.1fs (round %d, enriching in background)\n" % (
                        _tp1 - _tp, _tp2 - _tp1, _tp_feat2 - _tp_feat, _tp_odds2 - _tp_odds, _tp_core - _tp2, _tp4 - _tp, current_round_api))
            except Exception:
                pass
            return

        if path == "/api/predict_custom":
            home = params.get("home", ["?"])[0]
            away = params.get("away", ["?"])[0]

            cotes_dict = {}
            if "cote1" in params and "coteX" in params and "cote2" in params:
                cotes_dict["cote_1"] = float(params["cote1"][0])
                cotes_dict["cote_X"] = float(params["coteX"][0])
                cotes_dict["cote_2"] = float(params["cote2"][0])

            stats = get_stats()
            pred = prediction_engine.predire_equipes(stats, home, away, cotes_dict if cotes_dict else None)
            self.send_json(pred)
            return

        if path == "/api/ranking":
            try:
                from ml_features import get_ranking
                ranking = get_ranking()
                teams_list = sorted(ranking.values(), key=lambda t: t.get("position", 99))
                self.send_json({"teams": teams_list, "total": len(teams_list)})
            except Exception as e:
                self.send_json({"teams": [], "error": str(e)})
            return

        if path == "/api/cotes":
            try:
                stats = collect_cotes.get_cotes_stats()
                self.send_json(stats)
            except Exception as e:
                self.send_json({"error": str(e)})
            return

        if path == "/api/cotes/collect":
            try:
                result = collect_cotes.collecter_cotes()
                self.send_json(result)
            except Exception as e:
                self.send_json({"error": str(e)})
            return

        if path == "/api/cotes/matrice":
            try:
                matrice = collect_cotes.analyser_matrice_cotes()
                self.send_json(matrice)
            except Exception as e:
                self.send_json({"error": str(e)})
            return

        if path == "/api/collect_data":
            try:
                result = auto_collect.auto_collect()
                status = auto_collect.get_collect_status()
                if result.get("saved", 0) > 0:
                    global _stats, _last_refresh
                    _stats = None
                    _last_refresh = 0
                self.send_json({"collect": result, "status": status})
            except Exception as e:
                self.send_json({"error": str(e)})
            return

        if path == "/api/collect_status":
            try:
                status = auto_collect.get_collect_status()
                self.send_json(status)
            except Exception as e:
                self.send_json({"error": str(e)})
            return

        if path == "/api/round":
            self.send_json({"round": _current_round_detected, "age": round(time.time() - _current_round_time, 1)})
            return

        if path == "/api/history":
            global _history_enriched_cache, _history_enriched_time
            now = time.time()
            if _history_enriched_cache is None or (now - _history_enriched_time > _HISTORY_ENRICHED_TTL):
                _history_enriched_cache = _enrich_and_save()
                _history_enriched_time = now
            has_pending = any(
                not e.get("has_result") and e.get("round") != _current_round_detected
                for e in _history_enriched_cache
            )
            if has_pending:
                threading.Thread(target=_resolve_pending_rounds_bg, daemon=True).start()
            to_send = sorted(_history_enriched_cache, key=lambda x: x.get("timestamp", ""), reverse=True)[:10]
            self.send_json({"history": to_send})
            return

        if path == "/api/manual_rounds":
            rounds = load_manual_rounds()
            stats = get_stats()
            for rnd in rounds:
                preds = []
                for m in rnd.get("matches", []):
                    pred = prediction_engine.predire_equipes(stats, m["home"], m["away"])
                    pred["time"] = m.get("time", "")
                    preds.append(pred)
                rnd["predictions"] = preds
            self.send_json({"rounds": rounds})
            return

        if path == "/api/teams":
            self.send_json({"teams": get_all_teams()})
            return

        if path.startswith("/api/h2h"):
            import h2h_analyzer
            home = params.get("home", [""])[0]
            away = params.get("away", [""])[0]
            if home and away:
                exploits, h2h, hs, as_ = h2h_analyzer.analyze_match_exploits(home, away)
                self.send_json({"home": home, "away": away, "exploits": exploits, "h2h": h2h, "home_stats": hs, "away_stats": as_})
            else:
                stats = get_stats()
                all_teams = sorted(stats.get("team_stats", {}).keys()) if stats.get("team_stats") else []
                self.send_json({"teams": all_teams})
            return

        if path == "/api/team_profiles_all":
            import team_profiler
            csv_data = team_profiler.load_csv_data()
            preds = team_profiler.load_predictions()
            profiles = team_profiler.build_all_teams()
            cross = team_profiler.find_cross_team_patterns(profiles)
            summaries = {}
            for team, report in profiles.items():
                o = report["profile"]["overall"]
                h = report["profile"]["home"]
                a = report["profile"]["away"]
                summaries[team] = {
                    "n_matches": o["n"],
                    "win_rate": o["win_rate"],
                    "gf_avg": o["gf_avg"],
                    "ga_avg": o["ga_avg"],
                    "home_wr": h["win_rate"],
                    "home_n": h["n"],
                    "away_wr": a["win_rate"],
                    "away_n": a["n"],
                    "form": report["form"]["recent_momentum"],
                    "streak": report["form"]["streak"],
                    "btts_oui_rate": report["btts_profile"].get("btts_oui_rate", 0),
                    "n_upsets": len(report["high_odds_upsets"]),
                    "n_patterns": len(report["conditional_patterns"]),
                    "n_odds_zones": len(report["odds_ranges"]),
                    "key_insights": report["key_insights"][:3],
                }
            self.send_json({"summaries": summaries, "cross_patterns": cross})
            return

        if path.startswith("/api/team_profile"):
            import team_profiler
            team_name = params.get("team", [""])[0]
            if team_name:
                csv_data = team_profiler.load_csv_data()
                preds = team_profiler.load_predictions()
                report = team_profiler.build_team_report(csv_data, preds, team_name)
                self.send_json(report)
            else:
                csv_data = team_profiler.load_csv_data()
                teams = sorted(set(m["home_team"] for m in csv_data if m["home_team"]) | set(m["away_team"] for m in csv_data if m["away_team"]))
                self.send_json({"teams": teams})
            return

        if path == "/api/ml/train":
            def do_train():
                global _ml_models, _ml_trained
                try:
                    models, cv = train_ml_models()
                    if models:
                        self.send_json({"ok": True, "cv": cv})
                    else:
                        self.send_json({"ok": False, "error": str(cv)})
                except Exception as e:
                    self.send_json({"ok": False, "error": str(e)})
            threading.Thread(target=do_train, daemon=True).start()
            self.send_json({"ok": True, "status": "training_started"})
            return

        if path == "/api/ml/status":
            ml_models = get_ml_models()
            meta = ml_models.get("_meta", {}) if ml_models else {}
            self.send_json({
                "trained": ml_models is not None,
                "cv_results": meta.get("cv_results", {}),
                "top_features": meta.get("feature_importance", {}),
                "n_samples": meta.get("n_samples", 0),
                "calibrated": meta.get("calibrated", False),
            })
            return

        if path == "/api/calibration":
            cal = compute_calibration_data()
            self.send_json(cal)
            return

        if path == "/api/value_bets":
            stats = get_stats()
            historique = get_historique()
            predictions, err = prediction_engine.predire_tous(stats)
            ml_models = get_ml_models()
            if predictions and ml_models:
                all_features = []
                for p in predictions:
                    try:
                        features = build_features_live(
                            p["home_team"], p["away_team"], p.get("round", 0),
                            historique, stats["team_stats"], stats["elo_ratings"],
                            stats["h2h_stats"], stats["tendances"]
                        )
                        all_features.append(features[0] if features else None)
                    except Exception:
                        all_features.append(None)
                valid_features = [f for f in all_features if f is not None]
                valid_indices = [i for i, f in enumerate(all_features) if f is not None]
                if valid_features:
                    try:
                        ml_batch = ml_ensemble.predict_ensemble_batch(ml_models, valid_features)
                        for idx, vi in enumerate(valid_indices):
                            if idx < len(ml_batch) and ml_batch[idx]:
                                predictions[vi] = ml_ensemble.hybrid_predict(predictions[vi], ml_batch[idx])
                    except Exception:
                        pass
                if valid_features:
                    try:
                        tabpfn_results = ml_ensemble.predict_tabpfn_batch(ml_models, valid_features)
                        if tabpfn_results:
                            idx = 0
                            for vi in valid_indices:
                                if idx < len(tabpfn_results):
                                    tr = tabpfn_results[idx]
                                    p = predictions[vi]
                                    if "tabpfn_1x2_proba" in tr:
                                        proba = tr["tabpfn_1x2_proba"]
                                        if len(proba) >= 3:
                                            p["tabpfn_proba_1"] = proba[0]
                                            p["tabpfn_proba_X"] = proba[1]
                                            p["tabpfn_proba_2"] = proba[2]
                                            p["tabpfn_pred"] = tr["tabpfn_1x2_pred"]
                                            p["tabpfn_conf"] = tr["tabpfn_1x2_conf"]
                                    if "tabpfn_ou25_over" in tr:
                                        p["tabpfn_ou25"] = tr["tabpfn_ou25_over"]
                                    idx += 1
                    except Exception:
                        pass
            vb_list2 = value_bets.find_value_bets(predictions, min_edge=0.03)
            self.send_json({
                "value_bets": vb_list2,
                "n_predictions": len(predictions),
            })
            return

        if path == "/api/rng_patterns":
            try:
                csv_data = prediction_engine.charger_historique()
            except Exception:
                csv_data = []
            patterns = value_bets.analyze_rng_patterns(csv_data)
            self.send_json(patterns)
            return

        if path == "/api/simulate":
            pred_history = load_history()
            _enrich_from_snapshots(pred_history)
            strategy = params.get("strategy", ["value"])[0]
            bankroll = int(params.get("bankroll", [100000])[0])
            stake_pct = float(params.get("stake_pct", [0.02])[0])
            result = value_bets.simulate_betting_strategy(pred_history, strategy, bankroll, stake_pct)
            self.send_json(result)
            return

        if path == "/api/bankroll":
            data = value_bets.load_bankroll()
            self.send_json(data)
            return

        if path == "/api/auto_train_status":
            self.send_json({
                "last_train_time": _last_auto_train_time,
                "last_train_round": _last_auto_train_round,
                "auto_train_enabled": True,
            })
            return

        if path == "/api/futurs_rounds":
            try:
                result = predire_calendrier()
                self.send_json(result)
            except Exception as e:
                self.send_json({"error": str(e), "rounds": []})
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        if path == "/api/manual_rounds":
            try:
                data = json.loads(body)
                rounds = load_manual_rounds()
                new_round = {
                    "round": data.get("round", 0),
                    "matches": data.get("matches", []),
                }
                rounds.append(new_round)
                rounds.sort(key=lambda r: r.get("round", 0))
                save_manual_rounds(rounds)
                self.send_json({"ok": True, "round": new_round["round"]})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)})
            return

        if path == "/api/manual_rounds/delete":
            try:
                data = json.loads(body)
                rnd_num = data.get("round", 0)
                rounds = load_manual_rounds()
                rounds = [r for r in rounds if r.get("round") != rnd_num]
                save_manual_rounds(rounds)
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)})
            return

        self.send_response(404)
        self.end_headers()

    def send_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

def main():
    global _current_cycle
    print("=" * 60)
    print("  SCORABLE - SERVEUR DE PREDICTIONS")
    print("=" * 60)
    print()
    print("  Chargement de l'historique...")
    stats = get_stats()
    print(f"  OK {stats['total_matchs']} matchs charges")
    print(f"  Moyenne de buts: {stats['moy_buts']:.2f}")
    
    history = load_history()
    if history:
        max_cycle = max(h.get("cycle", 0) for h in history)
        _current_cycle = max_cycle
        print(f"  Cycle actuel: {_current_cycle}")
    else:
        _current_cycle = 0
        print("  Pas d'historique, cycle=0")
    print()
    print("  Nettoyage des donnees...")
    fixed = fix_csv_question_marks()
    if fixed > 0:
        print(f"  Corrige {fixed} lignes avec equipes manquantes")
        _stats = None
        _last_refresh = time.time()
    else:
        print("  Donnees propres")
    print()
    print("  Demarrage du collecteur automatique...")
    t = threading.Thread(target=collecteur_resultats, daemon=True)
    t.start()
    print()
    print("  Dashboard: http://localhost:8766")
    print("  API predict: http://localhost:8766/api/predict")
    print("  API custom: http://localhost:8766/api/predict_custom?home=X&away=Y")
    print("  API history: http://localhost:8766/api/history")
    print()
    print("  Ctrl+C pour arreter")
    print()

    import traceback
    while True:
        try:
            server = ThreadedHTTPServer(("127.0.0.1", 8766), BetHandler)
            print("  [OK] Serveur en ecoute sur http://127.0.0.1:8766")
            sys.stdout.flush()
            server.serve_forever()
            break
        except KeyboardInterrupt:
            print("\n  Arret du serveur.")
            try:
                server.server_close()
            except Exception:
                pass
            break
        except Exception as e:
            with open("server_err.log", "a", encoding="utf-8") as f:
                f.write("[RESTART] %s\n%s\n" % (e, traceback.format_exc()))
            time.sleep(2)

if __name__ == "__main__":
    main()
