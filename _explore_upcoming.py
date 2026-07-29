from playwright.sync_api import sync_playwright
import time
import json

def explore():
    api_data = []
    
    def on_response(response):
        url = response.url
        if 'hg-event' in url or 'sporty-tech' in url:
            try:
                body = response.json()
                api_data.append({'url': url, 'data': body})
            except:
                pass
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("response", on_response)
        
        # Go directly to matches and wait longer
        print("[1] Loading matches page...")
        page.goto("https://bet261.mg/virtual/category/instant-league/8060/matches",
                   timeout=30000, wait_until="domcontentloaded")
        
        # Wait for Angular to render
        print("[2] Waiting for Angular render...")
        time.sleep(5)
        
        # Accept cookies if present
        try:
            page.click("text=Autoriser tous les cookies", timeout=3000)
            time.sleep(1)
        except:
            pass
        
        # Wait more for data loading
        time.sleep(10)
        
        print("API calls: %d" % len(api_data))
        for call in api_data:
            url = call['url']
            data = call['data']
            if isinstance(data, dict):
                keys = list(data.keys())
                print("\n  URL: %s" % url[:100])
                print("  Keys: %s" % keys[:10])
                if 'rounds' in data:
                    for rnd in data['rounds']:
                        rn = rnd.get('roundNumber', '?')
                        matches = rnd.get('matches', [])
                        es = rnd.get('expectedStart', '')[:19]
                        print("    R%s (%s): %d matches" % (rn, es, len(matches)))
                        for m in matches[:2]:
                            ht = m.get('homeTeam', {})
                            at = m.get('awayTeam', {})
                            hname = ht.get('name', '?') if isinstance(ht, dict) else '?'
                            aname = at.get('name', '?') if isinstance(at, dict) else '?'
                            odds = {}
                            for bt in m.get('eventBetTypes', []):
                                bname = bt.get('name', '')
                                if bname == '1X2':
                                    for item in bt.get('eventBetTypeItems', []):
                                        odds[item.get('shortName','')] = item.get('odds', 0)
                            print("      %s vs %s  1X2=%s" % (hname, aname, odds))
        
        # Also try to get rendered match elements
        print("\n[3] Checking rendered match elements...")
        match_elements = page.evaluate("""() => {
            const results = [];
            // Try hg-match elements
            const hgMatches = document.querySelectorAll('hg-match, [class*=match-card], [class*=MatchCard]');
            hgMatches.forEach(el => {
                results.push({tag: el.tagName, text: el.innerText.substring(0, 200)});
            });
            
            // Also try getting inner HTML of main content area
            const main = document.querySelector('.main-content, [class*=content], main, .layout-content');
            if (main) {
                results.push({tag: 'MAIN', text: main.innerText.substring(0, 500)});
            }
            
            // Get full body innerHTML for Angular analysis
            const bodyHTML = document.body.innerHTML.substring(0, 5000);
            results.push({tag: 'BODY_SNIPPET', text: bodyHTML});
            
            return results;
        }""")
        
        for el in match_elements:
            if el['tag'] == 'BODY_SNIPPET':
                print("  Body snippet: %s..." % el['text'][:200])
            else:
                print("  <%s>: %s" % (el['tag'], el['text'][:100]))
        
        browser.close()

if __name__ == "__main__":
    explore()
