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
