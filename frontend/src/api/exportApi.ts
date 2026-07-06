/**
 * exportApi.ts — API calls for the server-side large CSV export background job.
 */

import apiClient from "./client";
import type { QueryPayload } from "../types/query.types";

export interface ExportCsvPayload {
  payload: QueryPayload;
  output_path: string;
}

export interface ExportCsvJobStartResponse {
  job_id: string;
  status: string;
  message: string;
  output_path: string;
}

export interface ExportCsvJobStatusResponse {
  job_id: string;
  status: string;
  message: string;
  output_path: string | null;
  rows_written: number;
  started_at: string | null;
  finished_at: string | null;
  last_error: string | null;
}

/**
 * Start a background CSV export job.
 */
export async function startExportCsv(payload: ExportCsvPayload): Promise<ExportCsvJobStartResponse> {
  const { data } = await apiClient.post<ExportCsvJobStartResponse>("/query/export-csv/start", payload);
  return data;
}

/**
 * Poll the status of a running CSV export job.
 */
export async function getExportCsvStatus(jobId: string): Promise<ExportCsvJobStatusResponse> {
  const { data } = await apiClient.get<ExportCsvJobStatusResponse>(`/query/export-csv/status/${jobId}`);
  return data;
}

/**
 * Cancel a running CSV export job.
 */
export async function cancelExportCsv(jobId: string): Promise<ExportCsvJobStatusResponse> {
  const { data } = await apiClient.post<ExportCsvJobStatusResponse>(`/query/export-csv/cancel/${jobId}`);
  return data;
}
