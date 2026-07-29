import requests

data = requests.get('http://localhost:8766/api/history', timeout=30).json()
failures = []
for h in sorted(data['history'], key=lambda x: x['round']):
    for p in h['predictions']:
        if p.get('dc_favori') and p.get('dc_correct') == False:
            dc_actual = '1X' if p.get('actual_dc_1X') else ('X2' if p.get('actual_dc_X2') else '12')
            failures.append({
                'round': h['round'], 'home': p['home_team'], 'away': p['away_team'],
                'dc_pred': p['dc_pred'], 'dc_conf': p['dc_confidence'],
                'dc_actual': dc_actual, 'score': str(p['actual_score_dom']) + '-' + str(p['actual_score_ext']),
                'res_code': p['res_code'], 'conf_1x2': p['confidence'],
                'prob_dc_1X': p.get('prob_dc_1X', 0), 'prob_dc_X2': p.get('prob_dc_X2', 0),
                'prob_dom': p.get('prob_dom', 0), 'prob_nul': p.get('prob_nul', 0), 'prob_ext': p.get('prob_ext', 0)
            })

print('=== ECHECS FAVORIS DC ===')
for f in failures:
    print("R" + str(f['round']) + ": " + f['home'] + " vs " + f['away'] + " | DC=" + f['dc_pred'] + "(" + str(f['dc_conf']) + "%) -> reel: " + f['dc_actual'] + " Score=" + f['score'] + " 1X2=" + f['res_code'] + "(" + str(f['conf_1x2']) + "%)")

all_favs = []
for h in data['history']:
    for p in h['predictions']:
        if p.get('dc_favori'):
            all_favs.append(p)

ok = [p for p in all_favs if p.get('dc_correct') == True]
fail = [p for p in all_favs if p.get('dc_correct') == False]
avg_ok = sum(p['dc_confidence'] for p in ok) / len(ok) if ok else 0
avg_fail = sum(p['dc_confidence'] for p in fail) / len(fail) if fail else 0
print("")
print("Conf moy SUCCES: " + str(round(avg_ok, 1)) + "%")
print("Conf moy ECHECS: " + str(round(avg_fail, 1)) + "%")
print("Total favoris: " + str(len(all_favs)) + ", OK: " + str(len(ok)) + ", FAIL: " + str(len(fail)))

print("")
print("=== SEUIL MINIMUM POUR 100% ===")
# Find minimum DC confidence threshold where all top 5 would pass
rounds = {}
for h in sorted(data['history'], key=lambda x: x['round']):
    rnd = h['round']
    rnd_favs = [p for p in h['predictions'] if p.get('has_result') and p.get('dc_confidence', 0) > 0]
    rnd_favs.sort(key=lambda x: x['dc_confidence'], reverse=True)
    rounds[rnd] = rnd_favs[:5]

for threshold in range(70, 96, 2):
    total_ok = 0
    total_all = 0
    for rnd, favs in rounds.items():
        top5 = [p for p in favs if p['dc_confidence'] >= threshold][:5]
        if len(top5) == 5:
            total_ok += sum(1 for p in top5 if p.get('dc_correct') == True)
            total_all += len(top5)
    if total_all > 0:
        pct = round(total_ok / total_all * 100, 1)
        count = total_all // len(rounds) if rounds else 0
        print("Seuil >=" + str(threshold) + "%: " + str(total_ok) + "/" + str(total_all) + " = " + str(pct) + "% (" + str(count) + " favoris/round)")
