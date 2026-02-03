import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DATASET_PAGES = [
    "https://www.justice.gov/epstein/doj-disclosures/data-set-9-files",
    "https://www.justice.gov/epstein/doj-disclosures/data-set-10-files",
    "https://www.justice.gov/epstein/doj-disclosures/data-set-11-files",
]

MAX_PAGE = 1000  # Test ?page=1 through ?page=1000 for each dataset
OUT_DIR = Path("doj_epstein_datasets_9_10_11_pdfs")
VALID_URLS_OUTPUT = Path("valid_page_urls.txt")  # Final list of valid URLs
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
    # Step 2: If valid_page_urls.txt exists, use it and only do PDF collection/download (no URL discovery).
    if VALID_URLS_OUTPUT.exists():
        valid_page_urls = [u.strip() for u in VALID_URLS_OUTPUT.read_text(encoding="utf-8").splitlines() if u.strip()]
        print(f"[*] Using {len(valid_page_urls)} valid page URLs from {VALID_URLS_OUTPUT}")
    else:
        valid_page_urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        if not valid_page_urls:
            # Phase 1: Discover valid URLs (?page=1..MAX_PAGE per dataset), then continue to Phase 2.
            for base_url in DATASET_PAGES:
                print(f"\n[*] Testing URLs for: {base_url}")
                try:
                    response = page.goto(base_url, wait_until="networkidle", timeout=60000)
                except PlaywrightTimeoutError:
                    print("   - Base URL timeout, skipping dataset")
                    continue
                if not response or not response.ok:
                    status = response.status if response else "fail"
                    print(f"   - Base URL invalid (status {status}), skipping dataset")
                    continue
                click_age_yes_if_present(page)

                for page_num in range(1, MAX_PAGE + 1):
                    url = f"{base_url}?page={page_num}"
                    try:
                        response = page.goto(url, wait_until="networkidle", timeout=60000)
                    except PlaywrightTimeoutError:
                        print(f"   - {url} -> timeout (stopping this dataset)")
                        break
                    if not response or not response.ok:
                        status = response.status if response else "fail"
                        print(f"   - {url} -> invalid (status {status}), stopping at page {page_num - 1}")
                        break
                    valid_page_urls.append(url)
                    if page_num <= 5 or page_num % 50 == 0 or page_num == MAX_PAGE:
                        print(f"   - valid: {url}")

            valid_page_urls.sort()
            VALID_URLS_OUTPUT.write_text("\n".join(valid_page_urls), encoding="utf-8")
            print(f"\n[*] Total valid page URLs: {len(valid_page_urls)}")
            print(f"[Saved] Valid URLs written to: {VALID_URLS_OUTPUT.resolve()}")

        if not valid_page_urls:
            print("No valid page URLs found.")
            browser.close()
            return

        # Phase 2: Collect PDFs from each valid page URL, then download.
        all_pdf_urls: set[str] = set()
        for url in valid_page_urls:
            try:
                response = page.goto(url, wait_until="networkidle", timeout=60000)
            except PlaywrightTimeoutError:
                continue
            if not response or not response.ok:
                continue
            pdfs = collect_pdfs_from_current_page(page)
            all_pdf_urls |= pdfs

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
