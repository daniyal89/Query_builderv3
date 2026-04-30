/**
 * mergeApi.ts - API calls for merge workflows.
 */

import apiClient from "./client";
import type {
  FolderMergeRequest,
  FolderMergeResponse,
  JoinKeyMapping,
  UploadSheetsResponse,
} from "../types/merge.types";

const LONG_RUNNING_TIMEOUT_MS = 10 * 60_000;

export async function uploadSheets(files: File[]): Promise<UploadSheetsResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });

  const response = await apiClient.post<UploadSheetsResponse>("/upload-sheets", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
    timeout: LONG_RUNNING_TIMEOUT_MS,
  });
  return response.data;
}

export async function mergeFolder(payload: FolderMergeRequest): Promise<FolderMergeResponse> {
  const response = await apiClient.post<FolderMergeResponse>("/merge-folder", payload, {
    timeout: LONG_RUNNING_TIMEOUT_MS,
  });
  return response.data;
}

export async function enrichData(
  dbPath: string,
  masterTable: string,
  fetchColumns: string[],
  joinKeys: JoinKeyMapping[],
  file: File
): Promise<{ blob: Blob; headers: Record<string, string> }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("db_path", dbPath);
  formData.append("master_table", masterTable);
  formData.append("fetch_columns", JSON.stringify(fetchColumns));
  formData.append("join_keys", JSON.stringify(joinKeys));

  const response = await apiClient.post("/enrich-data", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    responseType: "blob",
    timeout: LONG_RUNNING_TIMEOUT_MS,
  });

  return {
    blob: response.data as Blob,
    headers: response.headers as Record<string, string>,
  };
}
