# OECD Venture Capital Investments — Automated Extraction Runbook

Automated pipeline that navigates the OECD Data Explorer, downloads the
Venture Capital Investments dataset as a CSV, parses and pivots it into a
wide-format Excel data file, and writes a companion metadata file.

---

## Overview

| Item | Value |
|---|---|
| **Dataset** | OECD_VC_INV |
| **Provider** | OECD |
| **Source** | OECD Data Explorer — Venture Capital Investments |
| **Source URL** | https://stats.oecd.org/Index.aspx?DataSetCode=VC_INVEST |
| **Measure** | VC_INV_MKT (Venture Capital Investment as % of GDP and USD) |
| **Frequency** | Annual |
| **Coverage** | 37 countries, 2002 – present (dynamically extended each run) |
| **Output** | `.xlsx` data file + `.xlsx` metadata file + `.zip` archive |

---

## Pipeline Steps

```
Step 1 — SCRAPER
  Open OECD Data Explorer in a stealth Chrome browser.
  Read the "Last updated" date on the page.
  Compare against the cached date in release_date_cache.json.
    → Same date: skip download, exit cleanly (no new data).
    → New date (or first run):
        Expand the Time period filter to the full available year range
        (opens Start and End year dropdowns, selects earliest and latest,
        verifies each selection, then clicks Apply).
        Click "Download → Filtered data in tabular text (CSV)".
        Wait for the .csv file to finish downloading.
        Save the new date to release_date_cache.json.

Step 2 — PARSER
  Dynamically locate required columns (handles any header naming convention —
  exact, case-insensitive, or content-fingerprint detection).
  Filter rows where MEASURE == VC_INV_MKT.
  Map stage codes: _T → VCT, SEED → SEED, START → START, LATER → LATER.
  Pivot long → wide: rows = years, columns = {COUNTRY}.VCINV.{STAGE}.USDV.A.
  Preserve all decimal digits exactly as they appear in the source file.

Step 3 — FILE GENERATOR
  Write OECD_VC_INV_DATA_{timestamp}.xlsx
    Row 1: column codes   (e.g. AUS.VCINV.VCT.USDV.A)
    Row 2: descriptions   (e.g. Australia: Venture capital investments, Total, USD, current prices)
    Row 3+: data          (year, then one value per column)
  Write OECD_VC_INV_META_{timestamp}.xlsx
    One row per column code with full metadata fields.
  Write OECD_VC_INV_{timestamp}.zip
    Both xlsx files archived together.
  Copy all three files to output/latest/ for easy access.
```

---

## Output Column Format

Each data column follows the pattern:

```
{REF_AREA}.VCINV.{STAGE}.USDV.A
```

| Segment | Example | Meaning |
|---|---|---|
| `REF_AREA` | `AUS` | ISO 3-letter country code |
| `VCINV` | fixed | Venture Capital Investment |
| `STAGE` | `VCT` | Business development stage (see below) |
| `USDV` | fixed | USD, current prices |
| `A` | fixed | Annual |

**Stage codes:**

| Code | OECD Source Code | Description |
|---|---|---|
| `VCT` | `_T` | Total — all stages combined |
| `SEED` | `SEED` | Seed stage |
| `START` | `START` | Start-up and other early stage |
| `LATER` | `LATER` | Later stage venture |

**Example column:** `AUS.VCINV.VCT.USDV.A`
**Example description:** `Australia: Venture capital investments, Total, USD, current prices`

---

## Output File Structure

### Data file (`OECD_VC_INV_DATA_{timestamp}.xlsx`)

| Row | Content |
|---|---|
| 1 | Column codes (`AUS.VCINV.VCT.USDV.A`, …) — column A is empty (year column) |
| 2 | Column descriptions — column A is empty |
| 3+ | Data: column A = year (integer), columns B+ = values (USD millions, full precision) |

Values are stored as exact decimal strings (no float rounding). Up to 15+ significant
digits are preserved, matching the OECD source file exactly.

### Metadata file (`OECD_VC_INV_META_{timestamp}.xlsx`)

One row per column code. Fields:

`CODE`, `DESCRIPTION`, `FREQUENCY`, `MULTIPLIER`, `AGGREGATION_TYPE`,
`UNIT_TYPE`, `DATA_TYPE`, `DATA_UNIT`, `SEASONALLY_ADJUSTED`, `ANNUALIZED`,
`PROVIDER_MEASURE_URL`, `PROVIDER`, `SOURCE`, `SOURCE_DESCRIPTION`, `COUNTRY`, `DATASET`

---

## Folder Structure

```
OECD_VC_INV_Runbook/
├── orchestrator.py          # Entry point — runs the 3-step pipeline
├── config.py                # All configuration: URLs, selectors, paths, mappings
├── scraper.py               # Browser automation (undetected Chrome + Selenium)
├── parser.py                # CSV parser — dynamic column detection, pivot
├── file_generator.py        # Excel + zip writer
├── logger_setup.py          # Centralized logging (console + rotating file)
├── requirements.txt         # Python dependencies
├── release_date_cache.json  # Stores last downloaded release date
│
├── downloads/
│   └── {YYYYMMDD_HHMMSS}/   # Raw CSV download for each run
│
├── output/
│   ├── {YYYYMMDD_HHMMSS}/   # Timestamped output (DATA xlsx, META xlsx, zip)
│   └── latest/              # Always contains the most recent run's files
│
└── logs/
    └── {YYYYMMDD_HHMMSS}/   # Log file for each run
```

---

## Requirements

- Python 3.10+
- Google Chrome installed (version detected automatically from Windows registry)

```
pip install -r requirements.txt
```

Dependencies:

| Package | Purpose |
|---|---|
| `undetected-chromedriver >= 3.5.0` | Stealth Chrome browser (bypasses bot detection) |
| `selenium >= 4.15.0` | Browser automation (used internally by undetected-chromedriver) |
| `openpyxl >= 3.1.2` | Excel file writing |

All other modules (`csv`, `json`, `os`, `zipfile`, `shutil`, `winreg`, `logging`) are
Python standard library.

---

## Running the Pipeline

```bash
cd OECD_VC_INV_Runbook
python orchestrator.py
```

The script will:
1. Open a Chrome browser window (visible — not headless by default)
2. Navigate to the OECD Data Explorer
3. Check whether the data has been updated since the last run
4. If updated: expand the time period, download the CSV, parse it, and write output files
5. If not updated: print "No new data" and exit cleanly

Output files land in `output/{timestamp}/` and are also copied to `output/latest/`.

---

## Configuration

All settings are in [config.py](config.py). Key options:

| Setting | Default | Description |
|---|---|---|
| `BYPASS_RELEASE_DATE_CACHE` | `False` | Set `True` to force a download even if the release date has not changed (useful for testing) |
| `HEADLESS_MODE` | `False` | Run Chrome without a visible window |
| `DEBUG_MODE` | `True` | Verbose logging |
| `WAIT_TIMEOUT` | `30` | Seconds to wait for page elements |
| `PAGE_LOAD_DELAY` | `6` | Seconds after initial page load before interacting |
| `DOWNLOAD_WAIT_TIME` | `60` | Seconds to wait for the download to start |
| `DOWNLOAD_STALL_TIMEOUT` | `45` | Seconds of zero file-size growth before declaring a stall |
| `USE_TIMESTAMPED_FOLDERS` | `True` | Each run writes to its own subfolder |
| `TARGET_MEASURE` | `VC_INV_MKT` | OECD measure code to extract |

---

## Release Date Cache

`release_date_cache.json` stores the "Last updated" date that was shown on the
OECD Data Explorer page during the most recent successful download.

```json
{
  "last_updated": "February 25, 2026 at 4:37:19 PM",
  "cached_at": "2026-03-03 17:04:57"
}
```

On each run the scraper reads the live page date and compares it to `last_updated`.
If they match, the pipeline exits immediately without downloading. If they differ,
a new download is triggered and the cache is updated.

Set `BYPASS_RELEASE_DATE_CACHE = True` in `config.py` to skip this check (e.g.
during development or to re-run after a failed parse step).

---

## Dynamic Resilience

### Column detection (3 levels)
The parser never assumes fixed column positions in the source CSV. It uses:
1. **Exact match** — header equals the configured column name
2. **Case-insensitive match** — handles lower/upper/mixed headers
3. **Content fingerprint** — if headers are unrecognisable (e.g. `col_0`, `col_1`),
   the parser samples 30 rows and identifies columns by the shape of their data
   (year-like integers, numeric values, known measure codes, cardinality of unique
   values, etc.)

### Country and year coverage
The country list in `config.py` defines the preferred column ordering, but any
country present in the downloaded CSV that is not listed is appended automatically.
No countries are ever dropped.

The time period is set dynamically at runtime: the scraper opens the Start and End
year dropdowns, reads the available options, selects the earliest and latest years,
and verifies each selection before applying. If OECD extends the series in the
future, the pipeline will pick up the new years automatically.

---

## Data Accuracy

Output values are stored as raw decimal strings with `data_type='n'` in the Excel
XML, bypassing `openpyxl`'s float serialiser. This preserves the full precision of
the source file.

Verified against source CSV: **2,388 entries, 100% exact match** (37 countries,
4 stages, 2002–2024).
