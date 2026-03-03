# parser.py
# Parses the OECD filtered CSV and pivots it into the standard output structure

import os
import csv
import itertools
import logging
import config

logger = logging.getLogger(__name__)

# Number of data rows sampled for content-based column detection (Level 3)
_SAMPLE_SIZE = 30


class OECDParser:
    """
    Parses the OECD Venture Capital Investment CSV (long/tall format) and
    produces a wide pivot table that matches the standard output layout:

        Row 1  — column codes        e.g. AUS.VCINV.VCT.USDV.A
        Row 2  — column descriptions e.g. Australia: Venture capital investments, Total, USD, current prices
        Row 3+ — year rows           e.g. 2007, 439.68, ...

    The parser is fully dynamic:
      - It locates every required column by scanning the header row.
      - It discovers all (REF_AREA, STAGE) combinations present in the data.
      - It preserves blank OBS_VALUE cells as None (written as blank in xlsx).
      - It preserves numeric values exactly as they appear in the source file.
    """

    def __init__(self):
        self.logger = logger

    # =========================================================================
    # HEADER DISCOVERY
    # =========================================================================

    def find_column_indices(self, header_row, sample_rows=None):
        """
        Scan the header row and return a dict mapping logical names to
        zero-based column indices.

        Three-level detection — each column is tried at all levels before
        raising an error:

          Level 1 — Exact header text match
                    e.g. 'REF_AREA' == 'REF_AREA'

          Level 2 — Case-insensitive header text match
                    e.g. 'ref_area' matches 'REF_AREA'

          Level 3 — Content fingerprint match (requires sample_rows)
                    Analyses a sample of data rows to identify each column
                    by what values it contains, regardless of header text.
                    e.g. a column whose values are all 4-digit years → time_period

        Raises ValueError if any required column cannot be found by any level.
        """
        self.logger.info("Scanning CSV header row for required columns...")

        required   = config.CSV_COLUMNS      # logical_name -> expected_header_text
        indices    = {}
        unresolved = {}                       # logical_name -> expected_header_text

        # ── Levels 1 & 2: header text matching ──────────────────────────────
        for logical_name, expected_text in required.items():
            found = False

            # Level 1: exact
            for idx, cell in enumerate(header_row):
                if cell.strip() == expected_text.strip():
                    indices[logical_name] = idx
                    self.logger.debug(
                        f"  [L1-exact]  '{expected_text}' → col {idx}"
                    )
                    found = True
                    break

            # Level 2: case-insensitive
            if not found:
                for idx, cell in enumerate(header_row):
                    if cell.strip().lower() == expected_text.strip().lower():
                        indices[logical_name] = idx
                        self.logger.warning(
                            f"  [L2-icase]  '{expected_text}' matched "
                            f"'{cell.strip()}' at col {idx}"
                        )
                        found = True
                        break

            if not found:
                unresolved[logical_name] = expected_text

        # ── Level 3: content fingerprint (only for still-unresolved columns) ─
        if unresolved:
            if sample_rows:
                self.logger.info(
                    f"  {len(unresolved)} column(s) unresolved after header "
                    f"matching — attempting content-based detection..."
                )
                guessed = self._guess_columns_by_content(
                    header_row,
                    sample_rows,
                    set(unresolved.keys()),
                    already_claimed=set(indices.values()),
                )
                for logical_name, idx in guessed.items():
                    indices[logical_name] = idx
                    unresolved.pop(logical_name)
                    self.logger.warning(
                        f"  [L3-content] '{logical_name}' identified at col {idx} "
                        f"(header: '{header_row[idx].strip()}')"
                    )
            else:
                self.logger.warning(
                    "  No sample rows provided — content-based detection skipped."
                )

        # ── Raise if anything is still missing ──────────────────────────────
        if unresolved:
            missing = ', '.join(
                f"'{v}'" for v in unresolved.values()
            )
            raise ValueError(
                f"Required column(s) not found in CSV header: {missing}\n"
                f"Available headers: {[c.strip() for c in header_row]}"
            )

        self.logger.info(f"All {len(indices)} required columns located.")
        return indices

    # =========================================================================
    # DATA EXTRACTION
    # =========================================================================

    def parse_csv(self, file_path):
        """
        Main parse method.

        Steps:
          1. Detect encoding and open file.
          2. Read header + sample rows; locate required column indices
             using three-level detection (exact / case-insensitive / content).
          3. Process all rows: filter by TARGET_MEASURE, collect data.
          4. Build ordered list of (ref_area, stage) column combinations.
          5. Reorder to canonical country × stage order.
          6. Build pivot: year → {col_code: value_or_None}.
          7. Generate column codes and descriptions.
          8. Return structured result dict.

        Returns dict or None on failure.
        """
        self.logger.info(f"Parsing OECD CSV: {file_path}")

        if not os.path.exists(file_path):
            self.logger.error(f"File not found: {file_path}")
            return None

        try:
            # ----------------------------------------------------------------
            # STEP 1: Open file (handle BOM if present)
            # ----------------------------------------------------------------
            encoding = self._detect_encoding(file_path)
            self.logger.info(f"Using encoding: {encoding}")

            with open(file_path, 'r', encoding=encoding, newline='') as f:
                reader = csv.reader(f)

                # ----------------------------------------------------------------
                # STEP 2: Read header + sample rows, then locate columns
                # ----------------------------------------------------------------
                header_row = next(reader)

                # Strip BOM from first cell if present
                if header_row and header_row[0].startswith('\ufeff'):
                    header_row[0] = header_row[0].lstrip('\ufeff')

                # Buffer a small sample for Level-3 content detection.
                # The sample rows are re-processed in the main loop below
                # via itertools.chain so no data is skipped.
                sample_rows = []
                for row in reader:
                    sample_rows.append(row)
                    if len(sample_rows) >= _SAMPLE_SIZE:
                        break

                self.logger.info(
                    f"Buffered {len(sample_rows)} sample rows for "
                    f"content-based column detection."
                )

                indices = self.find_column_indices(header_row, sample_rows)

                idx_ref        = indices['ref_area']
                idx_ref_label  = indices['ref_area_label']
                idx_measure    = indices['measure']
                idx_stage      = indices['stage']
                idx_stage_label= indices['stage_label']
                idx_period     = indices['time_period']
                idx_value      = indices['obs_value']

                # ----------------------------------------------------------------
                # STEP 3: Process all rows (sample first, then rest of file)
                # ----------------------------------------------------------------
                self.logger.info(
                    f"Filtering rows: MEASURE == '{config.TARGET_MEASURE}'"
                )

                # raw_data: {(ref_area, stage): {year: raw_value_string}}
                raw_data = {}

                # col_meta: {(ref_area, stage): (ref_label, stage_label)}
                #   preserves first-seen labels for each combination
                col_meta = {}

                # col_order: ordered list of (ref_area, stage) as first encountered
                col_order = []

                # all years seen (as int)
                all_years = set()

                row_count = 0
                skipped   = 0

                for row in itertools.chain(sample_rows, reader):
                    if len(row) <= max(idx_ref, idx_measure, idx_stage, idx_period, idx_value):
                        skipped += 1
                        continue

                    measure_code = row[idx_measure].strip()
                    if measure_code != config.TARGET_MEASURE:
                        skipped += 1
                        continue

                    ref_area    = row[idx_ref].strip()
                    ref_label   = row[idx_ref_label].strip()
                    stage_raw   = row[idx_stage].strip()
                    stage_label = row[idx_stage_label].strip()
                    period_raw  = row[idx_period].strip()
                    value_raw   = row[idx_value].strip()   # keep exact string

                    if not ref_area or not stage_raw or not period_raw:
                        skipped += 1
                        continue

                    # Apply stage code mapping (e.g. '_T' → 'VCT')
                    stage_code = config.STAGE_CODE_MAPPING.get(stage_raw, stage_raw)

                    # Parse year (TIME_PERIOD is annual: just a 4-digit year)
                    try:
                        year = int(period_raw)
                    except ValueError:
                        self.logger.warning(
                            f"Could not parse TIME_PERIOD '{period_raw}' as year — skipping row"
                        )
                        skipped += 1
                        continue

                    key = (ref_area, stage_code)

                    # Register column order on first encounter
                    if key not in col_meta:
                        col_meta[key]  = (ref_label, stage_label)
                        col_order.append(key)
                        raw_data[key]  = {}

                    all_years.add(year)
                    # Store the raw string — empty string kept as-is
                    raw_data[key][year] = value_raw

                    row_count += 1

                self.logger.info(
                    f"Rows processed: {row_count} | Rows skipped: {skipped}"
                )
                self.logger.info(
                    f"Unique columns (country×stage): {len(col_order)}"
                )
                self.logger.info(
                    f"Year range: {min(all_years)} – {max(all_years)}"
                    if all_years else "No years found"
                )

                if not col_order or not all_years:
                    self.logger.error("No usable data found after filtering.")
                    return None

            # ----------------------------------------------------------------
            # STEP 3b: Reorder columns to canonical country × stage order
            # ----------------------------------------------------------------
            col_order = self._reorder_columns(col_order)
            self.logger.info(
                f"Columns reordered: {len(col_order)} (country × stage)"
            )

            # ----------------------------------------------------------------
            # STEP 4: Build column codes and descriptions
            # ----------------------------------------------------------------
            sorted_years = sorted(all_years)

            column_codes  = []
            column_descs  = []
            country_map   = {}   # col_code -> country label (for metadata)
            stage_map     = {}   # col_code -> stage label   (for metadata)
            ref_area_map  = {}   # col_code -> REF_AREA code (for metadata)

            for (ref_area, stage_code) in col_order:
                ref_label, stage_label = col_meta[(ref_area, stage_code)]

                col_code = config.COLUMN_CODE_FORMAT.format(
                    ref_area=ref_area,
                    stage=stage_code
                )
                col_desc = config.COLUMN_DESC_FORMAT.format(
                    country=ref_label,
                    stage_label=stage_label
                )

                column_codes.append(col_code)
                column_descs.append(col_desc)
                country_map[col_code]  = ref_label
                stage_map[col_code]    = stage_label
                ref_area_map[col_code] = ref_area

            self.logger.info(f"Column codes generated: {len(column_codes)}")

            # ----------------------------------------------------------------
            # STEP 5: Build pivot rows
            # ----------------------------------------------------------------
            # Each pivot row: {'year': int, col_code: value_or_None, ...}
            #
            # value_or_None:
            #   - None         if the source cell was blank (empty string)
            #   - raw string   if the source cell had a numeric string
            #     (written with data_type='n' by file_generator to preserve
            #      the exact decimal from the source file)

            pivot_rows = []

            for year in sorted_years:
                row_dict = {'year': year}

                for i, (ref_area, stage_code) in enumerate(col_order):
                    col_code  = column_codes[i]
                    value_raw = raw_data[(ref_area, stage_code)].get(year, '')

                    row_dict[col_code] = self._parse_value(value_raw)

                pivot_rows.append(row_dict)

            self.logger.info(
                f"Pivot complete: {len(pivot_rows)} year rows × "
                f"{len(column_codes)} columns"
            )

            # ----------------------------------------------------------------
            # STEP 6: Return result
            # ----------------------------------------------------------------
            return {
                'source_file':    file_path,
                'column_codes':   column_codes,
                'column_descs':   column_descs,
                'country_map':    country_map,
                'stage_map':      stage_map,
                'ref_area_map':   ref_area_map,
                'years':          sorted_years,
                'pivot_rows':     pivot_rows,
                'row_count':      len(pivot_rows),
                'col_count':      len(column_codes),
            }

        except ValueError as ve:
            self.logger.error(f"Column discovery failed: {ve}")
            return None
        except Exception as e:
            self.logger.error(f"Error parsing CSV: {e}", exc_info=True)
            return None

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _guess_columns_by_content(self, header_row, sample_rows, needed, already_claimed):
        """
        Identify columns by the patterns in their data values.

        For each column in `needed` (a set of logical names), tests each
        unclaimed column position in `header_row` against a fingerprint rule.
        Returns a dict of {logical_name: column_index} for any that match.

        Detection order matters — most distinctive patterns run first to avoid
        misidentification when columns share superficial characteristics.

        Fingerprint rules (in detection order)
        ---------------------------------------
        time_period    — all non-blank values are 4-digit integers (1900–2100)
        obs_value      — all non-blank values convert to float
        measure        — single repeated uppercase code containing '_' (< 20 chars)
        measure_label  — single repeated descriptive string (length > 10)
        stage          — all values are in STAGE_CODE_MAPPING keys (exact set)
        ref_area       — all values are 2–4 char purely alphabetic uppercase codes
        stage_label    — same unique-value count as the claimed 'stage' column
                         (stage codes and stage descriptions are 1-to-1)
        ref_area_label — same unique-value count as the claimed 'ref_area' column
                         (country codes and country names are 1-to-1)

        Cardinality matching (stage_label / ref_area_label) avoids the ambiguity
        between country names and stage descriptions, which look alike by shape
        but differ in how many unique values appear in any sample window.
        """
        n_cols       = len(header_row)
        known_stages = set(config.STAGE_CODE_MAPPING.keys())

        # Pre-compute (vals, non_blank) per column, skip already-claimed
        col_data = []
        for col_i in range(n_cols):
            if col_i in already_claimed:
                col_data.append(None)
                continue
            vals      = [row[col_i].strip() for row in sample_rows if col_i < len(row)]
            non_blank = [v for v in vals if v]
            col_data.append((vals, non_blank))

        guessed       = {}
        used          = set(already_claimed)
        claimed_uniq  = {}    # logical_name -> unique non-blank value count

        def pick(logical_name, test_fn):
            """Assign the first unclaimed column that passes test_fn."""
            if logical_name not in needed:
                return
            for col_i, data in enumerate(col_data):
                if col_i in used or data is None:
                    continue
                vals, non_blank = data
                if non_blank and test_fn(vals, non_blank):
                    guessed[logical_name]     = col_i
                    claimed_uniq[logical_name] = len(set(non_blank))
                    used.add(col_i)
                    col_data[col_i] = None     # mark claimed
                    return

        # ── Detection rules (most → least distinctive) ──────────────────────

        # TIME_PERIOD: every non-blank value is a 4-digit year
        pick('time_period', lambda v, nb:
            all(s.isdigit() and len(s) == 4 and 1900 <= int(s) <= 2100
                for s in nb))

        # OBS_VALUE: every non-blank value converts to a float
        pick('obs_value', lambda v, nb:
            all(self._is_numeric_string(s) for s in nb))

        # MEASURE: single repeated uppercase code containing an underscore
        pick('measure', lambda v, nb:
            len(set(nb)) == 1
            and '_' in nb[0]
            and nb[0].replace('_', '').isalpha()
            and nb[0].upper() == nb[0]
            and len(nb[0]) < 20)

        # Measure label: single repeated descriptive string (length > 10)
        pick('measure_label', lambda v, nb:
            len(set(nb)) == 1 and len(nb[0]) > 10)

        # BUSINESS_DEVELOPMENT_STAGE: all values exactly in the known set
        pick('stage', lambda v, nb:
            all(s in known_stages for s in nb))

        # REF_AREA: 2–4 char purely alphabetic uppercase codes
        pick('ref_area', lambda v, nb:
            all(s.isalpha() and s.upper() == s and 2 <= len(s) <= 4
                for s in nb))

        # Stage label: same cardinality as 'stage' + descriptive text (not all-caps)
        # Cardinality check: stage codes and stage labels are a 1-to-1 mapping,
        # so both columns must have the same number of unique values in the sample.
        stage_uniq = claimed_uniq.get('stage')
        pick('stage_label', lambda v, nb:
            len(set(nb)) == stage_uniq
            and all(len(s) > 1 and s.upper() != s for s in nb))

        # Reference area label: same cardinality as 'ref_area' + longer text
        ref_area_uniq = claimed_uniq.get('ref_area')
        pick('ref_area_label', lambda v, nb:
            len(set(nb)) == ref_area_uniq
            and all(len(s) > 3 for s in nb))

        return guessed

    def _reorder_columns(self, col_order):
        """
        Sort (ref_area, stage_code) tuples into the canonical output order:

          Primary key   — position in config.COUNTRY_ORDER
                          (countries absent from the list are appended at the end)
          Secondary key — position in config.STAGE_ORDER
                          (stages absent from the list are appended after known stages)

        This ensures the output columns match the reference file exactly, regardless
        of the order in which rows appear in the source CSV.
        """
        country_rank = {c: i for i, c in enumerate(config.COUNTRY_ORDER)}
        stage_rank   = {s: i for i, s in enumerate(config.STAGE_ORDER)}

        n_countries = len(config.COUNTRY_ORDER)
        n_stages    = len(config.STAGE_ORDER)

        def sort_key(key):
            ref_area, stage_code = key
            c_rank = country_rank.get(ref_area,   n_countries)
            s_rank = stage_rank.get(stage_code,   n_stages)
            return (c_rank, s_rank)

        return sorted(col_order, key=sort_key)

    def _detect_encoding(self, file_path):
        """
        Detect file encoding by reading the first bytes.
        Falls back to utf-8 if no BOM is detected.
        """
        with open(file_path, 'rb') as f:
            raw = f.read(4)

        if raw[:3] == b'\xef\xbb\xbf':
            return 'utf-8-sig'     # UTF-8 with BOM
        if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
            return 'utf-16'
        return 'utf-8'

    def _parse_value(self, raw_string):
        """
        Validate and normalise a raw OBS_VALUE string.

        Rules (as per project requirements):
          - Blank / whitespace-only → None        (written as empty cell in xlsx)
          - Valid numeric string    → raw string   (written as numeric cell via
                                                    data_type='n', preserving the
                                                    exact decimal from the source)
          - Non-numeric string      → raw string   (written as-is; warning logged)

        Returning the raw string (rather than a Python float) prevents openpyxl's
        XML serialiser from silently truncating trailing decimal digits.
        """
        s = raw_string.strip()

        if s == '':
            return None

        try:
            float(s)        # validate — raises ValueError if not a number
            return s        # return the exact source string
        except ValueError:
            self.logger.warning(
                f"OBS_VALUE '{s}' is not numeric — keeping as string"
            )
            return s

    def _is_numeric_string(self, s):
        """Return True if s represents a valid integer or floating-point number."""
        try:
            float(s)
            return True
        except (ValueError, TypeError):
            return False


def main():
    """Test the parser independently."""
    import sys
    import logging

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if len(sys.argv) < 2:
        # Default to the sample file for development testing
        sample = (
            r'project_information'
            r'\OECD.SDD.TPS,DSD_VC@DF_VC_INV,+...USD_EXC.A.csv'
        )
        file_path = sample
    else:
        file_path = sys.argv[1]

    parser = OECDParser()
    result = parser.parse_csv(file_path)

    if result:
        print(f"\n{'='*60}")
        print(f"PARSE RESULT")
        print(f"{'='*60}")
        print(f"  Columns     : {result['col_count']}")
        print(f"  Year rows   : {result['row_count']}")
        print(f"  Year range  : {result['years'][0]} – {result['years'][-1]}")
        print(f"\nFirst 5 column codes:")
        for code in result['column_codes'][:5]:
            print(f"  {code}")
        print(f"\nFirst 5 column descriptions:")
        for desc in result['column_descs'][:5]:
            print(f"  {desc}")
        print(f"\nFirst data row (year {result['pivot_rows'][0]['year']}):")
        row = result['pivot_rows'][0]
        non_blank = {k: v for k, v in row.items() if k != 'year' and v is not None}
        print(f"  Non-blank values: {len(non_blank)}")
        for code, val in list(non_blank.items())[:5]:
            print(f"    {code} = {val}")
    else:
        print("Parsing failed — check logs.")


if __name__ == '__main__':
    main()
