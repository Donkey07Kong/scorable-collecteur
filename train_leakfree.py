import sys, os, warnings
warnings.filterwarnings('ignore')
os.environ["TABPFN_NO_BROWSER"] = "1"
os.environ["JOBLIB_MULTIPROCESSING"] = "0"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from sklearn.preprocessing import LabelEncoder
from prediction_engine import charger_historique, calculer_stats_equipes, calculer_h2h
from ml_features import build_dataset, _compute_elo_leakfree
from ml_ensemble import train_ensemble, save_models, load_models

import ml_ensemble
ml_ensemble.HAS_TABPFN = False

donnees = charger_historique()
print(f"Loaded {len(donnees)} matches")

all_stats = calculer_stats_equipes(donnees)
elo = _compute_elo_leakfree(donnees, 9999)
h2h = calculer_h2h(donnees)

print("Training leak-free models...")
result = train_ensemble(donnees, all_stats, elo, h2h, all_stats)

if isinstance(result, tuple):
    models, cv_results = result
else:
    models = result

if models and isinstance(models, dict):
    save_models(models)
    print("Models saved!")
else:
    print(f"Training failed: {models}")
    sys.exit(1)

X, y_1x2, y_ou25, _, _, _, meta = build_dataset(donnees, all_stats, elo, h2h, all_stats)
le = LabelEncoder()
y1x2_enc = le.fit_transform(y_1x2)

split = int(len(X) * 0.8)
X_test = X[split:]
y_test = y1x2_enc[split:]
y_ou25_test = y_ou25[split:]
meta_test = meta[split:]

baseline = np.mean(np.full(len(y_test), np.bincount(y_test).argmax()) == y_test)
print(f"\nBaseline (most common): {baseline:.1%}")

keys_1x2 = ["rf_1x2", "xgb_1x2", "gb_1x2", "et_1x2", "lgbm_1x2"]
print("=== 1X2 ===")
all_1x2 = []
for key in keys_1x2:
    if key in models:
        try:
            proba = models[key].predict_proba(X_test)
            all_1x2.append(proba)
            acc = np.mean(np.argmax(proba, axis=1) == y_test)
            print(f"  {key}: {acc:.1%}")
        except Exception as e:
            print(f"  {key}: ERR {e}")

if all_1x2:
    avg = np.mean(all_1x2, axis=0)
    preds = np.argmax(avg, axis=1)
    acc = np.mean(preds == y_test)
    print(f"  ENSEMBLE: {acc:.1%}")
    print(f"  vs baseline: {(acc - baseline)*100:+.1f} pp")
    for lo, hi in [(0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]:
        mask = (np.max(avg, axis=1) >= lo) & (np.max(avg, axis=1) < hi)
        if mask.sum() > 0:
            bacc = np.mean(preds[mask] == y_test[mask])
            print(f"    [{lo:.0%}-{hi:.0%}]: n={mask.sum():4d}, acc={bacc:.1%}")

keys_ou25 = ["rf_ou25", "xgb_ou25", "gb_ou25", "et_ou25", "lgbm_ou25"]
print("\n=== O/U 2.5 ===")
all_ou = []
for key in keys_ou25:
    if key in models:
        try:
            proba = models[key].predict_proba(X_test)
            all_ou.append(proba)
            acc = np.mean(np.argmax(proba, axis=1) == y_ou25_test)
            print(f"  {key}: {acc:.1%}")
        except Exception as e:
            print(f"  {key}: ERR {e}")

if all_ou:
    avg = np.mean(all_ou, axis=0)
    preds = np.argmax(avg, axis=1)
    acc = np.mean(preds == y_ou25_test)
    print(f"  ENSEMBLE: {acc:.1%}")

if meta_test:
    rounds = [m['round'] for m in meta_test]
    print(f"\nTest rounds: {min(rounds)}-{max(rounds)}")
