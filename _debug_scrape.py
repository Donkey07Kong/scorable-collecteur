from playwright.sync_api import sync_playwright
import json
import time
import re

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://bet261.mg/virtual/category/instant-league/8060/results",
               timeout=30000, wait_until="networkidle")
    time.sleep(5)
    
    body = page.inner_text("body")
    browser.close()

# Show lines around first round
parts = re.split(r'Journ[ée]e\s+(\d+)', body)
if len(parts) >= 3:
    content = parts[2][:2000]
    lines = content.split('\n')
    for i, l in enumerate(lines[:80]):
        print("[%2d] '%s'" % (i, l.strip()))
