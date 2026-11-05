import apiClient from "./client";
import type {
  FTPDownloadRequest,
  FTPDownloadStartResponse,
  FTPDownloadStatusResponse,
} from "../types/ftp.types";

export async function startFtpDownload(payload: FTPDownloadRequest): Promise<FTPDownloadStartResponse> {
  const response = await apiClient.post<FTPDownloadStartResponse>("/ftp-download/start", payload, {
    timeout: 7_200_000,
  });
  return response.data;
}

export async function getFtpDownloadStatus(jobId: string): Promise<FTPDownloadStatusResponse> {
  const response = await apiClient.get<FTPDownloadStatusResponse>(`/ftp-download/status/${jobId}`, {
    timeout: 7_200_000,
  });
  return response.data;
}


export async function stopFtpDownload(jobId: string): Promise<FTPDownloadStatusResponse> {
  const response = await apiClient.post<FTPDownloadStatusResponse>(`/ftp-download/stop/${jobId}`, {}, {
    timeout: 7_200_000,
  });
  return response.data;
}

export interface FTPProfilesSummary {
  configured: boolean;
  path: string;
  host?: string | null;
  port?: number | null;
  profiles: { name: string; username: string }[];
}

/** Which profiles have a server-side password. Never returns a password. */
export async function getFtpProfiles(): Promise<FTPProfilesSummary> {
  const response = await apiClient.get<FTPProfilesSummary>("/ftp-download/profiles");
  return response.data;
}

export interface FTPOutputRootSetting {
  /** What this computer has saved, if anything. */
  saved: string | null;
  /** What the page should offer: the saved value, else a derived fallback. */
  effective: string | null;
}

export interface FTPDownloadSettings {
  path: string;
  output_roots: Record<string, FTPOutputRootSetting>;
}

/** Per-computer defaults for the FTP Download page (stored beside the backend). */
export async function getFtpDownloadSettings(): Promise<FTPDownloadSettings> {
  const response = await apiClient.get<FTPDownloadSettings>("/ftp-download/settings");
  return response.data;
}

/** Remember output roots as this computer's defaults. Kinds left out keep their value. */
export async function saveFtpDownloadSettings(outputRoots: Record<string, string>): Promise<FTPDownloadSettings> {
  const response = await apiClient.put<FTPDownloadSettings>("/ftp-download/settings", { output_roots: outputRoots });
  return response.data;
}
