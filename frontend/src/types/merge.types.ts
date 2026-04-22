/**
 * merge.types.ts — TypeScript interfaces for the multi-sheet merge and enrichment flow.
 *
 * Mirrors the backend's merge.py Pydantic models. Covers the three-phase
 * pipeline defined in HANDOVER.md §8 (Strict Business Rules):
 *   1. Upload Sheets  → detect columns
 *   2. Merge Sheets   → resolve conflicts via ConflictResolutionMap
 *   3. Enrich Data    → join against Master Table, download result
 */

// ─────────────── Shared ───────────────

/** The two supported composite key strategies for Master Table matching. */
export type CompositeKey = "Acc_id+DISCOM" | "Acc_id+DIV_CODE";

/** Output format for the enriched download. */
export type OutputFormat = "xlsx" | "csv";


// ─────────────── Phase 1: Upload Sheets ───────────────

/** A column discovered in an uploaded sheet. */
export interface DetectedColumn {
  /** Original column header as it appears in the file. */
  name: string;
  /** Filename this column was detected in. */
  source_file: string;
  /** Sheet/tab name within the file. */
  source_sheet: string;
  /** Up to 5 sample values from this column for user preview. */
  sample_values: string[];
}

/** Response from POST /api/upload-sheets. */
export interface UploadSheetsResponse {
  /** Temporary identifiers for each uploaded file. */
  file_ids: string[];
  /** Flat list of every column found across all uploaded sheets. */
  detected_columns: DetectedColumn[];
  /** Column names that appear in multiple files with potentially different meanings. */
  conflicts: string[];
}


// ─────────────── Phase 2: Merge Sheets (Conflict Resolution) ───────────────

/** Resolution directive for a single uploaded column. */
export interface ColumnResolution {
  /** File the column originates from. */
  source_file: string;
  /** Original column name in the source file. */
  source_column: string;
  /** 'map' = rename to standard_name; 'ignore' = drop this column. */
  action: "map" | "ignore";
  /** Canonical column name to map to. Required when action='map'. */
  standard_name?: string;
}

/**
 * Full conflict resolution payload submitted by the user.
 *
 * Maps every uploaded column to either a standard name or marks it
 * as ignored. The composite key columns must be present in the
 * resolved output for the enrichment phase to work.
 */
export interface ConflictResolutionMap {
  /** File identifiers from the upload step. */
  file_ids: string[];
  /** One resolution entry per detected column across all files. */
  resolutions: ColumnResolution[];
  /** Which composite key to use for matching against the Master Table. */
  composite_key: CompositeKey;
}

/** Response from POST /api/merge-sheets. */
export interface MergeSheetsResponse {
  /** Final list of standardized column names in the merged dataset. */
  merged_columns: string[];
  /** Total row count of the merged dataset. */
  total_rows: number;
  /** First N rows of the merged data for user verification. */
  preview_rows: Record<string, unknown>[];
  /** Identifier for the merged dataset, used in the enrichment step. */
  merge_id: string;
}


// ─────────────── Phase 3: Enrich Data ───────────────

/** Payload for POST /api/enrich-data. */
export interface EnrichmentRequest {
  /** Identifier of the merged dataset from the merge step. */
  merge_id: string;
  /** Name of the DuckDB Master Table to join against. */
  master_table: string;
  /** Which composite key to use for the join. */
  composite_key: CompositeKey;
  /** Column names from the Master Table to fetch and append. */
  fetch_columns: string[];
  /** Desired format for the downloadable output file. */
  output_format: OutputFormat;
}

/** Response from POST /api/enrich-data. */
export interface EnrichmentResponse {
  /** Relative URL to download the enriched output file. */
  download_url: string;
  /** Total rows in the output file. */
  total_rows: number;
  /** Rows that found a match in the Master Table. */
  matched_rows: number;
  /** Rows with no Master Table match. */
  unmatched_rows: number;
  /** Format of the output file. */
  output_format: OutputFormat;
}


// ─────────────── UI State ───────────────

/** Tracks the overall state of the merge/enrichment wizard in the UI. */
export interface MergeWizardState {
  /** Current step in the wizard. */
  step: "upload" | "resolve" | "enrich" | "download";
  /** Detected columns after upload. */
  uploadResult: UploadSheetsResponse | null;
  /** User-configured conflict resolutions. */
  resolutions: ColumnResolution[];
  /** Selected composite key. */
  compositeKey: CompositeKey | null;
  /** Merge result after conflict resolution. */
  mergeResult: MergeSheetsResponse | null;
  /** Enrichment result after join. */
  enrichResult: EnrichmentResponse | null;
  /** Whether an operation is in progress. */
  isLoading: boolean;
  /** Error message or null. */
  error: string | null;
}
