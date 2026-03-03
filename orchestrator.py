# orchestrator.py
# Main pipeline coordinator for OECD_VC_INV data extraction

import logging
import sys
from datetime import datetime

import config
from logger_setup import setup_logging
from scraper import OECDScraper
from parser import OECDParser
from file_generator import OECDFileGenerator

# Initialize logging first — all subsequent modules inherit from root logger
logger = setup_logging()


def print_banner():
    """Display application banner."""
    banner = """
    ==============================================================

          OECD Venture Capital Investments
          OECD Data Explorer — Automated Extraction

                   OECD_VC_INV Runbook

    ==============================================================
    """
    print(banner)


def print_configuration():
    """Display current configuration settings."""
    print(f"\n{'='*60}")
    print("CONFIGURATION")
    print(f"{'='*60}")
    print(f"Provider      : {config.PROVIDER_NAME}")
    print(f"Dataset       : {config.DATASET_NAME}")
    print(f"Source URL    : {config.BASE_URL}")
    print(f"Target Measure: {config.TARGET_MEASURE}")
    print(f"Run Timestamp : {config.RUN_TIMESTAMP}")
    print()
    print(f"Output Dir    : {config.OUTPUT_DIR}")
    print(f"Download Dir  : {config.DOWNLOAD_DIR}")
    print(f"Log Dir       : {config.LOG_DIR}")
    print(f"Date Cache    : {config.RELEASE_DATE_CACHE_FILE}")
    print(f"{'='*60}\n")


def main():
    """
    Main execution flow:

      STEP 1 — SCRAPER
        Navigate to OECD Data Explorer, check the 'Last updated' release date.
        If the date is the same as the cached value → exit (no new data).
        If the date is new (or first run) → download the filtered CSV.

      STEP 2 — PARSER
        Dynamically locate all required columns in the downloaded CSV.
        Filter to TARGET_MEASURE rows.
        Pivot long → wide (years as rows, country×stage as columns).
        Preserve all decimal values exactly as in the source file.

      STEP 3 — FILE GENERATOR
        Write OECD_VC_INV_DATA_{timestamp}.xlsx  (codes row, descs row, data rows)
        Write OECD_VC_INV_META_{timestamp}.xlsx  (one row per column code)
        Write OECD_VC_INV_{timestamp}.zip        (both xlsx files archived)
        Copy all three to latest/ folder
    """

    start_time = datetime.now()

    try:
        print_banner()
        print_configuration()

        logger.info("Starting OECD_VC_INV data extraction pipeline")

        # =================================================================
        # STEP 1: DOWNLOAD
        # =================================================================
        print(f"\n{'#'*60}")
        print("# STEP 1: DOWNLOADING CSV FROM OECD DATA EXPLORER")
        print(f"{'#'*60}\n")

        logger.info("STEP 1: Starting download...")

        scraper = OECDScraper()
        download_result = scraper.download_data()

        # If no new data, exit cleanly (not an error)
        if not download_result['downloaded']:
            reason = download_result.get('reason', 'Unknown reason')

            if 'No new data' in reason:
                print(f"\n[INFO] {reason}")
                print("Nothing to do — pipeline finished.")
                logger.info(f"Pipeline stopped: {reason}")
                return 0
            else:
                logger.error(f"Download failed: {reason}")
                print(f"\n[ERROR] Download failed: {reason}")
                print("Check logs for details.")
                sys.exit(1)

        downloaded_file = download_result['file_path']
        release_date    = download_result['release_date']

        logger.info(f"Download complete: {downloaded_file}")
        logger.info(f"Release date: {release_date}")

        print(f"\n  Downloaded : {downloaded_file}")
        print(f"  Release date: {release_date}")

        # =================================================================
        # STEP 2: PARSE
        # =================================================================
        print(f"\n{'#'*60}")
        print("# STEP 2: PARSING CSV")
        print(f"{'#'*60}\n")

        logger.info("STEP 2: Starting parse...")

        parser = OECDParser()

        print(f"  Parsing: {downloaded_file}")
        parsed_result = parser.parse_csv(downloaded_file)

        if not parsed_result:
            logger.error("Parsing failed. Exiting.")
            print("\n[ERROR] Failed to parse the downloaded CSV. Check logs.")
            sys.exit(1)

        logger.info(
            f"Parse complete: {parsed_result['col_count']} columns, "
            f"{parsed_result['row_count']} year rows"
        )

        print(f"\n{'='*60}")
        print(
            f"Parse complete: {parsed_result['col_count']} columns "
            f"({parsed_result['years'][0]}–{parsed_result['years'][-1]}), "
            f"{parsed_result['row_count']} year rows"
        )
        print(f"{'='*60}\n")

        # =================================================================
        # STEP 3: GENERATE OUTPUT FILES
        # =================================================================
        print(f"\n{'#'*60}")
        print("# STEP 3: GENERATING OUTPUT FILES")
        print(f"{'#'*60}\n")

        logger.info("STEP 3: Generating output files...")

        generator = OECDFileGenerator()
        output_files = generator.generate_files(parsed_result)

        if not output_files:
            logger.error("File generation failed. Exiting.")
            print("\n[ERROR] Failed to generate output files. Check logs.")
            sys.exit(1)

        logger.info("Output file generation complete")

        # =================================================================
        # SUMMARY
        # =================================================================
        end_time = datetime.now()
        duration = end_time - start_time

        print(f"\n{'='*60}")
        print("EXECUTION SUMMARY")
        print(f"{'='*60}")
        print(f"Status         : SUCCESS")
        print(f"Release Date   : {release_date}")
        print(f"Columns        : {parsed_result['col_count']}")
        print(f"Year Rows      : {parsed_result['row_count']}")
        print(f"Year Range     : {parsed_result['years'][0]} – {parsed_result['years'][-1]}")
        print()
        print(f"Output Files:")
        print(f"  Data xlsx    : {output_files['data_file']}")
        if output_files.get('meta_file'):
            print(f"  Meta xlsx    : {output_files['meta_file']}")
        if output_files.get('zip_file'):
            print(f"  Zip archive  : {output_files['zip_file']}")
        print()
        print(f"Latest Folder  : {output_files['latest_dir']}")
        print()
        print(f"Duration       : {duration}")
        print(f"Completed      : {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        logger.info(f"Pipeline completed successfully in {duration}")
        logger.info(
            f"Columns: {parsed_result['col_count']} | "
            f"Year rows: {parsed_result['row_count']}"
        )

        return 0

    except KeyboardInterrupt:
        logger.warning("Execution interrupted by user")
        print("\n\n[INTERRUPTED] Execution stopped by user")
        return 1

    except Exception as e:
        logger.critical(f"Unexpected error in pipeline: {e}", exc_info=True)
        print(f"\n\n[CRITICAL ERROR] {e}")
        print("Check logs for details.")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
