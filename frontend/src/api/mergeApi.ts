/**
 * mergeApi.ts - API calls for the multi-sheet merge and enrichment workflow.
 */

import apiClient from "./client";
import type {
  ConflictResolutionMap,
  MergeSheetsResponse,
  UploadSheetsResponse,
} from "../types/merge.types";

export async function uploadSheets(files: File[]): Promise<UploadSheetsResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });

  const response = await apiClient.post<UploadSheetsResponse>("/upload-sheets", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export async function mergeSheets(payload: ConflictResolutionMap): Promise<MergeSheetsResponse> {
  const response = await apiClient.post<MergeSheetsResponse>("/merge-sheets", payload);
  return response.data;
}

export async function enrichData(
  dbPath: string,
  fetchColumns: string[],
  compositeKey: string,
  file: File,
  mappedAcctIdCol: string,
  mappedSecondaryCol: string
): Promise<{ blob: Blob; headers: any }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("db_path", dbPath);
  formData.append("fetch_columns", JSON.stringify(fetchColumns));
  formData.append("composite_key", compositeKey);
  formData.append("mapped_acct_id_col", mappedAcctIdCol);
  formData.append("mapped_secondary_col", mappedSecondaryCol);

  const response = await apiClient.post("/enrich-data", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    responseType: "blob",
  });

  return {
    blob: response.data,
    headers: response.headers,
  };
}
