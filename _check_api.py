import json, requests

HEADERS = {
    'accept': 'application/json',
    'app-version': '34283',
    'referer': 'https://bet261.mg/'
}

# Check the main API for completed rounds with scores
url = 'https://hg-event-api-prod.sporty-tech.net/api/instantleagues/8060/matches'
r = requests.get(url, headers=HEADERS, timeout=10)
data = r.json()

for rnd in data.get('rounds', []):
    rn = rnd.get('roundNumber', 0)
    matches = rnd.get('matches', [])
    if not matches:
        continue
    # Check first match for score fields
    m = matches[0]
    home = m.get('homeTeam', {}).get('name', '?')
    away = m.get('awayTeam', {}).get('name', '?')
    mid = m.get('id', 0)
    
    # Check all score-related fields
    score_fields = {k: v for k, v in m.items() if 'score' in k.lower() or 'result' in k.lower() or 'status' in k.lower() or 'winner' in k.lower()}
    print("Round %d: %s vs %s (id=%d)" % (rn, home, away, mid))
    print("  Score fields: %s" % score_fields)
    print("  All keys: %s" % list(m.keys()))
    
    # Also check all matches for this round
    for m2 in matches:
        h2 = m2.get('homeTeam', {}).get('name', '?')
        a2 = m2.get('awayTeam', {}).get('name', '?')
        sf = {k: v for k, v in m2.items() if 'score' in k.lower() or 'result' in k.lower()}
        if sf:
            print("  %s vs %s: %s" % (h2, a2, sf))
    print()
