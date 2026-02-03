"""
Step 1: Discover valid page URLs only.
Does NOT download any PDFs. Run this first, then use load_files_locally for PDFs.

Works around age-verification / bot blocker:
1. Uses a real-looking browser (viewport, user-agent).
2. Waits for and clicks through the age gate so the session is verified.
3. Does NOT request ?page=N directly (site blocks that). Instead we discover
   valid URLs by clicking the "Next" link on each page and recording the URL
   we land on (same as a human). Stops when there is no Next link.
"""

import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DATASET_PAGES = [
    "https://www.justice.gov/epstein/doj-disclosures/data-set-9-files",
    "https://www.justice.gov/epstein/doj-disclosures/data-set-10-files",
    "https://www.justice.gov/epstein/doj-disclosures/data-set-11-files",
]

VALID_URLS_OUTPUT = Path("valid_page_urls.txt")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1920, "height": 1080}
AGE_GATE_WAIT_MS = 4000
NEXT_CLICK_DELAY_MS = 1200  # Delay between clicking Next (human-like)


def pass_age_gate_if_present(page) -> bool:
    """Wait for age gate, click Yes, wait for session. Returns True if we clicked."""
    try:
        age_question = page.locator("text=Are you 18 years of age or older?")
        age_question.wait_for(state="visible", timeout=15000)
    except Exception:
        return False
    try:
        for sel in ["a:has-text('Yes')", "button:has-text('Yes')", "[role='button']:has-text('Yes')"]:
            el = page.locator(sel).first
            if el.count() > 0:
                el.click()
                break
        else:
            return False
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(AGE_GATE_WAIT_MS / 1000.0)
        return True
    except Exception:
        return False


def click_next(page, base_url: str) -> bool:
    """Click the paginator Next link for this dataset. Returns True if we navigated."""
    base_path = base_url.rstrip("/").split("/")[-1]  # e.g. "data-set-10-files"
    # Next can be: same path in href, or relative ?page=N (stays on same dataset)
    selectors = [
        f"li.pager__item--next a[href*='{base_path}']",
        f"li.pager__item--next a[href*='?page=']",
        f"li.pager__item--next a",
        f"a[rel='next'][href*='{base_path}']",
        f"a[rel='next'][href*='?page=']",
        f".pager a:has-text('Next')",
        f"a:has-text('Next')[href*='?page=']",
        f"a:has-text('Next')[href*='{base_path}']",
    ]
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() > 0:
            href = loc.get_attribute("href") or ""
            # Reject links that go to a different dataset (e.g. data-set-12)
            if "data-set-" in href and base_path not in href:
                continue
            try:
                with page.expect_navigation(wait_until="networkidle", timeout=45000):
                    loc.click()
                return True
            except PlaywrightTimeoutError:
                time.sleep(1)
                return True
            except Exception:
                continue
    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=VIEWPORT,
            user_agent=USER_AGENT,
            locale="en-US",
            java_script_enabled=True,
        )
        page = context.new_page()

        valid_page_urls: list[str] = []

        for base_url in DATASET_PAGES:
            print(f"\n[*] Discovering pages for: {base_url}")
            try:
                response = page.goto(base_url, wait_until="networkidle", timeout=60000)
            except PlaywrightTimeoutError:
                print("   - Base URL timeout, skipping dataset")
                continue
            if not response or not response.ok:
                status = response.status if response else "fail"
                print(f"   - Base URL invalid (status {status}), skipping dataset")
                continue
            if pass_age_gate_if_present(page):
                print("   - Age verification passed")
            else:
                print("   - No age gate found (or already passed)")

            # Walk pagination by clicking Next (same dataset only); record each page URL
            seen = set()
            while True:
                url = page.url
                # Stay on this dataset: if we navigated away (e.g. to data-set-12), stop
                if base_url.rstrip("/") not in url:
                    break
                if url in seen:
                    break
                seen.add(url)
                valid_page_urls.append(url)
                print(f"   - valid: {url}")
                time.sleep(NEXT_CLICK_DELAY_MS / 1000.0)
                if not click_next(page, base_url):
                    break

        browser.close()

    valid_page_urls = sorted(set(valid_page_urls))
    print(f"\n[*] Total valid page URLs: {len(valid_page_urls)}")
    print("\n--- Valid page URLs (desired output) ---")
    for u in valid_page_urls:
        print(u)
    VALID_URLS_OUTPUT.write_text("\n".join(valid_page_urls), encoding="utf-8")
    print(f"\n[Saved] Valid URLs written to: {VALID_URLS_OUTPUT.resolve()}")


if __name__ == "__main__":
    main()
