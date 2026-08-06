/**
 * skipReasons.ts - Shared classification of the pipeline's skip/failure reasons.
 *
 * Two surfaces render these (`SkippedFiles` and `RowReconciliation`), and they
 * disagreed: one showed an empty division file as a benign grey skip while the
 * other counted it among "N file(s) failed" in a red card. One source of truth.
 *
 * `EMPTY_SOURCE_REASONS` mirrors the backend set of the same name in
 * `sidebar_tools_service.py` — keep them together.
 */

/** The source held zero rows. Nothing was lost, because there was nothing there. */
export const EMPTY_SOURCE_REASONS: ReadonlySet<string> = new Set([
  "EMPTY_FILE",
  "EMPTY_DATAFRAME",
  "EMPTY_DATA_ERROR",
]);

/** Reasons that mean "nothing to convert", as opposed to "something went wrong". */
export const BENIGN_REASONS: ReadonlySet<string> = new Set([
  ...EMPTY_SOURCE_REASONS,
  "ALREADY_EXISTS",
]);

export const REASON_HELP: Record<string, string> = {
  ALREADY_EXISTS: "Parquet already present and valid — reused, not reconverted.",
  EMPTY_FILE: "Source contains zero rows. Nothing to convert; no data lost.",
  EMPTY_DATAFRAME: "Source has no readable columns or rows. Nothing to convert.",
  EMPTY_DATA_ERROR: "Source could not be parsed as CSV at all — it holds no data.",
  CORRUPT_PARQUET_REBUILT: "Previous output was unreadable and was rebuilt.",
  MISSING_ACCT_ID_COLUMN: "No ACCT_ID column, so no row can be identified. Check the export.",
  ALL_ROWS_REJECTED_ACCT_ID: "Every row had an unusable ACCT_ID. See the quarantine file.",
  NOT_GZIP_HEADER: "Named .gz but is neither gzip nor readable text.",
  TRUNCATED_EOF: "Compressed stream ends mid-file — the download is incomplete.",
};
