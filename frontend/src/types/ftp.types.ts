export interface FTPDownloadProfile {
  name: string;
  username: string;
  password: string;
  remote_dir: string;
  local_subfolder?: string | null;
}

export interface FTPDownloadRequest {
  host: string;
  port: number;
  output_root: string;
  file_suffix: string;
  max_workers: number;
  max_retries: number;
  retry_delay_seconds: number;
  timeout_seconds: number;
  passive_mode: boolean;
  skip_existing: boolean;
  profiles: FTPDownloadProfile[];
}

export interface FTPProfileResult {
  profile_name: string;
  remote_dir: string;
  local_dir: string;
  found_files: number;
  downloaded_files: number;
  skipped_files: number;
  failed_files: number;
  errors: string[];
}

export interface FTPDownloadStartResponse {
  job_id: string;
  status: "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled";
}

export interface FTPDownloadStatusResponse {
  job_id: string;
  status: "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled";
  host: string;
  output_root: string;
  current_profile?: string | null;
  total_profiles: number;
  total_files_found: number;
  total_downloaded_files: number;
  total_skipped_files: number;
  total_failed_files: number;
  profile_results: FTPProfileResult[];
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}
