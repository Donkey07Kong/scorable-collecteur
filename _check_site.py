from playwright.sync_api import sync_playwright
import time
import json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    print("[Check] Loading bet261 virtual football page...")
    page.goto("https://bet261.mg/virtual/category/instant-league/8060",
               timeout=30000, wait_until="networkidle")
    time.sleep(5)
    
    body = page.inner_text("body")
    browser.close()

lines = [l.strip() for l in body.split('\n') if l.strip()]
print("Total lines:", len(lines))
print()
print("First 100 lines:")
for i, l in enumerate(lines[:100]):
    print("[%3d] %s" % (i, l[:120]))
