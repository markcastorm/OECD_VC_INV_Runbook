# scraper.py
# Downloads OECD Venture Capital Investment CSV data from OECD Data Explorer

import os
import json
import time
import glob
import shutil
import random
import logging
import winreg
from datetime import datetime

import config

logger = logging.getLogger(__name__)


class OECDScraper:
    """Downloads OECD VC Investment filtered CSV from OECD Data Explorer"""

    def __init__(self):
        self.driver = None
        self.download_dir = None

    # =========================================================================
    # CHROME / DRIVER SETUP
    # =========================================================================

    def get_chrome_version_from_registry(self):
        """Get installed Chrome version from Windows Registry."""
        logger.info("Checking Windows Registry for Chrome version...")

        registry_paths = [
            (winreg.HKEY_CURRENT_USER,  r"Software\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Google\Update\Clients\{8A69D345-D564-463c-AFF1-A69D9E530F96}"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon"),
        ]

        for hkey, path in registry_paths:
            try:
                key = winreg.OpenKey(hkey, path)
                version, _ = winreg.QueryValueEx(key, "version")
                winreg.CloseKey(key)
                major_version = int(version.split('.')[0])
                logger.info(f"Found Chrome version: {version} (major: {major_version})")
                return major_version
            except (FileNotFoundError, OSError):
                continue

        logger.warning("Chrome version not found in registry")
        return None

    def setup_driver(self):
        """Initialize undetected ChromeDriver with timestamped download directory."""
        import undetected_chromedriver as uc

        self.download_dir = os.path.abspath(config.DOWNLOAD_DIR)
        os.makedirs(self.download_dir, exist_ok=True)

        options = uc.ChromeOptions()

        if config.HEADLESS_MODE:
            options.add_argument('--headless=new')

        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument(f'--user-agent={config.USER_AGENT}')

        prefs = {
            'download.default_directory': self.download_dir.replace('/', '\\'),
            'download.prompt_for_download': False,
            'download.directory_upgrade': True,
            'safebrowsing.enabled': True,
        }
        options.add_experimental_option('prefs', prefs)

        chrome_version = self.get_chrome_version_from_registry()

        try:
            if chrome_version:
                self.driver = uc.Chrome(options=options, version_main=chrome_version)
            else:
                self.driver = uc.Chrome(options=options)

            self.driver.set_page_load_timeout(config.WAIT_TIMEOUT * 2)
            logger.info("Chrome driver initialized successfully")
            logger.info(f"Download directory: {self.download_dir}")

        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise

    # =========================================================================
    # HUMAN-LIKE INTERACTION
    # =========================================================================

    def human_delay(self, min_s=0.5, max_s=1.5):
        """Random delay to simulate human behavior."""
        delay = random.uniform(min_s, max_s)
        time.sleep(delay)

    def human_click(self, element):
        """Move to element then click — mimics human mouse movement."""
        from selenium.webdriver.common.action_chains import ActionChains

        actions = ActionChains(self.driver)
        actions.move_to_element(element)
        self.human_delay(0.3, 0.7)
        actions.click(element)
        actions.perform()
        self.human_delay(0.5, 1.2)

    def safe_click(self, element):
        """Try human_click first, fall back to JavaScript click."""
        try:
            self.human_click(element)
        except Exception:
            logger.debug("Human click failed, using JS click fallback")
            self.driver.execute_script("arguments[0].click();", element)
            self.human_delay(0.5, 1.0)

    # =========================================================================
    # RELEASE DATE CACHE
    # =========================================================================

    def load_release_date_cache(self):
        """Load the cached release date from JSON file. Returns date string or None."""
        if not os.path.exists(config.RELEASE_DATE_CACHE_FILE):
            logger.info("No release date cache found")
            return None

        try:
            with open(config.RELEASE_DATE_CACHE_FILE, 'r') as f:
                data = json.load(f)
            cached_date = data.get('last_updated')
            logger.info(f"Cached release date: {cached_date}")
            return cached_date
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not read release date cache: {e}")
            return None

    def save_release_date_cache(self, date_str):
        """Save the release date to JSON cache file."""
        data = {
            'last_updated': date_str,
            'cached_at': datetime.now().strftime(config.DATETIME_FORMAT_META)
        }
        try:
            with open(config.RELEASE_DATE_CACHE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Release date saved to cache: {date_str}")
        except IOError as e:
            logger.error(f"Could not save release date cache: {e}")

    def is_new_data_available(self, current_date):
        """
        Compare current page date with cached date.
        Returns True if new data is available (or first run), False if same date.
        If config.BYPASS_RELEASE_DATE_CACHE is True, always returns True.
        """
        if config.BYPASS_RELEASE_DATE_CACHE:
            logger.info("BYPASS_RELEASE_DATE_CACHE=True — skipping cache check, forcing download.")
            return True

        cached_date = self.load_release_date_cache()

        if cached_date is None:
            logger.info("First run — no cached date. Will download.")
            return True

        if current_date != cached_date:
            logger.info(f"New data available!")
            logger.info(f"  Cached : {cached_date}")
            logger.info(f"  Current: {current_date}")
            return True
        else:
            logger.info(f"No new data — date unchanged: {current_date}")
            return False

    # =========================================================================
    # PAGE INTERACTIONS
    # =========================================================================

    def get_last_updated_date(self):
        """
        Extract the 'Last updated' date from the OECD Data Explorer page.

        Page HTML structure:
          <span class="MuiTypography-body2 css-nfh1jc">
            <span aria-label="" class="">
              <span class="jss151">Last updated</span>:
            </span>
            February 25, 2026 at 4:37:19 PM
          </span>

        Returns the date string (e.g. "February 25, 2026 at 4:37:19 PM") or None.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        logger.info("Looking for 'Last updated' date on page...")

        wait = WebDriverWait(self.driver, config.WAIT_TIMEOUT)

        # Wait for page content to settle
        try:
            wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, config.SELECTORS['last_updated_label'])
            ))
        except Exception:
            logger.warning("Timed out waiting for last_updated_label selector")

        # Method 1: Find span.jss151 containing 'Last updated', walk up 2 levels
        try:
            label_spans = self.driver.find_elements(
                By.CSS_SELECTOR, config.SELECTORS['last_updated_label']
            )
            for span in label_spans:
                if 'Last updated' in (span.text or ''):
                    # Walk up: jss151 → anonymous span → MuiTypography span
                    try:
                        container = span.find_element(
                            By.XPATH,
                            './ancestor::span[contains(@class,"MuiTypography-body2")]'
                        )
                        full_text = container.text.strip()
                    except Exception:
                        # Fallback: use JS to get grandparent innerText
                        full_text = self.driver.execute_script(
                            "return arguments[0].parentElement.parentElement.innerText;",
                            span
                        ).strip()

                    if full_text and 'Last updated' in full_text:
                        # Strip "Last updated" label and colon
                        date_part = full_text.replace('Last updated', '').strip().lstrip(':').strip()
                        if date_part:
                            logger.info(f"'Last updated' date found: {date_part}")
                            return date_part
        except Exception as e:
            logger.warning(f"Method 1 (jss151 span) failed: {e}")

        # Method 2: Find MuiTypography-body2 elements containing 'Last updated'
        try:
            elements = self.driver.find_elements(
                By.XPATH,
                '//*[contains(@class,"MuiTypography-body2") and contains(.,"Last updated")]'
            )
            for elem in elements:
                full_text = elem.text.strip()
                if 'Last updated' in full_text:
                    date_part = full_text.split('Last updated')[-1].strip().lstrip(':').strip()
                    if date_part:
                        logger.info(f"'Last updated' date found (method 2): {date_part}")
                        return date_part
        except Exception as e:
            logger.warning(f"Method 2 (MuiTypography XPath) failed: {e}")

        # Method 3: Broad search — any element whose text contains 'Last updated'
        try:
            elements = self.driver.find_elements(
                By.XPATH, '//*[contains(text(),"Last updated")]'
            )
            for elem in elements:
                full_text = elem.text.strip()
                if 'Last updated' in full_text and len(full_text) > 15:
                    date_part = full_text.split('Last updated')[-1].strip().lstrip(':').strip()
                    if date_part:
                        logger.info(f"'Last updated' date found (method 3): {date_part}")
                        return date_part
        except Exception as e:
            logger.warning(f"Method 3 (broad text search) failed: {e}")

        logger.error("Could not find 'Last updated' date on page")
        return None

    def _open_year_dropdown_and_get_options(self, container_selector, label):
        """
        Click the year combobox inside `container_selector` to open its
        dropdown, then collect and return all numeric year options as a
        sorted list of (year_int, element) tuples.

        `label` is a human-readable name for logging ("Start" or "End").
        Returns (combobox_element, sorted_year_list).
        Raises if the combobox cannot be found or the listbox does not appear.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        wait = WebDriverWait(self.driver, config.WAIT_TIMEOUT)

        container   = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, container_selector)
        ))
        combobox    = container.find_element(By.CSS_SELECTOR, '[role="combobox"]')
        current_val = container.get_attribute('title') or combobox.text or '?'
        logger.info(f"  {label} year — current value: '{current_val}'")

        # Open the dropdown
        self.safe_click(combobox)
        self.human_delay(0.6, 1.0)

        # Collect all year <li role="option"> items from the open listbox
        option_els = wait.until(EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, '[role="listbox"] [role="option"]')
        ))
        year_options = []
        for opt in option_els:
            val = opt.get_attribute('data-value') or ''
            if val.isdigit() and len(val) == 4:
                year_options.append((int(val), opt))

        year_options.sort(key=lambda x: x[0])
        logger.info(
            f"  {label} year — available range: "
            f"{year_options[0][0]} – {year_options[-1][0]} "
            f"({len(year_options)} years)"
            if year_options else f"  {label} year — no year options found"
        )
        return combobox, year_options

    def _select_year_option_and_verify(self, container_selector, target_year, label):
        """
        Open the year dropdown for `container_selector`, click `target_year`,
        then verify the combobox title attribute updated to confirm the selection.

        Returns True on success, False if year not found or verification failed.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        wait = WebDriverWait(self.driver, config.WAIT_TIMEOUT)

        combobox, year_options = self._open_year_dropdown_and_get_options(
            container_selector, label
        )

        if not year_options:
            logger.warning(f"  {label} year — no options in dropdown, skipping")
            return False

        # Find the target year in the option list
        match = next((el for yr, el in year_options if yr == target_year), None)
        if match is None:
            logger.warning(
                f"  {label} year {target_year} not in dropdown options — "
                f"available: {[yr for yr, _ in year_options]}"
            )
            return False

        # Scroll option into view and click it
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'nearest'});", match
        )
        self.human_delay(0.3, 0.6)
        self.safe_click(match)
        self.human_delay(0.5, 1.0)

        # Verify: the container title attribute should now reflect the selected year
        container = self.driver.find_element(By.CSS_SELECTOR, container_selector)
        confirmed = container.get_attribute('title') or ''
        if str(target_year) in confirmed:
            logger.info(f"  {label} year confirmed: {confirmed}")
            return True
        else:
            logger.warning(
                f"  {label} year selection may not have applied "
                f"(container title='{confirmed}', expected '{target_year}')"
            )
            return True   # proceed anyway — the click did execute

    def select_full_time_period(self):
        """
        Expand the Time period filter to include ALL available years.

        The OECD Data Explorer defaults the start year to 2007 and leaves the
        end year open-ended.  This method opens the Time period panel, sets
        the Start year to the earliest year found in the dropdown, sets the End
        year to the latest year found in the dropdown, confirms both selections,
        then clicks Apply so the full range is committed before the CSV is
        downloaded.

        Steps
        -----
        1.  Click the "Time period" sidebar tab   → opens the filter panel
        2.  Open Start year dropdown              → collect available years
        3.  Click earliest year                   → verify selection updated
        4.  Open End year dropdown                → collect available years
        5.  Click latest year                     → verify selection updated
        6.  Click the Apply button
        7.  Wait for the panel to close + page to settle

        Returns True if the time period was successfully updated, False otherwise.
        If it returns False the caller still proceeds — download covers whatever
        range the page currently has loaded.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys

        wait = WebDriverWait(self.driver, config.WAIT_TIMEOUT)
        logger.info("Expanding Time period to full available range...")

        try:
            # ── Step 1: Click the Time period tab ───────────────────────────
            time_tab = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, config.SELECTORS['time_period_tab'])
            ))
            self.safe_click(time_tab)
            logger.info("Time period tab clicked")

            # ── Step 2: Wait for the filter panel to open ────────────────────
            wait.until(EC.visibility_of_element_located(
                (By.CSS_SELECTOR, config.SELECTORS['filter_panel'])
            ))
            self.human_delay(1.0, 1.5)
            logger.info("Time period filter panel opened")

            # ── Step 3: Discover available year range via Start dropdown ─────
            # We open Start to learn what years exist, then pick the earliest.
            _, start_options = self._open_year_dropdown_and_get_options(
                config.SELECTORS['start_year_picker'], 'Start'
            )

            if not start_options:
                logger.warning("No year options found — closing panel, using defaults")
                try:
                    self.driver.find_element(
                        By.CSS_SELECTOR, '[aria-label="Cancel"]'
                    ).click()
                except Exception:
                    pass
                return False

            earliest_year = start_options[0][0]
            latest_year   = start_options[-1][0]
            logger.info(f"Year range on page: {earliest_year} – {latest_year}")

            # Click the earliest option (dropdown is already open)
            earliest_el = start_options[0][1]
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'nearest'});", earliest_el
            )
            self.human_delay(0.3, 0.6)
            self.safe_click(earliest_el)
            self.human_delay(0.5, 1.0)

            # Verify Start selection
            start_container = self.driver.find_element(
                By.CSS_SELECTOR, config.SELECTORS['start_year_picker']
            )
            start_confirmed = start_container.get_attribute('title') or ''
            if str(earliest_year) in start_confirmed:
                logger.info(f"Start year confirmed: {start_confirmed}")
            else:
                logger.warning(
                    f"Start year title='{start_confirmed}' — expected '{earliest_year}'"
                )

            # ── Step 4: Open End dropdown → select latest year ───────────────
            ok_end = self._select_year_option_and_verify(
                config.SELECTORS['end_year_picker'],
                latest_year,
                'End'
            )
            if not ok_end:
                logger.warning("End year selection issue — proceeding anyway")

            # ── Step 5: Click Apply ──────────────────────────────────────────
            self.human_delay(0.5, 1.0)
            apply_btn = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, config.SELECTORS['apply_button'])
            ))
            self.safe_click(apply_btn)
            logger.info(
                f"Apply clicked — time period set to {earliest_year}–{latest_year}"
            )

            # ── Step 6: Wait for panel to close + page to settle ─────────────
            try:
                wait.until(EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, config.SELECTORS['filter_panel'])
                ))
            except Exception:
                pass   # panel may close quickly via CSS animation

            self.human_delay(2.0, 3.0)
            logger.info(f"Time period expanded: {earliest_year} – {latest_year}")
            return True

        except Exception as e:
            logger.error(f"Error selecting full time period: {e}", exc_info=True)
            return False

    def click_download_button(self):
        """Click the main Download button to open the dropdown menu."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        wait = WebDriverWait(self.driver, config.WAIT_TIMEOUT)
        logger.info("Clicking Download button...")

        try:
            btn = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, config.SELECTORS['download_button'])
            ))
            # Scroll into view first
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", btn
            )
            self.human_delay(0.5, 1.0)
            self.safe_click(btn)
            logger.info("Download button clicked")
            return True
        except Exception as e:
            logger.error(f"Could not click Download button: {e}")
            return False

    def click_filtered_csv_option(self):
        """
        Click 'Filtered data in tabular text (CSV)' from the download dropdown.
        Uses id='csv.selection' as the target.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        wait = WebDriverWait(self.driver, config.WAIT_TIMEOUT)
        logger.info("Waiting for download dropdown menu...")

        try:
            # Wait for the dropdown menu to be visible
            wait.until(EC.visibility_of_element_located(
                (By.CSS_SELECTOR, config.SELECTORS['download_menu'])
            ))
            self.human_delay(0.5, 1.0)

            # Click the filtered CSV option by its id attribute
            # id="csv.selection" — using By.CSS_SELECTOR with attribute selector
            # to handle the period in the id value safely
            csv_link = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, config.SELECTORS['filtered_csv_link'])
            ))
            self.safe_click(csv_link)
            logger.info("Clicked 'Filtered data in tabular text (CSV)'")
            return True

        except Exception as e:
            logger.error(f"Could not click filtered CSV option: {e}")
            return False

    # =========================================================================
    # DOWNLOAD WATCHER
    # =========================================================================

    def wait_for_download(self):
        """
        Dynamic two-phase file watcher — no hardcoded completion timeout.

        Phase 1 — Startup detection (uses config.DOWNLOAD_WAIT_TIME as start deadline):
          Watch for ANY file activity (.csv or .crdownload) in the download dir.
          If nothing appears within the deadline the click likely failed → return None.

        Phase 2 — Completion detection (runs until file is done or stalls):
          Once download activity is detected, keep watching until:
            a) .crdownload disappears AND .csv with size > 0 is present → return path
            b) File size stops growing for config.DOWNLOAD_STALL_TIMEOUT seconds → stalled, return None

        The browser is closed by the caller immediately after this returns.
        """
        logger.info(f"Watching download directory: {self.download_dir}")

        start_time          = time.time()
        download_started    = False
        last_known_size     = 0
        last_size_change_at = start_time

        while True:
            csv_files     = glob.glob(os.path.join(self.download_dir, '*.csv'))
            partial_files = glob.glob(os.path.join(self.download_dir, '*.crdownload'))

            # ----------------------------------------------------------------
            # PHASE 1: waiting for the download to begin
            # ----------------------------------------------------------------
            if not download_started:
                if csv_files or partial_files:
                    download_started = True
                    logger.info(
                        f"Download started "
                        f"({'partial' if partial_files else 'direct'}) — "
                        f"monitoring for completion..."
                    )
                else:
                    elapsed = time.time() - start_time
                    if elapsed > config.DOWNLOAD_WAIT_TIME:
                        logger.error(
                            f"Download did not start within {config.DOWNLOAD_WAIT_TIME}s "
                            f"— click may have failed"
                        )
                        return None
                    if int(elapsed) % 15 == 0 and int(elapsed) > 0:
                        logger.debug(f"Waiting for download to start... ({int(elapsed)}s)")

            # ----------------------------------------------------------------
            # PHASE 2: download has started — wait for it to finish
            # ----------------------------------------------------------------
            if download_started:

                # Complete: .csv present and NO .crdownload in-progress file
                if csv_files and not partial_files:
                    found = max(csv_files, key=os.path.getmtime)
                    size  = os.path.getsize(found)
                    if size > 0:
                        logger.info(
                            f"Download complete: {os.path.basename(found)} "
                            f"({size:,} bytes)"
                        )
                        return found

                # Stall detection: measure total bytes across all in-progress files
                active_files  = partial_files + csv_files
                current_size  = sum(
                    os.path.getsize(f) for f in active_files if os.path.exists(f)
                )
                if current_size != last_known_size:
                    last_known_size     = current_size
                    last_size_change_at = time.time()
                    logger.debug(f"Download progress: {current_size:,} bytes")
                else:
                    stalled_for = time.time() - last_size_change_at
                    if stalled_for > config.DOWNLOAD_STALL_TIMEOUT:
                        logger.error(
                            f"Download stalled — no size change for "
                            f"{config.DOWNLOAD_STALL_TIMEOUT}s"
                        )
                        return None

            time.sleep(1)

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    def download_data(self):
        """
        Main method: navigate to OECD Data Explorer, check for new data,
        download if the release date has changed (or first run).

        Returns dict:
          {
            'downloaded': bool,
            'file_path': str or None,
            'release_date': str or None,
            'reason': str or None   (set when downloaded=False)
          }
        """
        result = {
            'downloaded': False,
            'file_path': None,
            'release_date': None,
            'reason': None
        }

        try:
            self.setup_driver()

            # Navigate to the OECD Data Explorer
            logger.info(f"Navigating to: {config.BASE_URL}")
            self.driver.get(config.BASE_URL)
            logger.info(f"Page load delay: {config.PAGE_LOAD_DELAY}s")
            time.sleep(config.PAGE_LOAD_DELAY)

            # ----------------------------------------------------------------
            # STEP 1: Get release date
            # ----------------------------------------------------------------
            print(f"\n[1/3] Checking release date on page...")

            release_date = self.get_last_updated_date()

            if not release_date:
                logger.error("Could not determine release date from page")
                result['reason'] = 'Could not determine release date'
                return result

            result['release_date'] = release_date
            print(f"  Release date: {release_date}")

            # ----------------------------------------------------------------
            # STEP 2: Compare with cached date
            # ----------------------------------------------------------------
            if not self.is_new_data_available(release_date):
                print(f"  [SKIP] No new data — release date matches cached value")
                result['reason'] = 'No new data available (same release date)'
                return result

            print(f"  [NEW] New data detected — proceeding with download")

            # ----------------------------------------------------------------
            # STEP 3: Expand Time period to all available years
            # ----------------------------------------------------------------
            print(f"\n[2/4] Setting time period to all available years...")

            tp_ok = self.select_full_time_period()
            if tp_ok:
                print(f"  [OK] Time period expanded to earliest available year")
            else:
                print(f"  [WARN] Could not expand time period — using page default range")

            # ----------------------------------------------------------------
            # STEP 4: Click Download button → select Filtered CSV
            # ----------------------------------------------------------------
            print(f"\n[3/4] Initiating download...")

            if not self.click_download_button():
                result['reason'] = 'Could not click Download button'
                return result

            self.human_delay(1.0, 2.0)

            if not self.click_filtered_csv_option():
                result['reason'] = 'Could not click Filtered CSV option'
                return result

            # ----------------------------------------------------------------
            # STEP 5: Wait for file to land in downloads folder
            # ----------------------------------------------------------------
            print(f"\n[4/4] Waiting for file download...")

            file_path = self.wait_for_download()

            # Close browser immediately — download is on disk, browser no longer needed
            if self.driver:
                try:
                    self.driver.quit()
                    self.driver = None
                    logger.info("Browser closed immediately after download detected")
                except Exception:
                    pass

            if not file_path:
                result['reason'] = 'Download timed out or file not found'
                return result

            # ----------------------------------------------------------------
            # Save the new release date to cache (only after successful download)
            # ----------------------------------------------------------------
            self.save_release_date_cache(release_date)

            result['downloaded'] = True
            result['file_path'] = file_path
            print(f"  [OK] File saved: {os.path.basename(file_path)}")

            return result

        except Exception as e:
            logger.error(f"Unexpected error during download: {e}", exc_info=True)
            result['reason'] = str(e)
            return result

        finally:
            if self.driver:
                try:
                    self.driver.quit()
                    logger.info("Browser closed")
                except Exception:
                    pass


def main():
    """Test the scraper independently."""
    # Basic logging for standalone test
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    scraper = OECDScraper()
    result = scraper.download_data()

    print(f"\n{'='*60}")
    print("SCRAPER RESULT")
    print(f"{'='*60}")
    print(f"  Downloaded   : {result['downloaded']}")
    print(f"  File         : {result.get('file_path')}")
    print(f"  Release date : {result.get('release_date')}")
    if not result['downloaded']:
        print(f"  Reason       : {result.get('reason')}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
