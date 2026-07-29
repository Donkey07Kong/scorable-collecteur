def get_fav_odds(cote_1, cote_X, cote_2):
    odds = {'1': cote_1, 'X': cote_X, '2': cote_2}
    fav = min(odds, key=odds.get)
    return odds[fav], fav


def classify_match(cote_1, cote_X, cote_2, elo_home=None, elo_away=None):
    fav_odds, fav_side = get_fav_odds(cote_1, cote_X, cote_2)

    elo_diff = 0
    if elo_home is not None and elo_away is not None:
        elo_diff = elo_away - elo_home

    if cote_X < cote_1 and cote_X < cote_2:
        fav_side = 'X'
        fav_odds = cote_X
    elif cote_2 < 2.5 and elo_diff > 100:
        fav_side = '2'
        fav_odds = cote_2
    elif cote_1 < 2.5 and elo_diff < -100:
        fav_side = '1'
        fav_odds = cote_1
    else:
        fav_side = min({'1': cote_1, '2': cote_2}, key=lambda k: {'1': cote_1, '2': cote_2}[k])
        fav_odds = {'1': cote_1, '2': cote_2}[fav_side]

    result = None
    if fav_odds <= 1.20:
        result = {
            "zone": "ultra_dominant",
            "label": "Favori ultra dominateur",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "domination_totale",
            "fav_win_pct": 69,
            "btts_pct": 28,
            "over25_pct": 45,
            "over35_pct": 17,
            "avg_goals": 2.4,
            "likely_scores": ["2-0", "3-0", "4-0", "5-1", "6-1"],
            "bet_tips": ["Favori gagne facilement", "Under 3.5"],
            "btts_pred": "Non",
            "ou_pred": "Under 3.5 / Over 2.5 prudent",
            "confidence": "HAUTE",
        }
    elif fav_odds <= 1.35:
        result = {
            "zone": "domination_claire",
            "label": "Domination claire",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "domination_claire",
            "fav_win_pct": 67,
            "btts_pct": 49,
            "over25_pct": 62,
            "over35_pct": 40,
            "avg_goals": 3.0,
            "likely_scores": ["2-0", "3-0", "4-1", "5-1"],
            "bet_tips": ["Favori gagne", "Over 2.5"],
            "btts_pred": "50/50",
            "ou_pred": "Over 2.5",
            "confidence": "HAUTE",
        }
    elif fav_odds <= 1.45:
        result = {
            "zone": "domination_moderee",
            "label": "Domination moderee",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "domination_moderee",
            "fav_win_pct": 37,
            "btts_pct": 63,
            "over25_pct": 58,
            "over35_pct": 32,
            "avg_goals": 2.8,
            "likely_scores": ["2-1", "3-1", "4-1", "2-0"],
            "bet_tips": ["Victoire favori + Over", "BTTS possible"],
            "btts_pred": "Oui",
            "ou_pred": "Over 2.5",
            "confidence": "MOYENNE",
        }
    elif fav_odds <= 1.55:
        result = {
            "zone": "favori_moyen",
            "label": "Favori moyen fort",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "ouvert",
            "fav_win_pct": 60,
            "btts_pct": 48,
            "over25_pct": 60,
            "over35_pct": 36,
            "avg_goals": 2.9,
            "likely_scores": ["2-1", "3-1", "3-0", "2-0"],
            "bet_tips": ["Over 2.5", "Victoire favori"],
            "btts_pred": "50/50",
            "ou_pred": "Over 2.5",
            "confidence": "MOYENNE",
        }
    elif fav_odds <= 1.68:
        result = {
            "zone": "match_actif",
            "label": "Match actif",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "actif_ouvert",
            "fav_win_pct": 33,
            "btts_pct": 67,
            "over25_pct": 72,
            "over35_pct": 50,
            "avg_goals": 3.2,
            "likely_scores": ["1-2", "2-2", "1-3", "2-1"],
            "bet_tips": ["BTTS + Over 2.5", "Match ouvert"],
            "btts_pred": "Oui",
            "ou_pred": "Over 2.5",
            "confidence": "HAUTE",
        }
    elif fav_odds <= 1.78:
        result = {
            "zone": "equilibre_ouvert",
            "label": "Equilibre ouvert",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "equilibre_ouvert",
            "fav_win_pct": 54,
            "btts_pct": 62,
            "over25_pct": 54,
            "over35_pct": 23,
            "avg_goals": 2.7,
            "likely_scores": ["1-1", "2-2", "2-1", "1-0"],
            "bet_tips": ["BTTS Oui", "Over 1.5"],
            "btts_pred": "Oui",
            "ou_pred": "Over 1.5",
            "confidence": "MOYENNE",
        }
    elif fav_odds <= 1.89:
        result = {
            "zone": "indecis",
            "label": "Match indecis",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "indecis",
            "fav_win_pct": 61,
            "btts_pct": 39,
            "over25_pct": 50,
            "over35_pct": 39,
            "avg_goals": 2.8,
            "likely_scores": ["3-0", "2-0", "0-1", "1-0"],
            "bet_tips": ["Over 1.5", "Prudence"],
            "btts_pred": "Non",
            "ou_pred": "Over 1.5",
            "confidence": "FAIBLE",
        }
    elif fav_odds <= 2.00:
        result = {
            "zone": "serre",
            "label": "Match serre",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "serre",
            "fav_win_pct": 61,
            "btts_pct": 50,
            "over25_pct": 56,
            "over35_pct": 44,
            "avg_goals": 3.0,
            "likely_scores": ["0-2", "1-0", "2-2", "2-1"],
            "bet_tips": ["Prudence - Pas de pari recommande"],
            "btts_pred": "50/50",
            "ou_pred": "Neutre",
            "confidence": "FAIBLE",
        }
    elif fav_odds <= 2.15:
        result = {
            "zone": "equilibre_ferme",
            "label": "Equilibre tactique",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "ferme",
            "fav_win_pct": 41,
            "btts_pct": 71,
            "over25_pct": 59,
            "over35_pct": 29,
            "avg_goals": 2.8,
            "likely_scores": ["0-1", "1-1", "2-1", "1-0"],
            "bet_tips": ["Under 3.5", "BTTS possible"],
            "btts_pred": "Oui",
            "ou_pred": "Under 3.5",
            "confidence": "MOYENNE",
        }
    elif fav_odds <= 2.35:
        result = {
            "zone": "tres_ferme",
            "label": "Match tres ferme",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "tres_ferme",
            "fav_win_pct": 52,
            "btts_pct": 60,
            "over25_pct": 68,
            "over35_pct": 48,
            "avg_goals": 3.2,
            "likely_scores": ["2-2", "1-3", "0-1", "1-1"],
            "bet_tips": ["Under 2.5 prudent", "BTTS"],
            "btts_pred": "Oui",
            "ou_pred": "Under 2.5",
            "confidence": "MOYENNE",
        }
    elif fav_odds <= 2.55:
        result = {
            "zone": "indecision_totale",
            "label": "Indecision totale",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "indecision",
            "fav_win_pct": 32,
            "btts_pct": 37,
            "over25_pct": 37,
            "over35_pct": 21,
            "avg_goals": 2.3,
            "likely_scores": ["1-0", "0-1", "1-1"],
            "bet_tips": ["Double chance", "Under 2.5"],
            "btts_pred": "Non",
            "ou_pred": "Under 2.5",
            "confidence": "MOYENNE",
        }
    elif fav_odds <= 2.80:
        result = {
            "zone": "match_piege",
            "label": "Match piege",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "piege",
            "fav_win_pct": 40,
            "btts_pct": 55,
            "over25_pct": 50,
            "over35_pct": 35,
            "avg_goals": 2.7,
            "likely_scores": ["2-2", "2-1", "1-2"],
            "bet_tips": ["BTTS prudent", "Pas de favori clair"],
            "btts_pred": "50/50",
            "ou_pred": "Neutre",
            "confidence": "FAIBLE",
        }
    elif fav_odds <= 3.20:
        result = {
            "zone": "surprises",
            "label": "Match a surprises",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "surprises",
            "fav_win_pct": 35,
            "btts_pct": 60,
            "over25_pct": 55,
            "over35_pct": 45,
            "avg_goals": 3.0,
            "likely_scores": ["2-2", "2-3", "3-3"],
            "bet_tips": ["Over 3.5 possible", "BTTS"],
            "btts_pred": "Oui",
            "ou_pred": "Over 3.5",
            "confidence": "MOYENNE",
        }
    elif fav_odds <= 3.75:
        result = {
            "zone": "debrid",
            "label": "Match debrid",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "debrid",
            "fav_win_pct": 30,
            "btts_pct": 65,
            "over25_pct": 70,
            "over35_pct": 55,
            "avg_goals": 3.5,
            "likely_scores": ["3-3", "3-4", "4-2"],
            "bet_tips": ["Gros Over", "BTTS"],
            "btts_pred": "Oui",
            "ou_pred": "Over 3.5",
            "confidence": "HAUTE",
        }
    else:
        result = {
            "zone": "imprevisible",
            "label": "Match imprevisible",
            "fav_odds": round(fav_odds, 2),
            "fav_side": fav_side,
            "style": "spectacle",
            "fav_win_pct": 25,
            "btts_pct": 70,
            "over25_pct": 75,
            "over35_pct": 60,
            "avg_goals": 4.0,
            "likely_scores": ["3-5", "2-5", "3-3", "4-4"],
            "bet_tips": ["Match spectacle", "Gros Over"],
            "btts_pred": "Oui",
            "ou_pred": "Over 3.5",
            "confidence": "HAUTE",
        }
    result["elo_home"] = elo_home
    result["elo_away"] = elo_away
    result["cote_1"] = cote_1
    result["cote_X"] = cote_X
    result["cote_2"] = cote_2
    return result

def analyze_match(home_team, away_team, cote_1, cote_X, cote_2,
                  ml_pred=None, ml_confidence=None, poisson_pred=None,
                  elo_home=None, elo_away=None):
    matrix = classify_match(cote_1, cote_X, cote_2, elo_home, elo_away)

    matrix["home_team"] = home_team
    matrix["away_team"] = away_team
    matrix["cote_1"] = cote_1
    matrix["cote_X"] = cote_X
    matrix["cote_2"] = cote_2
    matrix["elo_home"] = elo_home
    matrix["elo_away"] = elo_away

    if ml_pred and ml_confidence:
        matrix["ml_pred"] = ml_pred
        matrix["ml_confidence"] = ml_confidence

    if poisson_pred:
        matrix["poisson_pred"] = poisson_pred

    return matrix


def get_combined_prediction(matrix_result, ml_result=None):
    tips = list(matrix_result.get("bet_tips", []))
    final_pred = {
        "matrix": matrix_result,
        "tips": tips,
        "btts": matrix_result.get("btts_pred", "?"),
        "ou": matrix_result.get("ou_pred", "?"),
        "fav_side": matrix_result.get("fav_side", "?"),
        "fav_odds": matrix_result.get("fav_odds", 0),
        "confidence": matrix_result.get("confidence", "FAIBLE"),
    }

    ml_pred = None
    ml_conf = 0
    if ml_result:
        ml_pred = ml_result.get("ml_pred_1x2", "?")
        ml_conf = ml_result.get("ml_confidence_1x2", 0)
        final_pred["ml_pred"] = ml_pred
        final_pred["ml_confidence"] = ml_conf

    cote_1 = matrix_result.get("cote_1", 3.0)
    cote_X = matrix_result.get("cote_X", 3.0)
    cote_2 = matrix_result.get("cote_2", 3.0)
    elo_h = matrix_result.get("elo_home", 1400) or 1400
    elo_a = matrix_result.get("elo_away", 1400) or 1400
    elo_diff = elo_a - elo_h

    mx_side = matrix_result.get("fav_side", "1")
    mx_zone = matrix_result.get("zone", "?")

    if cote_X <= cote_1 and cote_X <= cote_2:
        if ml_pred == "X":
            final_pred["final_pred"] = "X"
            final_pred["agreement"] = True
            final_pred["combined_confidence"] = "HAUTE"
            tips.append("X agree (cotes + ML)")
        elif ml_pred == "1" and elo_diff < -50:
            final_pred["final_pred"] = "1"
            final_pred["agreement"] = False
            final_pred["combined_confidence"] = "MOYENNE"
            tips.append("Favori nul mais ELO favor domicile")
        elif ml_pred == "2" and elo_diff > 50:
            final_pred["final_pred"] = "2"
            final_pred["agreement"] = False
            final_pred["combined_confidence"] = "MOYENNE"
            tips.append("Favori nul mais ELO favor exterieur")
        else:
            final_pred["final_pred"] = "X"
            final_pred["agreement"] = False
            final_pred["combined_confidence"] = "MOYENNE"
            tips.append("Nul favori par cotes")
    elif cote_2 < 2.5 and elo_diff > 100:
        final_pred["final_pred"] = "2"
        final_pred["agreement"] = (ml_pred == "2")
        final_pred["combined_confidence"] = "HAUTE"
        tips.append("Ext favori (cote+ELO confirme)")
    elif ml_pred == "2" and cote_2 < 2.5 and elo_diff > 50:
        final_pred["final_pred"] = "2"
        final_pred["agreement"] = True
        final_pred["combined_confidence"] = "MOYENNE"
        tips.append("ML detecte ext + cote favorable")
    elif ml_pred == "X" and cote_X <= cote_1 and cote_X <= cote_2:
        final_pred["final_pred"] = "X"
        final_pred["agreement"] = True
        final_pred["combined_confidence"] = "MOYENNE"
        tips.append("ML predit nul, cotes coherentes")
    elif mx_side == "X":
        final_pred["final_pred"] = "X"
        final_pred["agreement"] = (ml_pred == "X")
        final_pred["combined_confidence"] = "MOYENNE"
        tips.append("Nul par matrice de cotes")
    else:
        final_pred["final_pred"] = mx_side
        if ml_pred == mx_side:
            final_pred["agreement"] = True
            final_pred["combined_confidence"] = "HAUTE"
            tips.append("ML et Matrice d'accord -> %s" % mx_side)
        elif ml_pred == "X":
            final_pred["agreement"] = False
            final_pred["combined_confidence"] = "MOYENNE"
            tips.append("ML predit nul mais matrice -> %s" % mx_side)
        else:
            final_pred["agreement"] = False
            final_pred["combined_confidence"] = "MOYENNE"
            tips.append("Matrice -> %s (ML en desaccord)" % mx_side)

    return final_pred
