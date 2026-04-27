import apiClient from "./client";
import type {
  FileObjectRequest,
  FileObjectResponse,
  FilePreviewRequest,
  FilePreviewResponse,
} from "../types/localObject.types";

export async function createLocalFileObject(payload: FileObjectRequest): Promise<FileObjectResponse> {
  const response = await apiClient.post<FileObjectResponse>("/duckdb/file-object", payload, {
    timeout: 120_000,
  });
  return response.data;
}

export async function previewLocalFileObject(payload: FilePreviewRequest): Promise<FilePreviewResponse> {
  const response = await apiClient.post<FilePreviewResponse>("/duckdb/file-object/preview", payload, {
    timeout: 120_000,
  });
  return response.data;
}
