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

export async function runBuildDuckDb(payload: BuildDuckDbPayload): Promise<SidebarToolResponse> {
  const { data } = await apiClient.post<SidebarToolResponse>("/sidebar-tools/build-duckdb", payload);
  return data;
}

export async function runCsvToParquet(payload: CsvToParquetPayload): Promise<SidebarToolResponse> {
  const { data } = await apiClient.post<SidebarToolResponse>("/sidebar-tools/csv-to-parquet", payload);
  return data;
}
