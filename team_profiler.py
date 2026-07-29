"""
Team Profiler: Analyse individuelle de chaque equipe.
Trouve les patterns de victoire/defaite par equipe, ranges de cotes,
grosses surprises, patterns cycliques, et conditions gagnantes.
"""
import csv
import json
import os
from collections import defaultdict


def load_csv_data(path="donnees_equipes.csv"):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({
                    "round": int(row.get("round", 0)),
                    "match_id": int(row.get("match_id", 0)),
                    "home_team": row.get("home_team", ""),
                    "away_team": row.get("away_team", ""),
                    "score_dom": int(row.get("score_final_dom", 0)),
                    "score_ext": int(row.get("score_final_ext", 0)),
                    "total": int(row.get("nb_buts_total", 0)),
                    "victoire": row.get("victoire", ""),
                    "cycle": row.get("cycle", ""),
                })
            except (ValueError, TypeError):
                continue
    return rows


def load_predictions(path="historique_predictions.json"):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    all_preds = []
    for entry in data:
        rnd = entry.get("round", 0)
        snap = entry.get("playout_snapshot", {})
        for p in entry.get("predictions", []):
            home = p.get("home_team", "")
            away = p.get("away_team", "")
            tk = "%s|%s" % (home, away)
            result = snap.get(tk, {})
            resolved = result.get("_resolved", False)
            cotes_raw = p.get("cotes_raw", {})
            enriched = {
                "round": rnd,
                "home_team": home,
                "away_team": away,
                "match_id": p.get("match_id", 0),
                "cote_1": cotes_raw.get("cote_1", 0),
                "cote_X": cotes_raw.get("cote_X", 0),
                "cote_2": cotes_raw.get("cote_2", 0),
                "dc_1X": cotes_raw.get("dc_1X", 0),
                "dc_X2": cotes_raw.get("dc_X2", 0),
                "dc_12": cotes_raw.get("dc_12", 0),
                "over_25": cotes_raw.get("over_2.5", 0),
                "under_25": cotes_raw.get("under_2.5", 0),
                "btts_oui": cotes_raw.get("btts_oui", 0),
                "btts_non": cotes_raw.get("btts_non", 0),
                "confidence": p.get("confidence", 0),
                "pred_1x2": p.get("pred_1x2") or p.get("res_code", ""),
                "pred_dc": p.get("dc_pred", ""),
                "pred_ou25": p.get("ou_pred", ""),
                "pred_btts": p.get("btts_pred", ""),
                "prob_dom": p.get("prob_dom", 0),
                "prob_nul": p.get("prob_nul", 0),
                "prob_ext": p.get("prob_ext", 0),
                "home_elo": p.get("home_elo", 0),
                "away_elo": p.get("away_elo", 0),
                "home_form": p.get("home_form", 0),
                "away_form": p.get("away_form", 0),
                "home_over25": p.get("home_over25", 0),
                "away_over25": p.get("away_over25", 0),
            }
            if resolved:
                enriched["score_dom"] = result.get("score_dom", 0)
                enriched["score_ext"] = result.get("score_ext", 0)
                enriched["total_actual"] = result.get("total", 0)
                sd = enriched["score_dom"]
                se = enriched["score_ext"]
                enriched["actual_result"] = "1" if sd > se else "X" if sd == se else "2"
                enriched["actual_ou25"] = "Over" if enriched["total_actual"] > 2.5 else "Under"
                enriched["actual_btts"] = "Oui" if (sd > 0 and se > 0) else "Non"
                enriched["actual_dc_1X"] = enriched["actual_result"] in ["1", "X"]
                enriched["actual_dc_X2"] = enriched["actual_result"] in ["X", "2"]
                enriched["actual_dc_12"] = enriched["actual_result"] in ["1", "2"]
                enriched["has_result"] = True
            else:
                enriched["has_result"] = False
            all_preds.append(enriched)
    return all_preds


def get_team_matches(csv_data, team):
    home = []
    away = []
    for m in csv_data:
        if m["home_team"] == team:
            home.append(m)
        elif m["away_team"] == team:
            away.append(m)
    home.sort(key=lambda x: x["round"])
    away.sort(key=lambda x: x["round"])
    return home, away


def get_team_predictions(preds, team):
    as_home = [p for p in preds if p["home_team"] == team and p["has_result"]]
    as_away = [p for p in preds if p["away_team"] == team and p["has_result"]]
    return as_home, as_away


def compute_basic_profile(csv_data, team):
    home_matches, away_matches = get_team_matches(csv_data, team)
    all_matches = home_matches + away_matches

    def calc_stats(matches, label):
        n = len(matches)
        if n == 0:
            return {}
        wins = draws = losses = 0
        gf = ga = 0
        over25 = 0
        btts = 0
        score_dist = defaultdict(int)
        goals_for_dist = defaultdict(int)
        goals_against_dist = defaultdict(int)
        for m in matches:
            is_home = m["home_team"] == team
            sd, se = m["score_dom"], m["score_ext"]
            gf_match = sd if is_home else se
            ga_match = se if is_home else sd
            gf += gf_match
            ga += ga_match
            total = sd + se
            if total > 2.5:
                over25 += 1
            if sd > 0 and se > 0:
                btts += 1
            score_dist["%d-%d" % (sd, se)] += 1
            goals_for_dist[min(gf_match, 4)] += 1
            goals_against_dist[min(ga_match, 4)] += 1
            if is_home:
                if sd > se:
                    wins += 1
                elif sd == se:
                    draws += 1
                else:
                    losses += 1
            else:
                if se > sd:
                    wins += 1
                elif sd == se:
                    draws += 1
                else:
                    losses += 1
        return {
            "label": label,
            "n": n,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "win_rate": wins / n if n else 0,
            "draw_rate": draws / n if n else 0,
            "loss_rate": losses / n if n else 0,
            "gf_avg": gf / n if n else 0,
            "ga_avg": ga / n if n else 0,
            "gd_avg": (gf - ga) / n if n else 0,
            "over25_rate": over25 / n if n else 0,
            "btts_rate": btts / n if n else 0,
            "top_scores": sorted(score_dist.items(), key=lambda x: -x[1])[:5],
            "goals_for_dist": dict(sorted(goals_for_dist.items())),
            "goals_against_dist": dict(sorted(goals_against_dist.items())),
        }

    return {
        "team": team,
        "overall": calc_stats(all_matches, "global"),
        "home": calc_stats(home_matches, "domicile"),
        "away": calc_stats(away_matches, "exterieur"),
    }


def compute_form_profile(csv_data, team, window=10):
    home_matches, away_matches = get_team_matches(csv_data, team)
    all_matches = sorted(home_matches + away_matches, key=lambda x: x["round"])

    if len(all_matches) < window:
        return {"recent_form": 0, "recent_momentum": 0, "streak": "N/A", "last5": []}

    recent = all_matches[-window:]
    last5 = all_matches[-5:]

    pts_last5 = []
    for m in last5:
        is_home = m["home_team"] == team
        sd, se = m["score_dom"], m["score_ext"]
        if is_home:
            pts_last5.append(3 if sd > se else 1 if sd == se else 0)
        else:
            pts_last5.append(3 if se > sd else 1 if sd == se else 0)

    recent_pts = 0
    recent_n = len(recent)
    for m in recent:
        is_home = m["home_team"] == team
        sd, se = m["score_dom"], m["score_ext"]
        if is_home:
            recent_pts += 3 if sd > se else 1 if sd == se else 0
        else:
            recent_pts += 3 if se > sd else 1 if sd == se else 0

    streak = ""
    for m in reversed(all_matches):
        is_home = m["home_team"] == team
        sd, se = m["score_dom"], m["score_ext"]
        won = (is_home and sd > se) or (not is_home and se > sd)
        drew = sd == se
        if streak == "":
            streak = "W" if won else ("D" if drew else "L")
        elif (streak[-1] == "W" and won) or (streak[-1] == "D" and drew) or (streak[-1] == "L" and not won and not drew):
            streak += streak[-1]
        else:
            break

    gf_trend = 0
    ga_trend = 0
    if len(all_matches) >= window * 2:
        older = all_matches[-window * 2:-window]
        newer = all_matches[-window:]
        gf_older = sum((m["home_team"] == team and m["score_dom"] or m["score_ext"]) for m in older) / window
        gf_newer = sum((m["home_team"] == team and m["score_dom"] or m["score_ext"]) for m in newer) / window
        ga_older = sum((m["home_team"] == team and m["score_ext"] or m["score_dom"]) for m in older) / window
        ga_newer = sum((m["home_team"] == team and m["score_ext"] or m["score_dom"]) for m in newer) / window
        gf_trend = gf_newer - gf_older
        ga_trend = ga_newer - ga_older

    return {
        "recent_form": recent_pts / (recent_n * 3) if recent_n else 0,
        "recent_momentum": sum(pts_last5) / 15 if pts_last5 else 0,
        "streak": streak,
        "last5_results": ["W" if (m["home_team"] == team and m["score_dom"] > m["score_ext"]) or (m["away_team"] == team and m["score_ext"] > m["score_dom"]) else "D" if m["score_dom"] == m["score_ext"] else "L" for m in last5],
        "gf_trend": gf_trend,
        "ga_trend": ga_trend,
        "pts_last5": pts_last5,
    }


def analyze_odds_ranges(preds, team):
    as_home, as_away = get_team_predictions(preds, team)
    all_resolved = as_home + as_away
    if not all_resolved:
        return {}

    odds_buckets = {
        "fav_extreme": {"range": (1.0, 1.5), "matches": [], "desc": "Favori extreme (1.00-1.50)"},
        "fav_fort": {"range": (1.5, 2.0), "matches": [], "desc": "Favori fort (1.50-2.00)"},
        "fav_modere": {"range": (2.0, 2.5), "matches": [], "desc": "Favori modere (2.00-2.50)"},
        "equilibre": {"range": (2.5, 3.5), "matches": [], "desc": "Equilibre (2.50-3.50)"},
        "outsider": {"range": (3.5, 5.0), "matches": [], "desc": "Outsider (3.50-5.00)"},
        "gros_outsider": {"range": (5.0, 999), "matches": [], "desc": "Gros outsider (5.00+)"}
    }

    for p in all_resolved:
        is_home = p["home_team"] == team
        if is_home:
            team_odds = p.get("cote_1", 0)
        else:
            team_odds = p.get("cote_2", 0)

        if team_odds <= 0:
            continue

        won = (is_home and p["actual_result"] == "1") or (not is_home and p["actual_result"] == "2")
        drew = p["actual_result"] == "X"

        for bucket_key, bucket in odds_buckets.items():
            lo, hi = bucket["range"]
            if lo <= team_odds < hi:
                bucket["matches"].append({
                    "round": p["round"],
                    "opponent": p["away_team"] if is_home else p["home_team"],
                    "venue": "D" if is_home else "E",
                    "odds": team_odds,
                    "won": won,
                    "drew": drew,
                    "score": "%d-%d" % (p["score_dom"], p["score_ext"]),
                    "result": p["actual_result"],
                })

    result = {}
    for key, bucket in odds_buckets.items():
        matches = bucket["matches"]
        n = len(matches)
        if n == 0:
            continue
        wins = sum(1 for m in matches if m["won"])
        draws = sum(1 for m in matches if m["drew"])
        result[key] = {
            "desc": bucket["desc"],
            "range": bucket["range"],
            "n": n,
            "wins": wins,
            "draws": draws,
            "losses": n - wins - draws,
            "win_rate": wins / n,
            "draw_rate": draws / n,
            "avg_odds": sum(m["odds"] for m in matches) / n,
            "matches": matches,
            "always_win": wins == n,
            "always_lose": wins == 0 and draws == 0,
            "never_lose": wins + draws == n,
        }
    return result


def find_high_odds_upsets(preds, team, min_upset_odds=3.0):
    as_home, as_away = get_team_predictions(preds, team)
    all_resolved = as_home + as_away
    upsets = []
    for p in all_resolved:
        is_home = p["home_team"] == team
        team_odds = p.get("cote_1", 0) if is_home else p.get("cote_2", 0)
        won = (is_home and p["actual_result"] == "1") or (not is_home and p["actual_result"] == "2")
        if won and team_odds >= min_upset_odds:
            upsets.append({
                "round": p["round"],
                "opponent": p["away_team"] if is_home else p["home_team"],
                "venue": "D" if is_home else "E",
                "odds": team_odds,
                "score": "%d-%d" % (p["score_dom"], p["score_ext"]),
                "model_confidence": p.get("confidence", 0),
                "model_pred": p.get("pred_1x2", "?"),
                "prob_dom": p.get("prob_dom", 0),
                "prob_nul": p.get("prob_nul", 0),
                "prob_ext": p.get("prob_ext", 0),
                "home_elo": p.get("home_elo", 0),
                "away_elo": p.get("away_elo", 0),
                "home_form": p.get("home_form", 0),
                "away_form": p.get("away_form", 0),
            })
    return sorted(upsets, key=lambda x: -x["odds"])


def analyze_btts_profile(preds, team):
    as_home, as_away = get_team_predictions(preds, team)
    all_resolved = as_home + as_away
    if not all_resolved:
        return {}

    btts_oui_count = sum(1 for p in all_resolved if p["actual_btts"] == "Oui")
    btts_non_count = sum(1 for p in all_resolved if p["actual_btts"] == "Non")
    n = len(all_resolved)

    home_btts = 0
    home_n = 0
    away_btts = 0
    away_n = 0
    for p in all_resolved:
        is_home = p["home_team"] == team
        if is_home:
            home_n += 1
            if p["actual_btts"] == "Oui":
                home_btts += 1
        else:
            away_n += 1
            if p["actual_btts"] == "Oui":
                away_btts += 1

    btts_when_home = 0
    btts_when_home_n = 0
    btts_when_away = 0
    btts_when_away_n = 0
    for p in all_resolved:
        is_home = p["home_team"] == team
        if p["actual_result"] == "1":
            if is_home:
                btts_when_home += 1 if p["actual_btts"] == "Oui" else 0
                btts_when_home_n += 1
            else:
                btts_when_away += 1 if p["actual_btts"] == "Oui" else 0
                btts_when_away_n += 1
        elif p["actual_result"] == "2":
            if is_home:
                btts_when_away += 1 if p["actual_btts"] == "Oui" else 0
                btts_when_away_n += 1
            else:
                btts_when_home += 1 if p["actual_btts"] == "Oui" else 0
                btts_when_home_n += 1

    return {
        "btts_oui_rate": btts_oui_count / n,
        "btts_non_rate": btts_non_count / n,
        "btts_when_home_score": btts_when_home / btts_when_home_n if btts_when_home_n else 0,
        "btts_when_away_score": btts_when_away / btts_when_away_n if btts_when_away_n else 0,
        "btts_as_home": home_btts / home_n if home_n else 0,
        "btts_as_away": away_btts / away_n if away_n else 0,
        "total_resolved": n,
    }


def analyze_cycle_patterns(csv_data, preds, team):
    home_matches, away_matches = get_team_matches(csv_data, team)
    all_matches = home_matches + away_matches

    cycles = defaultdict(list)
    for m in all_matches:
        c = m.get("cycle", "")
        if c:
            cycles[c].append(m)

    cycle_profiles = {}
    for c, matches in sorted(cycles.items()):
        n = len(matches)
        if n < 3:
            continue
        wins = draws = losses = 0
        gf = ga = 0
        for m in matches:
            is_home = m["home_team"] == team
            sd, se = m["score_dom"], m["score_ext"]
            gf += (sd if is_home else se)
            ga += (se if is_home else sd)
            if is_home:
                if sd > se: wins += 1
                elif sd == se: draws += 1
                else: losses += 1
            else:
                if se > sd: wins += 1
                elif sd == se: draws += 1
                else: losses += 1
        cycle_profiles[c] = {
            "n": n,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "win_rate": wins / n,
            "gf_avg": gf / n,
            "ga_avg": ga / n,
        }
    return cycle_profiles


def mine_conditional_patterns(preds, team, min_support=3):
    as_home, as_away = get_team_predictions(preds, team)
    all_resolved = as_home + as_away
    if len(all_resolved) < min_support:
        return []

    patterns = []
    conditions = {
        "is_home": lambda p: p["home_team"] == team,
        "is_away": lambda p: p["away_team"] == team,
        "elo_superior": lambda p: (p["home_team"] == team and p.get("home_elo", 0) > p.get("away_elo", 0)) or (p["away_team"] == team and p.get("away_elo", 0) > p.get("home_elo", 0)),
        "elo_inferior": lambda p: (p["home_team"] == team and p.get("home_elo", 0) < p.get("away_elo", 0)) or (p["away_team"] == team and p.get("away_elo", 0) < p.get("home_elo", 0)),
        "good_form": lambda p: (p["home_team"] == team and p.get("home_form", 0) > 0.5) or (p["away_team"] == team and p.get("away_form", 0) > 0.5),
        "bad_form": lambda p: (p["home_team"] == team and p.get("home_form", 0) < 0.3) or (p["away_team"] == team and p.get("away_form", 0) < 0.3),
        "high_odds": lambda p: ((p["home_team"] == team and p.get("cote_1", 0)) or (p["away_team"] == team and p.get("cote_2", 0))) > 3.0,
        "low_odds": lambda p: ((p["home_team"] == team and p.get("cote_1", 0)) or (p["away_team"] == team and p.get("cote_2", 0))) < 2.0,
        "match_high_total": lambda p: p.get("prob_over_25", 0) if "prob_over_25" in p else (p.get("over_25", 99) < 2.0),
        "match_low_total": lambda p: p.get("prob_under_25", 0) if "prob_under_25" in p else (p.get("under_25", 99) < 2.0),
    }

    outcomes = {
        "wins": lambda p, t: (p["home_team"] == t and p["actual_result"] == "1") or (p["away_team"] == t and p["actual_result"] == "2"),
        "draws": lambda p, t: p["actual_result"] == "X",
        "losses": lambda p, t: (p["home_team"] == t and p["actual_result"] == "2") or (p["away_team"] == t and p["actual_result"] == "1"),
        "btts_oui": lambda p, t: p["actual_btts"] == "Oui",
        "btts_non": lambda p, t: p["actual_btts"] == "Non",
        "over25": lambda p, t: p["actual_ou25"] == "Over",
        "under25": lambda p, t: p["actual_ou25"] == "Under",
        "dc_1X": lambda p, t: p.get("actual_dc_1X", False),
        "dc_X2": lambda p, t: p.get("actual_dc_X2", False),
        "dc_12": lambda p, t: p.get("actual_dc_12", False),
    }

    combo_keys = list(conditions.keys())
    for i, ck1 in enumerate(combo_keys):
        for ck2 in combo_keys[i:]:
            cond_funcs = [conditions[ck1]]
            cond_names = [ck1]
            if ck1 != ck2:
                cond_funcs.append(conditions[ck2])
                cond_names.append(ck2)

            matched = []
            for p in all_resolved:
                try:
                    if all(cf(p) for cf in cond_funcs):
                        matched.append(p)
                except:
                    continue

            if len(matched) < min_support:
                continue

            n = len(matched)
            for out_name, out_func in outcomes.items():
                hits = sum(1 for p in matched if out_func(p, team))
                rate = hits / n
                if rate >= 0.85 and n >= min_support:
                    patterns.append({
                        "conditions": cond_names,
                        "outcome": out_name,
                        "rate": rate,
                        "hits": hits,
                        "total": n,
                        "confidence": rate * (n / (n + 2)),
                    })

    patterns.sort(key=lambda x: (-x["confidence"], -x["rate"], -x["total"]))
    return patterns


def build_team_report(csv_data, preds, team):
    basic = compute_basic_profile(csv_data, team)
    form = compute_form_profile(csv_data, team)
    odds = analyze_odds_ranges(preds, team)
    upsets = find_high_odds_upsets(preds, team, min_upset_odds=2.5)
    btts = analyze_btts_profile(preds, team)
    cycles = analyze_cycle_patterns(csv_data, preds, team)
    patterns = mine_conditional_patterns(preds, team, min_support=3)

    key_insights = []
    for bk, bv in odds.items():
        if bv["always_win"] and bv["n"] >= 2:
            key_insights.append({
                "type": "odds_guarantee",
                "desc": "Gagne TOUJOURS quand cote %s (%d/%d, %.0f%%)" % (bv["desc"], bv["wins"], bv["n"], bv["win_rate"] * 100),
                "severity": "high",
            })
        elif bv["never_lose"] and bv["n"] >= 3:
            key_insights.append({
                "type": "odds_solid",
                "desc": "Ne JAMAIS perdre quand cote %s (%d/%d, %.0f%% sans defaite)" % (bv["desc"], bv["wins"] + bv["draws"], bv["n"], (bv["win_rate"] + bv["draw_rate"]) * 100),
                "severity": "medium",
            })
        elif bv["always_lose"] and bv["n"] >= 2:
            key_insights.append({
                "type": "odds_danger",
                "desc": "Perd TOUJOURS quand cote %s (%d matchs)" % (bv["desc"], bv["n"]),
                "severity": "danger",
            })

    for u in upsets[:3]:
        key_insights.append({
            "type": "upset",
            "desc": "A gagne a %.2f vs %s (Round %d, %s, score %s)" % (u["odds"], u["opponent"], u["round"], u["venue"], u["score"]),
            "severity": "info",
        })

    for pat in patterns[:5]:
        key_insights.append({
            "type": "pattern",
            "desc": "Quand %s: %s (%d/%d = %.0f%%)" % (" + ".join(pat["conditions"]), pat["outcome"], pat["hits"], pat["total"], pat["rate"] * 100),
            "severity": "high" if pat["confidence"] > 0.7 else "medium",
        })

    return {
        "team": team,
        "profile": basic,
        "form": form,
        "odds_ranges": odds,
        "high_odds_upsets": upsets,
        "btts_profile": btts,
        "cycle_patterns": cycles,
        "conditional_patterns": patterns,
        "key_insights": key_insights,
        "n_matches_csv": basic["overall"]["n"],
        "n_matches_preds": len([p for p in preds if (p["home_team"] == team or p["away_team"] == team) and p["has_result"]]),
    }


def build_all_teams(csv_path="donnees_equipes.csv", json_path="historique_predictions.json"):
    csv_data = load_csv_data(csv_path)
    preds = load_predictions(json_path)

    teams = set()
    for m in csv_data:
        if m["home_team"]:
            teams.add(m["home_team"])
        if m["away_team"]:
            teams.add(m["away_team"])

    all_profiles = {}
    for team in sorted(teams):
        all_profiles[team] = build_team_report(csv_data, preds, team)

    return all_profiles


def find_cross_team_patterns(all_profiles):
    patterns = {
        "always_win_at_home_ranges": [],
        "never_lose_at_home_ranges": [],
        "btts_kings": [],
        "draw_masters": [],
        "upset_kings": [],
        "strongest_conditional": [],
    }

    for team, report in all_profiles.items():
        odds = report.get("odds_ranges", {})
        for bk, bv in odds.items():
            if bv.get("always_win") and bv["n"] >= 2:
                patterns["always_win_at_home_ranges"].append({"team": team, "range": bv["desc"], "n": bv["n"], "wr": bv["win_rate"]})
            if bv.get("never_lose") and bv["n"] >= 3:
                patterns["never_lose_at_home_ranges"].append({"team": team, "range": bv["desc"], "n": bv["n"], "wr": bv["win_rate"]})

        btts = report.get("btts_profile", {})
        if btts.get("btts_oui_rate", 0) > 0.6 and btts.get("total_resolved", 0) >= 5:
            patterns["btts_kings"].append({"team": team, "btts_oui_rate": btts["btts_oui_rate"], "n": btts["total_resolved"]})

        overall = report.get("profile", {}).get("overall", {})
        if overall.get("draw_rate", 0) > 0.4 and overall.get("n", 0) >= 5:
            patterns["draw_masters"].append({"team": team, "draw_rate": overall["draw_rate"], "n": overall["n"]})

        upsets = report.get("high_odds_upsets", [])
        if len(upsets) >= 2:
            patterns["upset_kings"].append({"team": team, "n_upsets": len(upsets), "max_odds": upsets[0]["odds"] if upsets else 0})

        conds = report.get("conditional_patterns", [])
        if conds and conds[0]["confidence"] > 0.8:
            patterns["strongest_conditional"].append({"team": team, "pattern": conds[0]})

    for key in patterns:
        patterns[key].sort(key=lambda x: -x.get("n", 0) if isinstance(x, dict) and "n" in x else 0)

    return patterns


def get_accumulator_evidence(home, away, all_profiles=None):
    if all_profiles is None:
        all_profiles = build_all_teams()

    home_report = all_profiles.get(home, {})
    away_report = all_profiles.get(away, {})

    evidence = {
        "home_team": home,
        "away_team": away,
        "home_evidence": [],
        "away_evidence": [],
        "head_to_head_conditions": [],
        "combined_confidence": 0,
    }

    for report, side, team in [(home_report, "home_evidence", home), (away_report, "away_evidence", away)]:
        odds = report.get("odds_ranges", {})
        form = report.get("form", {})
        basic = report.get("profile", {})
        conds = report.get("conditional_patterns", [])

        if form.get("streak", "").startswith("W") and len(form.get("streak", "")) >= 2:
            evidence[side].append({
                "factor": "Serie de victoires",
                "detail": "%s (W x%d)" % (form["streak"], len(form["streak"])),
                "weight": 0.15,
            })

        home_profile = basic.get("home", {}) if side == "home_evidence" else basic.get("away", {})
        if home_profile.get("win_rate", 0) > 0.6:
            evidence[side].append({
                "factor": "Fort a domicile/exterieur",
                "detail": "%.0f%% de victoires (%d matchs)" % (home_profile["win_rate"] * 100, home_profile["n"]),
                "weight": 0.2,
            })

        for pat in conds[:2]:
            evidence[side].append({
                "factor": "Pattern conditionnel",
                "detail": "Quand %s: %s (%.0f%%)" % (" + ".join(pat["conditions"]), pat["outcome"], pat["rate"] * 100),
                "weight": 0.25 * pat["confidence"],
            })

        overall = basic.get("overall", {})
        if overall.get("gf_avg", 0) > 1.5:
            evidence[side].append({
                "factor": "Attaque forte",
                "detail": "%.1f buts/match" % overall["gf_avg"],
                "weight": 0.1,
            })
        if overall.get("ga_avg", 0) < 0.8:
            evidence[side].append({
                "factor": "Defense solide",
                "detail": "%.1f buts encaisses/match" % overall["ga_avg"],
                "weight": 0.1,
            })

    total_weight = sum(e["weight"] for e in evidence["home_evidence"] + evidence["away_evidence"])
    evidence["combined_confidence"] = min(total_weight, 1.0)

    return evidence


_cached_profiles = None

def _get_profiles():
    global _cached_profiles
    if _cached_profiles is None:
        _cached_profiles = build_all_teams()
    return _cached_profiles

def invalidate_cache():
    global _cached_profiles
    _cached_profiles = None


def evaluate_match(home, away, home_odds=0, away_odds=0, venue="D", match_context=None):
    profiles = _get_profiles()
    home_report = profiles.get(home, {})
    away_report = profiles.get(away, {})

    signals = []
    dc_boosts = {"1X": 0, "X2": 0, "12": 0}
    ou_boosts = {"Over": 0, "Under": 0}
    btts_boosts = {"BTTS Oui": 0, "BTTS Non": 0}
    confidence_adjustment = 0
    history_matches = []

    for team, report, is_home in [(home, home_report, True), (away, away_report, False)]:
        if not report:
            continue

        odds_ranges = report.get("odds_ranges", {})
        for bk, bv in odds_ranges.items():
            lo, hi = bv["range"]
            team_odds = home_odds if is_home else away_odds
            if team_odds > 0 and lo <= team_odds < hi:
                if bv.get("always_win") and bv["n"] >= 2:
                    signals.append({
                        "type": "ODDS_GURANTEE",
                        "team": team,
                        "desc": "Gagne TOUJOURS en zone %s" % bv["desc"],
                        "evidence": "%d/%d = %.0f%%" % (bv["wins"], bv["n"], bv["win_rate"] * 100),
                        "strength": min(bv["n"] / 5.0, 1.0),
                        "severity": "critical",
                    })
                    if is_home:
                        dc_boosts["1X"] = max(dc_boosts["1X"], 0.15)
                    else:
                        dc_boosts["X2"] = max(dc_boosts["X2"], 0.15)
                    confidence_adjustment += 5
                elif bv.get("never_lose") and bv["n"] >= 3:
                    signals.append({
                        "type": "ODDS_SOLID",
                        "team": team,
                        "desc": "Ne JAMAIS perdre en zone %s" % bv["desc"],
                        "evidence": "%d/%d = %.0f%% sans defaite" % (bv["wins"] + bv["draws"], bv["n"], (bv["win_rate"] + bv["draw_rate"]) * 100),
                        "strength": min(bv["n"] / 7.0, 1.0),
                        "severity": "high",
                    })
                    if is_home:
                        dc_boosts["1X"] = max(dc_boosts["1X"], 0.10)
                    else:
                        dc_boosts["X2"] = max(dc_boosts["X2"], 0.10)
                    confidence_adjustment += 3
                elif bv.get("always_lose") and bv["n"] >= 2:
                    signals.append({
                        "type": "ODDS_DANGER",
                        "team": team,
                        "desc": "Perd TOUJOURS en zone %s" % bv["desc"],
                        "evidence": "%d/%d defaite" % (bv["losses"], bv["n"]),
                        "strength": min(bv["n"] / 3.0, 1.0),
                        "severity": "danger",
                    })
                    if is_home:
                        dc_boosts["X2"] = max(dc_boosts["X2"], 0.12)
                    else:
                        dc_boosts["1X"] = max(dc_boosts["1X"], 0.12)
                    confidence_adjustment -= 3

                if bv.get("n", 0) >= 3:
                    matches_in_zone = bv.get("matches", [])
                    wins_in_zone = [m for m in matches_in_zone if m.get("won")]
                    for wm in wins_in_zone:
                        history_matches.append({
                            "team": team,
                            "opponent": wm.get("opponent", "?"),
                            "venue": wm.get("venue", "?"),
                            "odds": wm.get("odds", 0),
                            "score": wm.get("score", "?"),
                            "round": wm.get("round", 0),
                            "pattern": bv["desc"],
                        })

        btts_prof = report.get("btts_profile", {})
        if btts_prof.get("btts_oui_rate", 0) > 0.6 and btts_prof.get("total_resolved", 0) >= 5:
            signals.append({
                "type": "BTTS_KING",
                "team": team,
                "desc": "BTTS Oui frequent: %.0f%%" % (btts_prof["btts_oui_rate"] * 100),
                "evidence": "%d matchs" % btts_prof["total_resolved"],
                "strength": btts_prof["btts_oui_rate"],
                "severity": "medium",
            })
            btts_boosts["BTTS Oui"] = max(btts_boosts["BTTS Oui"], 0.05)
        elif btts_prof.get("btts_non_rate", 0) > 0.6 and btts_prof.get("total_resolved", 0) >= 5:
            btts_boosts["BTTS Non"] = max(btts_boosts["BTTS Non"], 0.03)

        conds = report.get("conditional_patterns", [])
        for pat in conds[:3]:
            if pat["confidence"] < 0.75:
                continue
            venue_match = False
            if "is_home" in pat["conditions"] and is_home:
                venue_match = True
            elif "is_away" in pat["conditions"] and not is_home:
                venue_match = True
            elif "is_home" not in pat["conditions"] and "is_away" not in pat["conditions"]:
                venue_match = True

            if venue_match:
                outcome = pat["outcome"]
                sig_type = "COND_WIN" if outcome == "wins" else "COND_DC" if outcome.startswith("dc_") else "COND_OU" if outcome.startswith("over") or outcome.startswith("under") else "COND_BTTS" if outcome.startswith("btts") else "COND_PATTERN"
                signals.append({
                    "type": sig_type,
                    "team": team,
                    "desc": "Pattern: quand %s -> %s" % (" + ".join(pat["conditions"]), outcome),
                    "evidence": "%d/%d = %.0f%% (conf=%.0f%%)" % (pat["hits"], pat["total"], pat["rate"] * 100, pat["confidence"] * 100),
                    "strength": pat["confidence"],
                    "severity": "high" if pat["confidence"] > 0.85 else "medium",
                })
                if outcome == "dc_1X" and is_home:
                    dc_boosts["1X"] = max(dc_boosts["1X"], 0.10)
                elif outcome == "dc_X2" and not is_home:
                    dc_boosts["X2"] = max(dc_boosts["X2"], 0.10)
                elif outcome == "dc_12":
                    dc_boosts["12"] = max(dc_boosts["12"], 0.08)
                elif outcome == "over25":
                    ou_boosts["Over"] = max(ou_boosts["Over"], 0.05)
                elif outcome == "under25":
                    ou_boosts["Under"] = max(ou_boosts["Under"], 0.05)
                elif outcome == "btts_oui":
                    btts_boosts["BTTS Oui"] = max(btts_boosts["BTTS Oui"], 0.05)
                elif outcome == "btts_non":
                    btts_boosts["BTTS Non"] = max(btts_boosts["BTTS Non"], 0.05)
                elif outcome == "wins":
                    confidence_adjustment += 4 if pat["confidence"] > 0.85 else 2
                break

    critical_signals = [s for s in signals if s["severity"] == "critical"]
    high_signals = [s for s in signals if s["severity"] == "high"]

    return {
        "signals": signals,
        "critical_count": len(critical_signals),
        "high_count": len(high_signals),
        "dc_boosts": dc_boosts,
        "ou_boosts": ou_boosts,
        "btts_boosts": btts_boosts,
        "confidence_adjustment": confidence_adjustment,
        "history_matches": history_matches[:8],
        "has_profiler_data": len(signals) > 0,
        "signal_summary": "; ".join(s["desc"] for s in signals[:4]) if signals else "",
    }


if __name__ == "__main__":
    print("Building team profiles...")
    profiles = build_all_teams()
    print("Done. %d teams profiled." % len(profiles))

    cross = find_cross_team_patterns(profiles)
    print("\n=== Cross-team patterns ===")
    print("Always win zones:", len(cross["always_win_at_home_ranges"]))
    print("Never lose zones:", len(cross["never_lose_at_home_ranges"]))
    print("BTTS kings:", len(cross["btts_kings"]))
    print("Draw masters:", len(cross["draw_masters"]))
    print("Upset kings:", len(cross["upset_kings"]))

    for team in ["Algeria", "Egypt", "Morocco", "Nigeria"]:
        if team in profiles:
            r = profiles[team]
            print("\n=== %s ===" % team)
            print("  Matches: %d CSV, %d with odds" % (r["n_matches_csv"], r["n_matches_preds"]))
            o = r["profile"]["overall"]
            print("  Overall: %dW/%dD/%dL (%.0f%% WR) GF=%.1f GA=%.1f" % (
                o["wins"], o["draws"], o["losses"], o["win_rate"] * 100, o["gf_avg"], o["ga_avg"]))
            h = r["profile"]["home"]
            a = r["profile"]["away"]
            print("  Home: %.0f%% WR (%d) | Away: %.0f%% WR (%d)" % (
                h["win_rate"] * 100, h["n"], a["win_rate"] * 100, a["n"]))
            print("  Form: %s (%.2f) | Streak: %s" % (
                r["form"]["last5_results"], r["form"]["recent_momentum"], r["form"]["streak"]))
            for ins in r["key_insights"][:3]:
                print("  >> %s" % ins["desc"])
