import json
import os
from collections import defaultdict

def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def merge_rounds(main, backup):
    rounds = {}
    for entry in main:
        r = entry.get("round")
        if r is not None:
            rounds[r] = entry
    for entry in backup:
        r = entry.get("round")
        if r is not None and r not in rounds:
            rounds[r] = entry
    return sorted(rounds.values(), key=lambda x: x.get("round", 0))

def get_resolved_matches(all_rounds):
    matches = []
    for entry in all_rounds:
        rnd = entry.get("round", 0)
        for pred in entry.get("predictions", []):
            has_result = pred.get("has_result", False)
            actual_score_dom = pred.get("actual_score_dom")
            actual_score_ext = pred.get("actual_score_ext")
            if not has_result and actual_score_dom is None:
                continue
            if actual_score_dom is None or actual_score_ext is None:
                continue
            total_goals = pred.get("actual_total")
            if total_goals is None:
                total_goals = actual_score_dom + actual_score_ext
            actual_ou = "Over 2.5" if total_goals > 2.5 else "Under 2.5"
            pred_ou = pred.get("ou_pred", "")
            if not pred_ou:
                continue
            matches.append({
                "round": rnd,
                "home_team": pred.get("home_team", "?"),
                "away_team": pred.get("away_team", "?"),
                "score_pred": pred.get("score_pred", ""),
                "score_dom": pred.get("score_dom"),
                "score_ext": pred.get("score_ext"),
                "actual_score_dom": actual_score_dom,
                "actual_score_ext": actual_score_ext,
                "total_goals": total_goals,
                "ou_pred": pred_ou,
                "ou_confidence": pred.get("ou_confidence", 0),
                "prob_over_25": pred.get("prob_over_25", 0),
                "prob_under_25": pred.get("prob_under_25", 0),
                "total_buts_pred": pred.get("total_buts_pred", 0),
                "result_res_code": pred.get("res_code", ""),
                "ml_pred_1x2": pred.get("ml_pred_1x2", ""),
            })
    return matches

def analyze_ou(matches):
    print("=" * 70)
    print("  ANALYSE O/U 2.5 - CAF VIRTUAL FOOTBALL PREDICTIONS")
    print("=" * 70)
    print()

    total_matches = len(matches)
    print(f"Total matchs avec resultat: {total_matches}")
    print()

    # --- A. Overall O/U accuracy ---
    correct = 0
    incorrect = 0
    for m in matches:
        actual_ou = "Over 2.5" if m["total_goals"] > 2.5 else "Under 2.5"
        if m["ou_pred"] == actual_ou:
            correct += 1
        else:
            incorrect += 1

    overall_acc = correct / total_matches * 100 if total_matches > 0 else 0
    print(f"{'='*70}")
    print("  A. PRECISION O/U 2.5 GLOBALE")
    print(f"{'='*70}")
    print(f"  Correct: {correct}/{total_matches} ({overall_acc:.1f}%)")
    print(f"  Incorrect: {incorrect}/{total_matches} ({100-overall_acc:.1f}%)")
    print()

    # --- B. Breakdown by Over vs Under ---
    over_preds = [m for m in matches if m["ou_pred"] == "Over 2.5"]
    under_preds = [m for m in matches if m["ou_pred"] == "Under 2.5"]

    over_correct = sum(1 for m in over_preds if m["total_goals"] > 2.5)
    under_correct = sum(1 for m in under_preds if m["total_goals"] <= 2.5)

    over_acc = over_correct / len(over_preds) * 100 if over_preds else 0
    under_acc = under_correct / len(under_preds) * 100 if under_preds else 0

    print(f"{'='*70}")
    print("  B. PRECISION PAR TYPE DE PREDICTION")
    print(f"{'='*70}")
    print(f"  Over 2.5 predictions:  {over_correct}/{len(over_preds)} ({over_acc:.1f}%)")
    print(f"  Under 2.5 predictions: {under_correct}/{len(under_preds)} ({under_acc:.1f}%)")
    print()

    # --- C. Accuracy at different confidence thresholds ---
    print(f"{'='*70}")
    print("  C. PRECISION PAR SEUIL DE CONFIANCE")
    print(f"{'='*70}")
    print(f"  {'Seuil':<10} {'Matchs':<10} {'Correct':<10} {'Accuracy':<10}")
    print(f"  {'-'*40}")
    for threshold in [50, 55, 60, 65, 70, 75, 80]:
        filtered = [m for m in matches if m["ou_confidence"] >= threshold]
        if not filtered:
            continue
        filt_correct = sum(1 for m in filtered if m["ou_pred"] == ("Over 2.5" if m["total_goals"] > 2.5 else "Under 2.5"))
        filt_acc = filt_correct / len(filtered) * 100
        print(f"  >= {threshold}%{'':<6} {len(filtered):<10} {filt_correct:<10} {filt_acc:.1f}%")
    print()

    # --- D. ML vs Poisson agreement ---
    # We check if the prediction was set by hybrid (has ml_pred_1x2) or pure Poisson
    with_ml = [m for m in matches if m.get("ml_pred_1x2")]
    without_ml = [m for m in matches if not m.get("ml_pred_1x2")]

    if with_ml:
        ml_correct = sum(1 for m in with_ml if m["ou_pred"] == ("Over 2.5" if m["total_goals"] > 2.5 else "Under 2.5"))
        ml_acc = ml_correct / len(with_ml) * 100
    else:
        ml_acc = 0
    if without_ml:
        noml_correct = sum(1 for m in without_ml if m["ou_pred"] == ("Over 2.5" if m["total_goals"] > 2.5 else "Under 2.5"))
        noml_acc = noml_correct / len(without_ml) * 100
    else:
        noml_acc = 0

    print(f"{'='*70}")
    print("  D. PRECISION POISSON vs HYBRID (Poisson+ML)")
    print(f"{'='*70}")
    print(f"  Avec ML (hybrid):       {len(with_ml)} matchs, precision: {ml_acc:.1f}%")
    print(f"  Sans ML (pure Poisson): {len(without_ml)} matchs, precision: {noml_acc:.1f}%")
    print()

    # --- E. Average goals ---
    total_goals_all = [m["total_goals"] for m in matches]
    avg_goals = sum(total_goals_all) / len(total_goals_all) if total_goals_all else 0
    avg_pred = sum(m["total_buts_pred"] for m in matches) / len(matches) if matches else 0

    print(f"{'='*70}")
    print("  E. BUTS MOYENS")
    print(f"{'='*70}")
    print(f"  Buts moyens reels:      {avg_goals:.2f}")
    print(f"  Buts moyens predits:    {avg_pred:.2f}")
    print(f"  Ecart:                  {abs(avg_goals - avg_pred):.2f}")
    print()

    # --- F. Distribution of total goals ---
    print(f"{'='*70}")
    print("  F. DISTRIBUTION DES BUTS TOTAUX")
    print(f"{'='*70}")
    dist = defaultdict(int)
    for g in total_goals_all:
        if g >= 5:
            dist[5] += 1
        else:
            dist[g] += 1

    labels = {0: "0 but", 1: "1 but", 2: "2 buts", 3: "3 buts", 4: "4 buts", 5: "5+ buts"}
    for g in range(6):
        count = dist.get(g, 0)
        pct = count / total_matches * 100 if total_matches else 0
        bar = "#" * int(pct / 2)
        print(f"  {labels[g]:<10}: {count:>4} ({pct:>5.1f}%) {bar}")

    over25_count = sum(1 for g in total_goals_all if g > 2.5)
    under25_count = total_matches - over25_count
    print()
    print(f"  Over 2.5 reels:  {over25_count}/{total_matches} ({over25_count/total_matches*100:.1f}%)")
    print(f"  Under 2.5 reels: {under25_count}/{total_matches} ({under25_count/total_matches*100:.1f}%)")
    print()

    # --- G. Per-team O/U accuracy ---
    print(f"{'='*70}")
    print("  G. PRECISION O/U PAR EQUIPE")
    print(f"{'='*70}")

    team_stats = defaultdict(lambda: {"total": 0, "over_matches": 0, "under_matches": 0,
                                       "over_correct": 0, "under_correct": 0})
    for m in matches:
        for team in [m["home_team"], m["away_team"]]:
            ts = team_stats[team]
            ts["total"] += 1
            actual_ou = "Over 2.5" if m["total_goals"] > 2.5 else "Under 2.5"
            if m["ou_pred"] == "Over 2.5":
                ts["over_matches"] += 1
                if actual_ou == "Over 2.5":
                    ts["over_correct"] += 1
            else:
                ts["under_matches"] += 1
                if actual_ou == "Under 2.5":
                    ts["under_correct"] += 1

    # Teams with most matches
    team_list = sorted(team_stats.items(), key=lambda x: x[1]["total"], reverse=True)

    print(f"  {'Equipe':<25} {'Matchs':<8} {'Over':<8} {'Under':<8} {'Acc Over':<10} {'Acc Under':<10} {'Acc Tot':<10}")
    print(f"  {'-'*79}")
    for team, ts in team_list[:25]:
        over_acc = ts["over_correct"] / ts["over_matches"] * 100 if ts["over_matches"] > 0 else 0
        under_acc = ts["under_correct"] / ts["under_matches"] * 100 if ts["under_matches"] > 0 else 0
        total_correct = ts["over_correct"] + ts["under_correct"]
        total_acc = total_correct / ts["total"] * 100 if ts["total"] > 0 else 0
        print(f"  {team:<25} {ts['total']:<8} {ts['over_matches']:<8} {ts['under_matches']:<8} {over_acc:>5.1f}%    {under_acc:>5.1f}%    {total_acc:>5.1f}%")

    # Teams with most Over matches
    print()
    print("  --- Equipes avec le plus de matchs Over 2.5 reels ---")
    team_over_real = defaultdict(int)
    for m in matches:
        if m["total_goals"] > 2.5:
            team_over_real[m["home_team"]] += 1
            team_over_real[m["away_team"]] += 1
    for team, cnt in sorted(team_over_real.items(), key=lambda x: x[1], reverse=True)[:15]:
        ts = team_stats[team]
        real_over_pct = cnt / ts["total"] * 100 if ts["total"] > 0 else 0
        print(f"  {team:<25}: {cnt} Over reels ({real_over_pct:.0f}% de {ts['total']} matchs)")

    # Teams with most Under matches
    print()
    print("  --- Equipes avec le plus de matchs Under 2.5 reels ---")
    team_under_real = defaultdict(int)
    for m in matches:
        if m["total_goals"] <= 2.5:
            team_under_real[m["home_team"]] += 1
            team_under_real[m["away_team"]] += 1
    for team, cnt in sorted(team_under_real.items(), key=lambda x: x[1], reverse=True)[:15]:
        ts = team_stats[team]
        real_under_pct = cnt / ts["total"] * 100 if ts["total"] > 0 else 0
        print(f"  {team:<25}: {cnt} Under reels ({real_under_pct:.0f}% de {ts['total']} matchs)")

    # --- H. Calibration analysis ---
    print()
    print(f"{'='*70}")
    print("  H. ANALYSE DE CALIBRATION (prob_over_25 vs realisation)")
    print(f"{'='*70}")
    bins = [(0, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 100)]
    print(f"  {'Range prob':<15} {'Nb matchs':<12} {'Real Over%':<12} {'Pred moy%':<12}")
    print(f"  {'-'*51}")
    for lo, hi in bins:
        bin_matches = [m for m in matches if lo <= m["prob_over_25"] < hi]
        if not bin_matches:
            continue
        real_over = sum(1 for m in bin_matches if m["total_goals"] > 2.5)
        real_pct = real_over / len(bin_matches) * 100
        avg_pred = sum(m["prob_over_25"] for m in bin_matches) / len(bin_matches)
        print(f"  {lo}-{hi}%{'':<10} {len(bin_matches):<12} {real_pct:>5.1f}%       {avg_pred:>5.1f}%")

    # --- I. Score prediction accuracy context ---
    print()
    print(f"{'='*70}")
    print("  I. CONTEXTE: SCORE PREDIT vs REEL")
    print(f"{'='*70}")
    score_exact = sum(1 for m in matches if m["score_pred"] == f"{m['actual_score_dom']}-{m['actual_score_ext']}")
    print(f"  Score exact correct: {score_exact}/{total_matches} ({score_exact/total_matches*100:.1f}%)")
    score_diff = sum(abs((m["score_dom"] or 0) - m["actual_score_dom"]) + abs((m["score_ext"] or 0) - m["actual_score_ext"]) for m in matches)
    print(f"  Ecart moyen de buts: {score_diff/total_matches:.2f}")
    print()

    # --- J. Round range ---
    rounds = sorted(set(m["round"] for m in matches))
    print(f"  Rounds couverts: {rounds[0]} a {rounds[-1]} ({len(rounds)} rounds)")

if __name__ == "__main__":
    main_file = r"D:\Documents\261CAF\historique_predictions.json"
    bak_file = r"D:\Documents\261CAF\historique_predictions.json.bak"

    main_data = load_json(main_file)
    bak_data = load_json(bak_file)

    print(f"Main file: {len(main_data)} rounds")
    print(f"Bak file:  {len(bak_data)} rounds")

    all_rounds = merge_rounds(main_data, bak_data)
    print(f"Merged:    {len(all_rounds)} rounds (dedup by round)")
    print()

    matches = get_resolved_matches(all_rounds)
    analyze_ou(matches)
