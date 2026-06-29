import apiClient from "./client";

export interface BuildDuckDbPayload {
  db_path: string;
  input_path: string;
  object_name: string;
  object_type: "TABLE" | "VIEW";
  replace: boolean;
  month_label?: string;
}

export interface CsvToParquetPayload {
  input_path: string;
  output_path: string;
  compression: string;
  hir_file?: string;
  supp_mapper_file?: string;
  overwrite_parquet?: boolean;
}

export interface SidebarToolResponse {
  status: string;
  message: string;
  output_path?: string;
}

export interface BuildDuckDbJobStartResponse {
  job_id: string;
  status: "queued" | "running" | "cancelling" | "cancelled" | "completed" | "failed";
  message: string;
}

export interface BuildDuckDbJobStatusResponse {
  job_id: string;
  status: "queued" | "running" | "cancelling" | "cancelled" | "completed" | "failed";
  message: string;
  output_path?: string | null;
  progress_percent: number;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface CsvParquetJobStartResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface CsvParquetJobStatusResponse {
  job_id: string;
  status: "queued" | "running" | "cancelling" | "cancelled" | "completed" | "failed";
  message: string;
  processed_files: number;
  total_files: number;
  skipped_files: number;
  parquet_skipped_details?: string[];
  total_input_rows?: number;
  total_output_rows?: number;
  current_file?: string | null;
  output_path?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export async function runBuildDuckDb(payload: BuildDuckDbPayload): Promise<SidebarToolResponse> {
  const { data } = await apiClient.post<SidebarToolResponse>("/sidebar-tools/build-duckdb", payload);
  return data;
}

export async function startBuildDuckDbJob(payload: BuildDuckDbPayload): Promise<BuildDuckDbJobStartResponse> {
  const { data } = await apiClient.post<BuildDuckDbJobStartResponse>("/sidebar-tools/build-duckdb/start", payload);
  return data;
}

export async function getBuildDuckDbJobStatus(jobId: string): Promise<BuildDuckDbJobStatusResponse> {
  const { data } = await apiClient.get<BuildDuckDbJobStatusResponse>(`/sidebar-tools/build-duckdb/status/${jobId}`, {
    timeout: 120_000,
  });
  return data;
}

export async function stopBuildDuckDbJob(jobId: string): Promise<BuildDuckDbJobStatusResponse> {
  const { data } = await apiClient.post<BuildDuckDbJobStatusResponse>(`/sidebar-tools/build-duckdb/stop/${jobId}`);
  return data;
}

export async function runCsvToParquet(payload: CsvToParquetPayload): Promise<SidebarToolResponse> {
  const { data } = await apiClient.post<SidebarToolResponse>("/sidebar-tools/csv-to-parquet", payload);
  return data;
}

export async function startCsvToParquetJob(payload: CsvToParquetPayload): Promise<CsvParquetJobStartResponse> {
  const { data } = await apiClient.post<CsvParquetJobStartResponse>("/sidebar-tools/csv-to-parquet/start", payload);
  return data;
}

export async function getCsvToParquetJobStatus(jobId: string): Promise<CsvParquetJobStatusResponse> {
  const { data } = await apiClient.get<CsvParquetJobStatusResponse>(`/sidebar-tools/csv-to-parquet/status/${jobId}`, {
    timeout: 120_000,
  });
  return data;
}

export async function stopCsvToParquetJob(jobId: string): Promise<CsvParquetJobStatusResponse> {
  const { data } = await apiClient.post<CsvParquetJobStatusResponse>(`/sidebar-tools/csv-to-parquet/stop/${jobId}`);
  return data;
}

// ────────────── Full Pipeline (CSV→Parquet + Build DuckDB) ──────────────

export interface FullPipelinePayload {
  input_path: string;
  parquet_output_path: string;
  compression: string;
  hir_file?: string;
  supp_mapper_file?: string;
  db_path: string;
  object_name: string;
  object_type: "TABLE" | "VIEW";
  replace: boolean;
  month_label?: string;
  overwrite_parquet?: boolean;
}

export interface FullPipelineStartResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface FullPipelineStatusResponse {
  job_id: string;
  status: "queued" | "running" | "cancelling" | "cancelled" | "completed" | "failed";
  message: string;
  current_phase: string;
  parquet_processed_files: number;
  parquet_total_files: number;
  parquet_skipped_files: number;
  parquet_skipped_details?: string[];
  parquet_current_file?: string | null;
  parquet_output_path?: string | null;
  total_input_rows?: number;
  total_output_rows?: number;
  build_progress_percent: number;
  build_output_path?: string | null;
  overall_progress_percent: number;
  started_at?: string | null;
  finished_at?: string | null;
}

export async function startFullPipeline(payload: FullPipelinePayload): Promise<FullPipelineStartResponse> {
  const { data } = await apiClient.post<FullPipelineStartResponse>("/sidebar-tools/full-pipeline/start", payload);
  return data;
}

export async function getFullPipelineStatus(jobId: string): Promise<FullPipelineStatusResponse> {
  const { data } = await apiClient.get<FullPipelineStatusResponse>(`/sidebar-tools/full-pipeline/status/${jobId}`, {
    timeout: 120_000,
  });
  return data;
}

export async function stopFullPipeline(jobId: string): Promise<FullPipelineStatusResponse> {
  const { data } = await apiClient.post<FullPipelineStatusResponse>(`/sidebar-tools/full-pipeline/stop/${jobId}`);
  return data;
}
