/**
 * importer.types.ts — TypeScript interfaces for the CSV import workflow.
 *
 * Mirrors the backend's CSVMappingPayload, ColumnMapping, and ImportResult
 * Pydantic models. Also defines UI-specific CSVPreview for the staging view.
 */

/** Maps a single CSV column to a target DuckDB column. */
export interface ColumnMapping {
  /** Header name from the uploaded CSV file. */
  csvColumn: string;
  /** Target column name in the DuckDB table. */
  dbColumn: string;
  /** If true, this CSV column is ignored during import. */
  skip: boolean;
}

/** Parsed CSV preview data shown to the user before import. */
export interface CSVPreview {
  /** Original file name. */
  fileName: string;
  /** Detected CSV headers. */
  headers: string[];
  /** First N rows of parsed data for visual verification. */
  rows: string[][];
  /** Total number of data rows in the file (excluding header). */
  totalRows: number;
}

/** Payload submitted to POST /api/upload-csv for finalized import. */
export interface CSVMappingPayload {
  /** Temporary file identifier from the initial upload step. */
  fileId: string;
  /** DuckDB table to insert data into. */
  targetTable: string;
  /** Ordered list of column mapping directives. */
  columnMap: ColumnMapping[];
  /** If true, auto-create the target table from CSV schema. */
  createTableIfMissing: boolean;
}

/** Outcome summary of a CSV import operation. */
export interface ImportResult {
  /** Number of rows successfully inserted. */
  rowsInserted: number;
  /** Number of rows skipped due to errors. */
  rowsSkipped: number;
  /** Human-readable error messages for failed rows. */
  errors: string[];
  /** Table the data was imported into. */
  targetTable: string;
}

/** Tracks the overall state of the import wizard in the UI. */
export interface ImporterState {
  /** Current step: 'upload' → 'mapping' → 'importing' → 'done'. */
  step: "upload" | "mapping" | "importing" | "done";
  /** CSV preview data after file upload. */
  preview: CSVPreview | null;
  /** User-configured column mappings. */
  mappings: ColumnMapping[];
  /** Import result after completion. */
  result: ImportResult | null;
  /** Whether an operation is in progress. */
  isLoading: boolean;
  /** Error message or null. */
  error: string | null;
}
