from playwright.sync_api import sync_playwright
import json
import time
import re

KNOWN_TEAMS = {
    "Algeria", "Angola", "Benin", "Botswana", "Burkina Faso", "Cameroon",
    "Comoros", "DR Congo", "Egypt", "Equatorial Guinea", "Gabon", "Ivory Coast",
    "Mali", "Morocco", "Mozambique", "Nigeria", "Senegal", "South Africa",
    "Sudan", "Tanzania", "Tunisia", "Uganda", "Zambia", "Zimbabwe"
}

def scrape_all_results():
    results = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("[Scraper] Loading bet261 results...")
        page.goto("https://bet261.mg/virtual/category/instant-league/8060/results",
                   timeout=30000, wait_until="networkidle")
        time.sleep(5)
        
        # Click "Afficher plus" via JS
        clicks = 0
        for i in range(30):
            try:
                result = page.evaluate("""() => {
                    const els = document.querySelectorAll('div, button, a, span');
                    for (const el of els) {
                        if (el.textContent.trim() === 'Afficher plus' && el.offsetParent !== null) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if result:
                    time.sleep(2)
                    clicks += 1
                else:
                    break
            except Exception as e:
                print("Click error: %s" % e)
                break
        
        print("[Scraper] Clicked 'Afficher plus' %d times" % clicks)
        body = page.inner_text("body")
        browser.close()
    
    parts = re.split(r'Journ[ée]e\s+(\d+)', body)
    
    for idx in range(1, len(parts), 2):
        round_num = int(parts[idx])
        if idx + 1 >= len(parts):
            break
        content = parts[idx + 1]
        for stop in ["Afficher plus", "PANIER", "SERVICE CLIENT"]:
            if stop in content:
                content = content.split(stop)[0]
        
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        
        matches = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if line not in KNOWN_TEAMS:
                i += 1
                continue
            
            home_team = line
            j = i + 1
            score_line = -1
            while j < min(i + 6, len(lines)):
                score_m = re.match(r'^(\d+):(\d+)$', lines[j])
                if score_m:
                    sd = int(score_m.group(1))
                    se = int(score_m.group(2))
                    score_line = j
                    break
                j += 1
            
            if score_line < 0:
                i += 1
                continue
            
            k = score_line + 1
            away_team = None
            while k < min(score_line + 3, len(lines)):
                if lines[k] in KNOWN_TEAMS:
                    away_team = lines[k]
                    break
                k += 1
            
            if away_team:
                matches.append((home_team, away_team, sd, se))
                i = k + 1
            else:
                i += 1
        
        if matches:
            results[round_num] = matches
    
    total = sum(len(v) for v in results.values())
    print("[Scraper] %d rounds, %d matches" % (len(results), total))
    for rnd in sorted(results.keys(), reverse=True)[:5]:
        print("  Round %d: %d matches" % (rnd, len(results[rnd])))
    
    return results

if __name__ == "__main__":
    import os
    results = scrape_all_results()
    existing = {}
    path = "D:/Documents/261CAF/bet261_real_results.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except:
            pass
    merged = {str(k): v for k, v in existing.items()}
    for k, v in results.items():
        merged[str(k)] = v
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False)
    print("Saved %d rounds (merged %d new)" % (len(merged), len(results)))
