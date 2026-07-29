import json, requests

HEADERS = {
    'accept': 'application/json',
    'app-version': '34283',
    'referer': 'https://bet261.mg/'
}

# Dump full structure of one playout match
url = 'https://hg-event-api-prod.sporty-tech.net/api/instantleagues/round/38/playout?eventCategoryId=156008&parentEventCategoryId=8060'
r = requests.get(url, headers=HEADERS, timeout=5)
data = r.json()
matches = data.get('matches', [])
if matches:
    print("Full playout match structure:")
    print(json.dumps(matches[0], indent=2, ensure_ascii=False))
    print("\nAll top-level keys:", list(data.keys()))
