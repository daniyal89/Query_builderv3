import apiClient from "./client";

export interface AlterDbJoinPayload {
  db_path: string;
  table_name: string;
  new_column_name: string;
  column_type: string;
  file_path: string;
  join_master_col: string;
  join_file_col: string;
  value_file_col: string;
}

export interface AlterDbDerivedPayload {
  db_path: string;
  table_name: string;
  new_column_name: string;
  column_type: string;
  sql_formula: string;
}

export interface AlterDbDropPayload {
  db_path: string;
  table_name: string;
  column_name: string;
}

export interface AlterDbJobStatusResponse {
  job_id: string;
  status: "queued" | "running" | "cancelling" | "cancelled" | "completed" | "failed";
  message: string;
  progress_percent: number;
  started_at?: string | null;
  finished_at?: string | null;
}

export async function startAlterDbJoin(payload: AlterDbJoinPayload): Promise<AlterDbJobStatusResponse> {
  const { data } = await apiClient.post<AlterDbJobStatusResponse>("/alter-db/join/start", payload);
  return data;
}

export async function startAlterDbDerived(payload: AlterDbDerivedPayload): Promise<AlterDbJobStatusResponse> {
  const { data } = await apiClient.post<AlterDbJobStatusResponse>("/alter-db/derived/start", payload);
  return data;
}

export async function startAlterDbDrop(payload: AlterDbDropPayload): Promise<AlterDbJobStatusResponse> {
  const { data } = await apiClient.post<AlterDbJobStatusResponse>("/alter-db/drop/start", payload);
  return data;
}

export async function getAlterDbStatus(jobId: string): Promise<AlterDbJobStatusResponse> {
  const { data } = await apiClient.get<AlterDbJobStatusResponse>(`/alter-db/status/${jobId}`);
  return data;
}

export async function stopAlterDbJob(jobId: string): Promise<AlterDbJobStatusResponse> {
  const { data } = await apiClient.post<AlterDbJobStatusResponse>(`/alter-db/stop/${jobId}`);
  return data;
}

export async function getAlterDbTables(dbPath: string): Promise<string[]> {
  const { data } = await apiClient.get<string[]>("/alter-db/metadata/tables", {
    params: { db_path: dbPath },
  });
  return data;
}

export async function getAlterDbColumns(dbPath: string, tableName: string): Promise<string[]> {
  const { data } = await apiClient.get<string[]>("/alter-db/metadata/columns", {
    params: { db_path: dbPath, table_name: tableName },
  });
  return data;
}
