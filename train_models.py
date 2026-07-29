import sys
import time
import json
import os

sys.path.insert(0, '.')

import prediction_engine
import ml_ensemble

ml_ensemble.HAS_TABPFN = False

print("=== ENTRAINEMENT ML CAF (rapide) %s ===" % time.strftime("%Y-%m-%d %H:%M:%S"))
print()

historique = prediction_engine.charger_historique()
stats = prediction_engine.calculer_stats(historique)

print("Matchs: %d, Equipes: %d" % (len(historique), len(stats['team_stats'])))
print()

max_round = max(int(d.get("round", 0)) for d in historique)
max_train = max_round - 10 if max_round > 10 else None
print("max_train_round: %s (excluant rounds %d-%d)" % (max_train, (max_train or 0)+1, max_round))
print()

t0 = time.time()
models, cv = ml_ensemble.train_ensemble_fast(
    historique, stats["team_stats"], stats["elo_ratings"],
    stats["h2h_stats"], stats["tendances"], max_train_round=max_train
)
elapsed = time.time() - t0

if models:
    ml_ensemble.save_models(models)
    print()
    print("=== TRAINING TERMINE en %.0fs ===" % elapsed)
    print("Modeles sauvegardes dans ml_models/")
    if isinstance(cv, dict):
        for k, v in sorted(cv.items()):
            if isinstance(v, float):
                print("  %s: %.1f%%" % (k, v * 100))
else:
    print("ECHEC entrainement")

log = {
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "matchs": len(historique),
    "max_round": max_round,
    "max_train_round": max_train,
    "elapsed_sec": round(elapsed, 1),
    "cv_results": cv if isinstance(cv, dict) else {},
}
with open("train_log.json", "w", encoding="utf-8") as f:
    json.dump(log, f, indent=2)

print("Log sauvegarde dans train_log.json")
