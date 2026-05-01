import apiClient from "./client";
import type {
  DriveAuthStatusResponse,
  DriveDownloadRequest,
  DriveJobStartResponse,
  DriveJobStatusResponse,
  DriveUploadRequest,
} from "../types/drive.types";

export async function startDriveUpload(payload: DriveUploadRequest): Promise<DriveJobStartResponse> {
  const response = await apiClient.post<DriveJobStartResponse>("/drive/upload/start", payload, {
    timeout: 30_000,
  });
  return response.data;
}

export async function startDriveDownload(payload: DriveDownloadRequest): Promise<DriveJobStartResponse> {
  const response = await apiClient.post<DriveJobStartResponse>("/drive/download/start", payload, {
    timeout: 30_000,
  });
  return response.data;
}

export async function getDriveJobStatus(jobId: string): Promise<DriveJobStatusResponse> {
  const response = await apiClient.get<DriveJobStatusResponse>(`/drive/status/${jobId}`, {
    timeout: 30_000,
  });
  return response.data;
}

export async function getDriveAuthStatus(): Promise<DriveAuthStatusResponse> {
  const response = await apiClient.get<DriveAuthStatusResponse>("/drive/auth/status", {
    timeout: 30_000,
  });
  return response.data;
}

export async function loginGoogleDrive(): Promise<DriveAuthStatusResponse> {
  const response = await apiClient.post<DriveAuthStatusResponse>("/drive/auth/login", {}, {
    timeout: 120_000,
  });
  return response.data;
}

export async function logoutGoogleDrive(): Promise<DriveAuthStatusResponse> {
  const response = await apiClient.post<DriveAuthStatusResponse>("/drive/auth/logout", {}, {
    timeout: 30_000,
  });
  return response.data;
}

export async function stopDriveJob(jobId: string): Promise<DriveJobStatusResponse> {
  const response = await apiClient.post<DriveJobStatusResponse>(`/drive/stop/${jobId}`, {}, {
    timeout: 30_000,
  });
  return response.data;
}
