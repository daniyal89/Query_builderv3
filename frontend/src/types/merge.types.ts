/**
 * merge.types.ts - TypeScript interfaces for merge and enrichment flows.
 */

export type OutputFormat = "xlsx" | "csv";

export interface JoinKeyMapping {
  fileColumn: string;
  tableColumn: string;
}

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
  join_keys: JoinKeyMapping[];
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
  step: "upload" | "enrich" | "download";
  uploadResult: UploadSheetsResponse | null;
  enrichResult: EnrichmentResponse | null;
  isLoading: boolean;
  error: string | null;
  uploadedFile?: File | null;
}
