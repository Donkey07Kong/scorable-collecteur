import json

def correct_history_with_scraped():
    scraped_path = "D:/Documents/261CAF/bet261_real_results.json"
    history_path = "D:/Documents/261CAF/historique_predictions.json"
    
    with open(scraped_path, 'r', encoding='utf-8') as f:
        scraped = json.load(f)
    with open(history_path, 'r', encoding='utf-8') as f:
        history = json.load(f)
    
    scraped_int = {int(k): v for k, v in scraped.items()}
    
    scraped_lookup = {}
    for rnd, matches in scraped_int.items():
        for h, a, sd, se in matches:
            key = (h.lower().strip(), a.lower().strip())
            scraped_lookup[key] = (rnd, sd, se)
    
    corrected = 0
    matched_preds = 0
    unmatched = 0
    swapped = 0
    
    for entry in history:
        preds = entry.get('predictions', [])
        for pred in preds:
            home = pred.get('home_team', '').strip()
            away = pred.get('away_team', '').strip()
            key = (home.lower(), away.lower())
            rev_key = (away.lower(), home.lower())
            
            if key in scraped_lookup:
                _, sd, se = scraped_lookup[key]
                is_swapped = False
            elif rev_key in scraped_lookup:
                _, se_raw, sd_raw = scraped_lookup[rev_key]
                sd = se_raw
                se = sd_raw
                is_swapped = True
                swapped += 1
            else:
                unmatched += 1
                continue
            
            matched_preds += 1
            
            pred['actual_score_dom'] = sd
            pred['actual_score_ext'] = se
            pred['has_result'] = True
            pred['score_was_swapped'] = is_swapped
            
            pred_sd = pred.get('score_dom', 0)
            pred_se = pred.get('score_ext', 0)
            pred['correct_exact'] = (pred_sd == sd and pred_se == se)
            
            if sd > se:
                true_label = '1'
            elif sd == se:
                true_label = 'X'
            else:
                true_label = '2'
            pred['true_label_1x2'] = true_label
            pred['correct_1x2'] = (pred.get('res_code') == true_label)
            
            true_dc = []
            if sd >= se: true_dc.append('1X')
            if sd == se: true_dc.append('X')
            if sd <= se: true_dc.append('X2')
            if sd != se: true_dc.append('12')
            pred['true_dc'] = true_dc
            pred['correct_dc'] = (pred.get('dc_pred', '') in true_dc)
            
            true_total = sd + se
            pred['true_total'] = true_total
            
            true_btts = (sd > 0 and se > 0)
            pred['true_btts'] = true_btts
            pred['correct_btts'] = (true_btts == (pred.get('btts_pred') == 'BTTS Oui'))
            
            corrected += 1
    
    total_matches = 0
    total_exact = 0
    total_1x2 = 0
    total_dc = 0
    total_btts = 0
    
    for entry in history:
        for pred in entry.get('predictions', []):
            if pred.get('has_result'):
                total_matches += 1
                if pred.get('correct_exact'): total_exact += 1
                if pred.get('correct_1x2'): total_1x2 += 1
                if pred.get('correct_dc'): total_dc += 1
                if pred.get('correct_btts'): total_btts += 1
    
    print("=== CORRECTION RESULTS ===")
    print("Corrected (newly resolved): %d" % corrected)
    print("Swapped home/away: %d" % swapped)
    print("Unmatched: %d" % unmatched)
    print()
    print("=== GLOBAL PERFORMANCE ===")
    print("Matches with result: %d" % total_matches)
    if total_matches > 0:
        print("Exact:     %3d / %d = %.1f%%" % (total_exact, total_matches, 100*total_exact/total_matches))
        print("1X2:       %3d / %d = %.1f%%" % (total_1x2, total_matches, 100*total_1x2/total_matches))
        print("DC:        %3d / %d = %.1f%%" % (total_dc, total_matches, 100*total_dc/total_matches))
        print("BTTS:      %3d / %d = %.1f%%" % (total_btts, total_matches, 100*total_btts/total_matches))
    
    with open(history_path, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False)
    print("\nSaved.")

if __name__ == "__main__":
    correct_history_with_scraped()
