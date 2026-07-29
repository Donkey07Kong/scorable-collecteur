import sys
sys.stdout.reconfigure(encoding='utf-8')

from prediction_engine import calculer_stats, charger_historique
from ml_ensemble import train_ensemble, save_models

print("Chargement des donnees...")
d = charger_historique()
s = calculer_stats(d)

print("Entraînement de l'ensemble ML...")
models, cv = train_ensemble(d, s["team_stats"], s["elo_ratings"], s["h2h_stats"], s["tendances"])

if models:
    print("\nSauvegarde des modeles...")
    save_models(models)
    print("\n=== RESULTATS CV ===")
    for k, v in cv.items():
        if isinstance(v, float):
            print(f"  {k}: {v*100:.1f}%")
        else:
            print(f"  {k}: {v}")
else:
    print("Erreur:", cv)
