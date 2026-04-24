export type DriveAuthMode = "auto" | "oauth" | "service_account";
export type DriveJobStatus = "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled";
export type DriveJobType = "upload" | "download";

export interface DriveAuthConfig {
  mode: DriveAuthMode;
  oauth_client_json_path?: string | null;
  token_json_path?: string | null;
  service_account_json_path?: string | null;
}

export interface DriveUploadRequest {
  auth: DriveAuthConfig;
  local_folder: string;
  parent_folder_id: string;
  root_folder_name?: string | null;
  skip_existing: boolean;
  max_workers: number;
}

export interface DriveDownloadRequest {
  auth: DriveAuthConfig;
  drive_link_or_id: string;
  output_folder: string;
  overwrite_existing: boolean;
  export_google_files: boolean;
}

export interface DriveJobStartResponse {
  job_id: string;
  status: DriveJobStatus;
}

export interface DriveJobStatusResponse {
  job_id: string;
  status: DriveJobStatus;
  job_type: DriveJobType;
  message: string;
  total_items: number;
  processed_items: number;
  uploaded_items: number;
  downloaded_items: number;
  skipped_items: number;
  failed_items: number;
  output_path?: string | null;
  errors: string[];
  started_at?: string | null;
  finished_at?: string | null;
}

export interface DriveAuthStatusResponse {
  configured: boolean;
  token_exists: boolean;
  token_valid: boolean;
  message: string;
}
