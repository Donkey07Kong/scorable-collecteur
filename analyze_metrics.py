import requests
import json

data = requests.get("http://localhost:8766/api/history", timeout=10).json()
history = data["history"]

total = 0
correct = 0

by_conf = {"high": [0, 0], "mid": [0, 0], "low": [0, 0]}
by_dc_conf = {"high": [0, 0], "mid": [0, 0], "low": [0, 0]}
by_elo_diff = {"big": [0, 0], "medium": [0, 0], "small": [0, 0]}
by_form_diff = {"big": [0, 0], "medium": [0, 0], "small": [0, 0]}
by_dc_pred = {"1X": [0, 0], "X2": [0, 0]}
by_dc_correct = [0, 0]

for h in history:
    for p in h.get("predictions", []):
        if not p.get("has_result"):
            continue

        total += 1
        sd = p.get("actual_score_dom", 0)
        se = p.get("actual_score_ext", 0)
        actual = "1" if sd > se else "2" if se > sd else "X"
        res_correct = p.get("res_code") == actual
        if res_correct:
            correct += 1

        conf = p.get("confidence", 0)
        if conf >= 25:
            by_conf["high"][0] += 1
            if res_correct: by_conf["high"][1] += 1
        elif conf >= 18:
            by_conf["mid"][0] += 1
            if res_correct: by_conf["mid"][1] += 1
        else:
            by_conf["low"][0] += 1
            if res_correct: by_conf["low"][1] += 1

        dc_conf = p.get("dc_confidence", 0)
        dc_correct = p.get("dc_correct")
        if dc_conf >= 65:
            by_dc_conf["high"][0] += 1
            if dc_correct: by_dc_conf["high"][1] += 1
        elif dc_conf >= 55:
            by_dc_conf["mid"][0] += 1
            if dc_correct: by_dc_conf["mid"][1] += 1
        else:
            by_dc_conf["low"][0] += 1
            if dc_correct: by_dc_conf["low"][1] += 1

        if dc_correct is not None:
            by_dc_correct[0] += 1
            if dc_correct: by_dc_correct[1] += 1

        home_elo = p.get("home_elo", 1500)
        away_elo = p.get("away_elo", 1500)
        elo_diff = abs(home_elo - away_elo)
        if elo_diff > 100:
            by_elo_diff["big"][0] += 1
            if res_correct: by_elo_diff["big"][1] += 1
        elif elo_diff > 50:
            by_elo_diff["medium"][0] += 1
            if res_correct: by_elo_diff["medium"][1] += 1
        else:
            by_elo_diff["small"][0] += 1
            if res_correct: by_elo_diff["small"][1] += 1

        home_form = p.get("home_form", 0.5)
        away_form = p.get("away_form", 0.5)
        form_diff = abs(home_form - away_form)
        if form_diff > 0.2:
            by_form_diff["big"][0] += 1
            if res_correct: by_form_diff["big"][1] += 1
        elif form_diff > 0.1:
            by_form_diff["medium"][0] += 1
            if res_correct: by_form_diff["medium"][1] += 1
        else:
            by_form_diff["small"][0] += 1
            if res_correct: by_form_diff["small"][1] += 1

        dc_pred = p.get("dc_pred", "")
        if dc_pred in by_dc_pred:
            by_dc_pred[dc_pred][0] += 1
            if dc_correct: by_dc_pred[dc_pred][1] += 1

print("=" * 65)
print("  ANALYSE: QUELLES METRIQUES PREDISENT LE MIEUX?")
print("=" * 65)
print()
print("TOTAL: %d matchs, %d corrects = %.1f%% WR" % (total, correct, correct/total*100 if total else 0))
print()

print("1. CONFIANCE Poisson (1X2):")
for label, name in [("high", "HAUTE >25%"), ("mid", "MOYENNE 18-25%"), ("low", "FAIBLE <18%")]:
    n, c = by_conf[label]
    wr = c/n*100 if n else 0
    print("   %-20s: %d/%d = %.1f%%" % (name, c, n, wr))

print()
print("2. CONFIANCE DC (Double Chance):")
for label, name in [("high", "DC > 65%"), ("mid", "DC 55-65%"), ("low", "DC < 55%")]:
    n, c = by_dc_pred.get("", [0,0])
    n, c = by_dc_conf[label]
    wr = c/n*100 if n else 0
    print("   %-20s: %d/%d = %.1f%%" % (name, c, n, wr))

print()
print("3. ECART ELO (diff abs):")
for label, name in [("big", "ELO diff > 100"), ("medium", "ELO diff 50-100"), ("small", "ELO diff < 50")]:
    n, c = by_elo_diff[label]
    wr = c/n*100 if n else 0
    print("   %-20s: %d/%d = %.1f%%" % (name, c, n, wr))

print()
print("4. ECART FORME (diff forme):")
for label, name in [("big", "Forme diff > 20%"), ("medium", "Forme diff 10-20%"), ("small", "Forme diff < 10%")]:
    n, c = by_form_diff[label]
    wr = c/n*100 if n else 0
    print("   %-20s: %d/%d = %.1f%%" % (name, c, n, wr))

print()
print("5. DC PRED PAR TYPE:")
for label, name in [("1X", "DC 1X"), ("X2", "DC X2")]:
    n, c = by_dc_pred[label]
    wr = c/n*100 if n else 0
    print("   %-20s: %d/%d = %.1f%%" % (name, c, n, wr))

print()
print("6. DC GLOBAL:")
n, c = by_dc_correct
wr = c/n*100 if n else 0
print("   DC pred total: %d/%d = %.1f%%" % (c, n, wr))
