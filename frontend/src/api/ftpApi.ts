import apiClient from "./client";
import type {
  FTPDownloadRequest,
  FTPDownloadStartResponse,
  FTPDownloadStatusResponse,
} from "../types/ftp.types";

export async function startFtpDownload(payload: FTPDownloadRequest): Promise<FTPDownloadStartResponse> {
  const response = await apiClient.post<FTPDownloadStartResponse>("/ftp-download/start", payload, {
    timeout: 30_000,
  });
  return response.data;
}

export async function getFtpDownloadStatus(jobId: string): Promise<FTPDownloadStatusResponse> {
  const response = await apiClient.get<FTPDownloadStatusResponse>(`/ftp-download/status/${jobId}`, {
    timeout: 30_000,
  });
  return response.data;
}


export async function stopFtpDownload(jobId: string): Promise<FTPDownloadStatusResponse> {
  const response = await apiClient.post<FTPDownloadStatusResponse>(`/ftp-download/stop/${jobId}`, {}, {
    timeout: 30_000,
  });
  return response.data;
}
