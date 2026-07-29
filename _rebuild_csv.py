import csv
import json
import os
import shutil

def rebuild_csv_with_scraped():
    scraped_path = "D:/Documents/261CAF/bet261_real_results.json"
    csv_path = "D:/Documents/261CAF/donnees_equipes.csv"
    backup_path = "D:/Documents/261CAF/donnees_equipes_backup_%s.csv" % __import__('time').strftime('%Y%m%d_%H%M%S')
    
    shutil.copy2(csv_path, backup_path)
    print("Backup saved: %s" % backup_path)
    
    with open(scraped_path, 'r', encoding='utf-8') as f:
        scraped = json.load(f)
    
    new_rows = []
    round_counter = 1
    cycle_num = 21
    
    for rnd in sorted([int(k) for k in scraped.keys()]):
        matches = scraped[str(rnd)]
        for home, away, sd, se in matches:
            total = sd + se
            if sd > se:
                victoire = "dom"
            elif se > sd:
                victoire = "ext"
            else:
                victoire = "nul"
            
            match_id = 0
            
            new_rows.append({
                "round": str(rnd),
                "match_id": str(match_id),
                "home_team": home,
                "away_team": away,
                "score_final_dom": str(sd),
                "score_final_ext": str(se),
                "nb_buts_total": str(total),
                "nb_buts_dom": str(sd),
                "nb_buts_ext": str(se),
                "victoire": victoire,
                "cycle": str(cycle_num),
            })
    
    fieldnames = ["round", "match_id", "home_team", "away_team", "score_final_dom",
                   "score_final_ext", "nb_buts_total", "nb_buts_dom", "nb_buts_ext",
                   "victoire", "cycle"]
    
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(new_rows)
    
    print("New CSV: %d rows (%d rounds, %d matchs/round)" % (
        len(new_rows), len(scraped), len(scraped.get('1', []))))
    
    rounds = sorted(set(int(r["round"]) for r in new_rows))
    print("Rounds: %d - %d" % (min(rounds), max(rounds)))
    
    for rnd in rounds[:3]:
        n = len([r for r in new_rows if int(r["round"]) == rnd])
        sample = [r for r in new_rows if int(r["round"]) == rnd][0]
        print("  R%d: %d matchs, ex: %s vs %s %s-%s" % (
            rnd, n, sample["home_team"], sample["away_team"],
            sample["score_final_dom"], sample["score_final_ext"]))

if __name__ == "__main__":
    rebuild_csv_with_scraped()
