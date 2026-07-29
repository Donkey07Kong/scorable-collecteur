import json

with open("D:/Documents/261CAF/historique_predictions.json", "r", encoding="utf-8") as f:
    history = json.load(f)

cleared = 0
for entry in history:
    playout_id_map = entry.get("playout_id_map", {})
    if playout_id_map:
        continue  # Keep entries with proper ID mapping
    
    for pred in entry.get("predictions", []):
        if pred.get("has_result"):
            cleared += 1
            pred["has_result"] = False
            pred.pop("actual_score_dom", None)
            pred.pop("actual_score_ext", None)
            pred.pop("actual_total", None)
            pred.pop("result_source", None)
            pred.pop("actual_dc_1X", None)
            pred.pop("actual_dc_X2", None)
            pred.pop("actual_dc_12", None)
            pred.pop("dc_correct", None)
            pred.pop("ou_pred_correct", None)
            pred.pop("ou_actual", None)
            pred.pop("btts_correct", None)
            pred.pop("actual_btts", None)

with open("D:/Documents/261CAF/historique_predictions.json", "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=None)

print("Cleared %d has_result flags from old entries" % cleared)
print("Total entries: %d" % len(history))
