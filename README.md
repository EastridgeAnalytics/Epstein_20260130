# DOJ Epstein Disclosures – Local PDF Downloader

This project downloads PDF files from the U.S. Department of Justice (DOJ) Epstein-related disclosure pages (data sets 9, 10, and 11) and saves them to a local folder.

## What It Does

1. **Visits** each of three DOJ dataset listing pages in a headless browser.
2. **Handles the age gate** (“Are you 18 years or older?”) by clicking “Yes” when it appears.
3. **Walks pagination** by following the “Next” link on each page until there are no more pages.
4. **Collects** all unique PDF links from every page it visits.
5. **Downloads** each PDF using the same browser session (cookies/headers) and saves it to a local directory, skipping files that already exist.

## Requirements

- **Python 3** (tested with 3.13)
- **Playwright** and its Chromium browser

### Setup

```bash
pip install playwright
python -m playwright install
```

The second command downloads the Chromium binary used for headless browsing.

## How to Run

From the project directory:

```bash
python load_files_locally_20260130.py
```

The script prints progress (which URLs it visits, how many PDF links it finds, and which files it downloads or skips). PDFs are written to:

```
doj_epstein_datasets_9_10_11_pdfs/
```

## How the Code Works

### Target URLs

The script is configured for three base URLs:

- `https://www.justice.gov/epstein/doj-disclosures/data-set-9-files`
- `https://www.justice.gov/epstein/doj-disclosures/data-set-10-files`
- `https://www.justice.gov/epstein/doj-disclosures/data-set-11-files`

You can change these in the `DATASET_PAGES` list at the top of the script.

### Flow

1. **Playwright** starts Chromium in headless mode and opens a new page.
2. **For each dataset** (each base URL):
   - Navigate to the base URL.
   - If the response is not OK (e.g. 401, 403), skip that dataset and continue.
   - If the “Are you 18 years of age or older?” prompt appears, click “Yes” and wait for the page to settle.
   - **Pagination loop:**
     - Record the current page URL (to avoid infinite loops).
     - Find all links whose `href` ends in `.pdf` or `.ppdf` (including `.PDF` / `.PPDF`) and resolve them to absolute URLs. Add them to a set of unique PDF URLs.
     - Look for a “Next” link (e.g. `li.pager__item--next a` or `a[rel='next']`). If found, click it and repeat; if not, stop for that dataset.
3. **Download phase:** For each unique PDF URL (sorted for stable order):
   - If a file with the same name already exists and has size &gt; 0, skip it (`[OK] Exists`).
   - Otherwise, request the URL with the same browser context (so cookies/headers are sent). If the response is not OK or the body doesn’t start with `%PDF`, skip and log.
   - Write the response body to a temporary `.part` file, then rename it to the final filename so partial downloads are not left as “finished” files.

### Output and File Names

- **Console:** Lines like `[*] Dataset: ...`, `- <url> -> N pdf links`, `[OK] Exists: ...`, `[DL] Downloaded: ...`, `[!] HTTP ...` or `[!] Not a PDF ...`, and a final summary with the output directory path.
- **Files:** Each PDF is saved under `doj_epstein_datasets_9_10_11_pdfs/` using the filename from the URL (e.g. `EFTA01262782.pdf`). The script normalizes `.ppdf` typos in links to `.pdf`.

### Why Use a Browser?

The DOJ site returns 401/403 when paginated URLs (e.g. `?page=2`) are requested directly. By using Playwright to load the first page and then click “Next,” the script follows the same path a user would, so the server accepts the requests and all listed PDFs can be collected and downloaded within the same session.

## Notes

- **Data set 9** may return 401 (Unauthorized) in some environments; the script skips it and continues with data sets 10 and 11.
- **Re-running** is safe: existing PDFs are skipped. Only missing or empty files are downloaded.
- The script uses **ASCII-only** print messages so it runs cleanly on Windows consoles (e.g. cp1252) without Unicode errors.
