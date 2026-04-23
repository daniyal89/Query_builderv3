import apiClient from "./client";
import type { FTPDownloadRequest, FTPDownloadResponse } from "../types/ftp.types";

export async function startFtpDownload(payload: FTPDownloadRequest): Promise<FTPDownloadResponse> {
  const response = await apiClient.post<FTPDownloadResponse>("/ftp-download", payload, {
    timeout: 0,
  });
  return response.data;
}
