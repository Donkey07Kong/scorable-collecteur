import json, requests

HEADERS = {
    'accept': 'application/json',
    'app-version': '34283',
    'referer': 'https://bet261.mg/'
}

ROUND_TO_CHECK = 24

# 1. Fetch live playout
url = 'https://hg-event-api-prod.sporty-tech.net/api/instantleagues/round/%d/playout?eventCategoryId=156008&parentEventCategoryId=8060' % ROUND_TO_CHECK
r = requests.get(url, headers=HEADERS, timeout=5)
data = r.json()
playout_matches = data.get('matches', [])

playout_scores = []
for ev in playout_matches:
    goals = ev.get('goals', [])
    if goals:
        f = goals[-1]
        hs = int(f.get('homeScore', 0))
        aws = int(f.get('awayScore', 0))
    else:
        hs, aws = 0, 0
    playout_scores.append((hs, aws))

print("Playout scores (position order):")
for i, s in enumerate(playout_scores):
    print("  [%d] %d-%d" % (i, s[0], s[1]))

# 2. Load stored data
d = json.load(open('D:/Documents/261CAF/historique_predictions.json', 'r', encoding='utf-8'))
for e in d:
    if e.get('round') == ROUND_TO_CHECK:
        preds = e.get('predictions', [])
        snap = e.get('playout_snapshot', {})
        
        print("\nStored scores (prediction order):")
        stored_scores = []
        for p in preds:
            key = "%s|%s" % (p['home_team'], p['away_team'])
            s = snap.get(key, {})
            sd = s.get('score_dom', '?')
            se = s.get('score_ext', '?')
            stored_scores.append((sd, se))
            print("  %s vs %s: %s-%s" % (p['home_team'], p['away_team'], sd, se))
        
        # 3. Check if stored scores appear in playout
        print("\n--- Verification ---")
        playout_set = set(playout_scores)
        stored_set = set((int(x) if x != '?' else x, int(y) if y != '?' else y) for x, y in stored_scores if x != '?')
        
        missing_from_playout = stored_set - playout_set
        extra_in_playout = playout_set - stored_set
        print("Scores in stored but NOT in playout: %s" % missing_from_playout)
        print("Scores in playout but NOT in stored: %s" % extra_in_playout)
        
        # 4. Check CSV data
        import csv
        csv_path = 'D:/Documents/261CAF/donnees_equipes.csv'
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                csv_rows = [r for r in reader if int(r.get('round', 0)) == ROUND_TO_CHECK]
            print("\nCSV data for round %d: %d rows" % (ROUND_TO_CHECK, len(csv_rows)))
            for row in csv_rows[:3]:
                print("  %s vs %s: %s-%s" % (row['home_team'], row['away_team'], row.get('score_final_dom','?'), row.get('score_final_ext','?')))
        except Exception as ex:
            print("CSV error: %s" % ex)
        
        # 5. Check what bet261 ACTUALLY shows by fetching from predictions API (completed round might have scores)
        print("\n--- Checking prediction API for round %d ---" % ROUND_TO_CHECK)
        url2 = 'https://hg-event-api-prod.sporty-tech.net/api/instantleagues/8060/matches'
        r2 = requests.get(url2, headers=HEADERS, timeout=8)
        rd = r2.json()
        for rnd in rd.get('rounds', []):
            rn = rnd.get('roundNumber', 0)
            if rn == ROUND_TO_CHECK:
                for m in rnd.get('matches', []):
                    home = m.get('homeTeam', {}).get('name', '?')
                    away = m.get('awayTeam', {}).get('name', '?')
                    mid = m.get('id', 0)
                    score = m.get('score', {})
                    result = m.get('result', {})
                    print("  %s vs %s (id=%d) score=%s result=%s status=%s" % (
                        home, away, mid, score, result, m.get('status', '?')))
                break
        break
