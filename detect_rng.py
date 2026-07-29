import sys
sys.stdout.reconfigure(encoding='utf-8')
from prediction_engine import charger_historique
import math
from collections import Counter

d = charger_historique()
print(f"Total matchs: {len(d)}")

results = {"dom": 0, "ext": 0, "nul": 0}
totals = []
home_goals = []
away_goals = []
score_pairs = []

for m in d:
    sd = m["score_final_dom"]
    se = m["score_final_ext"]
    total = sd + se
    totals.append(total)
    home_goals.append(sd)
    away_goals.append(se)
    score_pairs.append((sd, se))
    if sd > se:
        results["dom"] += 1
    elif se > sd:
        results["ext"] += 1
    else:
        results["nul"] += 1

n = len(d)
print(f"\n=== DISTRIBUTION DES RESULTATS ===")
print(f"Dom: {results['dom']}/{n} = {results['dom']/n*100:.1f}%")
print(f"Nul: {results['nul']}/{n} = {results['nul']/n*100:.1f}%")
print(f"Ext: {results['ext']}/{n} = {results['ext']/n*100:.1f}%")

print(f"\n=== DISTRIBUTION DES BUTS ===")
print(f"Moy buts/match: {sum(totals)/len(totals):.2f}")
print(f"Moy buts domicile: {sum(home_goals)/len(home_goals):.2f}")
print(f"Moy buts exterieur: {sum(away_goals)/len(away_goals):.2f}")

goal_dist = Counter(totals)
print(f"\nDistribution totale buts:")
for g in sorted(goal_dist.keys()):
    print(f"  {g} buts: {goal_dist[g]}/{n} = {goal_dist[g]/n*100:.1f}%")

print(f"\n=== SCORES LES PLUS FREQUENTS ===")
sp = Counter(score_pairs)
for (hs, as_), cnt in sp.most_common(15):
    print(f"  {hs}-{as_}: {cnt} fois ({cnt/n*100:.1f}%)")

print(f"\n=== TEST DE RANDOMICITE ===")

home_advantage = sum(1 for i in range(n) if home_goals[i] > away_goals[i]) / n
print(f"Avantage domicile: {home_advantage*100:.1f}%")

home_scoring_rate = sum(home_goals) / n
away_scoring_rate = sum(away_goals) / n
print(f"Taux buts domicile: {home_scoring_rate:.2f}")
print(f"Taux buts exterieur: {away_scoring_rate:.2f}")

chi2 = 0
expected = n / 3
for v in results.values():
    chi2 += (v - expected) ** 2 / expected
print(f"\nChi2 test (H0: 33/33/33): {chi2:.2f}")
print(f"Critical value (alpha=0.05, df=2): 5.99")
print(f"Resultat: {'REJETE (pas random 33/33/33)' if chi2 > 5.99 else 'NON REJETE (possible random)'}")

print(f"\n=== TEST STREAKS ===")
streaks = []
current = {"team": None, "len": 0}
for m in d:
    sd = m["score_final_dom"]
    se = m["score_final_ext"]
    if sd > se:
        r = "dom"
    elif se > sd:
        r = "ext"
    else:
        r = "nul"
    if r == current["team"]:
        current["len"] += 1
    else:
        if current["len"] > 0:
            streaks.append(current)
        current = {"team": r, "len": 1}
if current["len"] > 0:
    streaks.append(current)

streak_dist = Counter(s["len"] for s in streaks)
print("Distribution des series:")
for l in sorted(streak_dist.keys())[:8]:
    print(f"  Serie de {l}: {streak_dist[l]} fois")

print(f"\n=== VERIFICATION PAR EQUIPE ===")
teams_played = {}
for m in d:
    h = m.get("home_team", "")
    a = m.get("away_team", "")
    sd = m["score_final_dom"]
    se = m["score_final_ext"]
    if h not in teams_played:
        teams_played[h] = {"j": 0, "bm": 0, "be": 0}
    if a not in teams_played:
        teams_played[a] = {"j": 0, "bm": 0, "be": 0}
    teams_played[h]["j"] += 1
    teams_played[h]["bm"] += sd
    teams_played[h]["be"] += se
    teams_played[a]["j"] += 1
    teams_played[a]["bm"] += se
    teams_played[a]["be"] += sd

print(f"Equipes uniques: {len(teams_played)}")
match_counts = [v["j"] for v in teams_played.values()]
print(f"Matchs/equipe: min={min(match_counts)}, max={max(match_counts)}, moy={sum(match_counts)/len(match_counts):.1f}")

team_forces = []
for t, v in teams_played.items():
    if v["j"] > 0:
        force = (v["bm"] - v["be"]) / v["j"]
        team_forces.append((t, force, v["j"]))

team_forces.sort(key=lambda x: x[1], reverse=True)
print(f"\nTop 5 equipes (force):")
for t, f, j in team_forces[:5]:
    print(f"  {t}: force={f:.2f} ({j} matchs)")
print(f"\nBottom 5 equipes:")
for t, f, j in team_forces[-5:]:
    print(f"  {t}: force={f:.2f} ({j} matchs)")

forces = [f for _, f, _ in team_forces]
spread = max(forces) - min(forces)
print(f"\nSpread des forces: {spread:.2f}")
print(f"Ecart-type des forces: {(sum((f - sum(forces)/len(forces))**2 for f in forces)/len(forces))**0.5:.2f}")

print(f"\n=== CONCLUSION ===")
if home_advantage > 0.45 and home_advantage < 0.55:
    print("ATTENTION: Avantage domicile faible/comme un RNG (45-55%)")
elif home_advantage > 0.50:
    print("Avantage domicile normal pour du football")

if spread < 2.0:
    print("ATTENTION: Les equipes sont tres proches en force (possible RNG)")
else:
    print("Les equipes ont des forces differentes (probablement pas pur RNG)")

if chi2 < 5.99:
    print("ATTENTION: Les resultats 1X2 suivent distribution uniforme (possible RNG)")
