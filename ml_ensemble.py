import os
import json
import math
import numpy as np
from collections import defaultdict

try:
    from sklearn.ensemble import (RandomForestClassifier, RandomForestRegressor,
                                  GradientBoostingClassifier, ExtraTreesClassifier,
                                  AdaBoostClassifier, StackingClassifier)
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score, StratifiedKFold, TimeSeriesSplit
    from sklearn.preprocessing import LabelEncoder
    from sklearn.calibration import CalibratedClassifierCV, calibration_curve
    from sklearn.isotonic import IsotonicRegression
    from xgboost import XGBClassifier, XGBRegressor
    HAS_ML = True
except ImportError:
    HAS_ML = False

try:
    from lightgbm import LGBMClassifier
    HAS_LGBM = True
except ImportError:
    HAS_LGBM = False

try:
    from tabpfn import TabPFNClassifier
    HAS_TABPFN = True
except ImportError:
    HAS_TABPFN = False

from ml_features import build_dataset, FEATURE_NAMES, build_features_for_match

MODEL_DIR = "ml_models"
ENSEMBLE_PATH = os.path.join(MODEL_DIR, "ensemble.json")


def _calibrate_model(base_model, X, y, task_name):
    try:
        cal_model = CalibratedClassifierCV(base_model, cv=3, method='isotonic')
        cal_model.fit(X, y)
        print("  Calibration %s OK (isotonic)" % task_name)
        return cal_model
    except Exception as e:
        print("  Calibration %s failed (%s), using sigmoid" % (task_name, e))
        try:
            cal_model = CalibratedClassifierCV(base_model, cv=3, method='sigmoid')
            cal_model.fit(X, y)
            return cal_model
        except Exception:
            base_model.fit(X, y)
            return base_model


def _measure_calibration(model, X, y_true, n_bins=10):
    try:
        y_proba = model.predict_proba(X)[:, 1] if len(np.unique(y_true)) == 2 else None
        if y_proba is None:
            prob_max = np.max(model.predict_proba(X), axis=1)
            y_binary = (np.arange(len(y_true)) == np.argmax(model.predict_proba(X), axis=1)).astype(int)
            y_true_binary = (y_true == np.array([np.argmax(model.predict_proba(X), axis=1)])).astype(int).flatten()
            if len(np.unique(y_true_binary)) < 2:
                return {}
            prob_true, prob_pred = calibration_curve(y_true_binary, prob_max, n_bins=min(n_bins, len(np.unique(prob_max))))
        else:
            prob_true, prob_pred = calibration_curve(y_true, y_proba, n_bins=min(n_bins, len(np.unique(y_proba))))
        if len(prob_true) < 2:
            return {}
        brier = float(np.mean((prob_pred - prob_true) ** 2))
        return {"brier": round(brier, 4), "n_bins": len(prob_true)}
    except Exception:
        return {}


def train_ensemble_fast(donnees, team_stats, elo_ratings, h2h_stats, tendances, max_train_round=None):
    """Version allégée du training - adaptee CPU modeste, sans stacking ni TabPFN."""
    if not HAS_ML:
        return None, "ML libraries not installed"

    print("Extraction des features...")
    X, y_1x2, y_ou25, y_ou35, y_pair, y_total, meta = build_dataset(
        donnees, team_stats, elo_ratings, h2h_stats, tendances, max_train_round=max_train_round
    )

    if len(X) < 50:
        return None, f"Pas assez de donnees: {len(X)}"

    print(f"Dataset: {len(X)} matchs, {X.shape[1]} features")

    le_1x2 = LabelEncoder()
    y_1x2_enc = le_1x2.fit_transform(y_1x2)

    models = {}

    base_models_1x2 = [
        ("rf_1x2", RandomForestClassifier(n_estimators=150, max_depth=10, min_samples_split=10,
            min_samples_leaf=5, random_state=42, class_weight="balanced", n_jobs=-1)),
        ("xgb_1x2", XGBClassifier(n_estimators=150, max_depth=6, learning_rate=0.08,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
            eval_metric="mlogloss", n_jobs=-1)),
        ("et_1x2", ExtraTreesClassifier(n_estimators=150, max_depth=10, min_samples_split=10,
            min_samples_leaf=5, random_state=42, class_weight="balanced", n_jobs=-1)),
    ]
    if HAS_LGBM:
        base_models_1x2.append(("lgbm_1x2", LGBMClassifier(n_estimators=150, max_depth=6, learning_rate=0.08,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
            class_weight="balanced", n_jobs=-1, verbose=-1)))

    print("Training + Calibration 1X2...")
    for name, base_model in base_models_1x2:
        print("  Training %s..." % name)
        models[name] = _calibrate_model(base_model, X, y_1x2_enc, name)

    base_models_ou25 = [
        ("rf_ou25", RandomForestClassifier(n_estimators=150, max_depth=8, min_samples_split=10,
            min_samples_leaf=5, random_state=42, n_jobs=-1)),
        ("xgb_ou25", XGBClassifier(n_estimators=150, max_depth=6, learning_rate=0.08,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
            eval_metric="logloss", n_jobs=-1)),
        ("et_ou25", ExtraTreesClassifier(n_estimators=150, max_depth=8, min_samples_split=10,
            min_samples_leaf=5, random_state=42, n_jobs=-1)),
    ]
    if HAS_LGBM:
        base_models_ou25.append(("lgbm_ou25", LGBMClassifier(n_estimators=150, max_depth=6, learning_rate=0.08,
            subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1, verbose=-1)))

    print("Training + Calibration O/U2.5...")
    for name, base_model in base_models_ou25:
        print("  Training %s..." % name)
        models[name] = _calibrate_model(base_model, X, y_ou25, name)

    print("Training O/U3.5...")
    rf_ou35 = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, n_jobs=-1)
    rf_ou35.fit(X, y_ou35)
    models["rf_ou35"] = rf_ou35

    xgb_ou35 = XGBClassifier(n_estimators=100, max_depth=6, learning_rate=0.08, random_state=42,
                              eval_metric="logloss", n_jobs=-1)
    xgb_ou35.fit(X, y_ou35)
    models["xgb_ou35"] = xgb_ou35

    print("Training Pair/Impair...")
    rf_pair = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, n_jobs=-1)
    rf_pair.fit(X, y_pair)
    models["rf_pair"] = rf_pair

    xgb_pair = XGBClassifier(n_estimators=100, max_depth=6, learning_rate=0.08, random_state=42,
                              eval_metric="logloss", n_jobs=-1)
    xgb_pair.fit(X, y_pair)
    models["xgb_pair"] = xgb_pair

    print("Training Total goals regressor...")
    rf_total = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42, n_jobs=-1)
    rf_total.fit(X, y_total)
    models["rf_total"] = rf_total

    xgb_total = XGBRegressor(n_estimators=100, max_depth=6, learning_rate=0.08, random_state=42, n_jobs=-1)
    xgb_total.fit(X, y_total)
    models["xgb_total"] = xgb_total

    print("Cross-validation rapide (3 splits)...")
    rounds_for_cv = np.array([m["round"] for m in meta])
    sort_idx = np.argsort(rounds_for_cv)
    X_sorted = X[sort_idx]
    y1_sorted = y_1x2_enc[sort_idx]
    y2_sorted = y_ou25[sort_idx]

    tscv = TimeSeriesSplit(n_splits=3)
    cv_results = {"n_samples": len(X), "n_features": X.shape[1]}

    for mname in ["rf_1x2", "xgb_1x2", "et_1x2", "lgbm_1x2"]:
        if mname in models:
            try:
                cv = cross_val_score(models[mname], X_sorted, y1_sorted, cv=tscv, scoring="accuracy")
                cv_results[mname] = float(cv.mean())
                print("  %s 1X2: %.1f%% (+/- %.1f%%)" % (mname, cv.mean()*100, cv.std()*100))
            except Exception as e:
                print("  CV %s failed: %s" % (mname, e))

    for mname in ["rf_ou25", "xgb_ou25", "et_ou25", "lgbm_ou25"]:
        if mname in models:
            try:
                cv = cross_val_score(models[mname], X_sorted, y2_sorted, cv=tscv, scoring="accuracy")
                cv_results[mname] = float(cv.mean())
                print("  %s O/U25: %.1f%% (+/- %.1f%%)" % (mname, cv.mean()*100, cv.std()*100))
            except Exception as e:
                print("  CV %s failed: %s" % (mname, e))

    print("\n=== CV Results (calibres) ===")
    for k, v in sorted(cv_results.items()):
        if isinstance(v, float):
            print(f"  {k}: {v*100:.1f}%")

    feature_importance = {}
    for mname in ["rf_1x2", "et_1x2"]:
        if mname in models:
            model = models[mname]
            base = model
            if hasattr(model, 'calibrated_classifiers_'):
                base = model.calibrated_classifiers_[0].estimator
            if hasattr(base, 'feature_importances_'):
                for i in np.argsort(base.feature_importances_)[::-1][:15]:
                    if i < len(FEATURE_NAMES):
                        fname = FEATURE_NAMES[i]
                        feature_importance[fname] = feature_importance.get(fname, 0) + float(base.feature_importances_[i]) / 2

    print("\nTop 15 features:")
    for fname, imp in sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"  {fname}: {imp:.4f}")

    models["_meta"] = {
        "label_encoder_classes": le_1x2.classes_.tolist(),
        "cv_results": cv_results,
        "feature_importance": feature_importance,
        "feature_names": FEATURE_NAMES,
        "n_samples": len(X),
        "calibrated": True,
    }

    return models, cv_results


def train_ensemble(donnees, team_stats, elo_ratings, h2h_stats, tendances, max_train_round=None):
    if not HAS_ML:
        return None, "ML libraries not installed"

    print("Extraction des features...")
    X, y_1x2, y_ou25, y_ou35, y_pair, y_total, meta = build_dataset(
        donnees, team_stats, elo_ratings, h2h_stats, tendances, max_train_round=max_train_round
    )

    if len(X) < 50:
        return None, f"Pas assez de donnees: {len(X)}"

    print(f"Dataset: {len(X)} matchs, {X.shape[1]} features")

    le_1x2 = LabelEncoder()
    y_1x2_enc = le_1x2.fit_transform(y_1x2)

    models = {}

    base_models_1x2 = [
        ("rf_1x2", RandomForestClassifier(n_estimators=300, max_depth=12, min_samples_split=10,
            min_samples_leaf=5, random_state=42, class_weight="balanced", n_jobs=-1)),
        ("xgb_1x2", XGBClassifier(n_estimators=300, max_depth=8, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
            use_label_encoder=False, eval_metric="mlogloss", n_jobs=-1)),
        ("gb_1x2", GradientBoostingClassifier(n_estimators=200, max_depth=6, learning_rate=0.05,
            subsample=0.8, random_state=42)),
        ("et_1x2", ExtraTreesClassifier(n_estimators=300, max_depth=12, min_samples_split=10,
            min_samples_leaf=5, random_state=42, class_weight="balanced", n_jobs=-1)),
    ]
    if HAS_LGBM:
        base_models_1x2.append(("lgbm_1x2", LGBMClassifier(n_estimators=300, max_depth=8, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
            class_weight="balanced", n_jobs=-1, verbose=-1)))

    print("Training + Calibration 1X2...")
    for name, base_model in base_models_1x2:
        print("  Training %s..." % name)
        models[name] = _calibrate_model(base_model, X, y_1x2_enc, name)

    print("Training Stacking 1X2 (meta-learner)...")
    stacking_estimators_1x2 = [
        ("rf", RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, class_weight="balanced", n_jobs=-1)),
        ("xgb", XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.05, random_state=42, eval_metric="mlogloss", n_jobs=-1)),
        ("gb", GradientBoostingClassifier(n_estimators=150, max_depth=5, learning_rate=0.05, subsample=0.8, random_state=42)),
        ("et", ExtraTreesClassifier(n_estimators=200, max_depth=10, random_state=42, class_weight="balanced", n_jobs=-1)),
    ]
    if HAS_LGBM:
        stacking_estimators_1x2.append(("lgbm", LGBMClassifier(n_estimators=200, max_depth=6, learning_rate=0.05, subsample=0.8, random_state=42, n_jobs=-1, verbose=-1)))
    stacking_1x2 = StackingClassifier(
        estimators=stacking_estimators_1x2,
        final_estimator=LogisticRegression(max_iter=1000, random_state=42),
        cv=3, n_jobs=-1, passthrough=False
    )
    stacking_1x2.fit(X, y_1x2_enc)
    models["stacking_1x2"] = stacking_1x2

    base_models_ou25 = [
        ("rf_ou25", RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_split=10,
            min_samples_leaf=5, random_state=42, n_jobs=-1)),
        ("xgb_ou25", XGBClassifier(n_estimators=300, max_depth=8, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
            use_label_encoder=False, eval_metric="logloss", n_jobs=-1)),
        ("gb_ou25", GradientBoostingClassifier(n_estimators=200, max_depth=6, learning_rate=0.05,
            subsample=0.8, random_state=42)),
        ("et_ou25", ExtraTreesClassifier(n_estimators=200, max_depth=10, min_samples_split=10,
            min_samples_leaf=5, random_state=42, n_jobs=-1)),
    ]
    if HAS_LGBM:
        base_models_ou25.append(("lgbm_ou25", LGBMClassifier(n_estimators=300, max_depth=8, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1, verbose=-1)))

    print("Training + Calibration O/U2.5...")
    for name, base_model in base_models_ou25:
        print("  Training %s..." % name)
        models[name] = _calibrate_model(base_model, X, y_ou25, name)

    print("Training Stacking O/U2.5...")
    stacking_estimators_ou25 = [
        ("rf", RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1)),
        ("xgb", XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.05, random_state=42, eval_metric="logloss", n_jobs=-1)),
        ("gb", GradientBoostingClassifier(n_estimators=150, max_depth=5, learning_rate=0.05, subsample=0.8, random_state=42)),
        ("et", ExtraTreesClassifier(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1)),
    ]
    if HAS_LGBM:
        stacking_estimators_ou25.append(("lgbm", LGBMClassifier(n_estimators=200, max_depth=6, learning_rate=0.05, subsample=0.8, random_state=42, n_jobs=-1, verbose=-1)))
    stacking_ou25 = StackingClassifier(
        estimators=stacking_estimators_ou25,
        final_estimator=LogisticRegression(max_iter=1000, random_state=42),
        cv=3, n_jobs=-1, passthrough=False
    )
    stacking_ou25.fit(X, y_ou25)
    models["stacking_ou25"] = stacking_ou25

    print("Training O/U3.5 ensemble...")
    rf_ou35 = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1)
    rf_ou35.fit(X, y_ou35)
    models["rf_ou35"] = rf_ou35

    xgb_ou35 = XGBClassifier(n_estimators=200, max_depth=8, learning_rate=0.05, random_state=42,
                              use_label_encoder=False, eval_metric="logloss", n_jobs=-1)
    xgb_ou35.fit(X, y_ou35)
    models["xgb_ou35"] = xgb_ou35

    print("Training Pair/Impair...")
    rf_pair = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1)
    rf_pair.fit(X, y_pair)
    models["rf_pair"] = rf_pair

    xgb_pair = XGBClassifier(n_estimators=200, max_depth=8, learning_rate=0.05, random_state=42,
                              use_label_encoder=False, eval_metric="logloss", n_jobs=-1)
    xgb_pair.fit(X, y_pair)
    models["xgb_pair"] = xgb_pair

    print("Training Total goals regressor...")
    rf_total = RandomForestRegressor(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1)
    rf_total.fit(X, y_total)
    models["rf_total"] = rf_total

    xgb_total = XGBRegressor(n_estimators=200, max_depth=8, learning_rate=0.05, random_state=42, n_jobs=-1)
    xgb_total.fit(X, y_total)
    models["xgb_total"] = xgb_total

    if HAS_TABPFN:
        max_tabpfn = min(300, len(X))
        X_tab = X[:max_tabpfn]
        y1_tab = y_1x2_enc[:max_tabpfn]
        y2_tab = y_ou25[:max_tabpfn]

        print("Training TabPFN 1X2 (%d echantillons)..." % max_tabpfn)
        try:
            tabpfn_1x2 = TabPFNClassifier(n_estimators=1, random_state=42, ignore_pretraining_limits=True)
            tabpfn_1x2.fit(X_tab, y1_tab)
            models["tabpfn_1x2"] = tabpfn_1x2
            print("  TabPFN 1X2 OK")
        except Exception as e:
            print("  TabPFN 1X2 failed: %s" % e)

        print("Training TabPFN O/U2.5 (%d echantillons)..." % max_tabpfn)
        try:
            tabpfn_ou25 = TabPFNClassifier(n_estimators=1, random_state=42, ignore_pretraining_limits=True)
            tabpfn_ou25.fit(X_tab, y2_tab)
            models["tabpfn_ou25"] = tabpfn_ou25
            print("  TabPFN O/U2.5 OK")
        except Exception as e:
            print("  TabPFN O/U2.5 failed: %s" % e)
    else:
        print("TabPFN not available, skipping...")

    print("Cross-validation temporelle + Calibration metrics...")
    rounds_for_cv = np.array([m["round"] for m in meta])
    sort_idx = np.argsort(rounds_for_cv)
    X_sorted = X[sort_idx]
    y1_sorted = y_1x2_enc[sort_idx]
    y2_sorted = y_ou25[sort_idx]

    tscv = TimeSeriesSplit(n_splits=5)

    cv_results = {"n_samples": len(X), "n_features": X.shape[1]}

    for mname in ["rf_1x2", "xgb_1x2", "gb_1x2", "et_1x2", "lgbm_1x2"]:
        if mname in models:
            try:
                cv = cross_val_score(models[mname], X_sorted, y1_sorted, cv=tscv, scoring="accuracy")
                cv_results[mname] = float(cv.mean())
                print("  %s 1X2: %.1f%% (+/- %.1f%%)" % (mname, cv.mean()*100, cv.std()*100))
            except Exception as e:
                print("  CV %s failed: %s" % (mname, e))

    for mname in ["rf_ou25", "xgb_ou25", "gb_ou25", "et_ou25", "lgbm_ou25"]:
        if mname in models:
            try:
                cv = cross_val_score(models[mname], X_sorted, y2_sorted, cv=tscv, scoring="accuracy")
                cv_results[mname] = float(cv.mean())
                print("  %s O/U25: %.1f%% (+/- %.1f%%)" % (mname, cv.mean()*100, cv.std()*100))
            except Exception as e:
                print("  CV %s failed: %s" % (mname, e))

    for mname in ["tabpfn_1x2", "tabpfn_ou25"]:
        if mname in models:
            try:
                y_target = y1_sorted if "1x2" in mname else y2_sorted
                cv = cross_val_score(models[mname], X_sorted, y_target, cv=tscv, scoring="accuracy")
                cv_results[mname] = float(cv.mean())
                print("  %s: %.1f%% (+/- %.1f%%)" % (mname, cv.mean()*100, cv.std()*100))
            except Exception as e:
                print("  CV %s failed: %s" % (mname, e))

    print("\n=== CV Results (calibres) ===")
    for k, v in sorted(cv_results.items()):
        if isinstance(v, float):
            print(f"  {k}: {v*100:.1f}%")

    feature_importance = {}
    for mname in ["rf_1x2", "et_1x2"]:
        if mname in models:
            model = models[mname]
            base = model
            if hasattr(model, 'calibrated_classifiers_'):
                base = model.calibrated_classifiers_[0].estimator
            if hasattr(base, 'feature_importances_'):
                for i in np.argsort(base.feature_importances_)[::-1][:15]:
                    if i < len(FEATURE_NAMES):
                        fname = FEATURE_NAMES[i]
                        feature_importance[fname] = feature_importance.get(fname, 0) + float(base.feature_importances_[i]) / 2

    print("\nTop 15 features:")
    for fname, imp in sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"  {fname}: {imp:.4f}")

    models["_meta"] = {
        "label_encoder_classes": le_1x2.classes_.tolist(),
        "cv_results": cv_results,
        "feature_importance": feature_importance,
        "feature_names": FEATURE_NAMES,
        "n_samples": len(X),
        "calibrated": True,
    }

    return models, cv_results


def save_models(models):
    os.makedirs(MODEL_DIR, exist_ok=True)
    import pickle
    for name, model in models.items():
        if name.startswith("tabpfn_"):
            path = os.path.join(MODEL_DIR, f"{name}.pkl")
            with open(path, "wb") as f:
                pickle.dump(model, f, protocol=4)
        elif name == "_meta":
            continue
        else:
            path = os.path.join(MODEL_DIR, f"{name}.pkl")
            with open(path, "wb") as f:
                pickle.dump(model, f)

    meta = models.get("_meta", {})
    meta["has_tabpfn"] = HAS_TABPFN and any(k.startswith("tabpfn_") for k in models)
    with open(ENSEMBLE_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Modeles sauvegardes dans {MODEL_DIR}/")


def load_models():
    import pickle
    if not os.path.exists(MODEL_DIR):
        return None

    models = {}
    meta_path = ENSEMBLE_PATH
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            models["_meta"] = json.load(f)

    model_names = ["rf_1x2", "xgb_1x2", "gb_1x2", "et_1x2", "lgbm_1x2", "stacking_1x2",
                   "rf_ou25", "xgb_ou25", "gb_ou25", "et_ou25", "lgbm_ou25", "stacking_ou25",
                   "rf_ou35", "xgb_ou35", "rf_pair", "xgb_pair", "rf_total", "xgb_total"]
    if HAS_TABPFN:
        model_names.extend(["tabpfn_1x2", "tabpfn_ou25"])

    for name in model_names:
        path = os.path.join(MODEL_DIR, f"{name}.pkl")
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    models[name] = pickle.load(f)
            except Exception as e:
                print(f"  Warning: could not load {name}: {e}")

    return models if len(models) > 1 else None


def predict_ensemble(models, features, meta=None):
    if not models or not HAS_ML:
        return None

    X = np.array(features).reshape(1, -1)

    if "_meta" in models and meta is None:
        meta = models["_meta"]
    classes = meta.get("label_encoder_classes", ["1", "2", "X"]) if meta else ["1", "2", "X"]

    def ensemble_predict_proba(model_dict, keys):
        probas = []
        for key in keys:
            if key in model_dict:
                model = model_dict[key]
                if hasattr(model, "predict_proba"):
                    proba = model.predict_proba(X)[0]
                    probas.append(proba)
        if not probas:
            return None
        return np.mean(probas, axis=0)

    def ensemble_predict_binary(model_dict, keys):
        preds = []
        for key in keys:
            if key in model_dict:
                model = model_dict[key]
                pred = model.predict(X)[0]
                preds.append(float(pred))
        if not preds:
            return 0.5
        return np.mean(preds)

    def ensemble_predict_value(model_dict, keys):
        preds = []
        for key in keys:
            if key in model_dict:
                model = model_dict[key]
                pred = model.predict(X)[0]
                preds.append(float(pred))
        if not preds:
            return 3.0
        return np.mean(preds)

    proba_1x2 = ensemble_predict_proba(models, ["rf_1x2", "xgb_1x2", "gb_1x2", "et_1x2", "lgbm_1x2"])

    ou25_raw = ensemble_predict_binary(models, ["rf_ou25", "xgb_ou25", "gb_ou25", "et_ou25", "lgbm_ou25"])

    ou35_raw = ensemble_predict_binary(models, ["rf_ou35", "xgb_ou35"])
    pair_raw = ensemble_predict_binary(models, ["rf_pair", "xgb_pair"])
    total_pred = ensemble_predict_value(models, ["rf_total", "xgb_total"])

    result = {
        "total_goals_pred": round(total_pred, 1),
        "ou25_prob_ml": round(ou25_raw * 100, 1),
        "ou35_prob_ml": round(ou35_raw * 100, 1),
        "pair_prob_ml": round(pair_raw * 100, 1),
        "ml_confidence_1x2": 0,
        "ml_pred_1x2": "?",
    }

    if proba_1x2 is not None:
        best_idx = np.argmax(proba_1x2)
        result["ml_pred_1x2"] = classes[best_idx]
        result["ml_confidence_1x2"] = round(float(proba_1x2[best_idx]) * 100, 1)
        result["ml_proba_1"] = round(float(proba_1x2[classes.index("1")]) * 100, 1) if "1" in classes else 33.3
        result["ml_proba_X"] = round(float(proba_1x2[classes.index("X")]) * 100, 1) if "X" in classes else 33.3
        result["ml_proba_2"] = round(float(proba_1x2[classes.index("2")]) * 100, 1) if "2" in classes else 33.3

    return result


def predict_ensemble_batch(models, all_features_list):
    if not models or not HAS_ML or not all_features_list:
        return [None] * len(all_features_list)

    X_batch = np.array(all_features_list)
    n = len(all_features_list)

    if "_meta" in models:
        meta = models["_meta"]
    else:
        meta = None
    classes = meta.get("label_encoder_classes", ["1", "2", "X"]) if meta else ["1", "2", "X"]

    def batch_proba(model_dict, keys):
        all_probas = []
        for key in keys:
            if key in model_dict and hasattr(model_dict[key], "predict_proba"):
                try:
                    proba = model_dict[key].predict_proba(X_batch)
                    all_probas.append(proba)
                except Exception:
                    pass
        if not all_probas:
            return None
        return np.mean(all_probas, axis=0)

    def batch_binary(model_dict, keys):
        all_preds = []
        for key in keys:
            if key in model_dict:
                try:
                    pred = model_dict[key].predict(X_batch)
                    all_preds.append(pred.astype(float))
                except Exception:
                    pass
        if not all_preds:
            return np.full(n, 0.5)
        return np.mean(all_preds, axis=0)

    def batch_value(model_dict, keys):
        all_preds = []
        for key in keys:
            if key in model_dict:
                try:
                    pred = model_dict[key].predict(X_batch)
                    all_preds.append(pred.astype(float))
                except Exception:
                    pass
        if not all_preds:
            return np.full(n, 3.0)
        return np.mean(all_preds, axis=0)

    proba_1x2 = batch_proba(models, ["rf_1x2", "xgb_1x2", "gb_1x2", "et_1x2", "lgbm_1x2"])
    ou25_raw = batch_binary(models, ["rf_ou25", "xgb_ou25", "gb_ou25", "et_ou25", "lgbm_ou25"])
    ou35_raw = batch_binary(models, ["rf_ou35", "xgb_ou35"])
    pair_raw = batch_binary(models, ["rf_pair", "xgb_pair"])
    total_pred = batch_value(models, ["rf_total", "xgb_total"])

    results = []
    for i in range(n):
        r = {
            "total_goals_pred": round(float(total_pred[i]), 1),
            "ou25_prob_ml": round(float(ou25_raw[i]) * 100, 1),
            "ou35_prob_ml": round(float(ou35_raw[i]) * 100, 1),
            "pair_prob_ml": round(float(pair_raw[i]) * 100, 1),
            "ml_confidence_1x2": 0,
            "ml_pred_1x2": "?",
        }
        if proba_1x2 is not None:
            p = proba_1x2[i]
            best_idx = int(np.argmax(p))
            r["ml_pred_1x2"] = classes[best_idx]
            r["ml_confidence_1x2"] = round(float(p[best_idx]) * 100, 1)
            r["ml_proba_1"] = round(float(p[classes.index("1")]) * 100, 1) if "1" in classes else 33.3
            r["ml_proba_X"] = round(float(p[classes.index("X")]) * 100, 1) if "X" in classes else 33.3
            r["ml_proba_2"] = round(float(p[classes.index("2")]) * 100, 1) if "2" in classes else 33.3
        results.append(r)

    return results


def predict_tabpfn_batch(models, all_features):
    if not models or not HAS_TABPFN:
        return None
    X_batch = np.array(all_features)
    results = []

    tabpfn_1x2 = models.get("tabpfn_1x2")
    tabpfn_ou25 = models.get("tabpfn_ou25")

    probas_1x2 = None
    probas_ou25 = None

    if tabpfn_1x2 is not None:
        try:
            probas_1x2 = tabpfn_1x2.predict_proba(X_batch)
        except Exception:
            pass

    if tabpfn_ou25 is not None:
        try:
            probas_ou25 = tabpfn_ou25.predict_proba(X_batch)
        except Exception:
            pass

    for i in range(len(all_features)):
        r = {}
        if probas_1x2 is not None and i < len(probas_1x2):
            p = probas_1x2[i]
            best = int(np.argmax(p))
            classes = ["0", "1", "2"]
            if hasattr(tabpfn_1x2, "classes_"):
                classes = [str(c) for c in tabpfn_1x2.classes_]
            r["tabpfn_1x2_proba"] = [round(float(x) * 100, 1) for x in p]
            r["tabpfn_1x2_pred"] = classes[best]
            r["tabpfn_1x2_conf"] = round(float(p[best]) * 100, 1)
        if probas_ou25 is not None and i < len(probas_ou25):
            p = probas_ou25[i]
            r["tabpfn_ou25_over"] = round(float(p[1]) * 100, 1) if len(p) > 1 else 50.0
        results.append(r)

    return results


def hybrid_predict(poisson_pred, ml_pred, weights=None):
    if ml_pred is None:
        return poisson_pred

    if weights is None:
        weights = {"poisson": 0.65, "ml": 0.35}

    result = dict(poisson_pred)

    for key in ["prob_dom", "prob_nul", "prob_ext"]:
        poisson_val = poisson_pred.get(key, 33.3)
        ml_key = {"prob_dom": "ml_proba_1", "prob_nul": "ml_proba_X", "prob_ext": "ml_proba_2"}.get(key)
        ml_val = ml_pred.get(ml_key, 33.3)
        result[key] = round(poisson_val * weights["poisson"] + ml_val * weights["ml"], 1)

    total_p = result["prob_dom"] + result["prob_nul"] + result["prob_ext"]
    if total_p > 0:
        result["prob_dom"] = round(result["prob_dom"] / total_p * 100, 1)
        result["prob_nul"] = round(result["prob_nul"] / total_p * 100, 1)
        result["prob_ext"] = round(result["prob_ext"] / total_p * 100, 1)

    ml_ou25 = ml_pred.get("ou25_prob_ml", 50)
    poisson_ou25 = poisson_pred.get("prob_over_25", 50)
    ou_weights = {"poisson": 0.50, "ml": 0.50}
    result["prob_over_25"] = round(poisson_ou25 * ou_weights["poisson"] + ml_ou25 * ou_weights["ml"], 1)
    result["prob_under_25"] = round(100 - result["prob_over_25"], 1)

    ml_ou35 = ml_pred.get("ou35_prob_ml", 35)
    poisson_ou35 = poisson_pred.get("prob_over_35", 35)
    result["prob_over_35"] = round(poisson_ou35 * ou_weights["poisson"] + ml_ou35 * ou_weights["ml"], 1)
    result["prob_under_35"] = round(100 - result["prob_over_35"], 1)

    ml_pair = ml_pred.get("pair_prob_ml", 50)
    poisson_pair = poisson_pred.get("prob_pair", 50)
    result["prob_pair"] = round(poisson_pair * weights["poisson"] + ml_pair * weights["ml"], 1)
    result["prob_impair"] = round(100 - result["prob_pair"], 1)

    result["ml_confidence"] = ml_pred.get("ml_confidence_1x2", 0)
    result["ml_pred_1x2"] = ml_pred.get("ml_pred_1x2", "?")
    result["total_goals_ml"] = ml_pred.get("total_goals_pred", 3.0)
    result["total_goals_pred"] = round(
        poisson_pred.get("total_buts_pred", 3.0) * weights["poisson"] +
        ml_pred.get("total_goals_pred", 3.0) * weights["ml"], 1
    )

    best_prob = max(result["prob_dom"], result["prob_nul"], result["prob_ext"])
    result["confidence"] = round(best_prob, 1)

    if best_prob >= result.get("ml_confidence", 0):
        result["confidence_source"] = "poisson"
    else:
        result["confidence_source"] = "ml"

    result["confidence"] = round(max(best_prob, result.get("ml_confidence", 0)), 1)

    if result["confidence"] >= 75:
        result["alert_level"] = "HAUTE"
        result["alert_color"] = "#e74c3c"
    elif result["confidence"] >= 60:
        result["alert_level"] = "MOYENNE"
        result["alert_color"] = "#f39c12"
    else:
        result["alert_level"] = "FAIBLE"
        result["alert_color"] = "#27ae60"

    if result["prob_dom"] > result["prob_nul"] and result["prob_dom"] > result["prob_ext"]:
        result["res_code"] = "1"
        result["resultat"] = "VICTOIRE DOMICILE (1)"
    elif result["prob_ext"] > result["prob_nul"]:
        result["res_code"] = "2"
        result["resultat"] = "VICTOIRE EXTERIEUR (2)"
    else:
        result["res_code"] = "X"
        result["resultat"] = "MATCH NUL (X)"

    result["ou_confidence"] = poisson_pred.get("ou_confidence", round(max(result["prob_over_25"], result["prob_under_25"]), 1))
    result["ou_pred"] = poisson_pred.get("ou_pred", "Under 2.5")

    return result


def select_high_confidence(predictions, min_confidence=70):
    selected = []
    for p in predictions:
        if p.get("confidence", 0) >= min_confidence:
            selected.append(p)
    selected.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return selected
