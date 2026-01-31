import os
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DATASET_PAGES = [
    "https://www.justice.gov/epstein/doj-disclosures/data-set-9-files",
    "https://www.justice.gov/epstein/doj-disclosures/data-set-10-files",
    "https://www.justice.gov/epstein/doj-disclosures/data-set-11-files",
]

OUT_DIR = Path("doj_epstein_datasets_9_10_11_pdfs")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def url_filename(u: str) -> str:
    name = os.path.basename(urlparse(u).path)
    return name or "download.pdf"

def normalize_pdf_url(u: str) -> str:
    # DOJ pages sometimes contain .ppdf typos; fix them.
    if u.lower().endswith(".ppdf"):
        return u[:-5] + ".pdf"
    return u

def looks_like_pdf_bytes(b: bytes) -> bool:
    return b[:4] == b"%PDF"

def collect_pdfs_from_current_page(page) -> set[str]:
    pdfs = set()
    anchors = page.locator("a[href$='.pdf'], a[href$='.PDF'], a[href$='.ppdf'], a[href$='.PPDF']")
    for i in range(anchors.count()):
        href = anchors.nth(i).get_attribute("href")
        if href:
            # make absolute
            abs_url = page.url
            full = page.evaluate(
                """([base, href]) => new URL(href, base).toString()""",
                [abs_url, href],
            )
            pdfs.add(normalize_pdf_url(full))
    return pdfs

def click_age_yes_if_present(page):
    # The DOJ site shows "Are you 18 years of age or older? Yes No" on these pages. :contentReference[oaicite:2]{index=2}
    try:
        if page.locator("text=Are you 18 years of age or older?").count() > 0:
            yes = page.locator("a:has-text('Yes'), button:has-text('Yes')").first
            if yes.count() > 0:
                yes.click()
                page.wait_for_load_state("networkidle", timeout=30000)
    except PlaywrightTimeoutError:
        pass

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        all_pdf_urls: set[str] = set()

        for start_url in DATASET_PAGES:
            print(f"\n[*] Visiting dataset: {start_url}")
            page.goto(start_url, wait_until="networkidle", timeout=60000)

            # Age gate
            click_age_yes_if_present(page)

            # Walk pagination
            seen_page_urls = set()
            while True:
                if page.url in seen_page_urls:
                    break
                seen_page_urls.add(page.url)

                pdfs = collect_pdfs_from_current_page(page)
                print(f"   - {page.url} -> {len(pdfs)} pdf links")
                all_pdf_urls |= pdfs

                if not click_next(page):
                    break

        print(f"\n[*] Total unique PDFs found: {len(all_pdf_urls)}")
        if not all_pdf_urls:
            print("No PDFs found. DOJ may have changed markup.")
            browser.close()
            return

        # Download using the same browser session (cookies/headers), avoiding the WAF issue.
        ok = 0
        for u in sorted(all_pdf_urls):
            fname = url_filename(u)
            out_path = OUT_DIR / fname

            if out_path.exists() and out_path.stat().st_size > 0:
                print(f"[OK] Exists: {fname}")
                ok += 1
                continue

            resp = context.request.get(u, timeout=120000)
            if not resp.ok:
                print(f"[!] HTTP {resp.status} for {u}")
                continue

            data = resp.body()
            if not looks_like_pdf_bytes(data):
                # Sometimes HTML slips through if access fails
                ctype = resp.headers.get("content-type", "")
                print(f"[!] Not a PDF for {fname} (content-type: {ctype})")
                continue

            tmp = out_path.with_suffix(out_path.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(out_path)

            print(f"[DL] Downloaded: {fname}")
            ok += 1

        print(f"\n[Done] Downloaded (or already existed): {ok}/{len(all_pdf_urls)}")
        print(f"Saved to: {OUT_DIR.resolve()}")
        browser.close()

if __name__ == "__main__":
    main()
