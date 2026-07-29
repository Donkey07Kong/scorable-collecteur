"""
Collecte automatique des cotes CAF depuis l'API bet261.mg
Sauvegarde dans cotes_historique.json pour construire la matrice des cotes.
"""
import os
import json
import time
import requests
from datetime import datetime

LEAGUE_ID = 8060
MATCHES_URL = f"https://hg-event-api-prod.sporty-tech.net/api/instantleagues/{LEAGUE_ID}/matches"
HEADERS = {
    "accept": "application/json",
    "app-version": "34283",
    "referer": "https://bet261.mg/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

COTES_FILE = "cotes_historique.json"


def load_cotes_historique():
    if os.path.exists(COTES_FILE):
        try:
            with open(COTES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {"rounds": {}, "last_update": None}
    return {"rounds": {}, "last_update": None}


def save_cotes_historique(data):
    data["last_update"] = datetime.now().isoformat()
    with open(COTES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extraire_cotes_simplifiees(event):
    """Extrait les cotes principales d'un match."""
    cotes = {}
    for bet_type in event.get("eventBetTypes", []):
        name = bet_type.get("name", "")
        items = bet_type.get("eventBetTypeItems", [])

        if name == "1X2":
            for item in items:
                sn = item.get("shortName", "")
                odds = item.get("odds", 0)
                if sn == "1":
                    cotes["cote_1"] = odds
                elif sn == "X":
                    cotes["cote_X"] = odds
                elif sn == "2":
                    cotes["cote_2"] = odds

        elif name == "+/-":
            for item in items:
                sn = item.get("shortName", "")
                odds = item.get("odds", 0)
                if "> 2.5" in sn:
                    cotes["over_2.5"] = odds
                elif "< 2.5" in sn:
                    cotes["under_2.5"] = odds
                elif "> 1.5" in sn:
                    cotes["over_1.5"] = odds
                elif "< 1.5" in sn:
                    cotes["under_1.5"] = odds
                elif "> 3.5" in sn:
                    cotes["over_3.5"] = odds
                elif "< 3.5" in sn:
                    cotes["under_3.5"] = odds

        elif name == "Double Chance":
            for item in items:
                sn = item.get("shortName", "")
                odds = item.get("odds", 0)
                if sn == "1X":
                    cotes["dc_1X"] = odds
                elif sn == "X2":
                    cotes["dc_X2"] = odds
                elif sn == "12":
                    cotes["dc_12"] = odds

        elif name == "Pair/Impair":
            for item in items:
                sn = item.get("shortName", "")
                odds = item.get("odds", 0)
                if sn == "Pair":
                    cotes["pair"] = odds
                elif sn == "Impair":
                    cotes["impair"] = odds

        elif name == "Total de buts":
            for item in items:
                cotes[f"total_{item.get('shortName', '')}"] = item.get("odds", 0)

    return cotes


def collecter_cotes():
    """Recupere les cotes actuelles et les sauvegarde."""
    historique = load_cotes_historique()

    try:
        resp = requests.get(MATCHES_URL, headers=HEADERS, timeout=10)
        data = resp.json()
    except Exception as e:
        return {"error": str(e), "collected": 0}

    rounds = data.get("rounds", [])
    total_collected = 0
    new_rounds = 0

    for rnd in rounds:
        rnd_num = rnd.get("roundNumber", rnd.get("round", "?"))
        matches = rnd.get("matches", [])
        if not matches:
            continue

        round_key = str(rnd_num)
        if round_key not in historique["rounds"]:
            historique["rounds"][round_key] = {
                "round": rnd_num,
                "collected_at": datetime.now().isoformat(),
                "matches": []
            }
            new_rounds += 1

        round_data = historique["rounds"][round_key]
        existing_ids = {m.get("match_id") for m in round_data["matches"]}

        for event in matches:
            match_id = event.get("id", 0)
            home = event.get("homeTeam", {}).get("name", "?")
            away = event.get("awayTeam", {}).get("name", "?")

            cotes = extraire_cotes_simplifiees(event)
            if not cotes.get("cote_1"):
                continue

            match_entry = {
                "match_id": match_id,
                "home_team": home,
                "away_team": away,
                "cotes": cotes,
                "collected_at": datetime.now().isoformat()
            }

            if match_id not in existing_ids:
                round_data["matches"].append(match_entry)
                total_collected += 1
            else:
                for i, m in enumerate(round_data["matches"]):
                    if m.get("match_id") == match_id:
                        round_data["matches"][i] = match_entry
                        break

    save_cotes_historique(historique)

    return {
        "collected": total_collected,
        "new_rounds": new_rounds,
        "total_rounds": len(historique["rounds"]),
        "total_matches": sum(len(r["matches"]) for r in historique["rounds"].values()),
    }


def get_cotes_stats():
    """Retourne les stats des cotes collectees."""
    historique = load_cotes_historique()
    stats = {
        "total_rounds": len(historique["rounds"]),
        "last_update": historique.get("last_update"),
        "rounds_summary": []
    }

    for rk, rv in sorted(historique["rounds"].items(), key=lambda x: int(x[0])):
        matches = rv.get("matches", [])
        if matches:
            avg_c1 = sum(m["cotes"].get("cote_1", 0) for m in matches if m["cotes"].get("cote_1")) / max(len(matches), 1)
            avg_cX = sum(m["cotes"].get("cote_X", 0) for m in matches if m["cotes"].get("cote_X")) / max(len(matches), 1)
            avg_c2 = sum(m["cotes"].get("cote_2", 0) for m in matches if m["cotes"].get("cote_2")) / max(len(matches), 1)
        else:
            avg_c1 = avg_cX = avg_c2 = 0

        stats["rounds_summary"].append({
            "round": int(rk),
            "matches": len(matches),
            "avg_cote_1": round(avg_c1, 2),
            "avg_cote_X": round(avg_cX, 2),
            "avg_cote_2": round(avg_c2, 2),
        })

    return stats


def analyser_matrice_cotes():
    """Analyse la matrice des cotes collectees."""
    historique = load_cotes_historique()
    all_matches = []
    for rv in historique["rounds"].values():
        all_matches.extend(rv.get("matches", []))

    if not all_matches:
        return {"error": "Pas de cotes collectees"}

    home_wins = 0
    draws = 0
    away_wins = 0
    total = len(all_matches)

    cote_buckets = {"1.0-1.5": [], "1.5-2.0": [], "2.0-2.5": [], "2.5-3.0": [], "3.0+": []}
    home_odds_list = []

    for m in all_matches:
        c = m.get("cotes", {})
        c1 = c.get("cote_1", 0)
        if c1 > 0:
            home_odds_list.append(c1)

    if home_odds_list:
        avg_home = sum(home_odds_list) / len(home_odds_list)
        avg_implied_home = sum(1/o for o in home_odds_list) / len(home_odds_list)
    else:
        avg_home = avg_implied_home = 0

    return {
        "total_matches": total,
        "avg_home_odds": round(avg_home, 2),
        "avg_implied_home_prob": round(avg_implied_home * 100, 1),
        "home_edge": "A determiner quand les resultats seront collectes",
    }


if __name__ == "__main__":
    print("=== Collecte des cotes CAF ===")
    result = collecter_cotes()
    print(f"Resultat: {json.dumps(result, indent=2)}")

    print("\n=== Stats ===")
    stats = get_cotes_stats()
    print(f"Total rounds: {stats['total_rounds']}")
    print(f"Derniere MAJ: {stats['last_update']}")
    for rs in stats["rounds_summary"]:
        print(f"  Round {rs['round']}: {rs['matches']} matchs - Avg 1X2: {rs['avg_cote_1']}/{rs['avg_cote_X']}/{rs['avg_cote_2']}")

    print("\n=== Matrice ===")
    matrice = analyser_matrice_cotes()
    print(json.dumps(matrice, indent=2))
