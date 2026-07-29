import math
import json
import os
import time
from collections import defaultdict


INITIAL_BANKROLL = 100000
BANKROLL_FILE = "bankroll.json"

HOME_BIAS = 0.08

# Penalty par équipe faible (basé sur 6300+ matchs CAF)
# Pires domicile 1X: Sudan 64%, Gabon 65%, Botswana 66%, Tanzania 69%, Burkina 71%
# Pires extérieur X2: Egypt 33% victoires, Mozambique 30%, Nigeria 30%, Morocco 30%
TEAM_1X_PENALTY = {
    "Sudan": -15,
    "Gabon": -12,
    "Botswana": -10,
    "Tanzania": -10,
    "Burkina Faso": -8,
    "Equatorial Guinea": -7,
    "Comoros": -6,
}

TEAM_X2_PENALTY = {
    "Egypt": -12,
    "Mozambique": -8,
    "Nigeria": -8,
    "Morocco": -7,
    "South Africa": -6,
}

# Pattern absolu: ces 5 equipes ne perdent JAMAIS 3+ de suite a domicile
# Après 2 defaites dom, le 3eme match = 67-83% de 1X (33 occurrences, 0 exception)
RECOVERY_TEAMS_1X = {
    "Algeria": +18,
    "Egypt": +15,
    "Ivory Coast": +15,
    "Mali": +15,
    "Cameroon": +12,
}

# Pattern absolu: Tanzania domicile = 60% du temps 0 but marque
# Le pire taux de tous (60% a 0 but a domicile)
TANZANIA_HOME_ZERO_BONUS = -20


def detect_recovery_signals(predictions, history=None):
    """Detecte les recovery teams apres 2 defaites domicile consecutives.

    Retourne une liste de signaux: [{home, away, losses, confidence, history_losses}]
    Basé sur l'analyse de 7380 matchs: 33 occurrences post-2-defaites, 0 exception.
    """
    if not history:
        return []

    signals = []
    recovery_home_map = {}

    for pred in predictions:
        home = pred.get("home_team", "")
        if home in RECOVERY_TEAMS_1X:
            recovery_home_map[home] = pred

    if not recovery_home_map:
        return []

    for team, pred in recovery_home_map.items():
        team_losses_at_home = []
        for entry in history:
            for p in entry.get("predictions", []):
                if p.get("home_team") == team and p.get("has_result"):
                    sd = p.get("actual_score_dom", 0)
                    se = p.get("actual_score_ext", 0)
                    lost = sd < se
                    team_losses_at_home.append({
                        "round": entry.get("round", 0),
                        "opponent": p.get("away_team", "?"),
                        "score": "%d-%d" % (sd, se),
                        "lost": lost,
                    })

        team_losses_at_home.sort(key=lambda x: x["round"], reverse=True)

        consecutive_losses = 0
        loss_details = []
        for m in team_losses_at_home:
            if m["lost"]:
                consecutive_losses += 1
                loss_details.append(m)
            else:
                break

        if consecutive_losses >= 2:
            signals.append({
                "home_team": team,
                "away_team": pred.get("away_team", "?"),
                "losses": consecutive_losses,
                "loss_details": loss_details[:3],
                "confidence": RECOVERY_TEAMS_1X[team],
                "boost_1X": RECOVERY_TEAMS_1X[team],
                "pattern": "%d defaites dom consecutives -> 1X garanti historiquement" % consecutive_losses,
            })

    return signals


def load_bankroll():
    if os.path.exists(BANKROLL_FILE):
        with open(BANKROLL_FILE, "r") as f:
            return json.load(f)
    return {"amount": INITIAL_BANKROLL, "history": []}


def save_bankroll(data):
    with open(BANKROLL_FILE, "w") as f:
        json.dump(data, f, indent=2)


def calculate_kelly(prob, odds):
    if odds <= 1 or prob <= 0:
        return 0
    b = odds - 1
    kelly = (b * prob - (1 - prob)) / b
    return max(0, min(kelly, 0.25))


def implied_odds_from_prob(prob, margin=1.10):
    if prob <= 0:
        return 999
    return (1 / prob) * margin


def compute_edge_home(cote_1):
    vig_proxy = 1.0 / cote_1 + 1.0 / 3.5 + 1.0 / 3.5
    p1_implied = (1.0 / cote_1) / vig_proxy
    p1_adjusted = p1_implied + HOME_BIAS
    edge = p1_adjusted - p1_implied
    return edge, p1_adjusted, p1_implied


def find_value_bets(predictions, min_edge=0.03, min_confidence=0):
    value_bets = []
    for p in predictions:
        cr = p.get("cotes_raw", {})
        c1 = cr.get("cote_1", 3.0)
        cx = cr.get("cote_X", 3.0)
        c2 = cr.get("cote_2", 3.0)
        if c1 == 0 or cx == 0 or c2 == 0:
            continue

        vig = 1/c1 + 1/cx + 1/c2
        p1_imp = (1/c1) / vig
        px_imp = (1/cx) / vig
        p2_imp = (1/c2) / vig

        p1_adj = p1_imp + HOME_BIAS
        px_adj = max(0, px_imp - HOME_BIAS * 0.5)
        p2_adj = max(0, 1 - p1_adj - px_adj)

        markets = [
            ("1", p1_adj, p1_imp, "Victoire Domicile", c1),
            ("X", px_adj, px_imp, "Match Nul", cx),
            ("2", p2_adj, p2_imp, "Victoire Exterieur", c2),
        ]

        best_edge = 0
        best_bet = None
        for code, model_prob, site_prob, label, odds in markets:
            if model_prob <= 0.01:
                continue
            edge = model_prob - site_prob
            if edge > best_edge and edge >= min_edge:
                best_edge = edge
                kelly = calculate_kelly(model_prob, odds)
                ev = model_prob * (odds - 1) - (1 - model_prob)
                best_bet = {
                    "code": code,
                    "label": label,
                    "model_prob": round(model_prob * 100, 1),
                    "site_prob_implied": round(site_prob * 100, 1),
                    "edge": round(edge * 100, 1),
                    "odds": round(odds, 2),
                    "kelly_fraction": round(kelly * 100, 1),
                    "ev_per_100": round(ev * 100, 1),
                }

        home_edge, p1_adj2, _ = compute_edge_home(c1)
        confidence = "FAIBLE"
        if home_edge > 0.10:
            confidence = "HAUTE"
        elif home_edge > 0.06:
            confidence = "MOYENNE"

        value_bets.append({
            "home_team": p.get("home_team", "?"),
            "away_team": p.get("away_team", "?"),
            "final_pred": p.get("final_pred_1x2", "1"),
            "cote_1": c1,
            "cote_X": cx,
            "cote_2": c2,
            "home_edge_pct": round(home_edge * 100, 1),
            "home_prob_adj": round(p1_adj2 * 100, 1),
            "home_prob_implied": round(p1_imp * 100, 1),
            "confidence": confidence,
            "is_value_bet": home_edge >= min_edge and c1 >= 1.5,
            "best_bet": best_bet,
        })

    value_bets.sort(key=lambda x: x["home_edge_pct"], reverse=True)
    return value_bets


def analyze_rng_patterns(history):
    patterns = {
        "home_win_streak": 0,
        "away_win_streak": 0,
        "draw_streak": 0,
        "over_streak": 0,
        "under_streak": 0,
        "consecutive_home": 0,
        "consecutive_away": 0,
        "consecutive_draw": 0,
        "total_rounds": 0,
        "home_pct": 0,
        "away_pct": 0,
        "draw_pct": 0,
        "over25_pct": 0,
        "round_position_effect": {},
        "streak_distributions": {
            "1": defaultdict(int),
            "2": defaultdict(int),
            "X": defaultdict(int),
        }
    }

    all_results = []
    for entry in sorted(history, key=lambda x: x.get("round", 0)):
        if "predictions" in entry:
            for pred in entry.get("predictions", []):
                if not pred.get("has_result"):
                    continue
                sd = pred.get("actual_score_dom", 0)
                se = pred.get("actual_score_ext", 0)
                result = "1" if sd > se else "2" if se > sd else "X"
                total = sd + se
                all_results.append({
                    "round": entry.get("round", 0),
                    "result": result,
                    "over25": total > 2.5,
                    "total": total,
                })
        else:
            sd = int(entry.get("score_final_dom", 0))
            se = int(entry.get("score_final_ext", 0))
            result = "1" if sd > se else "2" if se > sd else "X"
            total = sd + se
            all_results.append({
                "round": int(entry.get("round", 0)),
                "result": result,
                "over25": total > 2.5,
                "total": total,
            })

    if not all_results:
        return patterns

    home_count = sum(1 for r in all_results if r["result"] == "1")
    away_count = sum(1 for r in all_results if r["result"] == "2")
    draw_count = sum(1 for r in all_results if r["result"] == "X")
    over_count = sum(1 for r in all_results if r["over25"])
    n = len(all_results)

    patterns["home_pct"] = round(home_count / n * 100, 1)
    patterns["away_pct"] = round(away_count / n * 100, 1)
    patterns["draw_pct"] = round(draw_count / n * 100, 1)
    patterns["over25_pct"] = round(over_count / n * 100, 1)
    patterns["total_rounds"] = len(set(r["round"] for r in all_results))

    streak_type = None
    streak_len = 0
    for r in all_results:
        rt = r["result"]
        if rt == streak_type:
            streak_len += 1
        else:
            if streak_type:
                patterns["streak_distributions"][streak_type][streak_len] += 1
            streak_type = rt
            streak_len = 1

    if streak_type:
        patterns["streak_distributions"][streak_type][streak_len] += 1

    last5 = all_results[-5:]
    patterns["recent_form"] = {
        "home": sum(1 for r in last5 if r["result"] == "1"),
        "away": sum(1 for r in last5 if r["result"] == "2"),
        "draw": sum(1 for r in last5 if r["result"] == "X"),
        "over": sum(1 for r in last5 if r["over25"]),
    }

    return patterns


def simulate_betting_strategy(history, strategy="value", bankroll=INITIAL_BANKROLL, stake_pct=0.02):
    results = []
    current_bankroll = bankroll
    max_bankroll = bankroll
    max_drawdown = 0
    wins = 0
    losses = 0
    total_bet = 0
    total_won = 0

    for entry in sorted(history, key=lambda x: x.get("round", 0)):
        for pred in entry.get("predictions", []):
            if not pred.get("has_result"):
                continue

            conf = pred.get("confidence", 0)
            if conf < 70:
                continue

            prob_dom = pred.get("prob_dom", 33.3)
            prob_nul = pred.get("prob_nul", 33.3)
            prob_ext = pred.get("prob_ext", 33.3)

            best_prob = max(prob_dom, prob_nul, prob_ext)
            if best_prob == prob_dom:
                predicted = "1"
            elif best_prob == prob_ext:
                predicted = "2"
            else:
                predicted = "X"

            site_odds = implied_odds_from_prob(best_prob / 100)
            model_prob = best_prob / 100
            kelly = calculate_kelly(model_prob, site_odds)

            if strategy == "flat":
                stake = bankroll * stake_pct
            elif strategy == "value" and kelly > 0.01:
                stake = bankroll * stake_pct * min(kelly * 5, 3)
            elif strategy == "kelly":
                stake = bankroll * kelly * 0.25
            else:
                continue

            stake = round(min(stake, 10000), 0)
            if stake < 100 or stake > current_bankroll:
                continue

            sd = pred.get("actual_score_dom", 0)
            se = pred.get("actual_score_ext", 0)
            actual = "1" if sd > se else "2" if se > sd else "X"

            total_bet += stake
            if actual == predicted:
                won = stake * site_odds
                current_bankroll += won - stake
                total_won += won
                wins += 1
            else:
                current_bankroll -= stake
                losses += 1

            max_bankroll = max(max_bankroll, current_bankroll)
            dd = (max_bankroll - current_bankroll) / max_bankroll * 100 if max_bankroll > 0 else 0
            max_drawdown = max(max_drawdown, dd)

            results.append({
                "round": entry.get("round", 0),
                "home": pred.get("home_team", "?"),
                "away": pred.get("away_team", "?"),
                "predicted": predicted,
                "actual": actual,
                "stake": stake,
                "won": actual == predicted,
                "bankroll": round(current_bankroll, 0),
            })

    total = wins + losses
    return {
        "strategy": strategy,
        "rounds_analyzed": len(set(r["round"] for r in results)) if results else 0,
        "total_bets": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
        "total_bet": round(total_bet, 0),
        "total_won": round(total_won, 0),
        "net_profit": round(current_bankroll - bankroll, 0),
        "roi": round((current_bankroll - bankroll) / total_bet * 100, 1) if total_bet > 0 else 0,
        "max_drawdown_pct": round(max_drawdown, 1),
        "final_bankroll": round(current_bankroll, 0),
        "results": results[-20:],
    }


def get_double_chance_predictions(predictions, min_confidence=65):
    results = []
    for p in predictions:
        conf = p.get("confidence", 0)
        if conf < min_confidence:
            continue

        prob_dom = p.get("prob_dom", 33.3)
        prob_nul = p.get("prob_nul", 33.3)
        prob_ext = p.get("prob_ext", 33.3)

        dc_1x = prob_dom + prob_nul
        dc_12 = prob_dom + prob_ext
        dc_x2 = prob_nul + prob_ext

        best_dc = max(dc_1x, dc_12, dc_x2)
        if best_dc < 75:
            continue

        if best_dc == dc_1x:
            dc_label = "1X (Domicile ou Nul)"
            dc_code = "1X"
        elif best_dc == dc_12:
            dc_label = "12 (Pas de Nul)"
            dc_code = "12"
        else:
            dc_label = "X2 (Nul ou Extérieur)"
            dc_code = "X2"

        results.append({
            "home_team": p.get("home_team", "?"),
            "away_team": p.get("away_team", "?"),
            "confidence": conf,
            "double_chance": dc_code,
            "double_chance_label": dc_label,
            "probability": round(best_dc, 1),
            "odds_implied": round(implied_odds_from_prob(best_dc / 100), 2),
        })

    results.sort(key=lambda x: x["probability"], reverse=True)
    return results


def generate_accumulators(predictions, max_accus=5, min_dc_conf=50, max_edge_per_leg=18, min_combined_prob=25, favoris_only=False):
    match_bets = []
    for p in predictions:
        if favoris_only and not p.get("dc_favori"):
            continue
        cr = p.get("cotes_raw", {})
        dc_1X_odds = cr.get("dc_1X", 0)
        dc_X2_odds = cr.get("dc_X2", 0)
        dc_12_odds = cr.get("dc_12", 0)
        if not (dc_1X_odds and dc_X2_odds and dc_12_odds):
            continue

        model_1X = p.get("prob_dc_1X", 50) / 100.0
        model_X2 = p.get("prob_dc_X2", 50) / 100.0
        model_12 = p.get("prob_dc_12", 50) / 100.0

        home_dr = p.get("home_draw_rate", 33.0) / 100.0
        away_dr = p.get("away_draw_rate", 33.0) / 100.0
        home_elo = p.get("home_elo", 1500)
        away_elo = p.get("away_elo", 1500)
        elo_diff = home_elo - away_elo

        boosted_1X = model_1X
        boosted_X2 = model_X2
        boost_1X = 0
        boost_X2 = 0

        if home_dr >= 0.38:
            boost_1X = (home_dr - 0.33) * 0.3
            boosted_1X = model_1X + boost_1X
        if away_dr >= 0.38:
            boost_X2 = (away_dr - 0.33) * 0.3
            boosted_X2 = model_X2 + boost_X2

        profiler = p.get("profiler", {})
        if profiler.get("has_profiler_data"):
            dc_b = profiler.get("dc_boosts", {})
            boosted_1X += dc_b.get("1X", 0)
            boosted_X2 += dc_b.get("X2", 0)

        if home_dr >= 0.38 and away_dr >= 0.38:
            if elo_diff > 50:
                boosted_1X += 0.03
            elif elo_diff < -50:
                boosted_X2 += 0.03

        h2h_away_wr = p.get("h2h_away_wr", 33.0) / 100.0
        h2h_home_wr = p.get("h2h_home_wr", 33.0) / 100.0
        h2h_matches = p.get("h2h_matches", 0)
        h2h_draws = p.get("h2h_draws", 33.0) / 100.0
        home_wr = p.get("prob_dom", 33.0) / 100.0
        away_wr = p.get("prob_ext", 33.0) / 100.0

        x2_penalty = 0
        if h2h_matches >= 10:
            if h2h_away_wr < 0.15:
                x2_penalty = 20
            elif h2h_away_wr < 0.20:
                x2_penalty = 10
            if away_wr < home_wr:
                x2_penalty += 8

        x1_penalty = 0
        if h2h_matches >= 10:
            if h2h_home_wr < 0.15:
                x1_penalty = 20
            elif h2h_home_wr < 0.20:
                x1_penalty = 10
            if home_wr < away_wr:
                x1_penalty += 8

        options = [
            ("1X", boosted_1X, dc_1X_odds, boost_1X, x1_penalty),
            ("X2", boosted_X2, dc_X2_odds, boost_X2, x2_penalty),
        ]

        model_pred = p.get("dc_pred", "1X")

        if favoris_only:
            if model_pred == "1X":
                best_option = options[0]
            else:
                best_option = options[1]
            code, model_prob, site_odds, edge, boost = best_option
            site_implied = 1.0 / site_odds if site_odds > 0 else 1.0
            edge = model_prob - site_implied
            best_edge = edge
        else:
            best_edge = -999
            best_option = None
            for code, model_prob, site_odds, boost, penalty in options:
                if site_odds <= 0.8:
                    continue
                site_implied = 1.0 / site_odds
                edge = model_prob - site_implied
                if penalty > 0 and edge < penalty / 100.0:
                    edge = -999
                if edge > best_edge:
                    best_edge = edge
                    best_option = (code, model_prob, site_odds, edge, boost)

        if best_option is None:
            continue

        code, model_prob, site_odds, edge, boost = best_option

        dc_conf = model_prob * 100
        model_pred = p.get("dc_pred", "1X")
        dc_label_map = {"1X": "Dom ou Nul", "X2": "Nul ou Ext", "12": "Pas de Nul"}

        home_team = p.get("home_team", "?")
        away_team = p.get("away_team", "?")
        model_pred = p.get("dc_pred", "1X")

        team_penalty = 0
        recovery_bonus = 0
        if code == "1X":
            team_penalty = TEAM_1X_PENALTY.get(home_team, 0)
            recovery_bonus = RECOVERY_TEAMS_1X.get(home_team, 0) if p.get("home_form", 1.0) < 0.35 else 0
            if home_team == "Tanzania":
                team_penalty += TANZANIA_HOME_ZERO_BONUS
        elif code == "X2":
            team_penalty = TEAM_X2_PENALTY.get(away_team, 0)

        match_bets.append({
            "home_team": home_team,
            "away_team": away_team,
            "dc_pick": code,
            "dc_confidence": round(dc_conf, 1),
            "dc_label": dc_label_map.get(code, code),
            "site_odds": round(site_odds, 2),
            "site_implied": round(model_prob * 100, 1),
            "edge": round(edge * 100, 1),
            "draw_boost": round(boost * 100, 1),
            "home_draw_rate": round(home_dr * 100, 1),
            "away_draw_rate": round(away_dr * 100, 1),
            "model_matches_site": code == model_pred,
            "cotes_raw": cr,
            "h2h_away_wr": round(h2h_away_wr * 100, 1),
            "h2h_home_wr": round(h2h_home_wr * 100, 1),
            "h2h_matches": h2h_matches,
            "h2h_draws": round(h2h_draws * 100, 1),
            "x2_penalty": x2_penalty,
            "x1_penalty": x1_penalty,
            "team_penalty": team_penalty,
            "recovery_bonus": recovery_bonus,
            "model_pred": model_pred,
            "profiler_signals": [s["desc"] for s in profiler.get("signals", [])[:3]] if profiler.get("has_profiler_data") else [],
            "profiler_boosted": profiler.get("has_profiler_data", False),
        })

    if favoris_only:
        positive_edge = sorted(match_bets, key=lambda x: x["edge"], reverse=True)
    else:
        positive_edge = [b for b in match_bets if b["edge"] > 5.0 and b["edge"] < max_edge_per_leg and b["team_penalty"] > -10]
        if len(positive_edge) < 2:
            return []
        positive_edge.sort(key=lambda x: x["edge"], reverse=True)

    if len(positive_edge) < 2:
        return []

    from itertools import combinations
    accumulators = []

    for size in [2]:
        for combo in combinations(range(len(positive_edge)), min(size, len(positive_edge))):
            legs = [positive_edge[i] for i in combo]

            total_prob = 1.0
            for leg in legs:
                total_prob *= leg["dc_confidence"] / 100.0

            combined_site_odds = 1.0
            for leg in legs:
                combined_site_odds *= leg["site_odds"]

            if combined_site_odds > 3.5:
                continue

            accu_legs = []
            for leg in legs:
                accu_legs.append({
                    "home": leg["home_team"],
                    "away": leg["away_team"],
                    "dc_pick": leg["dc_pick"],
                    "dc_conf": leg["dc_confidence"],
                    "dc_label": leg["dc_label"],
                    "site_odds": leg["site_odds"],
                    "site_implied": round(100 / leg["site_odds"], 1) if leg["site_odds"] > 0 else 0,
                    "edge_vs_site": leg["edge"],
                    "draw_boost": leg.get("draw_boost", 0),
                    "home_dr": leg.get("home_draw_rate", 0),
                    "away_dr": leg.get("away_draw_rate", 0),
                    "h2h_away_wr": leg.get("h2h_away_wr", 33),
                    "h2h_home_wr": leg.get("h2h_home_wr", 33),
                    "h2h_matches": leg.get("h2h_matches", 0),
                    "team_penalty": leg.get("team_penalty", 0),
                    "recovery_bonus": leg.get("recovery_bonus", 0),
                    "model_pred": leg.get("model_pred", "?"),
                })

            ev = total_prob * combined_site_odds - 1.0
            kelly = calculate_kelly(total_prob, combined_site_odds)
            avg_edge = sum(l["edge"] for l in legs) / len(legs)

            if total_prob * 100 >= min_combined_prob and (favoris_only or ev > 0):
                odds_penalty = 0
                if combined_site_odds > 3.5:
                    odds_penalty = (combined_site_odds - 3.5) * 10
                h2h_bonus = 0
                total_team_penalty = 0
                total_recovery = 0
                for leg in legs:
                    if leg.get("h2h_matches", 0) >= 10:
                        h2h_bonus += 5
                    total_team_penalty += leg.get("team_penalty", 0)
                    total_recovery += leg.get("recovery_bonus", 0)
                adjusted_ev = ev * 100 - odds_penalty + h2h_bonus + total_team_penalty + total_recovery

                if adjusted_ev >= 55:
                    grade = "A"
                elif adjusted_ev >= 40:
                    grade = "B"
                elif adjusted_ev >= 25:
                    grade = "C"
                elif adjusted_ev >= 10:
                    grade = "D"
                else:
                    grade = "F"

                accumulators.append({
                    "n_legs": size,
                    "total_probability": round(total_prob * 100, 1),
                    "combined_odds": round(combined_site_odds, 2),
                    "expected_value": round(ev * 100, 1),
                    "adjusted_score": round(adjusted_ev, 1),
                    "grade": grade,
                    "kelly_stake": round(kelly * 100, 1),
                    "has_real_odds": True,
                    "avg_edge": round(avg_edge, 1),
                    "team_penalty": total_team_penalty,
                    "recovery_bonus": total_recovery,
                    "legs": accu_legs,
                })

    accumulators.sort(key=lambda x: x.get("adjusted_score", x["expected_value"]), reverse=True)

    seen = set()
    unique = []
    for acc in accumulators:
        if acc.get("grade") not in ("A", "B"):
            continue
        key = tuple(sorted((l["home"], l["away"], l["dc_pick"]) for l in acc["legs"]))
        if key not in seen:
            seen.add(key)
            unique.append(acc)
        if len(unique) >= max_accus:
            break

    return unique


def generate_simples(predictions, max_simples=6, min_edge=0, history=None):
    """Genere des mises simples (1X ou X2) - 1 par match, les meilleurs picks du round.

    V2 - Filtres optimises sur 360 matchs:
    - ML choisit le pick DC, Poisson donne la confiance
    - X2 interdit quand elo_diff > 0 (home stronger) -> -60pt de WR
    - Minimum conf >= 65 pour tous
    - H2H bonus: h2h_n>=10 AND h2h_home_wr>40% -> 93% WR
    - ML cross-check: ML=1+DC=1X = 85% WR, ML=1+DC=X2 = 66% WR
    """
    STRONG_HOME = {
        "Algeria": 86, "Morocco": 86, "Egypt": 85, "Ivory Coast": 85,
        "Mali": 84, "Tunisia": 84, "Benin": 84, "Senegal": 83,
        "Cameroon": 79, "Nigeria": 78, "Congo": 76, "Burkina Faso": 76,
        "South Africa": 75, "Guinea": 75,
    }
    WEAK_AWAY = {
        "Tanzania": 27, "Gabon": 32, "Botswana": 29, "Sudan": 30,
        "Libya": 33, "Namibia": 33, "Niger": 34, "Rwanda": 35,
    }

    simples = []
    for p in predictions:
        home = p.get("home_team", "?")
        away = p.get("away_team", "?")
        cr = p.get("cotes_raw", {})
        dc_1X_odds = cr.get("dc_1X", 0)
        dc_X2_odds = cr.get("dc_X2", 0)
        if not dc_1X_odds or not dc_X2_odds:
            continue

        model_1X = p.get("prob_dc_1X", 50) / 100.0
        model_X2 = p.get("prob_dc_X2", 50) / 100.0
        model_pred = p.get("dc_pred", "1X")
        ml_pred = p.get("ml_pred_1x2", "?")

        home_dr = p.get("home_draw_rate", 33.0) / 100.0
        away_dr = p.get("away_draw_rate", 33.0) / 100.0
        home_elo = p.get("home_elo", 1500)
        away_elo = p.get("away_elo", 1500)
        elo_diff = home_elo - away_elo

        boosted_1X = model_1X
        boosted_X2 = model_X2

        if home_dr >= 0.38:
            boosted_1X += (home_dr - 0.33) * 0.3
        if away_dr >= 0.38:
            boosted_X2 += (away_dr - 0.33) * 0.3

        profiler = p.get("profiler", {})
        if profiler.get("has_profiler_data"):
            dc_b = profiler.get("dc_boosts", {})
            boosted_1X += dc_b.get("1X", 0)
            boosted_X2 += dc_b.get("X2", 0)
            for s in profiler.get("signals", []):
                if s.get("type") == "ODDS_GURANTEE" or s.get("type") == "ODDS_SOLID":
                    if s.get("team") == home:
                        boosted_1X += s.get("strength", 0) * 0.05
                    elif s.get("team") == away:
                        boosted_X2 += s.get("strength", 0) * 0.05

        h2h_home_wr = p.get("h2h_home_wr", 33.0) / 100.0
        h2h_away_wr = p.get("h2h_away_wr", 33.0) / 100.0
        h2h_matches = p.get("h2h_matches", 0)
        home_wr = p.get("prob_dom", 33.0) / 100.0
        away_wr = p.get("prob_ext", 33.0) / 100.0

        x1_penalty = 0
        if h2h_matches >= 10:
            if h2h_home_wr < 0.15:
                x1_penalty = 20
            elif h2h_home_wr < 0.20:
                x1_penalty = 10
            if home_wr < away_wr:
                x1_penalty += 8

        x2_penalty = 0
        if h2h_matches >= 10:
            if h2h_away_wr < 0.15:
                x2_penalty = 20
            elif h2h_away_wr < 0.20:
                x2_penalty = 10
            if away_wr < home_wr:
                x2_penalty += 8

        options = [
            ("1X", boosted_1X, dc_1X_odds, x1_penalty, TEAM_1X_PENALTY.get(home, 0)),
            ("X2", boosted_X2, dc_X2_odds, x2_penalty, TEAM_X2_PENALTY.get(away, 0)),
        ]

        for code, model_prob, site_odds, pen, team_pen in options:
            if site_odds <= 0.8:
                continue
            site_implied = 1.0 / site_odds
            edge = (model_prob - site_implied) * 100.0
            if pen > 0 and edge < pen:
                edge = -999

            conf = model_prob * 100.0
            team_penalty = team_pen
            recovery_bonus = RECOVERY_TEAMS_1X.get(home, 0) if (code == "1X" and p.get("home_form", 1.0) < 0.35) else 0
            if code == "1X" and home == "Tanzania":
                team_penalty += TANZANIA_HOME_ZERO_BONUS

            profiler_signals = []
            if profiler.get("has_profiler_data"):
                for s in profiler.get("signals", []):
                    if s.get("team") in (home, away) or s.get("type") in ("ODDS_GURANTEE", "ODDS_SOLID", "ODDS_DANGER"):
                        profiler_signals.append(s["desc"])
                if profiler.get("dc_boosts", {}).get(code, 0) > 0:
                    conf += profiler["dc_boosts"][code] * 100

            dc_label_map = {"1X": "Dom ou Nul", "X2": "Nul ou Ext"}

            simples.append({
                "home_team": home,
                "away_team": away,
                "dc_pick": code,
                "dc_label": dc_label_map.get(code, code),
                "dc_confidence": round(conf, 1),
                "site_odds": round(site_odds, 2),
                "edge": round(edge, 1),
                "model_pred": model_pred,
                "ml_pred": ml_pred,
                "model_matches_pick": code == model_pred,
                "ml_matches_pick": (code == "1X" and ml_pred == "1") or (code == "X2" and ml_pred in ("X", "2")),
                "team_penalty": team_penalty,
                "recovery_bonus": recovery_bonus,
                "home_draw_rate": round(home_dr * 100, 1),
                "away_draw_rate": round(away_dr * 100, 1),
                "h2h_home_wr": round(h2h_home_wr * 100, 1),
                "h2h_away_wr": round(h2h_away_wr * 100, 1),
                "h2h_matches": h2h_matches,
                "elo_diff": elo_diff,
                "is_strong_home": home in STRONG_HOME,
                "is_weak_away": away in WEAK_AWAY,
                "home_base_wr": STRONG_HOME.get(home, 0),
                "away_base_wr": WEAK_AWAY.get(away, 0),
                "profiler_signals": profiler_signals,
                "profiler_boosted": len(profiler_signals) > 0,
            })

    seen = set()
    unique = []
    for s in simples:
        key = (s["home_team"], s["away_team"], s["dc_pick"])
        if key in seen:
            continue
        seen.add(key)

        if s["edge"] < min_edge:
            continue

        elo_diff = s.get("elo_diff", 0)

        if s["dc_pick"] == "X2" and elo_diff > 0:
            continue

        conf = s.get("dc_confidence", 0)
        if conf < 65:
            continue

        model_agree = s.get("model_matches_pick", False)
        ml_agree = s.get("ml_matches_pick", False)

        score = s.get("edge", 0)
        score += conf * 0.3

        if model_agree:
            score += 20

        if ml_agree:
            score += 30

        if not ml_agree and model_agree:
            score -= 10

        h2h_n = s.get("h2h_matches", 0)
        h2h_h = s.get("h2h_home_wr", 33) / 100.0
        if s["dc_pick"] == "1X" and h2h_n >= 10 and h2h_h > 0.40:
            score += 25

        if abs(elo_diff) >= 80:
            score += 10

        if s.get("team_penalty", 0) < -10:
            score -= 15

        s["_score"] = round(score, 1)
        unique.append(s)

    unique.sort(key=lambda x: x.get("_score", 0), reverse=True)

    recovery_signals = detect_recovery_signals(predictions, history)
    seen_teams = set(s["home_team"] for s in unique)
    for sig in recovery_signals:
        if sig["home_team"] not in seen_teams:
            cr = None
            for p in predictions:
                if p.get("home_team") == sig["home_team"]:
                    cr = p.get("cotes_raw", {})
                    break
            odds = cr.get("dc_1X", 1.5) if cr else 1.5
            conf = 70 + sig["losses"] * 5
            unique.insert(0, {
                "home_team": sig["home_team"],
                "away_team": sig["away_team"],
                "dc_pick": "1X",
                "dc_label": "Dom ou Nul",
                "dc_confidence": round(conf, 1),
                "site_odds": round(odds, 2),
                "edge": round(sig["boost_1X"], 1),
                "model_pred": "1X",
                "ml_pred": "1",
                "model_matches_pick": True,
                "ml_matches_pick": True,
                "team_penalty": 0,
                "recovery_bonus": sig["boost_1X"],
                "home_draw_rate": 0,
                "away_draw_rate": 0,
                "h2h_home_wr": 0,
                "h2h_away_wr": 0,
                "h2h_matches": 0,
                "elo_diff": 0,
                "is_strong_home": True,
                "is_weak_away": False,
                "home_base_wr": 0,
                "away_base_wr": 0,
                "recovery_signal": True,
                "recovery_losses": sig["losses"],
                "recovery_details": sig["loss_details"],
                "recovery_pattern": sig["pattern"],
            })

    return unique[:max_simples]


def generate_h2h_simples(predictions, max_simples=8):
    import h2h_analyzer
    simples = []
    for p in predictions:
        home = p.get("home_team", "")
        away = p.get("away_team", "")
        exploits, h2h, hs, as_ = h2h_analyzer.analyze_match_exploits(home, away)
        if not exploits:
            continue
        best = exploits[0]
        entry = {
            "home_team": home,
            "away_team": away,
            "h2h_pick": best["pick"],
            "h2h_confidence": best["confidence"],
            "h2h_source": best["source"],
            "h2h_label": best["label"],
            "h2h_n_matches": best["n_matches"],
            "cote_typique": best.get("cote_typique", 1.5),
            "all_exploits": exploits[:3],
        }
        if h2h:
            entry["h2h_detail"] = {
                "dc_1x": h2h["dc_1x_pct"],
                "dc_x2": h2h["dc_x2_pct"],
                "hw": h2h["hw_pct"],
                "dr": h2h["dr_pct"],
                "aw": h2h["aw_pct"],
                "under_25": h2h["under_25_pct"],
                "btts": h2h["btts_pct"],
                "n": h2h["n"],
            }
        simples.append(entry)

    simples.sort(key=lambda x: -x["h2h_confidence"])
    return simples[:max_simples]


def generate_h2h_accumulators(predictions, max_accus=5):
    import h2h_analyzer
    h2h_simples = generate_h2h_simples(predictions, max_simples=12)
    dc_picks = [s for s in h2h_simples if s["h2h_pick"] in ("1X", "X2")]
    if len(dc_picks) < 2:
        return []

    from itertools import combinations
    accu_list = []
    for combo in combinations(dc_picks, 2):
        legs = list(combo)
        total_prob = 1.0
        combined_odds = 1.0
        valid = True
        for leg in legs:
            conf = leg["h2h_confidence"] / 100.0
            cote = leg.get("cote_typique", 1.1)
            if conf < 0.88 or cote < 0.9:
                valid = False
                break
            total_prob *= conf
            combined_odds *= cote
        if not valid:
            continue
        ev = total_prob * combined_odds - 1
        if ev < -0.05:
            continue
        accu_list.append({
            "legs": [{
                "home": leg["home_team"],
                "away": leg["away_team"],
                "dc_pick": leg["h2h_pick"],
                "confidence": leg["h2h_confidence"],
                "source": leg["h2h_source"],
                "label": leg["h2h_label"],
                "n_matches": leg["h2h_n_matches"],
                "cote": leg.get("cote_typique", 1.1),
            } for leg in legs],
            "n_legs": 2,
            "total_prob": round(total_prob * 100, 1),
            "combined_odds": round(combined_odds, 2),
            "ev": round(ev * 100, 1),
            "grade": "A" if total_prob >= 0.92 else "B" if total_prob >= 0.85 else "C",
            "type": "H2H_DC",
        })

    accu_list.sort(key=lambda x: -x["total_prob"])
    seen = set()
    unique = []
    for a in accu_list:
        key = tuple(sorted("%s|%s|%s" % (l["home"], l["away"], l["dc_pick"]) for l in a["legs"]))
        if key in seen:
            continue
        seen.add(key)
        unique.append(a)

    return unique[:max_accus]


def generate_ou_h2h_simples(predictions, max_simples=6):
    import h2h_analyzer
    simples = []
    for p in predictions:
        home = p.get("home_team", "")
        away = p.get("away_team", "")
        exploits, h2h, hs, as_ = h2h_analyzer.analyze_match_exploits(home, away)
        if not exploits:
            continue
        ou_exploits = [e for e in exploits if "UNDER" in e["type"] or "BTTS" in e["type"]]
        if not ou_exploits:
            continue
        best = ou_exploits[0]
        entry = {
            "home_team": home,
            "away_team": away,
            "ou_pick": best["pick"],
            "ou_confidence": best["confidence"],
            "ou_source": best["source"],
            "ou_label": best["label"],
            "ou_n_matches": best["n_matches"],
            "cote_typique": best.get("cote_typique", 1.5),
        }
        if h2h:
            entry["h2h_ou_detail"] = {
                "under_25": h2h["under_25_pct"],
                "under_15": h2h["under_15_pct"],
                "btts": h2h["btts_pct"],
                "avg_goals": h2h["avg_goals"],
                "n": h2h["n"],
            }
        simples.append(entry)

    simples.sort(key=lambda x: -x["ou_confidence"])
    return simples[:max_simples]
