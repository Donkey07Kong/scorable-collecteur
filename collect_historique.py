import requests
import csv
import json
import time
import os

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "fr",
    "app-version": "34283",
    "referer": "https://bet261.mg/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

MATCHES_URL = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues/8060/matches"
PLAYOUT_URL = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues/round/{round}/playout?eventCategoryId=156008&parentEventCategoryId=8060"
CSV_FILE = "donnees_equipes.csv"


def load_existing():
    existing = set()
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.add((int(row["round"]), row["home_team"], row["away_team"]))
    return existing


def fetch_matches_for_round(rnd_num):
    try:
        url = MATCHES_URL + "?round=" + str(rnd_num)
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        rounds = data.get("rounds", [])
        if not rounds:
            return []
        matches = rounds[0].get("matches", [])
        results = []
        for m in matches:
            home = m["homeTeam"]["name"]
            away = m["awayTeam"]["name"]
            mid = m.get("id", 0)
            odds = {}
            for bt in m.get("eventBetTypes", []):
                if bt["name"] == "1X2":
                    for item in bt["eventBetTypeItems"]:
                        odds[item["shortName"]] = item["odds"]
            cote_1 = odds.get("1", 0)
            cote_X = odds.get("X", 0)
            cote_2 = odds.get("2", 0)
            if cote_1 and cote_X and cote_2:
                implied_1 = 1 / cote_1
                implied_X = 1 / cote_X
                implied_2 = 1 / cote_2
                total = implied_1 + implied_X + implied_2
                prob_dom = implied_1 / total
                prob_nul = implied_X / total
                prob_ext = implied_2 / total
            else:
                prob_dom = 0.4
                prob_nul = 0.3
                prob_ext = 0.3
            results.append({
                "home_team": home,
                "away_team": away,
                "match_id": mid,
                "cote_1": cote_1,
                "cote_X": cote_X,
                "cote_2": cote_2,
                "prob_dom_odds": round(prob_dom, 4),
                "prob_nul_odds": round(prob_nul, 4),
                "prob_ext_odds": round(prob_ext, 4),
            })
        return results
    except Exception as e:
        print("  ERROR fetch_matches round " + str(rnd_num) + ": " + str(e)[:60])
        return []


def fetch_playout_for_round(rnd_num):
    try:
        url = PLAYOUT_URL.format(round=rnd_num)
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        matches = data.get("matches", [])
        results = []
        for m in matches:
            goals = m.get("goals", [])
            if goals:
                final = goals[-1]
                sd = int(final.get("homeScore", 0))
                se = int(final.get("awayScore", 0))
            else:
                sd = 0
                se = 0
            mid = m.get("id", 0)
            results.append({
                "match_id": mid,
                "score_final_dom": sd,
                "score_final_ext": se,
                "total_buts": sd + se,
            })
        return results
    except Exception as e:
        print("  ERROR fetch_playout round " + str(rnd_num) + ": " + str(e)[:60])
        return []


def collect_all():
    existing = load_existing()
    print("Existing: " + str(len(existing)) + " rows")

    try:
        r = requests.get(MATCHES_URL, headers=HEADERS, timeout=10)
        data = r.json()
        rounds = data.get("rounds", [])
        max_round = max(int(rnd.get("roundNumber", 0)) for rnd in rounds) if rounds else 0
    except:
        max_round = 45
    print("Max round from API: " + str(max_round))

    total_new = 0
    for rnd_num in range(1, max_round + 1):
        matches = fetch_matches_for_round(rnd_num)
        if not matches:
            continue
        playout = fetch_playout_for_round(rnd_num)
        playout_by_id = {p["match_id"]: p for p in playout}

        new_in_round = 0
        rows_to_add = []
        for m in matches:
            key = (rnd_num, m["home_team"], m["away_team"])
            if key in existing:
                continue

            playout_data = playout_by_id.get(m["match_id"], {})
            sd = playout_data.get("score_final_dom", 0)
            se = playout_data.get("score_final_ext", 0)
            total = sd + se

            row = {
                "round": rnd_num,
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "match_id": m["match_id"],
                "score_final_dom": sd,
                "score_final_ext": se,
                "total_buts": total,
                "over_25": 1 if total > 2.5 else 0,
                "result": "1" if sd > se else "2" if se > sd else "X",
                "cote_1": m["cote_1"],
                "cote_X": m["cote_X"],
                "cote_2": m["cote_2"],
                "prob_dom_odds": m["prob_dom_odds"],
                "prob_nul_odds": m["prob_nul_odds"],
                "prob_ext_odds": m["prob_ext_odds"],
            }
            rows_to_add.append(row)
            existing.add(key)
            new_in_round += 1

        if rows_to_add:
            write_header = not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0
            with open(CSV_FILE, "a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows_to_add[0].keys()))
                if write_header:
                    writer.writeheader()
                writer.writerows(rows_to_add)
            total_new += new_in_round
            print("  Round " + str(rnd_num) + ": +" + str(new_in_round) + " new (" + str(len(matches)) + " total)")
        else:
            print("  Round " + str(rnd_num) + ": 0 new (all existing)")

        time.sleep(0.3)

    print("\nDone! Added " + str(total_new) + " new rows")

    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)
    print("Total CSV: " + str(len(all_rows)) + " rows")


if __name__ == "__main__":
    collect_all()
