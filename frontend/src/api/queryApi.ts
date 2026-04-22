/**
 * queryApi.ts — API calls for query execution.
 */

import apiClient from "./client";
import type { QueryPayload, QueryPreview, QueryResult } from "../types/query.types";

export async function previewQuery(payload: QueryPayload): Promise<QueryPreview> {
  const response = await apiClient.post<QueryPreview>("/query/preview", payload);
  return response.data;
}

export async function executeQuery(payload: QueryPayload): Promise<QueryResult> {
  const response = await apiClient.post<QueryResult>("/query", payload);
  return response.data;
}
