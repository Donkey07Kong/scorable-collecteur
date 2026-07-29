import csv
import os
import json
from collections import defaultdict

_csv_cache = None

def _load_csv():
    global _csv_cache
    if _csv_cache is not None:
        return _csv_cache
    rows = []
    for fn in ("donnees_equipes.csv", "donnees_matchs.csv"):
        fp = os.path.join(os.path.dirname(__file__), fn)
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    h = row.get("home_team", "").strip()
                    a = row.get("away_team", "").strip()
                    sd = int(float(row.get("score_final_dom", row.get("nb_buts_dom", 0))))
                    se = int(float(row.get("score_final_ext", row.get("nb_buts_ext", 0))))
                    total = sd + se
                    if h and a:
                        rows.append({"home": h, "away": a, "sd": sd, "se": se, "total": total})
                except (ValueError, TypeError):
                    continue
    _csv_cache = rows
    return rows


def get_h2h(home, away):
    rows = _load_csv()
    matches = [r for r in rows if r["home"] == home and r["away"] == away]
    n = len(matches)
    if n < 3:
        return None

    hw = sum(1 for r in matches if r["sd"] > r["se"])
    dr = sum(1 for r in matches if r["sd"] == r["se"])
    aw = sum(1 for r in matches if r["sd"] < r["se"])

    goals = [r["total"] for r in matches]
    avg_goals = sum(goals) / n

    under_25 = sum(1 for g in goals if g <= 2)
    under_15 = sum(1 for g in goals if g <= 1)
    over_25 = sum(1 for g in goals if g > 2)
    over_35 = sum(1 for g in goals if g > 3)

    home_goals = [r["sd"] for r in matches]
    away_goals = [r["se"] for r in matches]
    btts_yes = sum(1 for r in matches if r["sd"] > 0 and r["se"] > 0)

    dc_1x = hw + dr
    dc_x2 = dr + aw
    dc_12 = hw + aw

    scores = defaultdict(int)
    for r in matches:
        scores["%d-%d" % (r["sd"], r["se"])] += 1

    return {
        "home": home, "away": away, "n": n,
        "hw": hw, "dr": dr, "aw": aw,
        "hw_pct": round(hw / n * 100, 1),
        "dr_pct": round(dr / n * 100, 1),
        "aw_pct": round(aw / n * 100, 1),
        "dc_1x_pct": round(dc_1x / n * 100, 1),
        "dc_x2_pct": round(dc_x2 / n * 100, 1),
        "dc_12_pct": round(dc_12 / n * 100, 1),
        "avg_goals": round(avg_goals, 2),
        "under_25_pct": round(under_25 / n * 100, 1),
        "under_15_pct": round(under_15 / n * 100, 1),
        "over_25_pct": round(over_25 / n * 100, 1),
        "over_35_pct": round(over_35 / n * 100, 1),
        "btts_pct": round(btts_yes / n * 100, 1),
        "avg_home_goals": round(sum(home_goals) / n, 2),
        "avg_away_goals": round(sum(away_goals) / n, 2),
        "top_scores": sorted(scores.items(), key=lambda x: -x[1])[:5],
    }


def get_team_home_stats(team):
    rows = _load_csv()
    matches = [r for r in rows if r["home"] == team]
    n = len(matches)
    if n < 5:
        return None
    hw = sum(1 for r in matches if r["sd"] > r["se"])
    dr = sum(1 for r in matches if r["sd"] == r["se"])
    aw = sum(1 for r in matches if r["sd"] < r["se"])
    dc_1x = hw + dr
    goals = [r["total"] for r in matches]
    under_25 = sum(1 for g in goals if g <= 2)
    btts = sum(1 for r in matches if r["sd"] > 0 and r["se"] > 0)
    return {
        "team": team, "n": n,
        "hw_pct": round(hw / n * 100, 1),
        "dr_pct": round(dr / n * 100, 1),
        "aw_pct": round(aw / n * 100, 1),
        "dc_1x_pct": round(dc_1x / n * 100, 1),
        "under_25_pct": round(under_25 / n * 100, 1),
        "btts_pct": round(btts / n * 100, 1),
        "avg_goals": round(sum(goals) / n, 2),
    }


def get_team_away_stats(team):
    rows = _load_csv()
    matches = [r for r in rows if r["away"] == team]
    n = len(matches)
    if n < 5:
        return None
    hw = sum(1 for r in matches if r["sd"] > r["se"])
    dr = sum(1 for r in matches if r["sd"] == r["se"])
    aw = sum(1 for r in matches if r["sd"] < r["se"])
    dc_x2 = dr + aw
    goals = [r["total"] for r in matches]
    under_25 = sum(1 for g in goals if g <= 2)
    return {
        "team": team, "n": n,
        "opponent_hw_pct": round(hw / n * 100, 1),
        "opponent_dr_pct": round(dr / n * 100, 1),
        "away_win_pct": round(aw / n * 100, 1),
        "dc_x2_pct": round(dc_x2 / n * 100, 1),
        "under_25_pct": round(under_25 / n * 100, 1),
    }


def analyze_match_exploits(home, away):
    h2h = get_h2h(home, away)
    home_stats = get_team_home_stats(home)
    away_stats = get_team_away_stats(away)

    exploits = []

    if h2h and h2h["n"] >= 5:
        if h2h["dc_1x_pct"] >= 90:
            exploits.append({
                "type": "DC_1X_H2H",
                "pick": "1X",
                "confidence": h2h["dc_1x_pct"],
                "n_matches": h2h["n"],
                "source": "H2H direct",
                "cote_typique": 1.05 if h2h["dc_1x_pct"] >= 95 else 1.10,
                "label": "DC 1X H2H %.0f%% (%d matchs)" % (h2h["dc_1x_pct"], h2h["n"]),
            })
        if h2h["dc_x2_pct"] >= 90:
            exploits.append({
                "type": "DC_X2_H2H",
                "pick": "X2",
                "confidence": h2h["dc_x2_pct"],
                "n_matches": h2h["n"],
                "source": "H2H direct",
                "cote_typique": 1.15,
                "label": "DC X2 H2H %.0f%% (%d matchs)" % (h2h["dc_x2_pct"], h2h["n"]),
            })
        if h2h["under_25_pct"] >= 85:
            exploits.append({
                "type": "UNDER_25_H2H",
                "pick": "Under 2.5",
                "confidence": h2h["under_25_pct"],
                "n_matches": h2h["n"],
                "source": "H2H goals",
                "cote_typique": 1.50 if h2h["under_25_pct"] < 90 else 1.40,
                "label": "Under 2.5 H2H %.0f%% (%d matchs)" % (h2h["under_25_pct"], h2h["n"]),
            })
        if h2h["under_15_pct"] >= 75:
            exploits.append({
                "type": "UNDER_15_H2H",
                "pick": "Under 1.5",
                "confidence": h2h["under_15_pct"],
                "n_matches": h2h["n"],
                "source": "H2H goals",
                "cote_typique": 1.30,
                "label": "Under 1.5 H2H %.0f%% (%d matchs)" % (h2h["under_15_pct"], h2h["n"]),
            })
        if h2h["btts_pct"] <= 15:
            exploits.append({
                "type": "BTTS_NON_H2H",
                "pick": "BTTS Non",
                "confidence": 100 - h2h["btts_pct"],
                "n_matches": h2h["n"],
                "source": "H2H BTTS",
                "cote_typique": 1.40,
                "label": "BTTS Non H2H %.0f%% (%d matchs)" % (100 - h2h["btts_pct"], h2h["n"]),
            })
        if h2h["btts_pct"] >= 80:
            exploits.append({
                "type": "BTTS_OUI_H2H",
                "pick": "BTTS Oui",
                "confidence": h2h["btts_pct"],
                "n_matches": h2h["n"],
                "source": "H2H BTTS",
                "cote_typique": 1.80,
                "label": "BTTS Oui H2H %.0f%% (%d matchs)" % (h2h["btts_pct"], h2h["n"]),
            })
        if h2h["dr_pct"] >= 60:
            exploits.append({
                "type": "DRAW_H2H",
                "pick": "X",
                "confidence": h2h["dr_pct"],
                "n_matches": h2h["n"],
                "source": "H2H draws",
                "cote_typique": 2.80,
                "label": "Nul H2H %.0f%% (%d matchs)" % (h2h["dr_pct"], h2h["n"]),
            })

    if home_stats and home_stats["dc_1x_pct"] >= 85:
        exploits.append({
            "type": "DC_1X_HOME_TEAM",
            "pick": "1X",
            "confidence": home_stats["dc_1x_pct"],
            "n_matches": home_stats["n"],
            "source": "Stats domicile",
            "cote_typique": 1.15,
            "label": "%s domicile 1X %.0f%% (%d matchs)" % (home, home_stats["dc_1x_pct"], home_stats["n"]),
        })

    if away_stats and away_stats["away_win_pct"] <= 15:
        exploits.append({
            "type": "DC_1X_VS_WEAK_AWAY",
            "pick": "1X",
            "confidence": min(95, 100 - away_stats["away_win_pct"]),
            "n_matches": away_stats["n"],
            "source": "Stats ext. faible",
            "cote_typique": 1.10,
            "label": "%s ext. %.0f%% victoires -> fade" % (away, away_stats["away_win_pct"]),
        })

    if h2h and home_stats:
        combined_1x = h2h["dc_1x_pct"] * 0.6 + home_stats["dc_1x_pct"] * 0.4
        if combined_1x >= 90:
            exploits.append({
                "type": "DC_1X_COMBINED",
                "pick": "1X",
                "confidence": round(combined_1x, 1),
                "n_matches": h2h["n"],
                "source": "H2H + domicile",
                "cote_typique": 1.08,
                "label": "COMBINE 1X: H2H %.0f%% + Dom %.0f%% = %.0f%%" % (
                    h2h["dc_1x_pct"], home_stats["dc_1x_pct"], combined_1x),
            })

    exploits.sort(key=lambda x: -x["confidence"])
    return exploits, h2h, home_stats, away_stats


def find_all_exploitable_matches(predictions):
    results = []
    for p in predictions:
        home = p.get("home_team", "")
        away = p.get("away_team", "")
        exploits, h2h, hs, as_ = analyze_match_exploits(home, away)
        if exploits:
            results.append({
                "home": home, "away": away,
                "exploits": exploits,
                "h2h": h2h,
                "home_stats": hs,
                "away_stats": as_,
                "best_confidence": exploits[0]["confidence"] if exploits else 0,
            })
    results.sort(key=lambda x: -x["best_confidence"])
    return results


def build_h2h_full_db():
    rows = _load_csv()
    matchups = defaultdict(list)
    for r in rows:
        matchups[(r["home"], r["away"])].append(r)

    db = {}
    for (home, away), matches in matchups.items():
        n = len(matches)
        if n < 5:
            continue
        hw = sum(1 for r in matches if r["sd"] > r["se"])
        dr = sum(1 for r in matches if r["sd"] == r["se"])
        aw = sum(1 for r in matches if r["sd"] < r["se"])
        goals = [r["total"] for r in matches]
        btts = sum(1 for r in matches if r["sd"] > 0 and r["se"] > 0)

        db["%s|%s" % (home, away)] = {
            "n": n,
            "dc_1x_pct": round((hw + dr) / n * 100, 1),
            "dc_x2_pct": round((dr + aw) / n * 100, 1),
            "hw_pct": round(hw / n * 100, 1),
            "dr_pct": round(dr / n * 100, 1),
            "aw_pct": round(aw / n * 100, 1),
            "under_25_pct": round(sum(1 for g in goals if g <= 2) / n * 100, 1),
            "under_15_pct": round(sum(1 for g in goals if g <= 1) / n * 100, 1),
            "btts_no_pct": round((n - btts) / n * 100, 1),
            "avg_goals": round(sum(goals) / n, 2),
        }
    return db
