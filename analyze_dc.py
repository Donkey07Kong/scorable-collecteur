"""
Analyse Double Chance CAF:
- Statistiques des resultats 1X, X2, 12 sur les donnees historiques
- Comparaison avec les cotes DC du site
- Detection de value bets DC
"""
import csv
import json
import os

def load_data():
    rows = []
    f = "donnees_equipes.csv"
    if os.path.exists(f):
        with open(f, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    sd = int(float(row["score_final_dom"]))
                    se = int(float(row["score_final_ext"]))
                    rows.append({
                        "round": int(float(row["round"])),
                        "home": row["home_team"],
                        "away": row["away_team"],
                        "sd": sd,
                        "se": se,
                        "total": sd + se,
                    })
                except (KeyError, ValueError):
                    continue
    return rows


def load_cotes():
    if not os.path.exists("cotes_historique.json"):
        return []
    with open("cotes_historique.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    matches = []
    for rv in data.get("rounds", {}).values():
        for m in rv.get("matches", []):
            c = m.get("cotes", {})
            if c.get("dc_1X") or c.get("dc_X2") or c.get("dc_12"):
                matches.append({
                    "home": m.get("home_team", "?"),
                    "away": m.get("away_team", "?"),
                    "dc_1X": c.get("dc_1X", 0),
                    "dc_X2": c.get("dc_X2", 0),
                    "dc_12": c.get("dc_12", 0),
                    "cote_1": c.get("cote_1", 0),
                    "cote_X": c.get("cote_X", 0),
                    "cote_2": c.get("cote_2", 0),
                })
    return matches


def analyze():
    data = load_data()
    cotes = load_cotes()

    print("=" * 70)
    print("ANALYSE DOUBLE CHANCE - COUPE D'AFRIQUE")
    print("=" * 70)
    print(f"\nTotal matchs historiques: {len(data)}")
    print(f"Total matchs avec cotes DC: {len(cotes)}")

    # --- Resultats reels ---
    n = len(data)
    if n == 0:
        print("Pas de donnees!")
        return

    home_wins = sum(1 for d in data if d["sd"] > d["se"])
    draws = sum(1 for d in data if d["sd"] == d["se"])
    away_wins = sum(1 for d in data if d["sd"] < d["se"])

    dc_1X = home_wins + draws
    dc_X2 = draws + away_wins
    dc_12 = home_wins + away_wins

    print(f"\n--- RESULTATS REELS ---")
    print(f"  Domicile (1):  {home_wins:4d} / {n} = {home_wins/n*100:.1f}%")
    print(f"  Nul (X):       {draws:4d} / {n} = {draws/n*100:.1f}%")
    print(f"  Extérieur (2): {away_wins:4d} / {n} = {away_wins/n*100:.1f}%")
    print(f"\n  Double Chance:")
    print(f"  1X (Dom/Nul):    {dc_1X:4d} / {n} = {dc_1X/n*100:.1f}%")
    print(f"  X2 (Nul/Ext):    {dc_X2:4d} / {n} = {dc_X2/n*100:.1f}%")
    print(f"  12 (Dom/Ext):    {dc_12:4d} / {n} = {dc_12/n*100:.1f}%")

    # --- Par round ---
    rounds = sorted(set(d["round"] for d in data))
    print(f"\n--- PAR ROUND ---")
    for rnd in rounds:
        rnd_data = [d for d in data if d["round"] == rnd]
        r_n = len(rnd_data)
        r_hw = sum(1 for d in rnd_data if d["sd"] > d["se"])
        r_dr = sum(1 for d in rnd_data if d["sd"] == d["se"])
        r_aw = sum(1 for d in rnd_data if d["sd"] < d["se"])
        r_1X = r_hw + r_dr
        r_X2 = r_dr + r_aw
        r_12 = r_hw + r_aw
        print(f"  Round {rnd:3d}: {r_n:2d} matchs | 1={r_hw} X={r_dr} 2={r_aw} | DC: 1X={r_1X}({r_1X/r_n*100:.0f}%) X2={r_X2}({r_X2/r_n*100:.0f}%) 12={r_12}({r_12/r_n*100:.0f}%)")

    # --- Tendance domicile/exterieur ---
    print(f"\n--- TENDANCE DOMICILE vs EXTERIEUR ---")
    print(f"  Victoire domicile: {home_wins/n*100:.1f}% (moyenne football: ~46%)")
    print(f"  Avantage home dans CAF: {'OUI' if home_wins/n > 0.45 else 'NON'} ({home_wins/n*100:.1f}%)")

    # --- Score distribution ---
    print(f"\n--- DISTRIBUTION DES SCORES ---")
    scores = {}
    for d in data:
        s = f"{d['sd']}-{d['se']}"
        scores[s] = scores.get(s, 0) + 1
    for s, c in sorted(scores.items(), key=lambda x: -x[1])[:10]:
        print(f"  {s}: {c:3d} ({c/n*100:.1f}%)")

    # --- Buts par match ---
    totals = [d["total"] for d in data]
    avg_goals = sum(totals) / len(totals)
    over_25 = sum(1 for t in totals if t > 2.5) / len(totals)
    over_15 = sum(1 for t in totals if t > 1.5) / len(totals)
    print(f"\n--- BUTS ---")
    print(f"  Moyenne: {avg_goals:.2f} buts/match")
    print(f"  Over 1.5: {over_15*100:.1f}%")
    print(f"  Over 2.5: {over_25*100:.1f}%")

    # --- Cotes DC du site ---
    if cotes:
        print(f"\n--- COTES DC DU SITE (moyennes) ---")
        avg_1X = sum(m["dc_1X"] for m in cotes) / len(cotes)
        avg_X2 = sum(m["dc_X2"] for m in cotes) / len(cotes)
        avg_12 = sum(m["dc_12"] for m in cotes) / len(cotes)
        avg_c1 = sum(m["cote_1"] for m in cotes if m["cote_1"]) / max(len(cotes), 1)
        avg_cX = sum(m["cote_X"] for m in cotes if m["cote_X"]) / max(len(cotes), 1)
        avg_c2 = sum(m["cote_2"] for m in cotes if m["cote_2"]) / max(len(cotes), 1)

        print(f"  Cotes simples moyennes: 1={avg_c1:.2f} X={avg_cX:.2f} 2={avg_c2:.2f}")
        print(f"  Cotes DC moyennes:     1X={avg_1X:.2f} X2={avg_X2:.2f} 12={avg_12:.2f}")

        # Probabilities implicites
        pi_c1 = 1 / avg_c1 if avg_c1 else 0
        pi_cX = 1 / avg_cX if avg_cX else 0
        pi_c2 = 1 / avg_c2 if avg_c2 else 0
        pi_dc1X = 1 / avg_1X if avg_1X else 0
        pi_dcX2 = 1 / avg_X2 if avg_X2 else 0
        pi_dc12 = 1 / avg_12 if avg_12 else 0

        print(f"\n  Prob implicites (simples): 1={pi_c1*100:.1f}% X={pi_cX*100:.1f}% 2={pi_c2*100:.1f}%")
        print(f"  Prob implicites (DC):     1X={pi_dc1X*100:.1f}% X2={pi_dcX2*100:.1f}% 12={pi_dc12*100:.1f}%")
        print(f"  Total implicite simples:  {(pi_c1+pi_cX+pi_c2)*100:.1f}% (marge: {(pi_c1+pi_cX+pi_c2)*100-100:.1f}%)")
        print(f"  Total implicite DC:       {(pi_dc1X+pi_dcX2+pi_dc12)*100:.1f}% (marge: {(pi_dc1X+pi_dcX2+pi_dc12)*100-100:.1f}%)")

        # Expected DC from historical
        print(f"\n--- VALUE BET DC ---")
        print(f"  Frequence reelle historique:")
        print(f"    1X: {dc_1X/n*100:.1f}% vs implicite site: {pi_dc1X*100:.1f}% -> {'VALUE' if dc_1X/n > pi_dc1X else 'PAS VALUE'} (+{(dc_1X/n - pi_dc1X)*100:+.1f}pp)")
        print(f"    X2: {dc_X2/n*100:.1f}% vs implicite site: {pi_dcX2*100:.1f}% -> {'VALUE' if dc_X2/n > pi_dcX2 else 'PAS VALUE'} (+{(dc_X2/n - pi_dcX2)*100:+.1f}pp)")
        print(f"    12: {dc_12/n*100:.1f}% vs implicite site: {pi_dc12*100:.1f}% -> {'VALUE' if dc_12/n > pi_dc12 else 'PAS VALUE'} (+{(dc_12/n - pi_dc12)*100:+.1f}pp)")

        # Individual match DC value
        print(f"\n--- MATCHS DC VALUE (par match) ---")
        print(f"  {'Match':<35} {'Result':>7} {'DC':>4} {'Cote DC':>8} {'Edge':>7}")
        print(f"  {'-'*65}")
        for m in cotes:
            home_m = m["home"]
            away_m = m["away"]
            # Try to find result in historical
            result = None
            for d in data:
                if d["home"] == home_m and d["away"] == away_m:
                    result = d
                    break
            if not result:
                continue

            # Determine actual DC
            sd, se = result["sd"], result["se"]
            actual = ""
            if sd > se:
                actual = "1"
            elif sd == se:
                actual = "X"
            else:
                actual = "2"

            dc_result = ""
            dc_cote = 0
            if actual in ("1", "X"):
                dc_result = "1X"
                dc_cote = m["dc_1X"]
            if actual in ("X", "2"):
                dc_result = "X2"
                dc_cote = m["dc_X2"]
                if dc_result == "1X" and actual == "X":
                    # Both 1X and X2 win on draw
                    pass
            if actual in ("1", "2"):
                dc_result_12 = "12"
                dc_cote_12 = m["dc_12"]

            # Check all 3 DC
            for dc_name, dc_cote_val in [("1X", m["dc_1X"]), ("X2", m["dc_X2"]), ("12", m["dc_12"])]:
                if not dc_cote_val:
                    continue
                won = False
                if dc_name == "1X" and actual in ("1", "X"):
                    won = True
                elif dc_name == "X2" and actual in ("X", "2"):
                    won = True
                elif dc_name == "12" and actual in ("1", "2"):
                    won = True

                prob_impl = 1 / dc_cote_val if dc_cote_val else 0
                edge = 0
                # Estimate real prob from match context
                print(f"  {home_m + ' vs ' + away_m:<35} {actual:>7} {dc_name:>4} {dc_cote_val:>8.2f} {'WIN' if won else 'LOSS':>7}")


if __name__ == "__main__":
    analyze()
