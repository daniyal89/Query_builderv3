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

export interface FTPDownloadResponse {
  host: string;
  output_root: string;
  total_profiles: number;
  total_files_found: number;
  total_downloaded_files: number;
  total_skipped_files: number;
  total_failed_files: number;
  profile_results: FTPProfileResult[];
}
