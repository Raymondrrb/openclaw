#!/usr/bin/env python3
"""Explore ChatCut.io to evaluate its usefulness for the Rayviews pipeline.

User wants to know:
1. Can it generate videos from Amazon product images using Seedance 2.0?
2. What features does it offer for product ranking videos?
3. Pricing and capabilities
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running

    print("=" * 70)
    print("ChatCut.io Exploration")
    print("=" * 70)

    if not is_browser_running():
        print("ERROR: Brave browser not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        page = context.new_page()
        page.set_viewport_size({"width": 1440, "height": 900})

        # Step 1: Visit homepage
        print("\n[1] Visiting chatcut.io homepage...")
        page.goto("https://www.chatcut.io", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        page.screenshot(path=os.path.expanduser("~/Downloads/chatcut_home.png"))

        # Extract page content
        home_text = page.evaluate("""() => {
            return document.body.innerText.substring(0, 3000);
        }""")
        print(f"[1] Homepage text:\n{home_text[:1500]}")

        # Step 2: Check for features/pricing pages
        print("\n[2] Looking for feature links...")
        links = page.evaluate("""() => {
            var links = [];
            for (var a of document.querySelectorAll('a')) {
                var text = (a.innerText || '').trim();
                var href = a.href || '';
                if (text && href && (text.includes('Pricing') || text.includes('Feature') ||
                    text.includes('Blog') || text.includes('Product') || text.includes('Generate') ||
                    text.includes('Seedance') || text.includes('Image') || text.includes('Video'))) {
                    links.push({text: text.substring(0, 50), href: href});
                }
            }
            return links;
        }""")
        print(f"[2] Relevant links: {len(links)}")
        for l in links[:15]:
            print(f"  {l['text']:40s} -> {l['href']}")

        # Step 3: Visit pricing page
        print("\n[3] Checking pricing...")
        page.goto("https://www.chatcut.io/pricing", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        page.screenshot(path=os.path.expanduser("~/Downloads/chatcut_pricing.png"))

        pricing_text = page.evaluate("""() => {
            return document.body.innerText.substring(0, 3000);
        }""")
        print(f"[3] Pricing page:\n{pricing_text[:1500]}")

        # Step 4: Check projects page (user's link)
        print("\n[4] Checking /projects page...")
        page.goto("https://www.chatcut.io/projects", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        page.screenshot(path=os.path.expanduser("~/Downloads/chatcut_projects.png"))

        projects_text = page.evaluate("""() => {
            return document.body.innerText.substring(0, 3000);
        }""")
        print(f"[4] Projects page:\n{projects_text[:1500]}")

        # Step 5: Look for Seedance/image-to-video features
        print("\n[5] Searching for Seedance/image-to-video features...")
        seedance_check = page.evaluate("""() => {
            var body = document.body.innerText.toLowerCase();
            return {
                seedance: body.includes('seedance'),
                imageToVideo: body.includes('image to video') || body.includes('image-to-video'),
                textToVideo: body.includes('text to video') || body.includes('text-to-video'),
                generate: body.includes('generate video') || body.includes('video generation'),
                amazon: body.includes('amazon'),
                product: body.includes('product'),
            };
        }""")
        print(f"[5] Keyword check: {seedance_check}")

        # Step 6: Look for any "Generate" or "Create" buttons
        print("\n[6] Looking for generation features...")
        buttons = page.evaluate("""() => {
            var btns = [];
            for (var el of document.querySelectorAll('button, a[href], [role="button"]')) {
                var text = (el.innerText || '').trim();
                if (text && (text.includes('Generate') || text.includes('Create') ||
                    text.includes('New') || text.includes('Upload') || text.includes('Start'))) {
                    btns.push({
                        text: text.substring(0, 50),
                        tag: el.tagName,
                        href: el.href || ''
                    });
                }
            }
            return btns;
        }""")
        for b in buttons[:10]:
            print(f"  <{b['tag']}> {b['text']} -> {b.get('href', '')}")

        # Step 7: Try to find the video generation/creation flow
        print("\n[7] Exploring the app UI...")
        # Check if logged in or need to log in
        auth_state = page.evaluate("""() => {
            var body = document.body.innerText;
            if (body.includes('Sign in') || body.includes('Log in') || body.includes('Sign up')) {
                return 'needs_login';
            }
            if (body.includes('My Projects') || body.includes('Dashboard')) {
                return 'logged_in';
            }
            return 'unknown';
        }""")
        print(f"[7] Auth state: {auth_state}")

        # Check all navigation items
        nav_items = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('nav a, [class*="nav"] a, [class*="sidebar"] a, [class*="menu"] a')) {
                var text = (el.innerText || '').trim();
                if (text) items.push({text: text.substring(0, 50), href: el.href || ''});
            }
            return items;
        }""")
        print(f"[7] Navigation items: {len(nav_items)}")
        for item in nav_items[:20]:
            print(f"  {item['text']:40s} -> {item['href']}")

        # Step 8: Full page content scan for video generation keywords
        print("\n[8] Full content scan for relevant features...")
        full_scan = page.evaluate("""() => {
            var text = document.body.innerText.toLowerCase();
            var keywords = ['seedance', 'image to video', 'text to video', 'generate',
                          'ai video', 'product video', 'amazon', 'e-commerce',
                          'capcut', 'bytedance', 'video generation', 'image-to-video'];
            var found = {};
            for (var kw of keywords) {
                var idx = text.indexOf(kw);
                if (idx >= 0) {
                    // Extract surrounding context
                    var start = Math.max(0, idx - 50);
                    var end = Math.min(text.length, idx + kw.length + 50);
                    found[kw] = text.substring(start, end);
                }
            }
            return found;
        }""")
        print(f"[8] Keywords found in page: {len(full_scan)}")
        for kw, ctx in full_scan.items():
            print(f"  [{kw}]: ...{ctx}...")

        page.close()

        # Summary
        print("\n" + "=" * 70)
        print("CHATCUT.IO SUMMARY")
        print("=" * 70)

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
