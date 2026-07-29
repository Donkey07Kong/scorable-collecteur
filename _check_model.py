import csv, json, re

# 1. What does prediction_engine need from CSV?
with open('D:/Documents/261CAF/prediction_engine.py', 'r', encoding='utf-8') as f:
    pe = f.read()
match = re.search(r'required_cols\s*=\s*\{([^}]+)\}', pe)
print('Required cols:', match.group(1) if match else 'NOT FOUND')

# 2. What does team_profiler need?
with open('D:/Documents/261CAF/team_profiler.py', 'r', encoding='utf-8') as f:
    tp = f.read()
match = re.search(r'def load_csv_data.*?\n\n', tp, re.DOTALL)
if match:
    gets = re.findall(r'row\.get\("([^"]+)"', match.group(0))
    print('team_profiler reads:', gets)

# 3. Does the model retrain on startup?
match2 = re.search(r'(train_ensemble.*?\n\n)', pe, re.DOTALL)
if match2:
    print('train call in prediction_engine:', match2.group(0)[:200])

# 4. How many donnees does it expect?
n_match = re.search(r'donnees.*?=\s*charger_historique', pe)
print('charger_historique call:', n_match.group(0) if n_match else 'NOT FOUND')

# 5. Does dashboard.py also train?
with open('D:/Documents/261CAF/dashboard.py', 'r', encoding='utf-8') as f:
    dash = f.read()
train_calls = re.findall(r'train_ensemble\w*\(', dash)
print('train_ensemble calls in dashboard.py:', len(train_calls))
for i, line in enumerate(dash.split('\n'), 1):
    if 'train_ensemble' in line:
        print('  L%d: %s' % (i, line.strip()[:120]))

# 6. Check if ML model file exists
import os
for fn in os.listdir('D:/Documents/261CAF'):
    if fn.endswith('.pkl') or fn.endswith('.joblib') or 'model' in fn.lower():
        fpath = os.path.join('D:/Documents/261CAF', fn)
        sz = os.path.getsize(fpath)
        print('Model file: %s (%d bytes)' % (fn, sz))
