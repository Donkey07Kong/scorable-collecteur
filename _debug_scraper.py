import sys
sys.stdout = open(1, 'w', encoding='utf-8', closefd=False)

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://bet261.mg/virtual/category/instant-league/8060/results', timeout=30000, wait_until='networkidle')
    page.wait_for_timeout(5000)

    for i in range(5):
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
                page.wait_for_timeout(2000)
            else:
                print('No more Afficher plus at click', i)
                break
        except Exception as e:
            print('Click error:', e)
            break

    body = page.inner_text('body')
    print('BODY LENGTH:', len(body))
    print()
    print('FIRST 3000 CHARS:')
    print(body[:3000])
    browser.close()
