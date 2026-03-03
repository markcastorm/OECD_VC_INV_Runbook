# config.py
# OECD Venture Capital Investments - Data Collection Configuration

import os
from datetime import datetime

# =============================================================================
# DATA SOURCE CONFIGURATION
# =============================================================================

BASE_URL = 'https://stats.oecd.org/Index.aspx?DataSetCode=VC_INVEST'
PROVIDER_NAME = 'OECD'
DATASET_NAME = 'OECD_VC_INV'

# =============================================================================
# TIMESTAMPED FOLDERS CONFIGURATION
# =============================================================================

# Generate timestamp for this run (format: YYYYMMDD_HHMMSS)
RUN_TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')

# Use timestamped folders to avoid conflicts between runs
USE_TIMESTAMPED_FOLDERS = True

# =============================================================================
# BROWSER CONFIGURATION
# =============================================================================

HEADLESS_MODE = False
DEBUG_MODE = True
WAIT_TIMEOUT = 30           # Seconds to wait for page elements
PAGE_LOAD_DELAY = 6         # Seconds after initial page load
DOWNLOAD_WAIT_TIME    = 60   # Seconds to wait for the download to START (Phase 1)
DOWNLOAD_STALL_TIMEOUT = 45  # Seconds of zero size growth before declaring stalled (Phase 2)

# User-agent string for the browser
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

# =============================================================================
# RELEASE DATE CACHE
# =============================================================================

# JSON file that stores the last downloaded release date
# If the page date matches the cached date, no new download is triggered
RELEASE_DATE_CACHE_FILE = './release_date_cache.json'

# Set to True to ignore the cached release date and always download.
# Useful for testing the parser and file generator without a real date change.
BYPASS_RELEASE_DATE_CACHE = False

# =============================================================================
# WEB SCRAPING SELECTORS
# =============================================================================

SELECTORS = {
    # "Last updated" label span (jss151 is the JSS-generated class)
    'last_updated_label': 'span.jss151',

    # Download button in the page toolbar
    'download_button': '[data-testid="downloads-button"]',

    # The dropdown menu that appears after clicking the download button
    'download_menu': '[data-testid="downloads-menu"]',

    # "Filtered data in tabular text (CSV)" link — id has a period, use attribute selector
    'filtered_csv_link': '[id="csv.selection"]',

    # ── Time period filter ─────────────────────────────────────────────────
    # Sidebar tab that opens the Time period filter panel
    'time_period_tab':   '[data-testid="PANEL_PERIOD-tab"]',

    # The filter panel that slides open after clicking the tab
    'filter_panel':      '[data-testid="filter_panel"]',

    # Start-year picker container (contains the combobox inside)
    'start_year_picker': '[data-testid="year-Start-test-id"]',

    # End-year picker container
    'end_year_picker':   '[data-testid="year-End-test-id"]',

    # Apply button — confirms the time period selection and closes the panel
    'apply_button':      '#apply_button',
}

# =============================================================================
# CSV PARSING CONFIGURATION
# =============================================================================

# Column names to locate dynamically in the downloaded OECD CSV.
# The parser scans the header row to find these — never assumed to be at a
# fixed position.
CSV_COLUMNS = {
    'ref_area':        'REF_AREA',
    'ref_area_label':  'Reference area',
    'measure':         'MEASURE',
    'measure_label':   'Measure',
    'stage':           'BUSINESS_DEVELOPMENT_STAGE',
    'stage_label':     'Business development stage',
    'time_period':     'TIME_PERIOD',
    'obs_value':       'OBS_VALUE',
}

# Only rows where MEASURE matches this code are processed.
# Discovered dynamically by scanning the MEASURE column — not hardcoded per-row.
TARGET_MEASURE = 'VC_INV_MKT'

# =============================================================================
# STAGE CODE MAPPING
# =============================================================================

# Maps OECD internal BUSINESS_DEVELOPMENT_STAGE codes → standard output stage codes.
# The OECD CSV uses '_T' for Total; the standard output uses 'VCT'.
# All other stage codes pass through unchanged.
# Parser applies this map before building column codes — keeps parser logic generic.
STAGE_CODE_MAPPING = {
    '_T':    'VCT',     # Total
    'SEED':  'SEED',    # Seed
    'START': 'START',   # Start-up and other early stage
    'LATER': 'LATER',   # Later stage venture
}

# Stage order within each country (applied during column reordering)
STAGE_ORDER = ['VCT', 'SEED', 'START', 'LATER']

# =============================================================================
# COUNTRY / COLUMN ORDER
# =============================================================================

# Canonical country order for the output — matches the reference data arrangement exactly.
# Countries are listed in OECD standard ordering for this dataset.
# Any country found in the downloaded CSV but NOT listed here will be appended
# at the end (fully dynamic — new OECD members are never dropped).
COUNTRY_ORDER = [
    'AUS', 'AUT', 'BEL', 'CAN', 'CZE', 'DNK', 'FIN', 'FRA',
    'DEU', 'GRC', 'HUN', 'IRL', 'ITA', 'JPN', 'KOR', 'LUX',
    'NLD', 'NZL', 'NOR', 'POL', 'PRT', 'SVK', 'ESP', 'SWE',
    'CHE', 'GBR', 'USA', 'EST', 'ISR', 'LVA', 'LTU', 'ROU',
    'RUS', 'SVN', 'ZAF', 'BGR', 'HRV',
]

# =============================================================================
# OUTPUT COLUMN FORMAT
# =============================================================================

# Column code format for the data file header row 1.
# Placeholders: {ref_area} = REF_AREA code, {stage} = mapped stage code (after STAGE_CODE_MAPPING)
# Example:  AUS.VCINV.VCT.USDV.A
COLUMN_CODE_FORMAT = '{ref_area}.VCINV.{stage}.USDV.A'

# Column description format for the data file header row 2.
# Placeholders: {country} = Reference area label, {stage_label} = stage label
# Example:  Australia: Venture capital investments, Total, USD, current prices
COLUMN_DESC_FORMAT = '{country}: Venture capital investments, {stage_label}, USD, current prices'

# =============================================================================
# METADATA STANDARD FIELDS
# =============================================================================

METADATA_DEFAULTS = {
    'FREQUENCY':            'A',                    # Annual
    'AGGREGATION_TYPE':     'END_OF_PERIOD',
    'UNIT_TYPE':            'LEVEL',
    'DATA_TYPE':            'CURRENCY',
    'DATA_UNIT':            'USD Millions',
    'SEASONALLY_ADJUSTED':  'NSA',
    'ANNUALIZED':           False,
    'PROVIDER_MEASURE_URL': BASE_URL,
    'PROVIDER':             'AfricaAI',
    'SOURCE':               'OECD',
    'SOURCE_DESCRIPTION':   PROVIDER_NAME,
    'DATASET':              DATASET_NAME,
}

# Multiplier: UNIT_MULT in the OECD CSV is 6 (= Millions)
METADATA_MULTIPLIER = '1000000'

# Metadata file columns (exact order)
METADATA_COLUMNS = [
    'CODE',
    'DESCRIPTION',
    'FREQUENCY',
    'MULTIPLIER',
    'AGGREGATION_TYPE',
    'UNIT_TYPE',
    'DATA_TYPE',
    'DATA_UNIT',
    'SEASONALLY_ADJUSTED',
    'ANNUALIZED',
    'PROVIDER_MEASURE_URL',
    'PROVIDER',
    'SOURCE',
    'SOURCE_DESCRIPTION',
    'COUNTRY',
    'DATASET',
]

# =============================================================================
# DATE FORMATS
# =============================================================================

DATE_FORMAT_OUTPUT      = '%Y-%m-%d'
DATETIME_FORMAT_META    = '%Y-%m-%d %H:%M:%S'
FILENAME_DATE_FORMAT    = '%Y%m%d'

# =============================================================================
# OUTPUT CONFIGURATION
# =============================================================================

# Base directories
BASE_DOWNLOAD_DIR = './downloads'
BASE_OUTPUT_DIR   = './output'
BASE_LOG_DIR      = './logs'

# Apply timestamping if enabled
if USE_TIMESTAMPED_FOLDERS:
    DOWNLOAD_DIR = os.path.join(BASE_DOWNLOAD_DIR, RUN_TIMESTAMP)
    OUTPUT_DIR   = os.path.join(BASE_OUTPUT_DIR,   RUN_TIMESTAMP)
    LOG_DIR      = os.path.join(BASE_LOG_DIR,      RUN_TIMESTAMP)
else:
    DOWNLOAD_DIR = BASE_DOWNLOAD_DIR
    OUTPUT_DIR   = BASE_OUTPUT_DIR
    LOG_DIR      = BASE_LOG_DIR

# Latest folder — always contains the most recent run's output
LATEST_OUTPUT_DIR = os.path.join(BASE_OUTPUT_DIR, 'latest')

# File naming patterns (timestamp inserted at runtime)
DATA_FILE_PATTERN = 'OECD_VC_INV_DATA_{timestamp}.xlsx'
META_FILE_PATTERN = 'OECD_VC_INV_META_{timestamp}.xlsx'
ZIP_FILE_PATTERN  = 'OECD_VC_INV_{timestamp}.zip'

# Log file naming
LOG_FILE_PATTERN = 'oecd_vc_inv_{timestamp}.log'

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

LOG_LEVEL       = 'DEBUG' if DEBUG_MODE else 'INFO'
LOG_FORMAT      = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_TO_CONSOLE  = True
LOG_TO_FILE     = True

# =============================================================================
# ERROR HANDLING
# =============================================================================

# Continue pipeline even if non-critical steps fail
CONTINUE_ON_ERROR    = True
MAX_DOWNLOAD_RETRIES = 3
RETRY_DELAY          = 2.0   # Seconds between retries
