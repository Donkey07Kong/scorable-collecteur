import sys
import time
import json
import os
import csv

sys.path.insert(0, '.')

import prediction_engine
import ml_ensemble
import value_bets
import dashboard

HISTORY_FILE = "historique_predictions.json"
RETRAIN_AFTER_ROUNDS = 3

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def analyze_defeats(history):
    defeats = []
    for entry in history:
        rnd = entry.get("round", 0)
        accs = entry.get("accumulators", [])
        preds = entry.get("predictions", [])

        actual_map = {}
        for p in preds:
            if not p.get("has_result"):
                continue
            sd = p.get("actual_score_dom", 0)
            se = p.get("actual_score_ext", 0)
            ar = "1" if sd > se else "2" if se > sd else "X"
            tk = "%s|%s" % (p.get("home_team", ""), p.get("away_team", ""))
            actual_map[tk] = ar

        for acc in accs:
            legs = acc.get("legs", [])
            failed_legs = []
            for leg in legs:
                tk = "%s|%s" % (leg["home"], leg["away"])
                ar = actual_map.get(tk, "")
                pick = leg["dc_pick"]
                won = False
                if pick == "1X" and ar in ("1", "X"):
                    won = True
                elif pick == "X2" and ar in ("X", "2"):
                    won = True
                elif pick == "12" and ar in ("1", "2"):
                    won = True
                if not won:
                    failed_legs.append({
                        "home": leg["home"],
                        "away": leg["away"],
                        "dc_pick": pick,
                        "actual": ar,
                        "edge": leg.get("edge_vs_site", 0),
                        "h2h_away_wr": leg.get("h2h_away_wr", 33),
                        "h2h_matches": leg.get("h2h_matches", 0),
                    })

            if failed_legs:
                defeats.append({
                    "round": rnd,
                    "n_legs": acc.get("n_legs", 2),
                    "combined_odds": acc.get("combined_odds", 0),
                    "failed_legs": failed_legs,
                })

    return defeats

def find_patterns(defeats):
    patterns = {
        "common_failed_teams": {},
        "common_failed_picks": {"1X": 0, "X2": 0, "12": 0},
        "high_edge_failures": 0,
        "total_failures": 0,
        "low_h2h_failures": 0,
    }

    for d in defeats:
        for leg in d["failed_legs"]:
            for team_key in ["home", "away"]:
                team = leg[team_key]
                patterns["common_failed_teams"][team] = patterns["common_failed_teams"].get(team, 0) + 1
            patterns["common_failed_picks"][leg["dc_pick"]] = patterns["common_failed_picks"].get(leg["dc_pick"], 0) + 1
            patterns["total_failures"] += 1
            if leg["edge"] > 15:
                patterns["high_edge_failures"] += 1
            if leg["h2h_matches"] < 10:
                patterns["low_h2h_failures"] += 1

    patterns["common_failed_teams"] = dict(
        sorted(patterns["common_failed_teams"].items(), key=lambda x: -x[1])[:10]
    )

    return patterns

def find_wins(history):
    wins = {"1X": 0, "X2": 0, "12": 0, "total": 0}
    for entry in history:
        accs = entry.get("accumulators", [])
        preds = entry.get("predictions", [])
        actual_map = {}
        for p in preds:
            if not p.get("has_result"):
                continue
            sd = p.get("actual_score_dom", 0)
            se = p.get("actual_score_ext", 0)
            ar = "1" if sd > se else "2" if se > sd else "X"
            tk = "%s|%s" % (p.get("home_team", ""), p.get("away_team", ""))
            actual_map[tk] = ar

        for acc in accs:
            all_won = True
            for leg in acc.get("legs", []):
                tk = "%s|%s" % (leg["home"], leg["away"])
                ar = actual_map.get(tk, "")
                pick = leg["dc_pick"]
                won = False
                if pick == "1X" and ar in ("1", "X"):
                    won = True
                elif pick == "X2" and ar in ("X", "2"):
                    won = True
                elif pick == "12" and ar in ("1", "2"):
                    won = True
                if won:
                    wins[pick] = wins.get(pick, 0) + 1
                else:
                    all_won = False
            if all_won:
                wins["total"] += 1

    return wins

def retrain_models():
    print("[Auto-Improve] Re-entrainement rapide des modeles...")
    historique = prediction_engine.charger_historique()
    stats = prediction_engine.calculer_stats(historique)
    max_round = max(int(d.get("round", 0)) for d in historique)
    max_train = max_round - 10 if max_round > 10 else None

    t0 = time.time()
    models, cv = ml_ensemble.train_ensemble_fast(
        historique, stats["team_stats"], stats["elo_ratings"],
        stats["h2h_stats"], stats["tendances"], max_train_round=max_train
    )
    elapsed = time.time() - t0

    if models:
        ml_ensemble.save_models(models)
        print("[Auto-Improve] Modeles sauvegardes (%.0fs)" % elapsed)
        if isinstance(cv, dict):
            for k, v in sorted(cv.items()):
                if isinstance(v, float):
                    print("  %s: %.1f%%" % (k, v * 100))
        return True
    else:
        print("[Auto-Improve] ECHEC entrainement")
        return False

def main():
    print("=== AUTO-IMPROVE CAF %s ===" % time.strftime("%Y-%m-%d %H:%M:%S"))

    history = load_history()

    print("Enrichissement des resultats (CSV uniquement, pas de fetch playout)...")
    history = dashboard.enrichir_resultats(history, skip_playout=True)
    dashboard.save_history(history)

    defeats = analyze_defeats(history)
    patterns = find_patterns(defeats)
    wins = find_wins(history)

    total_accus = sum(len(e.get("accumulators", [])) for e in history)
    print()
    print("Historique: %d rounds, %d accumulateurs" % (len(history), total_accus))
    print("Victoires accumulateurs: %d (%.1f%%)" % (
        wins["total"], wins["total"] / max(total_accus, 1) * 100))
    print()
    print("Defaites: %d" % len(defeats))
    print("Jambes echouees: %d" % patterns["total_failures"])
    if patterns["total_failures"] > 0:
        print("Par type: %s" % patterns["common_failed_picks"])
        print("Equipes problematiques: %s" % dict(list(patterns["common_failed_teams"].items())[:5]))
        print("Taux elevation echec: %.1f%%" % (
            patterns["high_edge_failures"] / patterns["total_failures"] * 100))
        print("Taux H2H faible echec: %.1f%%" % (
            patterns["low_h2h_failures"] / patterns["total_failures"] * 100))

    print()
    print("Gains par type de pick:")
    for pick in ["1X", "12"]:
        p_wins = wins.get(pick, 0)
        p_total = sum(patterns["common_failed_picks"].get(pick, 0) + p_wins
                      for _ in [0])
        print("  %s: %d victoires" % (pick, p_wins))

    last_train_file = "train_log.json"
    last_train_round = 0
    if os.path.exists(last_train_file):
        try:
            with open(last_train_file, "r") as f:
                last_train = json.load(f)
                last_train_round = last_train.get("max_round", 0)
        except Exception:
            pass

    current_max = max((e.get("round", 0) for e in history), default=0)
    rounds_since_train = current_max - last_train_round

    if rounds_since_train >= RETRAIN_AFTER_ROUNDS:
        print()
        print("Re-entrainement necessaire (%d rounds depuis dernier)" % rounds_since_train)
        retrain_models()
    else:
        print()
        print("Prochain re-entrainement dans %d rounds" % (RETRAIN_AFTER_ROUNDS - rounds_since_train))

    log = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_rounds": len(history),
        "total_accumulators": total_accus,
        "wins": wins,
        "defeats": len(defeats),
        "patterns": patterns,
        "next_retrain_in": max(0, RETRAIN_AFTER_ROUNDS - rounds_since_train),
    }
    with open("auto_improve_log.json", "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    print()
    print("Log sauvegarde dans auto_improve_log.json")

if __name__ == "__main__":
    main()
