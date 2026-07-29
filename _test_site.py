import requests
import json

HEADERS = {'accept': 'application/json', 'app-version': '34283', 'referer': 'https://bet261.mg/'}

# Get current round from predictions API
url = 'https://hg-event-api-prod.sporty-tech.net/api/instantleagues/8060/matches'
r = requests.get(url, headers=HEADERS, timeout=10)
data = r.json()
rnd = data['rounds'][0]
rn = rnd['roundNumber']

# Build ID->teams from predictions
id_teams = {}
for m in rnd.get('matches', []):
    mid = m.get('id')
    ht = m.get('homeTeam', {}).get('name', '?')
    at = m.get('awayTeam', {}).get('name', '?')
    id_teams[mid] = (ht, at)

print('Current round: %d' % rn)
print('Prediction IDs: %s' % [m.get('id') for m in rnd.get('matches', [])])

# Fetch playout for CURRENT round
url2 = 'https://hg-event-api-prod.sporty-tech.net/api/instantleagues/round/%d/playout?eventCategoryId=156008&parentEventCategoryId=8060' % rn
r2 = requests.get(url2, headers=HEADERS, timeout=10)
data2 = r2.json()
play_matches = data2.get('matches', [])

print('Playout IDs: %s' % [m.get('id') for m in play_matches])
print()

# Direct ID matching
matched = 0
for m in play_matches:
    mid = m.get('id')
    goals = m.get('goals', [])
    if goals:
        g = goals[-1]
        score = '%d-%d' % (int(g.get('homeScore', 0)), int(g.get('awayScore', 0)))
    else:
        score = '0-0'
    if mid in id_teams:
        ht, at = id_teams[mid]
        print('  ID %d: %s vs %s = %s' % (mid, ht, at, score))
        matched += 1
    else:
        print('  ID %d: NO MATCH (score=%s)' % (mid, score))

print()
print('Direct ID match: %d/%d' % (matched, len(play_matches)))
print('ID MATCH: %s' % (set(m.get('id') for m in play_matches) == set(id_teams.keys())))
