import json

with open('D:/Documents/261/historique_predictions.json', 'r') as f:
    data = json.load(f)

# Map resultat to code
def result_code(r):
    if 'DOMICILE' in r:
        return '1'
    elif 'EXTERIEUR' in r:
        return '2'
    elif 'NUL' in r:
        return 'X'
    return None

total_matches = 0
correct_ml = 0
correct_matrix = 0
correct_combined = 0
matrix_total = 0
combined_total = 0
correct_ou25 = 0
ou_total = 0

zone_stats = {}
agree_correct = 0
agree_total = 0
disagree_correct = 0
disagree_total = 0

round_stats = {}

for e in data:
    rnd = e.get('round', '?')
    preds = e.get('predictions', [])
    if rnd not in round_stats:
        round_stats[rnd] = {'total': 0, 'ml': 0, 'mat': 0, 'mat_total': 0, 'cmb': 0, 'cmb_total': 0}

    for p in preds:
        result_raw = p.get('resultat', '')
        rc = result_code(result_raw)
        if not rc:
            continue
        total_matches += 1
        round_stats[rnd]['total'] += 1

        # ML
        ml_pred = p.get('ml_pred_1x2')
        if ml_pred:
            if str(ml_pred) == rc:
                correct_ml += 1
                round_stats[rnd]['ml'] += 1

        # Matrix
        mx = p.get('odds_matrix')
        if mx and mx.get('fav_side'):
            matrix_total += 1
            round_stats[rnd]['mat_total'] += 1
            if mx['fav_side'] == rc:
                correct_matrix += 1
                round_stats[rnd]['mat'] += 1

            zone = mx.get('label', 'inconnu')
            if zone not in zone_stats:
                zone_stats[zone] = {'total': 0, 'correct': 0}
            zone_stats[zone]['total'] += 1
            if mx['fav_side'] == rc:
                zone_stats[zone]['correct'] += 1

        # Combined
        cp = p.get('combined_prediction')
        if cp and cp.get('fav_side'):
            combined_total += 1
            round_stats[rnd]['cmb_total'] += 1
            if cp['fav_side'] == rc:
                correct_combined += 1
                round_stats[rnd]['cmb'] += 1

        # O/U
        ou_pred = p.get('ou_pred')
        if ou_pred:
            total_g = p.get('total_buts', 0) or 0
            ou_actual = 'Over' if total_g > 2.5 else 'Under'
            if ou_pred == ou_actual or ou_pred.upper() == ('OVER' if total_g > 2.5 else 'UNDER').upper():
                correct_ou25 += 1
            ou_total += 1

        # Agreement
        if cp and cp.get('fav_side'):
            if cp.get('agreement'):
                agree_total += 1
                if mx and mx.get('fav_side') == rc:
                    agree_correct += 1
            else:
                disagree_total += 1
                if mx and mx.get('fav_side') == rc:
                    disagree_correct += 1

print("=" * 50)
print("  STATISTIQUES DE REUSSITE (bet261 Virtual)")
print("=" * 50)
print()
print("Total matchs analyses: %d (sur %d rondes)" % (total_matches, len(data)))
print()
print("-" * 50)
print("  PERFORMANCE GLOBALE")
print("-" * 50)
print("  ML 1X2:        %d/%d = %.1f%%  (baseline: 56%%)" % (correct_ml, total_matches, correct_ml/total_matches*100))
if matrix_total > 0:
    print("  Matrice 1X2:   %d/%d = %.1f%%" % (correct_matrix, matrix_total, correct_matrix/matrix_total*100))
if combined_total > 0:
    print("  Combine:       %d/%d = %.1f%%" % (correct_combined, combined_total, correct_combined/combined_total*100))
if ou_total > 0:
    print("  O/U 2.5:       %d/%d = %.1f%%" % (correct_ou25, ou_total, correct_ou25/ou_total*100))

print()
print("-" * 50)
print("  ACCORD ML + MATRICE")
print("-" * 50)
if agree_total > 0:
    print("  D'accord:      %d/%d = %.1f%%" % (agree_correct, agree_total, agree_correct/agree_total*100))
if disagree_total > 0:
    print("  Desaccord:     %d/%d = %.1f%%" % (disagree_correct, disagree_total, disagree_correct/disagree_total*100))

print()
print("-" * 50)
print("  PAR ZONE DE COTE")
print("-" * 50)
for zone, s in sorted(zone_stats.items(), key=lambda x: -x[1]['correct']/max(x[1]['total'], 1)):
    pct = s['correct'] / s['total'] * 100 if s['total'] > 0 else 0
    delta = pct - 56.1
    sign = "+" if delta > 0 else ""
    print("  %-30s %d/%d = %5.1f%%  (%s%.1f vs baseline)" % (zone, s['correct'], s['total'], pct, sign, delta))

print()
print("-" * 50)
print("  TENDANCE PAR RONDE")
print("-" * 50)
for rnd in sorted(round_stats.keys(), key=lambda x: int(x)):
    s = round_stats[rnd]
    if s['total'] == 0:
        continue
    ml_pct = s['ml'] / s['total'] * 100
    mat_pct = s['mat'] / s['mat_total'] * 100 if s['mat_total'] > 0 else 0
    print("  R%-3d  %2d matchs  ML: %d/%2d (%4.0f%%)  Mat: %d/%2d (%4.0f%%)" % (
        int(rnd), s['total'], s['ml'], s['total'], ml_pct, s['mat'], s['mat_total'], mat_pct))

print()
print("=" * 50)
print("  VERDICT: RNG biaise = difficulte de predire")
print("=" * 50)
