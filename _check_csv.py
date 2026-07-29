import csv

csv_path = 'D:/Documents/261CAF/donnees_equipes.csv'
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = [r for r in reader if int(r.get('round', 0)) == 24]

# Find rows matching the prediction matchups
target_matches = [
    ("South Africa", "Benin"),
    ("Zambia", "Tanzania"),
    ("Cameroon", "Senegal"),
    ("Gabon", "Morocco"),
    ("DR Congo", "Tunisia"),
    ("Equatorial Guinea", "Egypt"),
    ("Botswana", "Burkina Faso"),
    ("Angola", "Ivory Coast"),
    ("Comoros", "Uganda"),
    ("Zimbabwe", "Algeria"),
    ("Nigeria", "Mali"),
    ("Mozambique", "Sudan"),
]

print("CSV rows for round 24 matching predictions:")
for t in target_matches:
    found = [r for r in rows if r['home_team'] == t[0] and r['away_team'] == t[1]]
    if found:
        for r in found:
            print("  %s vs %s: %s-%s cycle=%s match_id=%s" % (t[0], t[1], r['score_final_dom'], r['score_final_ext'], r.get('cycle', '?'), r.get('match_id', '?')))
    else:
        print("  %s vs %s: NOT FOUND" % t)

print("\nAll unique matchups in CSV round 24:")
seen = set()
for r in rows:
    k = (r['home_team'], r['away_team'])
    if k not in seen:
        seen.add(k)
        print("  %s vs %s: %s-%s cycle=%s" % (r['home_team'], r['away_team'], r['score_final_dom'], r['score_final_ext'], r.get('cycle', '?')))
