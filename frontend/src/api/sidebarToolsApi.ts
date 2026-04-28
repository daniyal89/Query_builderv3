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
}

export interface SidebarToolResponse {
  status: string;
  message: string;
  output_path?: string;
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
  current_file?: string | null;
  output_path?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export async function runBuildDuckDb(payload: BuildDuckDbPayload): Promise<SidebarToolResponse> {
  const { data } = await apiClient.post<SidebarToolResponse>("/sidebar-tools/build-duckdb", payload);
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
  const { data } = await apiClient.get<CsvParquetJobStatusResponse>(`/sidebar-tools/csv-to-parquet/status/${jobId}`);
  return data;
}

export async function stopCsvToParquetJob(jobId: string): Promise<CsvParquetJobStatusResponse> {
  const { data } = await apiClient.post<CsvParquetJobStatusResponse>(`/sidebar-tools/csv-to-parquet/stop/${jobId}`);
  return data;
}
