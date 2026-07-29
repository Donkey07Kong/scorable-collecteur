import json

d = json.load(open("D:/Documents/261CAF/historique_predictions.json", "r", encoding="utf-8"))

# Check a few entries with playout data
for i, e in enumerate(d[:10]):
    rnd = e.get("round")
    preds = e.get("predictions", [])
    ps = e.get("playout_snapshot", {})
    acc = e.get("accuracy_result", "?")
    total = e.get("total_matches_checked", "?")
    ts = e.get("timestamp", "?")
    
    has_playout = len(ps) > 0
    resolved = sum(1 for v in ps.values() if v.get("_resolved"))
    
    print(f"\n=== Entry {i}: Round {rnd} (ts={ts}) ===")
    print(f"  Predictions: {len(preds)}, Playout entries: {len(ps)}, Resolved: {resolved}")
    print(f"  accuracy_result: {acc}, total_checked: {total}")
    
    if preds and ps:
        for p in preds[:3]:
            key = f"{p['home_team']}|{p['away_team']}"
            pl = ps.get(key, {})
            real = f"{pl.get('score_dom','?')}-{pl.get('score_ext','?')}" if pl else "NO PLAYOUT"
            pred_score = p.get("score_pred", "?")
            print(f"  {p['home_team']} vs {p['away_team']}: pred={pred_score} real={real} res={pl.get('_resolved','?')}")

# Now check how many rounds have playout vs not
print("\n\n=== SUMMARY ===")
for i, e in enumerate(d):
    rnd = e.get("round")
    ps = e.get("playout_snapshot", {})
    resolved = sum(1 for v in ps.values() if v.get("_resolved"))
    preds = len(e.get("predictions", []))
    acc = e.get("accuracy_result", "?")
    ts = e.get("timestamp", "?")
    has_playout = "YES" if resolved > 0 else "NO"
    print(f"  Round {rnd}: playout={has_playout} ({resolved}/{preds}) acc={acc} ts={ts}")
