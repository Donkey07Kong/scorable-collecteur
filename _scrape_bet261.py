from playwright.sync_api import sync_playwright
import json
import time

captured = []

def on_response(response):
    url = response.url
    if 'sporty-tech' in url:
        try:
            body = response.text()
            captured.append({"url": url, "status": response.status, "body": body[:20000]})
        except:
            pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("response", on_response)
    
    page.goto("https://bet261.mg/virtual/category/instant-league/8060/matches", timeout=30000, wait_until="networkidle")
    time.sleep(5)
    
    # Find ALL clickable elements and their text
    print("=== All clickable elements ===")
    all_elements = page.query_selector_all("*")
    for el in all_elements:
        try:
            text = el.inner_text().strip()
            tag = el.evaluate("el => el.tagName")
            if text and len(text) < 30 and any(x in text.upper() for x in ['RESULTAT', 'RESULT', 'RÉSULTAT']):
                rect = el.bounding_box()
                print("  [%s] '%s' rect=%s" % (tag, text, rect))
        except:
            pass
    
    # Try using text locator
    print("\n=== Trying locator ===")
    try:
        result_el = page.locator("text=RÉSULTATS").first
        bbox = result_el.bounding_box()
        print("Found RÉSULTATS: bbox=%s" % bbox)
        result_el.click()
        time.sleep(5)
        page.wait_for_load_state("networkidle", timeout=10000)
        print("After click URL: %s" % page.url)
        
        text = page.inner_text("body")[:5000]
        print("\nPage text after click:\n%s" % text)
    except Exception as e:
        print("Error: %s" % e)
    
    # Also try navigating directly to results URL
    print("\n\n=== Trying direct results URL ===")
    try:
        captured.clear()
        page.goto("https://bet261.mg/virtual/category/instant-league/8060/results", timeout=20000, wait_until="networkidle")
        time.sleep(5)
        print("URL: %s" % page.url)
        text = page.inner_text("body")[:5000]
        print("\nPage text:\n%s" % text)
        
        for c in captured:
            if 'sporty-tech' in c["url"] and c["status"] == 200:
                try:
                    data = json.loads(c["body"])
                    if isinstance(data, dict):
                        for k, v in data.items():
                            if isinstance(v, list) and v and isinstance(v[0], dict):
                                print("\n%s: %d items, keys=%s" % (k, len(v), list(v[0].keys())[:10]))
                                if 'goals' in v[0] or 'homeScore' in v[0] or 'homeTeam' in v[0]:
                                    print("  SCORE DATA FOUND!")
                                    for m in v[:2]:
                                        print("  %s" % json.dumps(m, ensure_ascii=False)[:300])
                except:
                    pass
    except Exception as e:
        print("Error: %s" % e)
    
    browser.close()
