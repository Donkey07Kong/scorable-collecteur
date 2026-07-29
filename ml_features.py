import os
import json
import math
import requests
import time
import numpy as np
from collections import defaultdict

MODEL_PATH = "ml_ensemble.json"

_ranking_cache = None
_ranking_cache_time = 0

def get_ranking(league_id=8060):
    global _ranking_cache, _ranking_cache_time
    now = time.time()
    if _ranking_cache and (now - _ranking_cache_time < 300):
        return _ranking_cache
    try:
        headers = {
            "accept": "application/json",
            "app-version": "34283",
            "referer": "https://bet261.mg/"
        }
        r = requests.get(f"https://hg-event-api-prod.sporty-tech.net/api/instantleagues/{league_id}/ranking", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            teams = data.get("teams", [])
            _ranking_cache = {}
            for t in teams:
                hist = t.get("history", [])
                form_score = sum(3 if h == "Won" else (1 if h == "Draw" else 0) for h in hist) / max(len(hist) * 3, 1)
                total_matches = t.get("won", 0) + t.get("draw", 0) + t.get("lost", 0)
                win_rate = t.get("won", 0) / max(total_matches, 1)
                _ranking_cache[t["name"]] = {
                    "name": t["name"],
                    "position": t.get("position", 0),
                    "points": t.get("points", 0),
                    "won": t.get("won", 0),
                    "draw": t.get("draw", 0),
                    "lost": t.get("lost", 0),
                    "total_matches": total_matches,
                    "win_rate": win_rate,
                    "form_score": form_score,
                    "history": hist,
                }
            _ranking_cache_time = now
            return _ranking_cache
    except Exception:
        pass
    return _ranking_cache or {}


_elo_cache = {}
_team_stats_cache = {}

def _compute_elo_leakfree(donnees, rnd, k_factor=32, initial=1500):
    cache_key = (id(donnees), rnd)
    if cache_key in _elo_cache:
        return _elo_cache[cache_key]
    elo = {}
    for d in donnees:
        r = int(d.get("round", 0))
        if r >= rnd:
            break
        h = d.get("home_team", "")
        a = d.get("away_team", "")
        if not h or h == "?" or not a or a == "?":
            continue
        sd = d.get("score_final_dom", 0)
        se = d.get("score_final_ext", 0)
        for t in [h, a]:
            if t not in elo:
                elo[t] = initial
        elo_h = elo[h]
        elo_a = elo[a]
        expected_h = 1.0 / (1.0 + 10 ** ((elo_a - elo_h) / 400.0))
        if sd > se:
            score_h, score_a = 1.0, 0.0
        elif se > sd:
            score_h, score_a = 0.0, 1.0
        else:
            score_h, score_a = 0.5, 0.5
        elo[h] = elo_h + k_factor * (score_h - expected_h)
        elo[a] = elo_a + k_factor * (score_a - (1.0 - expected_h))
    _elo_cache[cache_key] = elo
    return elo


def _compute_h2h_leakfree(donnees, h, a, rnd):
    h2h_matches = [d for d in donnees
                    if int(d.get("round", 0)) < rnd
                    and tuple(sorted([d.get("home_team", ""), d.get("away_team", "")])) == tuple(sorted([h, a]))]
    n = len(h2h_matches)
    if n == 0:
        return 0, 0.33, 3.0

    h_wins = 0
    h_goals = 0
    a_goals = 0
    for m in h2h_matches:
        sd = m["score_final_dom"]
        se = m["score_final_ext"]
        home = m.get("home_team", "")
        if home == h:
            h_goals += sd
            a_goals += se
            if sd > se:
                h_wins += 1
        else:
            h_goals += se
            a_goals += sd
            if se > sd:
                h_wins += 1
        if home == a:
            h_goals += se  # wrong, fix below
            a_goals += sd
        # Actually simpler: just count based on h
    # Recompute cleanly
    h_wins = 0
    h_goals = 0
    a_goals = 0
    for m in h2h_matches:
        sd = m["score_final_dom"]
        se = m["score_final_ext"]
        home = m.get("home_team", "")
        if home == h:
            h_goals += sd
            a_goals += se
            if sd > se:
                h_wins += 1
        else:
            h_goals += se
            a_goals += sd
            if se > sd:
                h_wins += 1

    return n, h_wins / n, (h_goals + a_goals) / n


def _compute_team_stats_leakfree(donnees, team, rnd, n_recent=10):
    cache_key = (id(donnees), team, rnd, n_recent)
    if cache_key in _team_stats_cache:
        return _team_stats_cache[cache_key]
    all_matches = [d for d in donnees
                   if (d.get("home_team") == team or d.get("away_team") == team)
                   and int(d.get("round", 0)) < rnd]
    all_matches.sort(key=lambda x: int(x.get("round", 0)), reverse=True)

    recent = all_matches[:n_recent]
    home_matches = [m for m in recent if m.get("home_team") == team]
    away_matches = [m for m in recent if m.get("away_team") == team]

    def calc_rates(matches, team):
        if not matches:
            return 0.33, 0.33, 0.33, 1.5, 1.2, 0.5
        w, d, l = 0, 0, 0
        gf, ga = 0, 0
        for m in matches:
            sd, se = m["score_final_dom"], m["score_final_ext"]
            if m.get("home_team") == team:
                gf += sd; ga += se
                if sd > se: w += 1
                elif sd == se: d += 1
                else: l += 1
            else:
                gf += se; ga += sd
                if se > sd: w += 1
                elif se == sd: d += 1
                else: l += 1
        n = len(matches)
        wins = w / n
        draws = d / n
        losses = l / n
        avg_gf = gf / n
        avg_ga = ga / n
        form = (w * 3 + d) / (n * 3)
        return wins, draws, losses, avg_gf, avg_ga, form

    hw, hd, hl, hgf, hga, hform = calc_rates(home_matches, team)
    aw, ad, al, agf, aga, aform = calc_rates(away_matches, team)
    rw, rd, rl, rgf, rga, rform = calc_rates(recent, team)

    over25 = sum(1 for m in recent if m["score_final_dom"] + m["score_final_ext"] > 2.5) / max(len(recent), 1)
    force = rgf - rga

    result = {
        "home_win_rate": hw, "home_draw_rate": hd, "home_loss_rate": hl,
        "away_win_rate": aw, "away_draw_rate": ad, "away_loss_rate": al,
        "moy_home_bm": hgf, "moy_home_be": hga,
        "moy_away_bm": agf, "moy_away_be": aga,
        "force": force, "recent_form": rform,
        "over_25_ratio": over25,
    }
    _team_stats_cache[cache_key] = result
    return result


def build_features_for_match(donnees, idx, team_stats, elo_ratings, h2h_stats, tendances, all_stats):
    m = donnees[idx]
    h = m.get("home_team", "")
    a = m.get("away_team", "")
    if not h or h == "?" or not a or a == "?":
        return None

    sd = m["score_final_dom"]
    se = m["score_final_ext"]
    total = sd + se
    rnd = int(m.get("round", 0))

    elo_home = elo_ratings.get(h, 1500)
    elo_away = elo_ratings.get(a, 1500)
    elo_diff = elo_home - elo_away

    h2h_n, h2h_h_wr, h2h_avg_total = _compute_h2h_leakfree(donnees, h, a, rnd)

    home_info = _compute_team_stats_leakfree(donnees, h, rnd)
    away_info = _compute_team_stats_leakfree(donnees, a, rnd)

    recent_matches_h = [d for d in donnees if d.get("home_team") == h or d.get("away_team") == h]
    recent_matches_h = [d for d in recent_matches_h if int(d.get("round", 0)) < rnd]
    recent_matches_h.sort(key=lambda x: int(x.get("round", 0)), reverse=True)

    h_last5_gf = []
    h_last5_ga = []
    h_last5_pts = []
    for rm in recent_matches_h[:5]:
        if rm.get("home_team") == h:
            h_last5_gf.append(rm["score_final_dom"])
            h_last5_ga.append(rm["score_final_ext"])
        else:
            h_last5_gf.append(rm["score_final_ext"])
            h_last5_ga.append(rm["score_final_dom"])
        g1 = rm["score_final_dom"] if rm.get("home_team") == h else rm["score_final_ext"]
        g2 = rm["score_final_ext"] if rm.get("home_team") == h else rm["score_final_dom"]
        if g1 > g2:
            h_last5_pts.append(3)
        elif g1 == g2:
            h_last5_pts.append(1)
        else:
            h_last5_pts.append(0)

    recent_matches_a = [d for d in donnees if d.get("home_team") == a or d.get("away_team") == a]
    recent_matches_a = [d for d in recent_matches_a if int(d.get("round", 0)) < rnd]
    recent_matches_a.sort(key=lambda x: int(x.get("round", 0)), reverse=True)

    a_last5_gf = []
    a_last5_ga = []
    a_last5_pts = []
    for rm in recent_matches_a[:5]:
        if rm.get("home_team") == a:
            a_last5_gf.append(rm["score_final_dom"])
            a_last5_ga.append(rm["score_final_ext"])
        else:
            a_last5_gf.append(rm["score_final_ext"])
            a_last5_ga.append(rm["score_final_dom"])
        g1 = rm["score_final_dom"] if rm.get("home_team") == a else rm["score_final_ext"]
        g2 = rm["score_final_ext"] if rm.get("home_team") == a else rm["score_final_dom"]
        if g1 > g2:
            a_last5_pts.append(3)
        elif g1 == g2:
            a_last5_pts.append(1)
        else:
            a_last5_pts.append(0)

    def safe(lst, default=0):
        return sum(lst) / len(lst) if lst else default

    def trend(lst):
        if len(lst) < 2:
            return 0
        first_half = sum(lst[:len(lst)//2]) / max(len(lst)//2, 1)
        second_half = sum(lst[len(lst)//2:]) / max(len(lst) - len(lst)//2, 1)
        return second_half - first_half

    def stdev(lst):
        if len(lst) < 2:
            return 0
        m = sum(lst) / len(lst)
        return (sum((x - m) ** 2 for x in lst) / len(lst)) ** 0.5

    h_home_matches = [d for d in recent_matches_h if d.get("home_team") == h][:5]
    h_away_matches = [d for d in recent_matches_h if d.get("away_team") == h][:5]
    a_home_matches = [d for d in recent_matches_a if d.get("home_team") == a][:5]
    a_away_matches = [d for d in recent_matches_a if d.get("away_team") == a][:5]

    def team_points(matches, team):
        pts = []
        for m in matches:
            if m.get("home_team") == team:
                gf, ga = m["score_final_dom"], m["score_final_ext"]
            else:
                gf, ga = m["score_final_ext"], m["score_final_dom"]
            if gf > ga:
                pts.append(3)
            elif gf == ga:
                pts.append(1)
            else:
                pts.append(0)
        return pts

    h_home_pts = team_points(h_home_matches, h)
    h_away_pts = team_points(h_away_matches, h)
    a_home_pts = team_points(a_home_matches, a)
    a_away_pts = team_points(a_away_matches, a)

    strength_diff = home_info.get("force", 0) - away_info.get("force", 0)
    form_diff = home_info.get("recent_form", 0.5) - away_info.get("recent_form", 0.5)
    home_away_form_diff = home_info.get("home_win_rate", 0.33) - away_info.get("away_win_rate", 0.33)
    h_last5_winrate = sum(1 for p in h_last5_pts if p == 3) / max(len(h_last5_pts), 1)
    a_last5_winrate = sum(1 for p in a_last5_pts if p == 3) / max(len(a_last5_pts), 1)
    momentum_diff = h_last5_winrate - a_last5_winrate
    scoring_diff = home_info.get("moy_home_bm", 1.5) - away_info.get("moy_away_be", 1.5)
    conceding_diff = home_info.get("moy_home_be", 1.2) - away_info.get("moy_away_bm", 1.0)

    ranking = get_ranking()
    n_teams = max(len(ranking), 2) if ranking else 24
    home_ranking = ranking.get(h, {})
    away_ranking = ranking.get(a, {})

    features = [
        elo_home,
        elo_away,
        elo_diff,
        home_info.get("moy_home_bm", 1.5),
        home_info.get("moy_home_be", 1.2),
        away_info.get("moy_away_bm", 1.0),
        away_info.get("moy_away_be", 1.5),
        home_info.get("force", 0),
        away_info.get("force", 0),
        home_info.get("over_25_ratio", 0.5),
        away_info.get("over_25_ratio", 0.5),
        home_info.get("recent_form", 0.5),
        away_info.get("recent_form", 0.5),
        home_info.get("home_win_rate", 0.33),
        home_info.get("home_draw_rate", 0.33),
        home_info.get("home_loss_rate", 0.33),
        away_info.get("away_win_rate", 0.33),
        away_info.get("away_draw_rate", 0.33),
        away_info.get("away_loss_rate", 0.33),
        safe(h_last5_gf),
        safe(h_last5_ga),
        safe(h_last5_pts) / 3.0,
        safe(a_last5_gf),
        safe(a_last5_ga),
        safe(a_last5_pts) / 3.0,
        trend(h_last5_gf),
        trend(h_last5_ga),
        trend(a_last5_gf),
        trend(a_last5_ga),
        stdev(h_last5_gf),
        stdev(h_last5_ga),
        stdev(a_last5_gf),
        stdev(a_last5_ga),
        safe(h_home_pts) / 3.0,
        safe(h_away_pts) / 3.0,
        safe(a_home_pts) / 3.0,
        safe(a_away_pts) / 3.0,
        h2h_n,
        h2h_h_wr,
        h2h_avg_total,
        strength_diff,
        form_diff,
        home_away_form_diff,
        momentum_diff,
        scoring_diff,
        conceding_diff,
        # RANKING FEATURES (from bet261.classement)
        home_ranking.get("position", n_teams / 2),
        away_ranking.get("position", n_teams / 2),
        n_teams + 1 - home_ranking.get("position", n_teams / 2),
        n_teams + 1 - away_ranking.get("position", n_teams / 2),
        home_ranking.get("points", 0),
        away_ranking.get("points", 0),
        home_ranking.get("points", 0) - away_ranking.get("points", 0),
        home_ranking.get("win_rate", 0.33),
        away_ranking.get("win_rate", 0.33),
        home_ranking.get("win_rate", 0.33) - away_ranking.get("win_rate", 0.33),
        home_ranking.get("form_score", 0.33),
        away_ranking.get("form_score", 0.33),
        home_ranking.get("form_score", 0.33) - away_ranking.get("form_score", 0.33),
        abs(home_ranking.get("position", 12) - away_ranking.get("position", 12)),
    ]

    labels = {
        "result": "1" if sd > se else ("2" if se > sd else "X"),
        "over25": 1 if total > 2.5 else 0,
        "over35": 1 if total > 3.5 else 0,
        "pair": 1 if total % 2 == 0 else 0,
        "total_goals": total,
        "home_goals": sd,
        "away_goals": se,
    }

    return features, labels, h, a, rnd


def predire_poisson_fast(team_attack_info, team_defend_info, all_stats):
    if not team_attack_info or not team_defend_info:
        return 3.0
    all_attack = [s["moy_bm"] for s in all_stats.values()]
    avg_attack = sum(all_attack) / max(len(all_attack), 1)
    attack = team_attack_info.get("moy_bm", avg_attack)
    defense = team_defend_info.get("moy_be", avg_attack)
    return (attack + defense) / 2.0


def build_dataset(donnees, team_stats, elo_ratings, h2h_stats, tendances, max_train_round=None):
    X = []
    y_1x2 = []
    y_ou25 = []
    y_ou35 = []
    y_pair = []
    y_total = []
    metadata = []

    running_elo = {}
    elo_k = 32
    elo_init = 1500

    for idx in range(len(donnees)):
        m = donnees[idx]
        h = m.get("home_team", "")
        a = m.get("away_team", "")
        rnd = int(m.get("round", 0))

        if not h or h == "?" or not a or a == "?":
            continue

        for t in [h, a]:
            if t not in running_elo:
                running_elo[t] = elo_init

        elo_snapshot = dict(running_elo)

        result = build_features_for_match(donnees, idx, team_stats, elo_snapshot, h2h_stats, tendances, team_stats)
        if result is None:
            continue

        features, labels, h2, a2, rnd2 = result

        if max_train_round is not None and rnd2 > max_train_round:
            continue

        min_round_needed = 5
        h_matches = sum(1 for d in donnees if (d.get("home_team") == h2 or d.get("away_team") == h2) and int(d.get("round", 0)) < rnd2)
        a_matches = sum(1 for d in donnees if (d.get("home_team") == a2 or d.get("away_team") == a2) and int(d.get("round", 0)) < rnd2)
        if h_matches < min_round_needed or a_matches < min_round_needed:
            continue

        sd = m.get("score_final_dom", 0)
        se = m.get("score_final_ext", 0)
        elo_h = running_elo[h]
        elo_a = running_elo[a]
        exp_h = 1.0 / (1.0 + 10 ** ((elo_a - elo_h) / 400.0))
        if sd > se:
            sh, sa = 1.0, 0.0
        elif se > sd:
            sh, sa = 0.0, 1.0
        else:
            sh, sa = 0.5, 0.5
        running_elo[h] = elo_h + elo_k * (sh - exp_h)
        running_elo[a] = elo_a + elo_k * (sa - (1.0 - exp_h))

        X.append(features)
        y_1x2.append(labels["result"])
        y_ou25.append(labels["over25"])
        y_ou35.append(labels["over35"])
        y_pair.append(labels["pair"])
        y_total.append(labels["total_goals"])
        metadata.append({"home": h2, "away": a2, "round": rnd2, "score": f"{labels['home_goals']}-{labels['away_goals']}"})

    return (np.array(X), np.array(y_1x2), np.array(y_ou25), np.array(y_ou35),
            np.array(y_pair), np.array(y_total), metadata)


FEATURE_NAMES = [
    "elo_home", "elo_away", "elo_diff",
    "h_home_bm", "h_home_be", "a_away_bm", "a_away_be",
    "h_force", "a_force",
    "h_over25", "a_over25",
    "h_form", "a_form",
    "h_home_wr", "h_home_dr", "h_home_lr",
    "a_away_wr", "a_away_dr", "a_away_lr",
    "h_last5_gf", "h_last5_ga", "h_last5_pts",
    "a_last5_gf", "a_last5_ga", "a_last5_pts",
    "h_gf_trend_5", "h_ga_trend_5", "a_gf_trend_5", "a_ga_trend_5",
    "h_gf_stdev", "h_ga_stdev", "a_gf_stdev", "a_ga_stdev",
    "h_home_form", "h_away_form", "a_home_form", "a_away_form",
    "h2h_n", "h2h_h_wr", "h2h_avg_total",
    "strength_diff", "form_diff", "home_away_form_diff",
    "momentum_diff", "scoring_diff", "conceding_diff",
    "h_position", "a_position", "h_inv_position", "a_inv_position",
    "h_points", "a_points", "points_diff",
    "h_win_rate_rank", "a_win_rate_rank", "win_rate_rank_diff",
    "h_form_rank", "a_form_rank", "form_rank_diff",
    "position_gap",
]


def build_features_live(home_team, away_team, current_round, donnees, team_stats, elo_ratings, h2h_stats, tendances):
    if not home_team or not away_team:
        return None

    h = home_team
    a = away_team
    rnd = current_round

    max_round = 0
    for d in donnees:
        r = int(d.get("round", 0))
        if r > max_round:
            max_round = r
    if rnd == 0:
        rnd = max_round + 1

    leakfree_elo = _compute_elo_leakfree(donnees, rnd)
    elo_home = leakfree_elo.get(h, 1500)
    elo_away = leakfree_elo.get(a, 1500)
    elo_diff = elo_home - elo_away

    h2h_n, h2h_h_wr, h2h_avg_total = _compute_h2h_leakfree(donnees, h, a, rnd)
    home_info = _compute_team_stats_leakfree(donnees, h, rnd)
    away_info = _compute_team_stats_leakfree(donnees, a, rnd)

    def get_team_recent(team, limit=5):
        matches = [d for d in donnees if (d.get("home_team") == team or d.get("away_team") == team)
                   and int(d.get("round", 0)) < rnd]
        matches.sort(key=lambda x: int(x.get("round", 0)), reverse=True)
        return matches[:limit]

    recent_h = get_team_recent(h)
    recent_a = get_team_recent(a)

    def safe(lst, default=0):
        return sum(lst) / len(lst) if lst else default

    def trend(lst):
        if len(lst) < 2:
            return 0
        half = len(lst) // 2
        if half == 0:
            return 0
        first_half = sum(lst[:half]) / half
        second_half = sum(lst[half:]) / max(len(lst) - half, 1)
        return second_half - first_half

    def stdev(lst):
        if len(lst) < 2:
            return 0
        m = sum(lst) / len(lst)
        return (sum((x - m) ** 2 for x in lst) / len(lst)) ** 0.5

    def extract_recent_stats(matches, team):
        gf_list, ga_list, pts_list = [], [], []
        for rm in matches:
            if rm.get("home_team") == team:
                gf, ga = rm["score_final_dom"], rm["score_final_ext"]
            else:
                gf, ga = rm["score_final_ext"], rm["score_final_dom"]
            gf_list.append(gf)
            ga_list.append(ga)
            if gf > ga:
                pts_list.append(3)
            elif gf == ga:
                pts_list.append(1)
            else:
                pts_list.append(0)
        return gf_list, ga_list, pts_list

    h_gf, h_ga, h_pts = extract_recent_stats(recent_h, h)
    a_gf, a_ga, a_pts = extract_recent_stats(recent_a, a)

    h_home_matches = [d for d in recent_h if d.get("home_team") == h]
    h_away_matches = [d for d in recent_h if d.get("away_team") == h]
    a_home_matches = [d for d in recent_a if d.get("home_team") == a]
    a_away_matches = [d for d in recent_a if d.get("away_team") == a]

    def team_points(matches, team):
        pts = []
        for m in matches:
            if m.get("home_team") == team:
                gf, ga = m["score_final_dom"], m["score_final_ext"]
            else:
                gf, ga = m["score_final_ext"], m["score_final_dom"]
            if gf > ga:
                pts.append(3)
            elif gf == ga:
                pts.append(1)
            else:
                pts.append(0)
        return pts

    h_home_pts = team_points(h_home_matches, h)
    h_away_pts = team_points(h_away_matches, h)
    a_home_pts = team_points(a_home_matches, a)
    a_away_pts = team_points(a_away_matches, a)

    h_last5_pts = h_pts[:5]
    a_last5_pts = a_pts[:5]
    h_last5_winrate = sum(1 for p in h_last5_pts if p == 3) / max(len(h_last5_pts), 1)
    a_last5_winrate = sum(1 for p in a_last5_pts if p == 3) / max(len(a_last5_pts), 1)

    strength_diff = home_info.get("force", 0) - away_info.get("force", 0)
    form_diff = home_info.get("recent_form", 0.5) - away_info.get("recent_form", 0.5)
    home_away_form_diff = home_info.get("home_win_rate", 0.33) - away_info.get("away_win_rate", 0.33)
    momentum_diff = h_last5_winrate - a_last5_winrate
    scoring_diff = home_info.get("moy_home_bm", 1.5) - away_info.get("moy_away_be", 1.5)
    conceding_diff = home_info.get("moy_home_be", 1.2) - away_info.get("moy_away_bm", 1.0)

    ranking = get_ranking()
    n_teams = max(len(ranking), 2) if ranking else 24
    home_ranking = ranking.get(h, {})
    away_ranking = ranking.get(a, {})

    features = [
        elo_home,
        elo_away,
        elo_diff,
        home_info.get("moy_home_bm", 1.5),
        home_info.get("moy_home_be", 1.2),
        away_info.get("moy_away_bm", 1.0),
        away_info.get("moy_away_be", 1.5),
        home_info.get("force", 0),
        away_info.get("force", 0),
        home_info.get("over_25_ratio", 0.5),
        away_info.get("over_25_ratio", 0.5),
        home_info.get("recent_form", 0.5),
        away_info.get("recent_form", 0.5),
        home_info.get("home_win_rate", 0.33),
        home_info.get("home_draw_rate", 0.33),
        home_info.get("home_loss_rate", 0.33),
        away_info.get("away_win_rate", 0.33),
        away_info.get("away_draw_rate", 0.33),
        away_info.get("away_loss_rate", 0.33),
        safe(h_gf),
        safe(h_ga),
        safe(h_pts) / 3.0,
        safe(a_gf),
        safe(a_ga),
        safe(a_pts) / 3.0,
        trend(h_gf),
        trend(h_ga),
        trend(a_gf),
        trend(a_ga),
        stdev(h_gf),
        stdev(h_ga),
        stdev(a_gf),
        stdev(a_ga),
        safe(h_home_pts) / 3.0,
        safe(h_away_pts) / 3.0,
        safe(a_home_pts) / 3.0,
        safe(a_away_pts) / 3.0,
        h2h_n,
        h2h_h_wr,
        h2h_avg_total,
        strength_diff,
        form_diff,
        home_away_form_diff,
        momentum_diff,
        scoring_diff,
        conceding_diff,
        # RANKING FEATURES (from bet261.classement)
        home_ranking.get("position", n_teams / 2),
        away_ranking.get("position", n_teams / 2),
        n_teams + 1 - home_ranking.get("position", n_teams / 2),
        n_teams + 1 - away_ranking.get("position", n_teams / 2),
        home_ranking.get("points", 0),
        away_ranking.get("points", 0),
        home_ranking.get("points", 0) - away_ranking.get("points", 0),
        home_ranking.get("win_rate", 0.33),
        away_ranking.get("win_rate", 0.33),
        home_ranking.get("win_rate", 0.33) - away_ranking.get("win_rate", 0.33),
        home_ranking.get("form_score", 0.33),
        away_ranking.get("form_score", 0.33),
        home_ranking.get("form_score", 0.33) - away_ranking.get("form_score", 0.33),
        abs(home_ranking.get("position", 12) - away_ranking.get("position", 12)),
    ]

    return features, None, home_team, away_team, rnd
