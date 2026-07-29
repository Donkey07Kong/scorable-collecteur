"""
collecteur_live.py - Collecteur 24/7 donnees bet261 CAF
Capture: scores, cotes (30+ types), classement equipes par round.
Sauvegarde: live_data.csv (matchs) + rankings_per_round.json (classements).
"""

import os
import csv
import json
import time
import threading
import signal
import requests
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIVE_CSV = os.path.join(BASE_DIR, "live_data.csv")
RANKING_FILE = os.path.join(BASE_DIR, "rankings_per_round.json")
DONNEES_CSV = os.path.join(BASE_DIR, "donnees_equipes.csv")
LOG_FILE = os.path.join(BASE_DIR, "server_err.log")

MATCHES_URL = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues/8060/matches"
RANKING_URL = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues/8060/ranking"
PLAYOUT_URL = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues/round/{round}/playout?eventCategoryId=156008&parentEventCategoryId=8060"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "app-version": "34283",
    "referer": "https://bet261.mg/",
}

TARGET_MIN = 20000
POLL_INTERVAL = 30
CSV_LOCK = threading.Lock()

_cycle = 1
_last_round = None
_running = True
_shutdown_requested = False
_odds_cache = {}


def _log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[LIVE] %s %s" % (ts, msg)
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except Exception:
        pass


def _detect_cycle():
    global _cycle
    try:
        if os.path.exists(DONNEES_CSV):
            import csv
            with open(DONNEES_CSV, "r", encoding="utf-8") as f:
                max_cycle = 0
                for row in csv.DictReader(f):
                    c = int(row.get("cycle", 0))
                    if c > max_cycle:
                        max_cycle = c
                if max_cycle > 0:
                    _cycle = max_cycle
                    _log("Cycle detecte: %d" % _cycle)
    except Exception as e:
        _log("Erreur detection cycle: %s" % e)


def _fetch_api_matches():
    try:
        r = requests.get(MATCHES_URL, headers=HEADERS, timeout=10)
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
        return current_round, current_matches
    except Exception as e:
        _log("Erreur API: %s" % e)
        return None, []


def _fetch_playout(round_num):
    url = PLAYOUT_URL.format(round=round_num)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        data = resp.json()
        results = []
        for ev in data.get("matches", []):
            goals = ev.get("goals", [])
            if goals:
                final = goals[-1]
                hs = int(final.get("homeScore", 0))
                aws = int(final.get("awayScore", 0))
            else:
                hs = 0
                aws = 0
            results.append({"match_id": ev.get("id"), "score_dom": hs, "score_ext": aws, "total": hs + aws})
        return results
    except Exception as e:
        _log("Erreur playout R%d: %s" % (round_num, e))
        return []


def _fetch_ranking():
    try:
        r = requests.get(RANKING_URL, headers=HEADERS, timeout=10)
        data = r.json()
        rankings = {}
        for t in data.get("teams", []):
            rankings[t["name"]] = {
                "position": t.get("position", 0),
                "points": t.get("points", 0),
                "won": t.get("won", 0),
                "draw": t.get("draw", 0),
                "lost": t.get("lost", 0),
                "history": t.get("history", []),
            }
        return rankings
    except Exception as e:
        _log("Erreur ranking: %s" % e)
        return {}


def _extract_odds(matches):
    """Extrait TOUTES les cotes disponibles des matchs."""
    odds_by_pos = []
    for m in matches:
        bts = {bt["name"]: bt["eventBetTypeItems"] for bt in m.get("eventBetTypes", [])}

        def _odds(name, short):
            items = bts.get(name, [])
            return next((i["odds"] for i in items if i["shortName"] == short), 0)

        def _find_ou(threshold):
            for bt in m.get("eventBetTypes", []):
                if bt["name"] == "+/-":
                    for item in bt["eventBetTypeItems"]:
                        if item["shortName"] == "> %s" % threshold:
                            return item["odds"]
            return 0

        def _find_ou_under(threshold):
            for bt in m.get("eventBetTypes", []):
                if bt["name"] == "+/-":
                    for item in bt["eventBetTypeItems"]:
                        if item["shortName"] == "< %s" % threshold:
                            return item["odds"]
            return 0

        items_total = bts.get("Total de buts", [])
        items_ht = bts.get("Mi-tps 1X2", [])
        items_ht_dc = bts.get("Mi-tps DC", [])
        items_ht_btts = bts.get("Les deux equipes marquent / 1ere mi temps", [])

        odds_by_pos.append({
            "cote_1": _odds("1X2", "1"),
            "cote_X": _odds("1X2", "X"),
            "cote_2": _odds("1X2", "2"),
            "cote_1X": _odds("Double Chance", "1X"),
            "cote_X2": _odds("Double Chance", "X2"),
            "cote_12": _odds("Double Chance", "12"),
            "cote_over05": _find_ou("0.5"),
            "cote_under05": _find_ou_under("0.5"),
            "cote_over15": _find_ou("1.5"),
            "cote_under15": _find_ou_under("1.5"),
            "cote_over25": _find_ou("2.5"),
            "cote_under25": _find_ou_under("2.5"),
            "cote_over35": _find_ou("3.5"),
            "cote_under35": _find_ou_under("3.5"),
            "cote_total_buts": json.dumps({i["shortName"]: i["odds"] for i in items_total}) if items_total else "",
            "cote_btts_oui": _odds("G/NG", "Oui"),
            "cote_btts_non": _odds("G/NG", "Non"),
            "cote_pair": _odds("Pair/Impair", "Pair"),
            "cote_impair": _odds("Pair/Impair", "Impair"),
            "cote_ht_1": next((i["odds"] for i in items_ht if i["shortName"] == "1"), 0),
            "cote_ht_X": next((i["odds"] for i in items_ht if i["shortName"] == "X"), 0),
            "cote_ht_2": next((i["odds"] for i in items_ht if i["shortName"] == "2"), 0),
            "cote_ht_1X": next((i["odds"] for i in items_ht_dc if i["shortName"] == "1X"), 0),
            "cote_ht_X2": next((i["odds"] for i in items_ht_dc if i["shortName"] == "X2"), 0),
            "cote_ht_12": next((i["odds"] for i in items_ht_dc if i["shortName"] == "12"), 0),
            "cote_ht_btts_oui": next((i["odds"] for i in items_ht_btts if i["shortName"] == "Oui"), 0),
            "cote_ht_btts_non": next((i["odds"] for i in items_ht_btts if i["shortName"] == "Non"), 0),
        })
    return odds_by_pos


def _ensure_csv():
    if os.path.exists(LIVE_CSV):
        return
    with open(LIVE_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "round", "cycle", "home_team", "away_team",
            "score_dom", "score_ext", "total",
            "cote_1", "cote_X", "cote_2",
            "cote_1X", "cote_X2", "cote_12",
            "cote_over05", "cote_under05",
            "cote_over15", "cote_under15",
            "cote_over25", "cote_under25",
            "cote_over35", "cote_under35",
            "cote_total_buts",
            "cote_btts_oui", "cote_btts_non",
            "cote_pair", "cote_impair",
            "cote_ht_1", "cote_ht_X", "cote_ht_2",
            "cote_ht_1X", "cote_ht_X2", "cote_ht_12",
            "cote_ht_btts_oui", "cote_ht_btts_non",
            "source", "match_id", "timestamp",
        ])
    _log("CSV cree: %s" % LIVE_CSV)


def _csv_has_round(rnd, cycle):
    try:
        with open(LIVE_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if int(row.get("round", 0)) == rnd and int(row.get("cycle", 0)) == cycle:
                    return True
    except Exception:
        pass
    return False


def _get_positions_from_matches(matches):
    pos_list = []
    for m in matches:
        home = m.get("homeTeam", {}).get("name", "")
        away = m.get("awayTeam", {}).get("name", "")
        mid = m.get("id", 0)
        if home and away:
            pos_list.append((home, away, mid))
    return pos_list


def _save_ranking_snapshot(rnd, cycle, rankings):
    if not rankings:
        return
    key = "%d_%d" % (rnd, cycle)
    existing = {}
    if os.path.exists(RANKING_FILE):
        try:
            with open(RANKING_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
    if key not in existing:
        existing[key] = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "rankings": rankings,
        }
        with open(RANKING_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        _log("Ranking R%d C%d sauvegarde (%d equipes)" % (rnd, cycle, len(rankings)))


def _write_csv_rows(rows):
    with CSV_LOCK:
        with open(LIVE_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for row in rows:
                w.writerow(row)


def _process_round(rnd):
    if _csv_has_round(rnd, _cycle):
        return

    cotes = _odds_cache.pop(rnd, [])
    pr = _fetch_playout(rnd)
    if not pr:
        _log("Pas de playout pour R%d" % rnd)
        return

    _, matches = _fetch_api_matches()
    api_list = _get_positions_from_matches(matches)

    rows = []
    for i, p in enumerate(pr):
        if i < len(api_list):
            home, away, mid = api_list[i]
        else:
            home = "Unknown_%d" % i
            away = "Unknown_%d" % (i + 12)
            mid = 0

        o = cotes[i] if i < len(cotes) else {}
        rows.append([
            rnd, _cycle, home, away,
            p["score_dom"], p["score_ext"], p["total"],
            o.get("cote_1", 0), o.get("cote_X", 0), o.get("cote_2", 0),
            o.get("cote_1X", 0), o.get("cote_X2", 0), o.get("cote_12", 0),
            o.get("cote_over05", 0), o.get("cote_under05", 0),
            o.get("cote_over15", 0), o.get("cote_under15", 0),
            o.get("cote_over25", 0), o.get("cote_under25", 0),
            o.get("cote_over35", 0), o.get("cote_under35", 0),
            o.get("cote_total_buts", ""),
            o.get("cote_btts_oui", 0), o.get("cote_btts_non", 0),
            o.get("cote_pair", 0), o.get("cote_impair", 0),
            o.get("cote_ht_1", 0), o.get("cote_ht_X", 0), o.get("cote_ht_2", 0),
            o.get("cote_ht_1X", 0), o.get("cote_ht_X2", 0), o.get("cote_ht_12", 0),
            o.get("cote_ht_btts_oui", 0), o.get("cote_ht_btts_non", 0),
            "playout", mid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ])

    if rows:
        _write_csv_rows(rows)
        _log("R%d sauv: %d matchs, %d avec cotes" % (rnd, len(rows), len(cotes)))


def _handle_transition(old_round, new_round):
    global _cycle
    if old_round and new_round < old_round:
        _cycle += 1
        _log("Cycle %d! R%d -> R%d" % (_cycle, old_round, new_round))

    rounds_to_process = []
    if old_round and new_round > old_round:
        rounds_to_process = list(range(old_round, new_round))
    elif old_round and new_round < old_round:
        rounds_to_process = list(range(old_round, 47)) + list(range(1, new_round))

    for rnd in rounds_to_process:
        _process_round(rnd)


def _count_live_rows():
    try:
        with open(LIVE_CSV, "r", encoding="utf-8") as f:
            return sum(1 for _ in csv.DictReader(f))
    except Exception:
        return 0


def _main_loop():
    global _last_round, _running
    _detect_cycle()
    _ensure_csv()

    retrain_count = 0
    ranking_saved_for = set()
    stop_at_cycle = None

    _log("Demarrage (cycle=%d, target=%d matchs)" % (_cycle, TARGET_MIN))

    while _running:
        try:
            current_round, matches = _fetch_api_matches()

            if current_round:
                if _last_round is None:
                    _last_round = current_round
                    if matches:
                        _odds_cache[current_round] = _extract_odds(matches)
                    _log("Round: R%d" % current_round)
                elif current_round != _last_round:
                    was = _last_round
                    _last_round = current_round
                    _log("Transition: R%d -> R%d" % (was, current_round))
                    if matches:
                        _odds_cache[current_round] = _extract_odds(matches)
                    _handle_transition(was, current_round)
                    retrain_count += 1
                    if retrain_count % 10 == 0:
                        threading.Thread(target=_try_retrain, daemon=True).start()
                else:
                    if matches and current_round not in _odds_cache:
                        _odds_cache[current_round] = _extract_odds(matches)

                rk_key = "%d_%d" % (current_round, _cycle)
                if rk_key not in ranking_saved_for:
                    rankings = _fetch_ranking()
                    if rankings:
                        _save_ranking_snapshot(current_round, _cycle, rankings)
                        ranking_saved_for.add(rk_key)

            if _shutdown_requested and stop_at_cycle is None:
                total = _count_live_rows()
                if total >= TARGET_MIN:
                    stop_at_cycle = _cycle
                    _log("Cible %d atteinte (%d) — arret en fin de cycle C%d" % (TARGET_MIN, total, stop_at_cycle))

            if stop_at_cycle is not None and _cycle > stop_at_cycle:
                _log("Cycle C%d termine — arret propre" % stop_at_cycle)
                _running = False
                break

        except Exception as e:
            _log("Erreur: %s" % e)

        time.sleep(POLL_INTERVAL)


def _try_retrain():
    try:
        import prediction_engine
        import ml_ensemble
        import csv as csv_mod

        if not os.path.exists(LIVE_CSV):
            return

        donnees = []
        with open(LIVE_CSV, "r", encoding="utf-8") as f:
            for row in csv_mod.DictReader(f):
                sd = int(row.get("score_dom", 0))
                se = int(row.get("score_ext", 0))
                total = sd + se
                victory = "dom" if sd > se else "ext" if se > sd else "nul"
                donnees.append({
                    "round": int(row["round"]),
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "score_final_dom": sd,
                    "score_final_ext": se,
                    "nb_buts_total": total,
                    "nb_buts_dom": sd,
                    "nb_buts_ext": se,
                    "victoire": victory,
                    "cycle": int(row.get("cycle", 0)),
                })

        if len(donnees) < 50:
            return

        stats = prediction_engine.calculer_stats(donnees)
        models, cv = ml_ensemble.train_ensemble_fast(
            donnees, stats["team_stats"], stats["elo_ratings"],
            stats["h2h_stats"], stats["tendances"]
        )
        if models:
            ml_ensemble.save_models(models)
            _log("Retrain OK: %d matchs (live data only)" % len(donnees))
    except Exception as e:
        _log("Retrain erreur: %s" % e)


def _signal_handler(sig, frame):
    global _shutdown_requested
    _log("Signal %d recu — arret en fin de cycle en cours" % sig)
    _shutdown_requested = True


def main():
    try:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except ValueError:
        pass
    _log("=" * 50)
    _log("COLLECTEUR DEMARRE - attend R1 prochain cycle")
    _log("=" * 50)
    _main_loop()
    _log("Arrete proprement")


if __name__ == "__main__":
    main()
