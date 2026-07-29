import csv
import math
import os
import requests
import json
import time

MATCHES_URL = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues/8060/matches"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "fr",
    "app-version": "34283",
    "referer": "https://bet261.mg/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
}

HISTORIQUE_PATH = "donnees_matchs.csv"

def charger_historique(fichier=HISTORIQUE_PATH):
    donnees = []
    required_cols = {"nb_buts_total", "nb_buts_dom", "nb_buts_ext", "score_final_dom", "score_final_ext"}

    if os.path.exists(fichier):
        with open(fichier, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames and required_cols.issubset(set(reader.fieldnames)):
                for row in reader:
                    try:
                        row["nb_buts_total"] = int(float(row["nb_buts_total"]))
                        row["nb_buts_dom"] = int(float(row["nb_buts_dom"]))
                        row["nb_buts_ext"] = int(float(row["nb_buts_ext"]))
                        row["score_final_dom"] = int(float(row["score_final_dom"]))
                        row["score_final_ext"] = int(float(row["score_final_ext"]))
                        donnees.append(row)
                    except (KeyError, ValueError):
                        continue

    equipes_file = "donnees_equipes.csv"
    if os.path.exists(equipes_file):
        with open(equipes_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames and required_cols.issubset(set(reader.fieldnames)):
                for row in reader:
                    try:
                        row["nb_buts_total"] = int(float(row["nb_buts_total"]))
                        row["nb_buts_dom"] = int(float(row["nb_buts_dom"]))
                        row["nb_buts_ext"] = int(float(row["nb_buts_ext"]))
                        row["score_final_dom"] = int(float(row["score_final_dom"]))
                        row["score_final_ext"] = int(float(row["score_final_ext"]))
                        donnees.append(row)
                    except (KeyError, ValueError):
                        continue

    return donnees

def calculer_stats(donnees):
    n = len(donnees)
    if n == 0:
        return {
            "total_matchs": 0, "moy_buts": 1.5, "moy_dom": 0.8, "moy_ext": 0.7,
            "over_15": 0.55, "over_25": 0.50, "over_35": 0.30,
            "v_dom": 0.50, "v_ext": 0.25, "nuls": 0.25,
            "pair_impair": {"pair": 0.50, "impair": 0.50},
            "score_dist": {}, "distrib_norm": {},
            "team_stats": {}, "h2h_stats": {},
            "elo_ratings": {}, "tendances": {},
            "equipes": []
        }
    buts = [d["nb_buts_total"] for d in donnees]

    distrib = {}
    for b in buts:
        distrib[b] = distrib.get(b, 0) + 1

    distrib_norm = {k: v / n for k, v in distrib.items()}

    moy_buts = sum(buts) / n
    moy_dom = sum(d["nb_buts_dom"] for d in donnees) / n
    moy_ext = sum(d["nb_buts_ext"] for d in donnees) / n

    over_15 = sum(1 for b in buts if b > 1.5) / n
    over_25 = sum(1 for b in buts if b > 2.5) / n
    over_35 = sum(1 for b in buts if b > 3.5) / n

    v_dom = sum(1 for d in donnees if d["victoire"] == "dom") / n
    v_ext = sum(1 for d in donnees if d["victoire"] == "ext") / n
    nuls = sum(1 for d in donnees if d["victoire"] == "nul") / n

    pair_count = sum(1 for b in buts if b % 2 == 0)
    impair_count = n - pair_count

    score_dist = {}
    for d in donnees:
        key = (d["score_final_dom"], d["score_final_ext"])
        score_dist[key] = score_dist.get(key, 0) + 1

    home_advantage = (moy_dom - moy_ext) / max(moy_dom, 0.01)

    team_stats = calculer_stats_equipes(donnees)
    elo_ratings = calculer_elo(donnees)
    h2h_stats = calculer_h2h(donnees)
    tendances = calculer_tendances(donnees)

    return {
        "moy_buts": moy_buts,
        "moy_dom": moy_dom,
        "moy_ext": moy_ext,
        "over_15": over_15,
        "over_25": over_25,
        "over_35": over_35,
        "v_dom": v_dom,
        "v_ext": v_ext,
        "nuls": nuls,
        "draw_rate": nuls,
        "home_win_rate": v_dom,
        "distrib": distrib,
        "distrib_norm": distrib_norm,
        "pair_ratio": pair_count / n,
        "impair_ratio": impair_count / n,
        "score_dist": score_dist,
        "home_advantage": home_advantage,
        "total_matchs": n,
        "team_stats": team_stats,
        "elo_ratings": elo_ratings,
        "h2h_stats": h2h_stats,
        "tendances": tendances,
    }

def calculer_stats_equipes(donnees, decay=0.94):
    max_round = 0
    for d in donnees:
        r = int(d.get("round", 0))
        if r > max_round:
            max_round = r

    teams = {}
    for d in donnees:
        h = d.get("home_team", "")
        a = d.get("away_team", "")
        if not h or h == "?" or not a or a == "?":
            continue

        rnd = int(d.get("round", 0))
        age = max_round - rnd if max_round > 0 else 0
        w = decay ** age

        sd = d["score_final_dom"]
        se = d["score_final_ext"]
        total = sd + se
        rnd_key = int(d.get("round", 0))

        for t in [h, a]:
            if t not in teams:
                teams[t] = {
                    "j": 0, "bm": 0, "be": 0, "v": 0, "n": 0, "d": 0,
                    "home_j": 0, "home_bm": 0, "home_be": 0,
                    "away_j": 0, "away_bm": 0, "away_be": 0,
                    "over_25_for": 0, "over_25_against": 0,
                    "goals_for_dist": {0: 0, 1: 0, 2: 0, 3: 0, "4+": 0},
                    "goals_against_dist": {0: 0, 1: 0, 2: 0, 3: 0, "4+": 0},
                    "recent": [],
                    "home_over_25": 0, "away_over_25": 0,
                    "home_pair": 0, "away_pair": 0,
                    "home_draws": 0, "home_wins": 0, "home_losses": 0,
                    "away_wins": 0, "away_draws": 0, "away_losses": 0,
                    "consecutive_wins": 0, "consecutive_losses": 0, "consecutive_draws": 0,
                }

        s = teams[h]
        s["j"] += w
        s["bm"] += sd * w
        s["be"] += se * w
        s["home_j"] += w
        s["home_bm"] += sd * w
        s["home_be"] += se * w
        if total > 2.5:
            s["over_25_for"] += w
            s["home_over_25"] += w
        if (sd + se) % 2 == 0:
            s["home_pair"] += w

        gf = min(sd, 4)
        ga = min(se, 4)
        gf_key = "4+" if sd >= 4 else sd
        ga_key = "4+" if se >= 4 else se
        s["goals_for_dist"][gf_key] = s["goals_for_dist"].get(gf_key, 0) + w
        s["goals_against_dist"][ga_key] = s["goals_against_dist"].get(ga_key, 0) + w

        if sd > se:
            s["v"] += w
            s["home_wins"] += w
        elif se > sd:
            s["d"] += w
            s["home_losses"] += w
        else:
            s["n"] += w
            s["home_draws"] += w

        s["recent"].append({"round": rnd_key, "gf": sd, "ga": se, "is_home": True, "won": sd > se, "draw": sd == se})

        t2 = teams[a]
        t2["j"] += w
        t2["bm"] += se * w
        t2["be"] += sd * w
        t2["away_j"] += w
        t2["away_bm"] += se * w
        t2["away_be"] += sd * w
        if total > 2.5:
            t2["over_25_for"] += w
            t2["away_over_25"] += w
        if (sd + se) % 2 == 0:
            t2["away_pair"] += w

        gf2 = min(se, 4)
        ga2 = min(sd, 4)
        gf2_key = "4+" if se >= 4 else se
        ga2_key = "4+" if sd >= 4 else sd
        t2["goals_for_dist"][gf2_key] = t2["goals_for_dist"].get(gf2_key, 0) + w
        t2["goals_against_dist"][ga2_key] = t2["goals_against_dist"].get(ga2_key, 0) + w

        if se > sd:
            t2["v"] += w
            t2["away_wins"] += w
        elif sd > se:
            t2["d"] += w
            t2["away_losses"] += w
        else:
            t2["n"] += w
            t2["away_draws"] += w

        t2["recent"].append({"round": rnd_key, "gf": se, "ga": sd, "is_home": False, "won": se > sd, "draw": se == sd})

    result = {}
    for t, s in teams.items():
        j = s["j"]
        if j == 0:
            continue

        recent_sorted = sorted(s["recent"], key=lambda x: x["round"], reverse=True)[:5]
        recent_wins = sum(1 for r in recent_sorted if r["won"])
        recent_draws = sum(1 for r in recent_sorted if r["draw"])
        recent_losses = len(recent_sorted) - recent_wins - recent_draws
        recent_gf = sum(r["gf"] for r in recent_sorted) / max(len(recent_sorted), 1)
        recent_ga = sum(r["ga"] for r in recent_sorted) / max(len(recent_sorted), 1)

        home_j = s["home_j"] if s["home_j"] > 0 else 1
        away_j = s["away_j"] if s["away_j"] > 0 else 1

        form_score = (recent_wins * 3 + recent_draws) / max(len(recent_sorted) * 3, 1)

        result[t] = {
            "matchs": round(j),
            "moy_bm": s["bm"] / j,
            "moy_be": s["be"] / j,
            "moy_home_bm": s["home_bm"] / home_j,
            "moy_home_be": s["home_be"] / home_j,
            "moy_away_bm": s["away_bm"] / away_j,
            "moy_away_be": s["away_be"] / away_j,
            "force": (s["bm"] - s["be"]) / j,
            "recent_form": form_score,
            "recent_gf_avg": recent_gf,
            "recent_ga_avg": recent_ga,
            "recent_wins": recent_wins,
            "recent_draws": recent_draws,
            "recent_losses": recent_losses,
            "over_25_ratio": s["over_25_for"] / j,
            "home_over_25_ratio": s["home_over_25"] / home_j if home_j > 0 else 0.5,
            "away_over_25_ratio": s["away_over_25"] / away_j if away_j > 0 else 0.5,
            "pair_ratio": (s["home_pair"] + s["away_pair"]) / j,
            "goals_for_dist": {k: v / j for k, v in s["goals_for_dist"].items()},
            "goals_against_dist": {k: v / j for k, v in s["goals_against_dist"].items()},
            "home_win_rate": s["home_wins"] / home_j,
            "home_draw_rate": s["home_draws"] / home_j,
            "home_loss_rate": s["home_losses"] / home_j,
            "away_win_rate": s["away_wins"] / away_j,
            "away_draw_rate": s["away_draws"] / away_j,
            "away_loss_rate": s["away_losses"] / away_j,
        }
    return result


def calculer_elo(donnees, k_factor=32, initial=1500):
    max_round = 0
    for d in donnees:
        r = int(d.get("round", 0))
        if r > max_round:
            max_round = r

    elo = {}
    for d in donnees:
        h = d.get("home_team", "")
        a = d.get("away_team", "")
        if not h or h == "?" or not a or a == "?":
            continue

        rnd = int(d.get("round", 0))

        for t in [h, a]:
            if t not in elo:
                elo[t] = {"rating": initial, "matches": 0, "history": []}

        sd = d["score_final_dom"]
        se = d["score_final_ext"]

        elo_h = elo[h]["rating"]
        elo_a = elo[a]["rating"]

        expected_h = 1.0 / (1.0 + 10 ** ((elo_a - elo_h) / 400.0))
        expected_a = 1.0 - expected_h

        if sd > se:
            score_h, score_a = 1.0, 0.0
        elif se > sd:
            score_h, score_a = 0.0, 1.0
        else:
            score_h, score_a = 0.5, 0.5

        elo[h]["rating"] = elo_h + k_factor * (score_h - expected_h)
        elo[a]["rating"] = elo_a + k_factor * (score_a - expected_a)
        elo[h]["matches"] += 1
        elo[a]["matches"] += 1
        elo[h]["history"].append({"round": rnd, "rating": elo[h]["rating"], "delta": k_factor * (score_h - expected_h)})
        elo[a]["history"].append({"round": rnd, "rating": elo[a]["rating"], "delta": k_factor * (score_a - expected_a)})

    return {t: e["rating"] for t, e in elo.items()}


def calculer_h2h(donnees):
    h2h = {}
    for d in donnees:
        h = d.get("home_team", "")
        a = d.get("away_team", "")
        if not h or h == "?" or not a or a == "?":
            continue

        sd = d["score_final_dom"]
        se = d["score_final_ext"]
        total = sd + se
        rnd = int(d.get("round", 0))

        key = tuple(sorted([h, a]))
        if key not in h2h:
            h2h[key] = {"matches": [], "team1": key[0], "team2": key[1]}

        h2h[key]["matches"].append({
            "round": rnd,
            "home": h, "away": a,
            "home_goals": sd, "away_goals": se,
            "total": total,
        })

    result = {}
    for key, data in h2h.items():
        t1, t2 = data["team1"], data["team2"]
        matches = data["matches"]

        t1_wins = 0
        t2_wins = 0
        draws = 0
        t1_goals = 0
        t2_goals = 0

        for m in matches:
            if m["home"] == t1:
                g1, g2 = m["home_goals"], m["away_goals"]
            else:
                g1, g2 = m["away_goals"], m["home_goals"]

            t1_goals += g1
            t2_goals += g2
            if g1 > g2:
                t1_wins += 1
            elif g2 > g1:
                t2_wins += 1
            else:
                draws += 1

        n = len(matches)
        result[key] = {
            "n_matches": n,
            f"{t1}_wins": t1_wins / n if n > 0 else 0.33,
            f"{t2}_wins": t2_wins / n if n > 0 else 0.33,
            "draws": draws / n if n > 0 else 0.33,
            f"{t1}_avg_goals": t1_goals / n if n > 0 else 1.5,
            f"{t2}_avg_goals": t2_goals / n if n > 0 else 1.5,
            "avg_total": (t1_goals + t2_goals) / n if n > 0 else 3.0,
        }

    return result


def calculer_tendances(donnees, window=5):
    max_round = 0
    for d in donnees:
        r = int(d.get("round", 0))
        if r > max_round:
            max_round = r

    teams = {}
    for d in donnees:
        h = d.get("home_team", "")
        a = d.get("away_team", "")
        if not h or h == "?" or not a or a == "?":
            continue

        rnd = int(d.get("round", 0))
        sd = d["score_final_dom"]
        se = d["score_final_ext"]

        for t in [h, a]:
            if t not in teams:
                teams[t] = []

        teams[h].append({"round": rnd, "gf": sd, "ga": se, "is_home": True})
        teams[a].append({"round": rnd, "gf": se, "ga": sd, "is_home": False})

    result = {}
    for t, matches in teams.items():
        matches.sort(key=lambda x: x["round"])

        if len(matches) < 3:
            result[t] = {
                "gf_trend": 0, "ga_trend": 0, "total_trend": 0,
                "gf_consistency": 1.0, "ga_consistency": 1.0,
                "home_form": 0.5, "away_form": 0.5,
                "momentum": 0,
            }
            continue

        gf_list = [m["gf"] for m in matches]
        ga_list = [m["ga"] for m in matches]
        total_list = [m["gf"] + m["ga"] for m in matches]

        recent = matches[-window:]
        older = matches[:-window] if len(matches) > window else matches[:max(len(matches)//2, 1)]

        recent_gf = sum(m["gf"] for m in recent) / len(recent)
        older_gf = sum(m["gf"] for m in older) / len(older)
        recent_ga = sum(m["ga"] for m in recent) / len(recent)
        older_ga = sum(m["ga"] for m in older) / len(older)
        recent_total = sum(m["gf"] + m["ga"] for m in recent) / len(recent)
        older_total = sum(m["gf"] + m["ga"] for m in older) / len(older)

        gf_trend = recent_gf - older_gf
        ga_trend = recent_ga - older_ga
        total_trend = recent_total - older_total

        def stdev(vals):
            if len(vals) < 2:
                return 0
            m = sum(vals) / len(vals)
            return (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5

        gf_consistency = 1.0 / (1.0 + stdev(gf_list))
        ga_consistency = 1.0 / (1.0 + stdev(ga_list))

        home_matches = [m for m in matches if m["is_home"]]
        away_matches = [m for m in matches if not m["is_home"]]

        def calc_form(ms):
            if not ms:
                return 0.5
            recent_ms = ms[-window:]
            pts = 0
            for m in recent_ms:
                if m["gf"] > m["ga"]:
                    pts += 3
                elif m["gf"] == m["ga"]:
                    pts += 1
            return pts / (len(recent_ms) * 3)

        home_form = calc_form(home_matches)
        away_form = calc_form(away_matches)

        last_5 = matches[-5:]
        momentum = 0
        for i, m in enumerate(last_5):
            weight = (i + 1) / len(last_5)
            if m["gf"] > m["ga"]:
                momentum += weight
            elif m["gf"] < m["ga"]:
                momentum -= weight
        momentum /= len(last_5)

        result[t] = {
            "gf_trend": gf_trend,
            "ga_trend": ga_trend,
            "total_trend": total_trend,
            "gf_consistency": gf_consistency,
            "ga_consistency": ga_consistency,
            "home_form": home_form,
            "away_form": away_form,
            "momentum": momentum,
        }

    return result


def extraire_cotes(event):
    cotes = {}
    cotes_all = {}
    for bet_type in event.get("eventBetTypes", []):
        name = bet_type.get("name", "")
        items = bet_type.get("eventBetTypeItems", [])

        market = {}
        for item in items:
            sn = item.get("shortName", "")
            odds = item.get("odds", 0)
            if odds and odds > 0:
                market[sn] = odds

        if market:
            cotes_all[name] = market

        if name == "1X2":
            for item in items:
                sn = item["shortName"]
                if sn == "1":
                    cotes["cote_1"] = item["odds"]
                elif sn == "X":
                    cotes["cote_X"] = item["odds"]
                elif sn == "2":
                    cotes["cote_2"] = item["odds"]

        elif name == "+/-":
            for item in items:
                sn = item["shortName"]
                if "> 1.5" in sn:
                    cotes["over_1.5"] = item["odds"]
                elif "< 1.5" in sn:
                    cotes["under_1.5"] = item["odds"]
                elif "> 2.5" in sn:
                    cotes["over_2.5"] = item["odds"]
                elif "< 2.5" in sn:
                    cotes["under_2.5"] = item["odds"]
                elif "> 3.5" in sn:
                    cotes["over_3.5"] = item["odds"]
                elif "< 3.5" in sn:
                    cotes["under_3.5"] = item["odds"]

        elif name == "Total de buts":
            for item in items:
                cotes[f"total_{item['shortName']}"] = item["odds"]

        elif name == "Double Chance":
            for item in items:
                sn = item["shortName"]
                if sn == "1X":
                    cotes["dc_1X"] = item["odds"]
                elif sn == "X2":
                    cotes["dc_X2"] = item["odds"]
                elif sn == "12":
                    cotes["dc_12"] = item["odds"]

        elif name == "Pair/Impair":
            for item in items:
                sn = item["shortName"]
                if sn == "Pair":
                    cotes["pair"] = item["odds"]
                elif sn == "Impair":
                    cotes["impair"] = item["odds"]

        elif name == "G/NG":
            for item in items:
                sn = item["shortName"]
                if sn == "Oui":
                    cotes["btts_oui"] = item["odds"]
                elif sn == "Non":
                    cotes["btts_non"] = item["odds"]

    cotes["cotes_all"] = cotes_all
    return cotes

def cotes_vers_proba(cotes):
    probas = {}

    if "cote_1" in cotes and "cote_X" in cotes and "cote_2" in cotes:
        inv_1 = 1.0 / cotes["cote_1"]
        inv_X = 1.0 / cotes["cote_X"]
        inv_2 = 1.0 / cotes["cote_2"]
        total = inv_1 + inv_X + inv_2
        probas["prob_dom"] = inv_1 / total
        probas["prob_nul"] = inv_X / total
        probas["prob_ext"] = inv_2 / total

    for key in ("over_1.5", "over_2.5", "over_3.5"):
        if key in cotes:
            probas[f"prob_{key.replace('.', '')}"] = 1.0 / cotes[key]
            under_key = key.replace("over", "under")
            under_cote_key = under_key
            if under_cote_key in cotes:
                probas[f"prob_{under_cote_key.replace('.', '')}"] = 1.0 / cotes[under_cote_key]

    if "pair" in cotes and "impair" in cotes:
        inv_pair = 1.0 / cotes["pair"]
        inv_impair = 1.0 / cotes["impair"]
        total_pi = inv_pair + inv_impair
        probas["prob_pair"] = inv_pair / total_pi
        probas["prob_impair"] = inv_impair / total_pi

    if "btts_oui" in cotes and "btts_non" in cotes:
        inv_oui = 1.0 / cotes["btts_oui"]
        inv_non = 1.0 / cotes["btts_non"]
        total_btts = inv_oui + inv_non
        probas["prob_btts_oui"] = inv_oui / total_btts
        probas["prob_btts_non"] = inv_non / total_btts

    return probas

def predire_match(stats, probas, home_team, away_team):
    prob_dom_odds = probas.get("prob_dom", stats["v_dom"])
    prob_nul_odds = probas.get("prob_nul", stats["nuls"])
    prob_ext_odds = probas.get("prob_ext", stats["v_ext"])

    base_total = stats["moy_buts"]
    team_stats = stats.get("team_stats", {})
    elo_ratings = stats.get("elo_ratings", {})
    h2h_stats = stats.get("h2h_stats", {})
    tendances = stats.get("tendances", {})

    home_info = team_stats.get(home_team)
    away_info = team_stats.get(away_team)
    h_trend = tendances.get(home_team, {})
    a_trend = tendances.get(away_team, {})

    elo_home = elo_ratings.get(home_team, 1500)
    elo_away = elo_ratings.get(away_team, 1500)
    elo_expected_home = 1.0 / (1.0 + 10 ** ((elo_away - elo_home) / 400.0))

    h2h_key = tuple(sorted([home_team, away_team]))
    h2h = h2h_stats.get(h2h_key, None)

    if home_info and away_info:
        home_attack = home_info["moy_home_bm"]
        home_defense = home_info["moy_home_be"]
        away_attack = away_info["moy_away_bm"]
        away_defense = away_info["moy_away_be"]

        all_attack = [s["moy_bm"] for s in team_stats.values()]
        avg_attack = sum(all_attack) / max(len(all_attack), 1)

        h_factor = home_attack / max(avg_attack, 0.1)
        a_factor = away_attack / max(avg_attack, 0.1)

        h_form_home = h_trend.get("home_form", home_info["recent_form"])
        a_form_away = a_trend.get("away_form", away_info["recent_form"])
        form_diff = h_form_home - a_form_away

        h_momentum = h_trend.get("momentum", 0)
        a_momentum = a_trend.get("momentum", 0)

        h_consistency = (h_trend.get("gf_consistency", 0.5) + h_trend.get("ga_consistency", 0.5)) / 2.0
        a_consistency = (a_trend.get("gf_consistency", 0.5) + a_trend.get("ga_consistency", 0.5)) / 2.0

        h_gf_trend = h_trend.get("gf_trend", 0)
        h_ga_trend = h_trend.get("ga_trend", 0)
        a_gf_trend = a_trend.get("gf_trend", 0)
        a_ga_trend = a_trend.get("ga_trend", 0)

        h_recent_gf = home_info["recent_gf_avg"]
        h_recent_ga = home_info["recent_ga_avg"]
        a_recent_gf = away_info["recent_gf_avg"]
        a_recent_ga = away_info["recent_ga_avg"]

        lambda_dom_attack = home_attack * 0.5 + h_recent_gf * 0.3 + max(0, h_gf_trend) * 0.2
        lambda_dom_defense_factor = away_defense * 0.5 + a_recent_ga * 0.3 + max(0, a_ga_trend) * 0.2
        lambda_ext_attack = away_attack * 0.5 + a_recent_gf * 0.3 + max(0, a_gf_trend) * 0.2
        lambda_ext_defense_factor = home_defense * 0.5 + h_recent_ga * 0.3 + max(0, h_ga_trend) * 0.2

        lambda_dom_base = (lambda_dom_attack + lambda_dom_defense_factor) / 2.0
        lambda_ext_base = (lambda_ext_attack + lambda_ext_defense_factor) / 2.0

        lambda_dom_base *= (0.6 + 0.4 * h_factor)
        lambda_ext_base *= (0.6 + 0.4 * a_factor)

        form_adjust = form_diff * 0.18
        momentum_adjust = (h_momentum - a_momentum) * 0.12
        lambda_dom_base += form_adjust + momentum_adjust
        lambda_ext_base -= (form_adjust + momentum_adjust)

        if h2h and h2h["n_matches"] >= 2:
            h2h_weight = min(h2h["n_matches"] / 6.0, 1.0) * 0.15
            h2h_home_wins = h2h.get(f"{home_team}_wins", 0.33)
            h2h_avg_total = h2h.get("avg_total", base_total)
            lambda_dom_base *= (1.0 + (h2h_home_wins - 0.33) * h2h_weight * 2)
            lambda_ext_base *= (1.0 + ((1 - h2h_home_wins - 0.33) - 0.33) * h2h_weight * 2)

        team_total = lambda_dom_base + lambda_ext_base
        team_total = max(0.5, min(team_total, 5.5))
    else:
        lambda_dom_base = None
        lambda_ext_base = None
        h_consistency = 0.5
        a_consistency = 0.5
        form_diff = 0
        team_total = base_total

    h_over25 = home_info["over_25_ratio"] if home_info else 0.5
    a_over25 = away_info["over_25_ratio"] if away_info else 0.5
    match_over25_tendency = (h_over25 + a_over25) / 2.0

    elo_total_adjust = elo_expected_home * 0.15
    elo_total_adjust = max(-0.3, min(elo_total_adjust, 0.3))

    h2h_total_adjust = 0
    if h2h and h2h["n_matches"] >= 2:
        h2h_total_adjust = (h2h["avg_total"] - base_total) * 0.1

    trend_total_adjust = 0
    if home_info and away_info:
        trend_total_adjust = (h_trend.get("total_trend", 0) + a_trend.get("total_trend", 0)) * 0.08

    o25_implied = probas.get("prob_over_25", None)
    if o25_implied is not None:
        odds_total = 2.5 + (o25_implied - 0.5) * 2.0
        odds_total = max(1.5, min(odds_total, 5.0))
        target_total = (team_total * 0.45 + base_total * 0.10 + odds_total * 0.25 +
                       match_over25_tendency * 4.0 * 0.10 + elo_total_adjust * 2.0 +
                       h2h_total_adjust + trend_total_adjust)
    else:
        target_total = (team_total * 0.65 + base_total * 0.12 + match_over25_tendency * 4.0 * 0.12 +
                       elo_total_adjust * 2.0 + h2h_total_adjust + trend_total_adjust)

    target_total = max(0.5, min(target_total, 5.5))

    draw_rate_hist = stats.get("draw_rate", 0.26)
    home_win_rate_hist = stats.get("home_win_rate", 0.46)
    avg_goals_hist = stats.get("moy_buts", 2.5)

    if lambda_dom_base is not None:
        total_team = lambda_dom_base + lambda_ext_base
        if total_team > 0:
            dom_ratio = lambda_dom_base / total_team
        else:
            dom_ratio = 0.5

        h_home_wr = home_info["home_win_rate"]
        a_away_lr = away_info["away_loss_rate"]
        wr_ratio = (h_home_wr + a_away_lr) / 2.0

        odds_based = prob_dom_odds / max(prob_dom_odds + prob_ext_odds, 0.01)

        elo_based = elo_expected_home

        h2h_adjust = 0
        if h2h and h2h["n_matches"] >= 2:
            h2h_home_wr = h2h.get(f"{home_team}_wins", 0.33)
            h2h_adjust = (h2h_home_wr - 0.33) * 0.1

        dom_ratio = (dom_ratio * 0.35 + odds_based * 0.25 + wr_ratio * 0.15 +
                    elo_based * 0.15 + (0.5 + form_diff * 0.2) * 0.10 + h2h_adjust)
    else:
        log_ratio = math.log(max(prob_dom_odds, 0.05) / max(prob_ext_odds, 0.05))
        log_ratio = max(-2.0, min(log_ratio, 2.0))
        elo_log = math.log(max(elo_expected_home, 0.05) / max(1 - elo_expected_home, 0.05))
        elo_log = max(-2.0, min(elo_log, 2.0))
        dom_ratio = 0.5 + (log_ratio * 0.10 + elo_log * 0.05)

    dom_ratio = max(0.33, min(dom_ratio, 0.78))

    lambda_dom = target_total * dom_ratio
    lambda_ext = target_total * (1.0 - dom_ratio)

    home_advantage_bonus = 0.10
    lambda_dom += home_advantage_bonus
    lambda_ext -= home_advantage_bonus * 0.15

    consistency_avg = (h_consistency + a_consistency) / 2.0
    spread_factor = 0.85 + consistency_avg * 0.3
    lambda_dom *= spread_factor
    lambda_ext *= spread_factor

    lambda_dom = max(0.2, min(lambda_dom, 5.5))
    lambda_ext = max(0.2, min(lambda_ext, 5.5))

    scores = []

    draw_boost = 1.0
    zero_zero_boost = 1.0
    low_scoring_factor = 1.0
    parity_factor = 1.0

    if draw_rate_hist > 0.30:
        draw_boost = 1.0 + (draw_rate_hist - 0.26) * 0.35
        parity_factor = 1.0 + (0.46 - home_win_rate_hist) * 0.20
        if draw_rate_hist > 0.35:
            zero_zero_boost = 1.0 + (draw_rate_hist - 0.30) * 0.30

    for hd in range(6):
        for ad in range(6):
            p_dom = math.exp(-lambda_dom)
            for k in range(1, hd + 1):
                p_dom *= lambda_dom / k
            p_ext = math.exp(-lambda_ext)
            for k in range(1, ad + 1):
                p_ext *= lambda_ext / k

            p_score = p_dom * p_ext

            if hd == ad:
                p_score *= draw_boost
                if hd == 0:
                    p_score *= zero_zero_boost
            else:
                if hd == 0 or ad == 0:
                    p_score *= low_scoring_factor
                goal_diff = abs(hd - ad)
                if goal_diff == 1:
                    p_score *= parity_factor

            hist_factor = 1.0
            if (hd, ad) in stats["score_dist"]:
                hist_factor = 1.0 + (stats["score_dist"][(hd, ad)] / stats["total_matchs"]) * 0.3

            if home_info and away_info:
                team_adj = 1.0
                h_gf = home_info["goals_for_dist"].get(hd if hd < 5 else "4+", 0)
                h_ga = home_info["goals_against_dist"].get(ad if ad < 5 else "4+", 0)
                a_gf = away_info["goals_for_dist"].get(ad if ad < 5 else "4+", 0)
                a_ga = away_info["goals_against_dist"].get(hd if hd < 5 else "4+", 0)
                team_adj *= (1.0 + h_gf * 0.12 + h_ga * 0.12 + a_gf * 0.12 + a_ga * 0.12)

                if h2h and h2h["n_matches"] >= 2:
                    h2h_adj = 1.0
                    h2h_avg_h = h2h.get(f"{home_team}_avg_goals", 1.5)
                    h2h_avg_a = h2h.get(f"{away_team}_avg_goals", 1.5)
                    if abs(hd - h2h_avg_h) < 1.5:
                        h2h_adj *= 1.08
                    if abs(ad - h2h_avg_a) < 1.5:
                        h2h_adj *= 1.08
                    team_adj *= h2h_adj

                p_score *= team_adj

            p_score *= hist_factor
            scores.append((hd, ad, p_score))

    total_p = sum(p for _, _, p in scores)
    scores = [(d, a, p / total_p) for d, a, p in scores]
    scores.sort(key=lambda x: -x[2])

    total_by_goals = {}
    for hd, ad, p in scores:
        total = hd + ad
        if total not in total_by_goals:
            total_by_goals[total] = {"prob": 0, "best_score": (hd, ad), "best_p": 0}
        total_by_goals[total]["prob"] += p
        if p > total_by_goals[total]["best_p"]:
            total_by_goals[total]["best_p"] = p
            total_by_goals[total]["best_score"] = (hd, ad)

    best_total = max(total_by_goals.keys(), key=lambda t: total_by_goals[t]["prob"])
    best_d, best_a = total_by_goals[best_total]["best_score"]
    best_p = total_by_goals[best_total]["prob"]
    total_buts = best_total

    if best_d > best_a:
        resultat = "VICTOIRE DOMICILE (1)"
        res_code = "1"
    elif best_a > best_d:
        resultat = "VICTOIRE EXTERIEUR (2)"
        res_code = "2"
    else:
        resultat = "MATCH NUL (X)"
        res_code = "X"

    p_over_15 = sum(p for d, a, p in scores if d + a > 1.5)
    p_over_25 = sum(p for d, a, p in scores if d + a > 2.5)
    p_over_35 = sum(p for d, a, p in scores if d + a > 3.5)
    p_under_15 = 1.0 - p_over_15
    p_under_25 = 1.0 - p_over_25
    p_under_35 = 1.0 - p_over_35

    if home_team == "Mali" or away_team == "Mali":
        p_under_35 = min(p_under_35 * 1.12, 0.99)
        p_under_25 = min(p_under_25 * 1.08, 0.99)
        p_over_35 = 1.0 - p_under_35
        p_over_25 = 1.0 - p_under_25

    OU_CALIBRATION_FACTOR = 1.85
    p_over_25_raw = p_over_25
    p_over_25_calibrated = min(p_over_25 * OU_CALIBRATION_FACTOR, 0.88)
    p_under_25_calibrated = 1.0 - p_over_25_calibrated

    odds_over_25 = probas.get("prob_over_25", None)
    odds_under_25 = probas.get("prob_under_25", None)
    if odds_over_25 is not None and odds_over_25 > 0:
        p_over_25 = p_over_25_calibrated * 0.35 + odds_over_25 * 0.65
        p_under_25 = 1.0 - p_over_25
    else:
        p_over_25 = p_over_25_calibrated
        p_under_25 = p_under_25_calibrated

    OU_BASELINE = 0.287
    cote_over_25 = 1.0 / odds_over_25 if odds_over_25 and odds_over_25 > 0 else 0

    if cote_over_25 > 0:
        if cote_over_25 < 1.70:
            ou_pred = "Over 2.5"
            ou_confidence = min(p_over_25 * 100 + 15, 95)
        elif cote_over_25 < 3.20 and p_over_25 > OU_BASELINE * 0.95:
            ou_pred = "Over 2.5"
            ou_confidence = min(p_over_25 * 100 + 5, 90)
        elif p_over_25 > OU_BASELINE * 1.15:
            ou_pred = "Over 2.5"
            ou_confidence = min(p_over_25 * 100, 85)
        else:
            ou_pred = "Under 2.5"
            ou_confidence = min(p_under_25 * 100, 95)
    else:
        if p_over_25 > OU_BASELINE * 1.20:
            ou_pred = "Over 2.5"
            ou_confidence = min(p_over_25 * 100, 88)
        else:
            ou_pred = "Under 2.5"
            ou_confidence = min(p_under_25 * 100, 95)

    p_over_35_cal = min(p_over_35 * OU_CALIBRATION_FACTOR * 0.9, 0.80)
    odds_over_35 = probas.get("prob_over_35", None)
    if odds_over_35 is not None and odds_over_35 > 0:
        p_over_35 = p_over_35_cal * 0.40 + odds_over_35 * 0.60
    else:
        p_over_35 = p_over_35_cal
    p_under_35 = 1.0 - p_over_35

    p_pair_raw = sum(p for d, a, p in scores if (d + a) % 2 == 0)
    p_impair_raw = 1.0 - p_pair_raw
    p_pair = p_pair_raw
    p_impair = p_impair_raw

    p_btts_poisson = sum(p for d, a, p in scores if d > 0 and a > 0)
    p_btts_non_poisson = 1.0 - p_btts_poisson

    prob_btts_oui_implied = probas.get("prob_btts_oui", None)
    prob_btts_non_implied = probas.get("prob_btts_non", None)

    if prob_btts_oui_implied is not None and prob_btts_oui_implied > 0:
        BTTS_BLEND = 0.40
        p_btts_oui = p_btts_poisson * (1 - BTTS_BLEND) + prob_btts_oui_implied * BTTS_BLEND
        p_btts_non = 1.0 - p_btts_oui
    else:
        p_btts_oui = p_btts_poisson
        p_btts_non = p_btts_non_poisson

    btts_source = "odds+poisson" if prob_btts_oui_implied is not None else "poisson"

    if p_btts_oui >= 0.62:
        btts_pred = "BTTS Oui"
        btts_confidence = min(p_btts_oui * 100, 92)
    elif p_btts_non >= 0.62:
        btts_pred = "BTTS Non"
        btts_confidence = min(p_btts_non * 100, 92)
    elif p_btts_oui > p_btts_non:
        btts_pred = "BTTS Oui"
        btts_confidence = min(p_btts_oui * 100, 85)
    else:
        btts_pred = "BTTS Non"
        btts_confidence = min(p_btts_non * 100, 85)

    prob_dom = sum(p for d, a, p in scores if d > a)
    prob_nul = sum(p for d, a, p in scores if d == a)
    prob_ext = sum(p for d, a, p in scores if d < a)

    p_dc_1X = prob_dom + prob_nul
    p_dc_X2 = prob_nul + prob_ext
    p_dc_12 = prob_dom + prob_ext

    confidence = best_p
    confidence_pct = confidence * 100

    if confidence_pct >= 25:
        alert_level = "HAUTE"
        alert_color = "#e74c3c"
    elif confidence_pct >= 18:
        alert_level = "MOYENNE"
        alert_color = "#f39c12"
    else:
        alert_level = "FAIBLE"
        alert_color = "#27ae60"

    top_scores = []
    seen = set()
    for d, a, p in scores:
        if (d, a) not in seen:
            seen.add((d, a))
            top_scores.append({"dom": d, "ext": a, "prob": round(p * 100, 1)})
        if len(top_scores) >= 5:
            break

    total_predicted = sum(p * (d + a) for d, a, p in scores)

    result_obj = {
        "home_team": home_team,
        "away_team": away_team,
        "score_pred": f"{best_d}-{best_a}",
        "score_dom": best_d,
        "score_ext": best_a,
        "resultat": resultat,
        "res_code": res_code,
        "total_buts": total_buts,
        "total_buts_pred": round(total_predicted, 1),
        "confidence": round(confidence_pct, 1),
        "ou_confidence": round(ou_confidence, 1),
        "ou_pred": ou_pred,
        "alert_level": alert_level,
        "alert_color": alert_color,
        "top_scores": top_scores,
        "prob_over_15": round(p_over_15 * 100, 1),
        "prob_over_25": round(p_over_25 * 100, 1),
        "prob_over_35": round(p_over_35 * 100, 1),
        "prob_under_15": round(p_under_15 * 100, 1),
        "prob_under_25": round(p_under_25 * 100, 1),
        "prob_under_35": round(p_under_35 * 100, 1),
        "prob_pair": round(p_pair * 100, 1),
        "prob_impair": round(p_impair * 100, 1),
        "prob_btts_oui": round(p_btts_oui * 100, 1),
        "prob_btts_non": round(p_btts_non * 100, 1),
        "btts_pred": btts_pred,
        "btts_confidence": round(btts_confidence, 1),
        "btts_source": btts_source,
        "prob_dom": round(prob_dom * 100, 1),
        "prob_nul": round(prob_nul * 100, 1),
        "prob_ext": round(prob_ext * 100, 1),
        "prob_dc_1X": round(p_dc_1X * 100, 1),
        "prob_dc_X2": round(p_dc_X2 * 100, 1),
        "prob_dc_12": round(p_dc_12 * 100, 1),
        "dc_pred": "",
        "dc_confidence": 0,
        "cotes": {
            "dom": round(1 / max(prob_dom, 0.01), 2),
            "nul": round(1 / max(prob_nul, 0.01), 2),
            "ext": round(1 / max(prob_ext, 0.01), 2),
            "cote_1": round(1 / max(prob_dom, 0.01), 2),
            "cote_X": round(1 / max(prob_nul, 0.01), 2),
            "cote_2": round(1 / max(prob_ext, 0.01), 2),
        },
    }

    if home_info and away_info:
        result_obj["home_form"] = h_trend.get("home_form", 0.5)
        result_obj["away_form"] = a_trend.get("away_form", 0.5)
        result_obj["home_over25"] = home_info["over_25_ratio"]
        result_obj["away_over25"] = away_info["over_25_ratio"]
        result_obj["home_elo"] = round(elo_home)
        result_obj["away_elo"] = round(elo_away)
        result_obj["home_momentum"] = round(h_momentum, 2)
        result_obj["away_momentum"] = round(a_momentum, 2)
        result_obj["home_consistency"] = round(h_consistency, 2)
        result_obj["away_consistency"] = round(a_consistency, 2)
        result_obj["home_gf_trend"] = round(h_gf_trend, 2)
        result_obj["away_gf_trend"] = round(a_gf_trend, 2)
        result_obj["home_draw_rate"] = round(home_info.get("home_draw_rate", 0.33) * 100, 1)
        result_obj["away_draw_rate"] = round(away_info.get("away_draw_rate", 0.33) * 100, 1)
        if h2h and h2h["n_matches"] >= 3:
            result_obj["h2h_matches"] = h2h["n_matches"]
            away_wins_key = f"{away_team}_wins"
            home_wins_key = f"{home_team}_wins"
            result_obj["h2h_away_wr"] = round(h2h.get(away_wins_key, 0.33) * 100, 1)
            result_obj["h2h_home_wr"] = round(h2h.get(home_wins_key, 0.33) * 100, 1)
            result_obj["h2h_draws"] = round(h2h.get("draws", 0.33) * 100, 1)
            result_obj["h2h_avg_total"] = round(h2h.get("avg_total", 2.5), 1)
        else:
            result_obj["h2h_matches"] = 0
            result_obj["h2h_away_wr"] = 33.0
            result_obj["h2h_home_wr"] = 33.0
            result_obj["h2h_draws"] = 33.0
            result_obj["h2h_avg_total"] = 2.5

    dc_options = [
        ("1X", p_dc_1X, "Dom ou Nul"),
        ("X2", p_dc_X2, "Nul ou Ext"),
        ("12", p_dc_12, "Dom ou Ext"),
    ]

    dc_1X_score = p_dc_1X
    dc_X2_score = p_dc_X2 * 0.92
    dc_12_score = p_dc_12 * 0.88

    if dc_X2_score > dc_1X_score and p_dc_X2 - p_dc_1X < 0.05:
        dc_X2_score = dc_1X_score - 0.01

    dc_scored = [
        ("1X", dc_1X_score, p_dc_1X, "Dom ou Nul"),
        ("X2", dc_X2_score, p_dc_X2, "Nul ou Ext"),
        ("12", dc_12_score, p_dc_12, "Dom ou Ext"),
    ]
    dc_scored.sort(key=lambda x: x[1], reverse=True)
    best_dc = dc_scored[0]

    result_obj["dc_pred"] = best_dc[0]
    result_obj["dc_confidence"] = round(best_dc[2] * 100, 1)
    result_obj["dc_label"] = best_dc[3]
    result_obj["dc_all"] = [
        {"code": c, "prob": round(p * 100, 1), "label": l}
        for c, p, l in dc_options
    ]

    return result_obj

def fetch_live_matches():
    try:
        response = requests.get(MATCHES_URL, headers=HEADERS, timeout=10)
        data = response.json()
    except Exception as e:
        return [], str(e)

    rounds = data.get("rounds", [])
    all_matches = []

    for rnd in rounds:
        for event in rnd.get("matches", []):
            home_team = event.get("homeTeam", {}).get("name", "?")
            away_team = event.get("awayTeam", {}).get("name", "?")
            round_num = rnd.get("roundNumber", "?")
            match_id = event.get("id", 0)

            cotes = extraire_cotes(event)
            probas = cotes_vers_proba(cotes)

            all_matches.append({
                "round": round_num,
                "match_id": match_id,
                "home_team": home_team,
                "away_team": away_team,
                "cotes_raw": cotes,
                "probas": probas,
            })

    return all_matches, None

def predire_tous(stats):
    matches, err = fetch_live_matches()
    if err:
        return [], err

    predictions = []
    for m in matches:
        pred = predire_match(stats, m["probas"], m["home_team"], m["away_team"])
        pred["round"] = m["round"]
        pred["match_id"] = m["match_id"]
        pred["cotes_raw"] = m["cotes_raw"]
        pred["cotes_btts_oui"] = m["cotes_raw"].get("btts_oui", 0)
        pred["cotes_btts_non"] = m["cotes_raw"].get("btts_non", 0)

        cr = m["cotes_raw"]
        if cr.get("cote_1") and cr.get("cote_X") and cr.get("cote_2"):
            pred["cotes"]["cote_1"] = cr["cote_1"]
            pred["cotes"]["cote_X"] = cr["cote_X"]
            pred["cotes"]["cote_2"] = cr["cote_2"]
            pred["cotes"]["dom"] = cr["cote_1"]
            pred["cotes"]["nul"] = cr["cote_X"]
            pred["cotes"]["ext"] = cr["cote_2"]

        pred["dc_source"] = "model"
        pred["dc_favori"] = False

        dc_before = pred["dc_pred"]
        croiser_dc_avec_cotes(pred, m["cotes_raw"])
        if pred.get("dc_source") == "odds_cross":
            pred["dc_odds_crossed"] = True
            pred["dc_pred_before_cross"] = dc_before
        else:
            pred["dc_odds_crossed"] = False

        predictions.append(pred)

    candidates = []
    for pred in predictions:
        score = _calc_favori_score(pred)
        if score > 0:
            pred["_favori_score"] = score
            candidates.append(pred)

    candidates.sort(key=lambda p: p["_favori_score"], reverse=True)
    for i, p in enumerate(candidates[:5]):
        p["dc_favori"] = True
        p["dc_favori_rank"] = i + 1

    for p in predictions:
        if "_favori_score" in p:
            del p["_favori_score"]

    return predictions, None


def _calc_favori_score(pred):
    score = pred.get("dc_confidence", 0)

    if pred.get("dc_odds_crossed"):
        score -= 25

    res_code = pred.get("res_code", "")
    ml_pred = pred.get("ml_pred_1x2", "")
    dc_pred = pred.get("dc_pred", "")

    ml_poisson_agree = False
    if ml_pred and res_code:
        ml_poisson_agree = (ml_pred == res_code)

    dc_compat_ml = False
    dc_compat_poisson = False
    if dc_pred == "1X":
        dc_compat_ml = ml_pred in ("1", "X")
        dc_compat_poisson = res_code in ("1", "X")
    elif dc_pred == "X2":
        dc_compat_ml = ml_pred in ("X", "2")
        dc_compat_poisson = res_code in ("X", "2")
    elif dc_pred == "12":
        dc_compat_ml = ml_pred in ("1", "2")
        dc_compat_poisson = res_code in ("1", "2")

    dc_both_support = dc_compat_ml and dc_compat_poisson

    if not dc_both_support:
        score -= 30

    home_elo = pred.get("home_elo", 1500)
    away_elo = pred.get("away_elo", 1500)
    elo_ok = True
    elo_diff = abs(home_elo - away_elo)
    if dc_pred == "1X":
        elo_ok = (home_elo - away_elo) >= 100
        if not elo_ok:
            score -= 15
    elif dc_pred == "X2":
        elo_ok = (away_elo - home_elo) >= 100
        if not elo_ok:
            score -= 20
        if elo_diff < 50:
            score -= 10

    if dc_pred == "X2":
        prob_ext = pred.get("prob_ext", 33)
        prob_dom = pred.get("prob_dom", 33)
        if prob_ext < prob_dom:
            score -= 25

    if pred.get("dc_odds_crossed") and not dc_both_support:
        return 0

    home_form = pred.get("home_form", 0.5)
    away_form = pred.get("away_form", 0.5)
    home_momentum = pred.get("home_momentum", 0)
    away_momentum = pred.get("away_momentum", 0)

    if dc_pred == "1X":
        if home_form < 0.25 and home_momentum < -1:
            score -= 12
    elif dc_pred == "X2":
        if away_form < 0.25 and away_momentum < -1:
            score -= 12

    if dc_pred == "1X":
        p_dc = pred.get("prob_dc_1X", 50)
        if p_dc > 65:
            score += 5

    return max(score, 0)


def croiser_dc_avec_cotes(pred, cotes_raw):
    dc_1X_odds = cotes_raw.get("dc_1X", 0)
    dc_X2_odds = cotes_raw.get("dc_X2", 0)
    dc_12_odds = cotes_raw.get("dc_12", 0)
    if not (dc_1X_odds and dc_X2_odds and dc_12_odds):
        return

    site_implied = {
        "1X": 1.0 / dc_1X_odds,
        "X2": 1.0 / dc_X2_odds,
        "12": 1.0 / dc_12_odds,
    }
    model_probs = {
        "1X": pred.get("prob_dc_1X", 50) / 100.0,
        "X2": pred.get("prob_dc_X2", 50) / 100.0,
        "12": pred.get("prob_dc_12", 50) / 100.0,
    }

    edges = {}
    for code in ["1X", "X2", "12"]:
        edges[code] = model_probs[code] - site_implied[code]

    model_best = max(model_probs, key=model_probs.get)
    site_best = max(site_implied, key=site_implied.get)

    if model_best == site_best:
        return

    model_second = sorted(model_probs.values(), reverse=True)[1]
    site_second = sorted(site_implied.values(), reverse=True)[1]

    model_margin = model_probs[model_best] - model_second
    site_margin = site_implied[site_best] - site_second

    if site_margin > 0.06 and site_implied[site_best] > model_probs[site_best]:
        best_code = site_best
        best_prob = site_implied[best_code] * 100
        pred["dc_pred"] = best_code
        pred["dc_confidence"] = round(best_prob, 1)
        labels = {"1X": "Dom ou Nul", "X2": "Nul ou Ext", "12": "Dom ou Ext"}
        pred["dc_label"] = labels.get(best_code, "")
        pred["dc_source"] = "odds_cross"
        pred["dc_all"] = [
            {"code": c, "prob": round(p * 100, 1), "label": l}
            for c, p, l in [
                ("1X", model_probs["1X"], "Dom ou Nul"),
                ("X2", model_probs["X2"], "Nul ou Ext"),
                ("12", model_probs["12"], "Dom ou Ext"),
            ]
        ]

    elif edges[model_best] > 0.05:
        pred["dc_source"] = "model_edge"

def predire_equipes(stats, home_team, away_team, cotes_dict=None):
    if cotes_dict:
        probas = cotes_vers_proba(cotes_dict)
    else:
        probas = {}

    pred = predire_match(stats, probas, home_team, away_team)
    return pred
