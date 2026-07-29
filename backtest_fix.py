import json
import sys
sys.path.insert(0, 'D:/Documents/261')
import odds_matrix

with open('D:/Documents/261/historique_predictions.json', 'r') as f:
    data = json.load(f)

def result_code(r):
    if 'DOMICILE' in r: return '1'
    elif 'EXTERIEUR' in r: return '2'
    elif 'NUL' in r: return 'X'
    return None

def fix_ml_pred(ml_pred, ml_conf, p):
    if ml_pred == 'X':
        p1 = p.get('ml_proba_1', 33)
        p2 = p.get('ml_proba_2', 33)
        total = p1 + p2
        if total > 0:
            if p1 >= p2:
                return '1', round(p1 / total * 100, 1)
            else:
                return '2', round(p2 / total * 100, 1)
        return '1', 50.0
    return ml_pred, ml_conf

total = 0
old_ml_correct = 0
old_mx_correct = 0
new_mx_correct = 0
new_combined_correct = 0
baseline_home = 0

zone_fails_old = {}
zone_fails_new = {}
disagree_fails_new = []

for e in data:
    for p in e['predictions']:
        rc = result_code(p.get('resultat', ''))
        if not rc:
            continue
        total += 1

        cr = p.get('cotes_raw', {})
        c1 = cr.get('cote_1', 2.0)
        cx = cr.get('cote_X', 3.5)
        c2 = cr.get('cote_2', 3.5)
        elo_h = p.get('home_elo', None)
        elo_a = p.get('away_elo', None)

        ml_pred_raw = p.get('ml_pred_1x2', '?')
        ml_conf_raw = p.get('ml_confidence_1x2', 0)
        ml_pred, ml_conf = fix_ml_pred(ml_pred_raw, ml_conf_raw, p)

        mx_old = p.get('odds_matrix', {})
        old_fav = mx_old.get('fav_side', '?') if mx_old else '?'
        if old_fav == rc:
            old_mx_correct += 1

        if ml_pred == rc:
            old_ml_correct += 1
        if rc == '1':
            baseline_home += 1

        new_mx = odds_matrix.classify_match(c1, cx, c2, elo_h, elo_a)
        new_mx_fav = new_mx.get('fav_side', '?')
        if new_mx_fav == rc:
            new_mx_correct += 1
        else:
            z = new_mx.get('label', '?')
            zone_fails_new[z] = zone_fails_new.get(z, 0) + 1

        ml_p = dict(p)
        ml_p['ml_pred_1x2'] = ml_pred
        ml_p['ml_confidence_1x2'] = ml_conf
        cp = odds_matrix.get_combined_prediction(new_mx, ml_p)
        new_final = cp.get('final_pred', '1')
        if new_final == rc:
            new_combined_correct += 1
        else:
            if not cp.get('agreement', True):
                disagree_fails_new.append({
                    'home': p.get('home_team'),
                    'away': p.get('away_team'),
                    'result': rc,
                    'final': new_final,
                    'ml': ml_pred,
                    'mx': new_mx_fav,
                    'zone': new_mx.get('label', '?'),
                    'c1': c1, 'c2': c2,
                    'elo_h': elo_h or 0, 'elo_a': elo_a or 0,
                })

print("=" * 55)
print("  BACKTEST AVEC CORRECTIONS (%d matchs)" % total)
print("=" * 55)
print()
print("  Baseline (toujours 1):  %d/%d = %.1f%%" % (baseline_home, total, baseline_home/total*100))
print("  Ancien ML:              %d/%d = %.1f%%" % (old_ml_correct, total, old_ml_correct/total*100))
print("  Ancienne Matrice:       %d/%d = %.1f%%" % (old_mx_correct, total, old_mx_correct/total*100))
print()
print("  Nouvelle Matrice (no-X): %d/%d = %.1f%%" % (new_mx_correct, total, new_mx_correct/total*100))
print("  Final Combine:          %d/%d = %.1f%%" % (new_combined_correct, total, new_combined_correct/total*100))
print()
gain = (new_combined_correct - old_mx_correct) / total * 100
print("  GAIN vs ancienne matrice: +%.1f%%" % gain)

print()
print("=== ECHECS DU COMBINE (desaccord) ===")
print("Nombre: %d" % len(disagree_fails_new))
for f in disagree_fails_new:
    print("  %s vs %s -> %s | Final:%s ML:%s Mat:%s (%s)" % (
        f['home'], f['away'], f['result'], f['final'], f['ml'], f['mx'], f['zone']))
    print("    Cotes: 1=%.2f 2=%.2f | ELO: H=%d A=%d" % (f['c1'], f['c2'], f['elo_h'], f['elo_a']))

print()
print("=== ECHECS RESTANTS (tous) ===")
from collections import Counter
remaining_fails = 0
for e in data:
    for p in e['predictions']:
        rc = result_code(p.get('resultat', ''))
        if not rc: continue
        cr = p.get('cotes_raw', {})
        c1 = cr.get('cote_1', 2.0)
        cx = cr.get('cote_X', 3.5)
        c2 = cr.get('cote_2', 3.5)
        elo_h = p.get('home_elo', None)
        elo_a = p.get('away_elo', None)
        ml_pred, ml_conf = fix_ml_pred(p.get('ml_pred_1x2', '?'), p.get('ml_confidence_1x2', 0), p)
        new_mx = odds_matrix.classify_match(c1, cx, c2, elo_h, elo_a)
        ml_p = dict(p)
        ml_p['ml_pred_1x2'] = ml_pred
        ml_p['ml_confidence_1x2'] = ml_conf
        cp = odds_matrix.get_combined_prediction(new_mx, ml_p)
        final = cp.get('final_pred', '1')
        if final != rc:
            remaining_fails += 1
print("Total echecs restants: %d/%d = %.1f%%" % (remaining_fails, total, remaining_fails/total*100))
