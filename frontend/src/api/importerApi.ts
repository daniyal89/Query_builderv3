/**
 * importerApi.ts — API calls for the CSV upload and import workflow.
 */

import apiClient from "./client";
import type { CSVMappingPayload, ImportResult } from "../types/importer.types";

/** POST /api/parse-csv — Upload a CSV file and get headers + preview. */
export async function uploadCSV(file: File): Promise<{file_id: string, headers: string[], preview: string[][]}> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post("/parse-csv", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

/** POST /api/import-csv — Submit finalized column mappings for import. */
export async function submitMapping(payload: CSVMappingPayload): Promise<ImportResult> {
  const response = await apiClient.post("/import-csv", payload);
  return response.data;
}
