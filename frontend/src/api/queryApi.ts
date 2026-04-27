/**
 * queryApi.ts — API calls for query execution.
 */

import apiClient from "./client";
import type { QueryPayload, QueryPreview, QueryResult } from "../types/query.types";

const ORACLE_QUERY_TIMEOUT_MS = 300_000;

export async function previewQuery(payload: QueryPayload): Promise<QueryPreview> {
  const response = await apiClient.post<QueryPreview>("/query/preview", payload, {
    timeout: payload.engine === "oracle" ? ORACLE_QUERY_TIMEOUT_MS : undefined,
  });
  return response.data;
}

export async function executeQuery(payload: QueryPayload): Promise<QueryResult> {
  const response = await apiClient.post<QueryResult>("/query", payload, {
    timeout: payload.engine === "oracle" ? ORACLE_QUERY_TIMEOUT_MS : undefined,
  });
  return response.data;
}
