/**
 * mergeApi.ts — API calls for the multi-sheet merge and enrichment workflow.
 */

import apiClient from "./client";
import type {
  UploadSheetsResponse,
  ConflictResolutionMap,
  MergeSheetsResponse
} from "../types/merge.types";

/**
 * POST /api/upload-sheets
 * Uploads multiple Excel/CSV files/sheets to the backend for initial column detection.
 */
export async function uploadSheets(files: File[]): Promise<UploadSheetsResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });

  const response = await apiClient.post<UploadSheetsResponse>(
    "/upload-sheets",
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );
  return response.data;
}

/**
 * POST /api/merge-sheets
 * Submits the resolved conflict mappings and receives the merged dataset context.
 */
export async function mergeSheets(payload: ConflictResolutionMap): Promise<MergeSheetsResponse> {
  const response = await apiClient.post<MergeSheetsResponse>("/merge-sheets", payload);
  return response.data;
}

/**
 * POST /api/enrich-data
 * Joins the merged dataset with the Master Table and returns a blob stream.
 */
export async function enrichData(
  dbPath: string,
  fetchColumn: string,
  compositeKey: string,
  file: File
): Promise<{ blob: Blob; headers: any }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("db_path", dbPath);
  formData.append("fetch_column", fetchColumn);
  formData.append("composite_key", compositeKey);

  const response = await apiClient.post("/enrich-data", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    responseType: "blob",
  });

  return {
    blob: response.data,
    headers: response.headers,
  };
}

