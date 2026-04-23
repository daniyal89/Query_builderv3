/**
 * merge.types.ts - TypeScript interfaces for merge and enrichment flows.
 */

export type CompositeKey = "Acc_id+DISCOM" | "Acc_id+DIV_CODE";
export type OutputFormat = "xlsx" | "csv";

export interface DetectedColumn {
  name: string;
  source_file: string;
  source_sheet: string;
  sample_values: string[];
}

export interface UploadSheetsResponse {
  file_ids: string[];
  detected_columns: DetectedColumn[];
  conflicts: string[];
}

export interface ColumnResolution {
  source_file: string;
  source_column: string;
  action: "map" | "ignore";
  standard_name?: string;
}

export interface ConflictResolutionMap {
  file_ids: string[];
  resolutions: ColumnResolution[];
  composite_key: CompositeKey;
}

export interface MergeSheetsResponse {
  merged_columns: string[];
  total_rows: number;
  preview_rows: Record<string, unknown>[];
  merge_id: string;
}

export interface FolderMergeRequest {
  source_folder: string;
  output_path: string;
  include_subfolders: boolean;
}

export interface FolderMergeResponse {
  output_path: string;
  output_format: OutputFormat;
  total_files: number;
  merged_items: number;
  total_rows: number;
  total_columns: number;
}

export interface EnrichmentRequest {
  merge_id: string;
  master_table: string;
  composite_key: CompositeKey;
  fetch_columns: string[];
  output_format: OutputFormat;
}

export interface EnrichmentResponse {
  download_url: string;
  total_rows: number;
  matched_rows: number;
  unmatched_rows: number;
  output_format: OutputFormat;
}

export interface MergeWizardState {
  step: "upload" | "resolve" | "enrich" | "download";
  uploadResult: UploadSheetsResponse | null;
  resolutions: ColumnResolution[];
  compositeKey: CompositeKey | null;
  mergeResult: MergeSheetsResponse | null;
  enrichResult: EnrichmentResponse | null;
  isLoading: boolean;
  error: string | null;
  uploadedFile?: File | null;
}
