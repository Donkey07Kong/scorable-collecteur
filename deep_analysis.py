import pandas as pd
import warnings
from collections import defaultdict

warnings.filterwarnings("ignore")

# ============================================================
# LOAD DATA
# ============================================================
print("=" * 80)
print("LOADING DATA")
print("=" * 80)

df = pd.read_csv(
    "D:/Documents/261CAF/donnees_equipes.csv",
    on_bad_lines="warn",
)

# Normalize column names
df.columns = df.columns.str.strip()
print(f"\nColumns: {df.columns.tolist()}")
print(f"Total rows loaded: {len(df)}")

# Keep only rows with all 11 core columns
core_cols = [
    "round", "match_id", "home_team", "away_team",
    "score_final_dom", "score_final_ext",
    "nb_buts_total", "nb_buts_dom", "nb_buts_ext",
    "victoire", "cycle",
]
df = df[core_cols].copy()

# Drop rows with any NaN in key fields
df.dropna(subset=["home_team", "away_team", "score_final_dom", "score_final_ext", "victoire"], inplace=True)

# Convert numeric columns
for c in ["round", "match_id", "score_final_dom", "score_final_ext", "nb_buts_total", "nb_buts_dom", "nb_buts_ext", "cycle"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

df.dropna(subset=["score_final_dom", "score_final_ext"], inplace=True)
df["score_final_dom"] = df["score_final_dom"].astype(int)
df["score_final_ext"] = df["score_final_ext"].astype(int)
df["nb_buts_total"] = df["nb_buts_total"].astype(int)
df["nb_buts_dom"] = df["nb_buts_dom"].astype(int)
df["nb_buts_ext"] = df["nb_buts_ext"].astype(int)

print(f"Usable rows after cleanup: {len(df)}")

# ============================================================
# 1. BASIC STATS
# ============================================================
print("\n" + "=" * 80)
print("1. BASIC STATISTICS")
print("=" * 80)

all_teams = sorted(set(df["home_team"].unique()) | set(df["away_team"].unique()))
print(f"\nTotal matches: {len(df)}")
print(f"Total unique teams: {len(all_teams)}")
print(f"Round range: {int(df['round'].min())} to {int(df['round'].max())}")
print(f"Cycle range: {int(df['cycle'].min())} to {int(df['cycle'].max())}")

print(f"\nAll teams ({len(all_teams)}):")
for t in all_teams:
    print(f"  - {t}")

# Overall result distribution
dom_wins = (df["victoire"] == "dom").sum()
ext_wins = (df["victoire"] == "ext").sum()
draws = (df["victoire"] == "nul").sum()
total = len(df)
print(f"\nOverall results:")
print(f"  Home wins (dom):  {dom_wins:5d} ({dom_wins/total*100:.1f}%)")
print(f"  Away wins (ext):  {ext_wins:5d} ({ext_wins/total*100:.1f}%)")
print(f"  Draws (nul):      {draws:5d} ({draws/total*100:.1f}%)")

# ============================================================
# 2. PER-TEAM ANALYSIS
# ============================================================
print("\n" + "=" * 80)
print("2. PER-TEAM ANALYSIS")
print("=" * 80)

team_stats = {}

for team in all_teams:
    home = df[df["home_team"] == team]
    away = df[df["away_team"] == team]

    h_total = len(home)
    a_total = len(away)

    if h_total == 0 and a_total == 0:
        continue

    h_wins = (home["victoire"] == "dom").sum()
    h_losses = (home["victoire"] == "ext").sum()
    h_draws = (home["victoire"] == "nul").sum()
    h_goals_scored = home["nb_buts_dom"].sum()
    h_goals_conceded = home["nb_buts_ext"].sum()

    a_wins = (away["victoire"] == "ext").sum()
    a_losses = (away["victoire"] == "dom").sum()
    a_draws = (away["victoire"] == "nul").sum()
    a_goals_scored = away["nb_buts_ext"].sum()
    a_goals_conceded = away["nb_buts_dom"].sum()

    total_matches = h_total + a_total
    total_wins = h_wins + a_wins
    total_losses = h_losses + a_losses
    total_draws = h_draws + a_draws

    team_stats[team] = {
        "home_matches": h_total,
        "home_win_rate": h_wins / h_total * 100 if h_total > 0 else 0,
        "home_loss_rate": h_losses / h_total * 100 if h_total > 0 else 0,
        "home_draw_rate": h_draws / h_total * 100 if h_total > 0 else 0,
        "home_avg_scored": h_goals_scored / h_total if h_total > 0 else 0,
        "home_avg_conceded": h_goals_conceded / h_total if h_total > 0 else 0,
        "away_matches": a_total,
        "away_win_rate": a_wins / a_total * 100 if a_total > 0 else 0,
        "away_loss_rate": a_losses / a_total * 100 if a_total > 0 else 0,
        "away_draw_rate": a_draws / a_total * 100 if a_total > 0 else 0,
        "away_avg_scored": a_goals_scored / a_total if a_total > 0 else 0,
        "away_avg_conceded": a_goals_conceded / a_total if a_total > 0 else 0,
        "total_matches": total_matches,
        "total_win_rate": total_wins / total_matches * 100 if total_matches > 0 else 0,
        "total_draw_rate": total_draws / total_matches * 100 if total_matches > 0 else 0,
    }

# Print full team table
print(f"\n{'Team':<25} {'HM':>4} {'H_W%':>6} {'H_D%':>6} {'H_L%':>6} {'H_GF':>5} {'H_GA':>5} | {'AM':>4} {'A_W%':>6} {'A_D%':>6} {'A_L%':>6} {'A_GF':>5} {'A_GA':>5}")
print("-" * 125)

for team in sorted(team_stats.keys()):
    s = team_stats[team]
    print(f"{team:<25} {s['home_matches']:>4} {s['home_win_rate']:>5.1f}% {s['home_draw_rate']:>5.1f}% {s['home_loss_rate']:>5.1f}% {s['home_avg_scored']:>5.2f} {s['home_avg_conceded']:>5.2f} | {s['away_matches']:>4} {s['away_win_rate']:>5.1f}% {s['away_draw_rate']:>5.1f}% {s['away_loss_rate']:>5.1f}% {s['away_avg_scored']:>5.2f} {s['away_avg_conceded']:>5.2f}")

# ============================================================
# 3. KEY PATTERNS
# ============================================================
print("\n" + "=" * 80)
print("3. KEY PATTERNS - TEAMS WITH >70% HOME WIN RATE")
print("=" * 80)

strong_home = [(t, s) for t, s in team_stats.items() if s["home_win_rate"] > 70 and s["home_matches"] >= 3]
strong_home.sort(key=lambda x: -x[1]["home_win_rate"])
for team, s in strong_home:
    print(f"  {team:<25} Home W%: {s['home_win_rate']:.1f}% ({int(s['home_matches'])} matches, {s['home_avg_scored']:.2f} GF, {s['home_avg_conceded']:.2f} GA)")

print("\n" + "=" * 80)
print("4. KEY PATTERNS - TEAMS WITH <20% AWAY WIN RATE")
print("=" * 80)

weak_away = [(t, s) for t, s in team_stats.items() if s["away_win_rate"] < 20 and s["away_matches"] >= 3]
weak_away.sort(key=lambda x: x[1]["away_win_rate"])
for team, s in weak_away:
    print(f"  {team:<25} Away W%: {s['away_win_rate']:.1f}% ({int(s['away_matches'])} matches, {s['away_avg_scored']:.2f} GF, {s['away_avg_conceded']:.2f} GA)")

print("\n" + "=" * 80)
print("5. KEY PATTERNS - TEAMS WITH VERY HIGH AWAY WIN RATE (>50%)")
print("=" * 80)

strong_away = [(t, s) for t, s in team_stats.items() if s["away_win_rate"] > 50 and s["away_matches"] >= 3]
strong_away.sort(key=lambda x: -x[1]["away_win_rate"])
for team, s in strong_away:
    print(f"  {team:<25} Away W%: {s['away_win_rate']:.1f}% ({int(s['away_matches'])} matches, {s['away_avg_scored']:.2f} GF, {s['away_avg_conceded']:.2f} GA)")

# ============================================================
# 6. GOALS ANALYSIS
# ============================================================
print("\n" + "=" * 80)
print("6. GOALS ANALYSIS")
print("=" * 80)

avg_total_goals = df["nb_buts_total"].mean()
print(f"\nAverage total goals per match: {avg_total_goals:.2f}")
print(f"Average home goals: {df['nb_buts_dom'].mean():.2f}")
print(f"Average away goals: {df['nb_buts_ext'].mean():.2f}")

for g in range(8):
    count = (df["nb_buts_total"] == g).sum()
    pct = count / total * 100
    bar = "#" * int(pct / 2)
    print(f"  {g} goals: {count:5d} ({pct:5.1f}%) {bar}")

low_scoring = (df["nb_buts_total"] <= 1).sum()
print(f"\n% matches with 0-1 goals (low scoring): {low_scoring/total*100:.1f}%")

mid_scoring = ((df["nb_buts_total"] >= 2) & (df["nb_buts_total"] <= 3)).sum()
print(f"% matches with 2-3 goals (mid scoring):  {mid_scoring/total*100:.1f}%")

high_scoring = (df["nb_buts_total"] >= 4).sum()
print(f"% matches with 4+ goals (high scoring):  {high_scoring/total*100:.1f}%")

# Home advantage in goals
print(f"\nHome teams outscore away teams in {(df['nb_buts_dom'] > df['nb_buts_ext']).sum() / total * 100:.1f}% of matches")
print(f"Away teams outscore home teams in {(df['nb_buts_ext'] > df['nb_buts_dom']).sum() / total * 100:.1f}% of matches")
print(f"Goals are equal in {(df['nb_buts_dom'] == df['nb_buts_ext']).sum() / total * 100:.1f}% of matches")

# ============================================================
# 7. SCORING PATTERNS (First half vs Second half)
# ============================================================
print("\n" + "=" * 80)
print("7. SCORING PATTERNS - FIRST HALF vs SECOND HALF")
print("=" * 80)

first_half = df["nb_buts_dom"].sum() + df["nb_buts_ext"].sum()
second_half_goals = df["nb_buts_total"].sum() - first_half
total_goals_all = df["nb_buts_total"].sum()

print(f"Total goals across all matches: {int(total_goals_all)}")
print(f"  First half goals (from nb_buts_dom + nb_buts_ext): {int(first_half)} ({first_half/total_goals_all*100:.1f}%)")
print(f"  Second half goals (remaining from nb_buts_total):  {int(second_half_goals)} ({second_half_goals/total_goals_all*100:.1f}%)")
print(f"\n  Note: The CSV columns nb_buts_dom/nb_buts_ext appear to represent first-half scoring.")
print(f"  Second-half goals = nb_buts_total - (nb_buts_dom + nb_buts_ext)")

# ============================================================
# 8. HEAD-TO-HEAD PATTERNS
# ============================================================
print("\n" + "=" * 80)
print("8. HEAD-TO-HEAD PATTERNS - MOST DOMINANT MATCHUPS")
print("=" * 80)

h2h = defaultdict(lambda: {"home_wins": 0, "away_wins": 0, "draws": 0, "total": 0, "home_goals": 0, "away_goals": 0})

for _, row in df.iterrows():
    h, a = row["home_team"], row["away_team"]
    key = f"{h} vs {a}"
    h2h[key]["total"] += 1
    h2h[key]["home_goals"] += row["nb_buts_dom"]
    h2h[key]["away_goals"] += row["nb_buts_ext"]
    if row["victoire"] == "dom":
        h2h[key]["home_wins"] += 1
    elif row["victoire"] == "ext":
        h2h[key]["away_wins"] += 1
    else:
        h2h[key]["draws"] += 1

# Filter to matchups with at least 3 meetings
min_h2h = 3
h2h_filtered = {k: v for k, v in h2h.items() if v["total"] >= min_h2h}

# Sort by dominance (win% of one side)
h2h_dominant = []
for matchup, stats in h2h_filtered.items():
    total_m = stats["total"]
    home_pct = stats["home_wins"] / total_m * 100
    away_pct = stats["away_wins"] / total_m * 100
    draw_pct = stats["draws"] / total_m * 100
    max_pct = max(home_pct, away_pct, draw_pct)
    winner = ""
    if home_pct == max_pct:
        winner = matchup.split(" vs ")[0] + " (home)"
    elif away_pct == max_pct:
        winner = matchup.split(" vs ")[1] + " (away)"
    else:
        winner = "DRAW"
    h2h_dominant.append((matchup, stats, max_pct, winner))

h2h_dominant.sort(key=lambda x: -x[2])

print(f"\nMatchups with {min_h2h}+ meetings, sorted by dominance:")
print(f"\n{'Matchup':<45} {'#':>3} {'HomeW%':>7} {'AwayW%':>7} {'Draw%':>7} {'H_GF':>5} {'A_GF':>5}")
print("-" * 85)

for matchup, stats, max_pct, winner in h2h_dominant:
    total_m = stats["total"]
    home_pct = stats["home_wins"] / total_m * 100
    away_pct = stats["away_wins"] / total_m * 100
    draw_pct = stats["draws"] / total_m * 100
    print(f"{matchup:<45} {total_m:>3} {home_pct:>6.1f}% {away_pct:>6.1f}% {draw_pct:>6.1f}% {stats['home_goals']:>5} {stats['away_goals']:>5}")

# ============================================================
# 9. ALWAYS-PATTERNS (100% or 0% records)
# ============================================================
print("\n" + "=" * 80)
print("9. PERFECT/MEMORYLESS PATTERNS - TEAMS WITH 100% OR 0% IN CATEGORY")
print("=" * 80)

print("\nTeams that ALWAYS win at home (100% home win rate, min 3 matches):")
for team, s in sorted(team_stats.items(), key=lambda x: -x[1]["home_win_rate"]):
    if s["home_win_rate"] == 100 and s["home_matches"] >= 3:
        print(f"  {team:<25} ({int(s['home_matches'])} home matches)")

print("\nTeams that NEVER win at home (0% home win rate, min 3 matches):")
for team, s in sorted(team_stats.items(), key=lambda x: x[1]["home_win_rate"]):
    if s["home_win_rate"] == 0 and s["home_matches"] >= 3:
        print(f"  {team:<25} ({int(s['home_matches'])} home matches)")

print("\nTeams that ALWAYS win away (100% away win rate, min 3 matches):")
for team, s in sorted(team_stats.items(), key=lambda x: -x[1]["away_win_rate"]):
    if s["away_win_rate"] == 100 and s["away_matches"] >= 3:
        print(f"  {team:<25} ({int(s['away_matches'])} away matches)")

print("\nTeams that NEVER win away (0% away win rate, min 3 matches):")
for team, s in sorted(team_stats.items(), key=lambda x: x[1]["away_win_rate"]):
    if s["away_win_rate"] == 0 and s["away_matches"] >= 3:
        print(f"  {team:<25} ({int(s['away_matches'])} away matches)")

print("\nTeams that ALWAYS draw when at home (100% home draw rate, min 3 matches):")
for team, s in sorted(team_stats.items(), key=lambda x: -x[1]["home_draw_rate"]):
    if s["home_draw_rate"] == 100 and s["home_matches"] >= 3:
        print(f"  {team:<25} ({int(s['home_matches'])} home matches)")

print("\nTeams that NEVER draw when at home (0% home draw rate, min 3 matches):")
for team, s in sorted(team_stats.items(), key=lambda x: x[1]["home_draw_rate"]):
    if s["home_draw_rate"] == 0 and s["home_matches"] >= 3:
        print(f"  {team:<25} ({int(s['home_matches'])} home matches)")

# ============================================================
# 10. HEAD-TO-HEAD: ALWAYS WIN / ALWAYS DRAW
# ============================================================
print("\n" + "=" * 80)
print("10. HEAD-TO-HEAD: 100% DOMINANCE MATCHUPS")
print("=" * 80)

print(f"\nMatchups where home team ALWAYS wins (min {min_h2h} meetings):")
for matchup, stats, max_pct, winner in h2h_dominant:
    total_m = stats["total"]
    if stats["home_wins"] == total_m and total_m >= min_h2h:
        print(f"  {matchup:<45} ({total_m} matches)")

print(f"\nMatchups where away team ALWAYS wins (min {min_h2h} meetings):")
for matchup, stats, max_pct, winner in h2h_dominant:
    total_m = stats["total"]
    if stats["away_wins"] == total_m and total_m >= min_h2h:
        print(f"  {matchup:<45} ({total_m} matches)")

print(f"\nMatchups that ALWAYS draw (min {min_h2h} meetings):")
for matchup, stats, max_pct, winner in h2h_dominant:
    total_m = stats["total"]
    if stats["draws"] == total_m and total_m >= min_h2h:
        print(f"  {matchup:<45} ({total_m} matches)")

# ============================================================
# 11. CYCLE ANALYSIS
# ============================================================
print("\n" + "=" * 80)
print("11. CYCLE ANALYSIS (tournament rounds)")
print("=" * 80)

for cycle in sorted(df["cycle"].dropna().unique()):
    c = int(cycle)
    cycle_df = df[df["cycle"] == c]
    cw = (cycle_df["victoire"] == "dom").sum()
    ca = (cycle_df["victoire"] == "ext").sum()
    cd = (cycle_df["victoire"] == "nul").sum()
    ct = len(cycle_df)
    if ct > 0:
        print(f"  Cycle {c}: {ct} matches | Home wins: {cw} ({cw/ct*100:.1f}%) | Away wins: {ca} ({ca/ct*100:.1f}%) | Draws: {cd} ({cd/ct*100:.1f}%)")

# ============================================================
# 12. TOP/BOTTOM TEAMS BY OVERALL WIN RATE
# ============================================================
print("\n" + "=" * 80)
print("12. OVERALL WIN RATE RANKINGS (min 10 total matches)")
print("=" * 80)

qualified = [(t, s) for t, s in team_stats.items() if s["total_matches"] >= 10]
qualified.sort(key=lambda x: -x[1]["total_win_rate"])

print(f"\n{'Rank':<5} {'Team':<25} {'Matches':>7} {'Win%':>6} {'Draw%':>6} {'Loss%':>6}")
print("-" * 65)
for i, (team, s) in enumerate(qualified, 1):
    loss_pct = 100 - s["total_win_rate"] - s["total_draw_rate"]
    print(f"{i:<5} {team:<25} {s['total_matches']:>7} {s['total_win_rate']:>5.1f}% {s['total_draw_rate']:>5.1f}% {loss_pct:>5.1f}%")

# ============================================================
# 13. SYMMETRIC MATCHUP ANALYSIS (A vs B and B vs A)
# ============================================================
print("\n" + "=" * 80)
print("13. SYMMETRIC MATCHUP PATTERNS (both A@home vs B AND B@home vs A)")
print("=" * 80)

teams_in_h2h = set()
for matchup in h2h:
    parts = matchup.split(" vs ")
    teams_in_h2h.add(parts[0])
    teams_in_h2h.add(parts[1])

symmetric_found = False
checked = set()
for t1 in teams_in_h2h:
    for t2 in teams_in_h2h:
        if t1 == t2:
            continue
        key_ab = f"{t1} vs {t2}"
        key_ba = f"{t2} vs {t1}"
        pair = tuple(sorted([t1, t2]))
        if pair in checked:
            continue
        checked.add(pair)

        if key_ab in h2h and key_ba in h2h:
            symmetric_found = True
            ab = h2h[key_ab]
            ba = h2h[key_ba]
            ab_total = ab["total"]
            ba_total = ba["total"]
            print(f"\n  {t1} (home) vs {t2}: {ab_total} matches | H_W: {ab['home_wins']}/{ab_total} | A_W: {ab['away_wins']}/{ab_total} | Draw: {ab['draws']}/{ab_total}")
            print(f"  {t2} (home) vs {t1}: {ba_total} matches | H_W: {ba['home_wins']}/{ba_total} | A_W: {ba['away_wins']}/{ba_total} | Draw: {ba['draws']}/{ba_total}")
            print(f"  Combined: {ab_total + ba_total} matches | {t1} total W: {ab['home_wins'] + ba['away_wins']}/{ab_total + ba_total} ({(ab['home_wins'] + ba['away_wins'])/(ab_total + ba_total)*100:.1f}%) | {t2} total W: {ba['home_wins'] + ab['away_wins']}/{ab_total + ba_total} ({(ba['home_wins'] + ab['away_wins'])/(ab_total + ba_total)*100:.1f}%)")

if not symmetric_found:
    print("  No symmetric matchups found.")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
