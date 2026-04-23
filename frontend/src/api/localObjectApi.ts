import apiClient from "./client";
import type { FileObjectRequest, FileObjectResponse } from "../types/localObject.types";

export async function createLocalFileObject(payload: FileObjectRequest): Promise<FileObjectResponse> {
  const response = await apiClient.post<FileObjectResponse>("/duckdb/file-object", payload, {
    timeout: 120_000,
  });
  return response.data;
}
