import json, requests

HEADERS = {
    'accept': 'application/json',
    'app-version': '34283',
    'referer': 'https://bet261.mg/'
}

# First check what rounds are available in main API
url = 'https://hg-event-api-prod.sporty-tech.net/api/instantleagues/8060/matches'
r = requests.get(url, headers=HEADERS, timeout=10)
data = r.json()
for rnd in data.get('rounds', []):
    rn = rnd.get('roundNumber', 0)
    ms = rnd.get('matches', [])
    if ms:
        print("Main API round %d: %d matches" % (rn, len(ms)))

# Now try playout for the current round
for rn_test in [24, 32, 33, 34, 35, 36, 37, 38, 39, 40]:
    url2 = 'https://hg-event-api-prod.sporty-tech.net/api/instantleagues/round/%d/playout?eventCategoryId=156008&parentEventCategoryId=8060' % rn_test
    try:
        r2 = requests.get(url2, headers=HEADERS, timeout=5)
        data2 = r2.json()
        matches2 = data2.get('matches', [])
        if matches2:
            m0 = matches2[0]
            goals = m0.get('goals', [])
            home = m0.get('homeTeam', {})
            away = m0.get('awayTeam', {})
            print("Playout round %d: %d matches, first has homeTeam=%s awayTeam=%s" % (
                rn_test, len(matches2),
                json.dumps(home, ensure_ascii=False)[:200],
                json.dumps(away, ensure_ascii=False)[:200]
            ))
        else:
            print("Playout round %d: 0 matches" % rn_test)
    except Exception as e:
        print("Playout round %d: error %s" % (rn_test, e))
