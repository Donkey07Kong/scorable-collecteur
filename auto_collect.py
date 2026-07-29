"""
Auto-collecteur CAF: collecte les matchs + odds a chaque round,
puis recupere les scores via playout quand le round est termine.
Sauvegarde dans donnees_equipes.csv pour enrichir le modele ML.

MATCHING: d'abord par noms d'equipes, sinon par position (fallback)
car le playout API ne garde pas les noms pour les anciens rounds.
"""
import os
import csv
import json
import requests

LEAGUE_ID = 8060
MATCHES_URL = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues/" + str(LEAGUE_ID) + "/matches"
PLAYOUT_URL = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues/round/{round}/playout?eventCategoryId=156008&parentEventCategoryId=8060"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "fr",
    "app-version": "34283",
    "referer": "https://bet261.mg/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

CSV_FILE = "donnees_equipes.csv"
PENDING_FILE = "auto_collect_pending.json"
STATE_FILE = "auto_collect_state.json"
CSV_FIELDS = ["round", "match_id", "home_team", "away_team", "score_final_dom",
              "score_final_ext", "nb_buts_total", "nb_buts_dom", "nb_buts_ext", "victoire", "cycle"]


def load_pending():
    if os.path.exists(PENDING_FILE):
        try:
            with open(PENDING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_pending(data):
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"cycle": 1, "last_round": 0}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def detect_cycle(current_round):
    """Detect if a new cycle started. Returns (cycle, is_new_cycle)."""
    state = load_state()
    last_round = state.get("last_round", 0)
    cycle = state.get("cycle", 1)
    if last_round > 0 and current_round < last_round - 10:
        cycle += 1
        print("  [Collecteur] Nouveau cycle detecte! round %d < %d -> cycle %d" % (current_round, last_round, cycle))
    state["last_round"] = current_round
    state["cycle"] = cycle
    save_state(state)
    return cycle


def get_existing_pairs():
    pairs = set()
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    key = (int(row["round"]), row["home_team"], row["away_team"])
                    pairs.add(key)
                except:
                    pass
    return pairs


def get_collect_status():
    pending = load_pending()
    total = 0
    rounds = set()
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                try:
                    rounds.add(int(row["round"]))
                except:
                    pass
    return {
        "total_rows": total,
        "existing_rounds": sorted(rounds),
        "pending_rounds": sorted(int(k) for k in pending.keys()),
    }


def fetch_current_matches():
    try:
        r = requests.get(MATCHES_URL, headers=HEADERS, timeout=10)
        data = r.json()
        results = []
        for rnd in data.get("rounds", []):
            rnd_num = rnd.get("roundNumber", 0)
            for event in rnd.get("matches", []):
                home = event.get("homeTeam", {}).get("name", "")
                away = event.get("awayTeam", {}).get("name", "")
                if not home or not away or home.isdigit() or away.isdigit():
                    continue
                results.append({
                    "round": rnd_num,
                    "match_id": event.get("id", 0),
                    "home_team": home,
                    "away_team": away,
                })
        return results
    except Exception:
        return []


def fetch_playout_scores(rnd_num):
    try:
        url = PLAYOUT_URL.format(round=rnd_num)
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        matches = data.get("matches", [])
        scores = []
        for m in matches:
            goals = m.get("goals", [])
            if goals:
                final = goals[-1]
                sd = int(final.get("homeScore", 0))
                se = int(final.get("awayScore", 0))
            else:
                sd = 0
                se = 0
            home_name = m.get("homeTeam", {}).get("name", "")
            away_name = m.get("awayTeam", {}).get("name", "")
            scores.append({
                "home": home_name,
                "away": away_name,
                "sd": sd,
                "se": se,
            })
        return scores
    except Exception:
        return []


def append_to_csv(rows):
    if not rows:
        return 0
    file_exists = os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 10
    with open(CSV_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def auto_collect():
    pending = load_pending()
    existing_pairs = get_existing_pairs()

    matches = fetch_current_matches()
    if not matches:
        return {"status": "no_matches", "saved": 0}

    current_rounds = set(m["round"] for m in matches)
    saved = 0

    current_round = max(current_rounds) if current_rounds else 0
    cycle = detect_cycle(current_round)

    for rnd_num_str in sorted(pending.keys(), key=lambda x: int(x)):
        rnd_num = int(rnd_num_str)
        pending_matches = pending[rnd_num_str]
        scores = fetch_playout_scores(rnd_num)
        if not scores:
            continue

        use_names = len(scores) > 0 and scores[0]["home"] != "" and scores[0]["home"] != "?"

        if use_names:
            score_map = {}
            for s in scores:
                if s["home"] and s["away"]:
                    score_map[(s["home"], s["away"])] = s
            matched = 0
            rows = []
            still_pending = []
            for pm in pending_matches:
                pair_key = (rnd_num, pm["home_team"], pm["away_team"])
                if pair_key in existing_pairs:
                    continue
                s = score_map.get((pm["home_team"], pm["away_team"]))
                if s:
                    sd, se = s["sd"], s["se"]
                    nbt = sd + se
                    victoire = "dom" if sd > se else ("ext" if se > sd else "nul")
                    rows.append({
                        "round": rnd_num_str, "match_id": pm["match_id"],
                        "home_team": pm["home_team"], "away_team": pm["away_team"],
                        "score_final_dom": sd, "score_final_ext": se,
                        "nb_buts_total": nbt, "nb_buts_dom": sd,
                        "nb_buts_ext": se, "victoire": victoire,
                        "cycle": str(cycle),
                    })
                    existing_pairs.add(pair_key)
                    matched += 1
                else:
                    still_pending.append(pm)
        else:
            if len(scores) != len(pending_matches):
                print("  [Collecteur] Round %s: playout=%d vs need=%d, skipping (cycle mismatch)" % (
                    rnd_num_str, len(scores), len(pending_matches)))
                continue
            rows = []
            still_pending = []
            matched = 0
            for i, pm in enumerate(pending_matches):
                pair_key = (rnd_num, pm["home_team"], pm["away_team"])
                if pair_key in existing_pairs:
                    continue
                if i < len(scores):
                    s = scores[i]
                    sd, se = s["sd"], s["se"]
                    nbt = sd + se
                    victoire = "dom" if sd > se else ("ext" if se > sd else "nul")
                    rows.append({
                        "round": rnd_num_str, "match_id": pm["match_id"],
                        "home_team": pm["home_team"], "away_team": pm["away_team"],
                        "score_final_dom": sd, "score_final_ext": se,
                        "nb_buts_total": nbt, "nb_buts_dom": sd,
                        "nb_buts_ext": se, "victoire": victoire,
                        "cycle": str(cycle),
                    })
                    existing_pairs.add(pair_key)
                    matched += 1
                else:
                    still_pending.append(pm)

        if rows:
            append_to_csv(rows)
            saved += len(rows)

        if still_pending:
            pending[rnd_num_str] = still_pending
        elif rnd_num_str in pending:
            del pending[rnd_num_str]

    for m in matches:
        rnd_str = str(m["round"])
        if rnd_str not in pending:
            pending[rnd_str] = []
        seen = {(p["home_team"], p["away_team"]) for p in pending[rnd_str]}
        if (m["home_team"], m["away_team"]) not in seen:
            pending[rnd_str].append({
                "match_id": m["match_id"],
                "home_team": m["home_team"],
                "away_team": m["away_team"],
            })

    save_pending(pending)

    return {
        "status": "ok",
        "current_rounds": sorted(current_rounds),
        "pending_rounds": sorted(int(k) for k in pending.keys()),
        "saved": saved,
    }


if __name__ == "__main__":
    result = auto_collect()
    print(json.dumps(result, indent=2))
    status = get_collect_status()
    print(json.dumps(status, indent=2))
