import apiClient from "./client";

export type MonthlyRunJobStatus = "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled";
export type MonthlyRunStepStatus = "pending" | "skipped" | "running" | "completed" | "failed" | "cancelled";
export type MonthlyRunOutcome = "completed" | "not_available_yet" | "partial" | "failed" | "cancelled";
/** Where the month's CSVs come from: the FTP server (then uploaded to Drive), or Drive itself when someone already uploaded it. */
export type MasterSource = "ftp" | "drive";

export interface MonthlyAutomationConfig {
  ftp_host: string;
  ftp_port: number;
  ftp_remote_template: string;
  discoms: string[];
  csv_root: string;
  parquet_root: string;
  db_path: string;
  object_type: "TABLE" | "VIEW";
  compression: string;
  drive_parent_folder_id: string;
  drive_root_name_template: string;
  drive_max_workers: number;
  ftp_max_workers: number;
  /** This computer's default source. */
  master_source: MasterSource;
}

export interface MonthlyRunPlan {
  default_month: string;
  month: string;
  token: string;
  object_name: string;
  remote_dir: string;
  csv_dir: string;
  csv_glob: string;
  parquet_dir: string;
  drive_root_name: string;
}

export interface MonthlyRunStepState {
  status: MonthlyRunStepStatus;
  message: string;
  job_id?: string | null;
  detail: Record<string, unknown>;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface MonthlyRunStatusResponse {
  job_id: string;
  status: MonthlyRunJobStatus;
  message: string;
  month: string;
  object_name: string;
  outcome?: MonthlyRunOutcome | null;
  source: MasterSource;
  current_step?: string | null;
  steps: Record<string, MonthlyRunStepState>;
  resumed_steps: string[];
  missing_discoms: string[];
  paths: Record<string, string>;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface MonthlyRunMarker {
  month: string;
  exists: boolean;
  steps: Record<string, MonthlyRunStepState>;
  last_job_id?: string | null;
  updated_at?: string | null;
}

export interface MonthlyRunStartResponse {
  job_id: string;
  status: MonthlyRunJobStatus;
  message: string;
  month: string;
  object_name: string;
}

export async function getAutomationConfig(): Promise<MonthlyAutomationConfig> {
  const { data } = await apiClient.get<MonthlyAutomationConfig>("/automation/config");
  return data;
}

export async function saveAutomationConfig(config: MonthlyAutomationConfig): Promise<MonthlyAutomationConfig> {
  const { data } = await apiClient.put<MonthlyAutomationConfig>("/automation/config", config);
  return data;
}

export async function getMonthlyRunPlan(month?: string): Promise<MonthlyRunPlan> {
  const { data } = await apiClient.get<MonthlyRunPlan>("/automation/monthly-run/plan", {
    params: month ? { month } : undefined,
  });
  return data;
}

export async function getMonthlyRunMarker(month?: string): Promise<MonthlyRunMarker> {
  const { data } = await apiClient.get<MonthlyRunMarker>("/automation/monthly-run/marker", {
    params: month ? { month } : undefined,
  });
  return data;
}

export async function getActiveMonthlyRun(): Promise<MonthlyRunStatusResponse | null> {
  const { data } = await apiClient.get<MonthlyRunStatusResponse | null>("/automation/monthly-run/active");
  return data ?? null;
}

export async function startMonthlyRun(payload: {
  month?: string;
  from_scratch?: boolean;
  source?: MasterSource;
}): Promise<MonthlyRunStartResponse> {
  const { data } = await apiClient.post<MonthlyRunStartResponse>("/automation/monthly-run/start", payload);
  return data;
}

export async function getMonthlyRunStatus(jobId: string): Promise<MonthlyRunStatusResponse> {
  const { data } = await apiClient.get<MonthlyRunStatusResponse>(`/automation/monthly-run/status/${jobId}`);
  return data;
}

export async function stopMonthlyRun(jobId: string): Promise<MonthlyRunStatusResponse> {
  const { data } = await apiClient.post<MonthlyRunStatusResponse>(`/automation/monthly-run/stop/${jobId}`, {});
  return data;
}
