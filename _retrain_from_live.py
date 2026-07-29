"""
_retrain_from_live.py - Reentraine les modeles ML UNIQUEMENT
avec les donnees live (live_data.csv). Pas d'anciennes donnees.
"""

import os
import csv
import json
import time
import sys

LIVE_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_data.csv")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_err.log")


def _log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "[RETRAIN] %s %s" % (ts, msg)
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except Exception:
        pass


def retrain():
    _log("Chargement live_data.csv...")
    if not os.path.exists(LIVE_CSV):
        _log("Fichier introuvable: %s" % LIVE_CSV)
        return False

    donnees = []
    with open(LIVE_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sd = int(row.get("score_dom", 0))
            se = int(row.get("score_ext", 0))
            total = sd + se
            victory = "dom" if sd > se else "ext" if se > sd else "nul"
            donnees.append({
                "round": int(row["round"]),
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "score_final_dom": sd,
                "score_final_ext": se,
                "nb_buts_total": total,
                "nb_buts_dom": sd,
                "nb_buts_ext": se,
                "victoire": victory,
                "cycle": int(row.get("cycle", 0)),
            })

    _log(" %d matchs charges" % len(donnees))

    if len(donnees) < 50:
        _log("Pas assez de donnees (%d < 50)" % len(donnees))
        return False

    try:
        import prediction_engine
        import ml_ensemble
    except ImportError as e:
        _log("ML libraries manquantes: %s" % e)
        return False

    _log("Calcul stats...")
    t0 = time.time()

    stats = prediction_engine.calculer_stats(donnees)
    models, cv = ml_ensemble.train_ensemble_fast(
        donnees, stats["team_stats"], stats["elo_ratings"],
        stats["h2h_stats"], stats["tendances"]
    )
    elapsed = time.time() - t0

    if models:
        ml_ensemble.save_models(models)
        cv_summary = {}
        for k, v in cv.items():
            cv_summary[k] = round(v * 100, 1) if isinstance(v, float) else v
        _log("Training OK (%.1fs)! CV: %s" % (elapsed, json.dumps(cv_summary)))
        return True
    else:
        _log("Training echoue: %s" % cv)
        return False


if __name__ == "__main__":
    ok = retrain()
    sys.exit(0 if ok else 1)
