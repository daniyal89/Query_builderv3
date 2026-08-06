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
const LONG_RUNNING_TIMEOUT_MS = 0; // No timeout

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

export interface MergeProgressEvent {
  event: "progress";
  stage: string;
  detail: string;
  current: number;
  total: number;
}

/** Absolute URL for raw `fetch` calls — relative paths are rejected outside a browser. */
function apiUrl(path: string): string {
  const origin = typeof window !== "undefined" ? window.location?.origin : undefined;
  return origin ? new URL(path, origin).toString() : path;
}

export async function mergeFolderWithProgress(
  payload: FolderMergeRequest,
  onProgress?: (event: MergeProgressEvent) => void,
): Promise<FolderMergeResponse> {
  const response = await fetch(apiUrl("/api/merge-folder"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: "Merge failed" }));
    throw new Error(errorBody.detail || `Merge failed with status ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response stream available");

  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: FolderMergeResponse | null = null;
  let errorMsg: string | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE messages from buffer
    const lines = buffer.split("\n");
    buffer = lines.pop() || ""; // Keep incomplete last line in buffer

    let currentEventType = "";
    let currentData = "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEventType = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        currentData = line.slice(6);
      } else if (line === "" && currentData) {
        // End of an SSE message
        try {
          const parsed = JSON.parse(currentData);
          if (currentEventType === "progress" && onProgress) {
            onProgress(parsed as MergeProgressEvent);
          } else if (currentEventType === "result") {
            finalResult = parsed.data as FolderMergeResponse;
          } else if (currentEventType === "error") {
            errorMsg = parsed.detail || "Merge failed";
          }
        } catch {
          // Ignore malformed JSON
        }
        currentEventType = "";
        currentData = "";
      }
    }
  }

  if (errorMsg) throw new Error(errorMsg);
  if (!finalResult) throw new Error("Merge completed but no result was received");

  return finalResult;
}

/** Backward-compatible wrapper (no progress). */
export async function mergeFolder(payload: FolderMergeRequest): Promise<FolderMergeResponse> {
  return mergeFolderWithProgress(payload);
}

export async function enrichData(
  dbPath: string,
  masterTable: string,
  fetchColumns: string[],
  joinKeys: JoinKeyMapping[],
  outputFormat: "xlsx" | "csv",
  file: File,
  signal?: AbortSignal
): Promise<{ blob: Blob; headers: Record<string, string> }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("db_path", dbPath);
  formData.append("master_table", masterTable);
  formData.append("fetch_columns", JSON.stringify(fetchColumns));
  formData.append("join_keys", JSON.stringify(joinKeys));
  formData.append("output_format", outputFormat);

  const response = await apiClient.post("/enrich-data", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    responseType: "blob",
    timeout: LONG_RUNNING_TIMEOUT_MS,
    signal,
  });

  return {
    blob: response.data as Blob,
    headers: response.headers as Record<string, string>,
  };
}
