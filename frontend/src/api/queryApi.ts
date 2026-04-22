/**
 * queryApi.ts — API calls for query execution.
 */

import apiClient from "./client";
import type { QueryPayload, QueryResult } from "../types/query.types";

export async function executeQuery(payload: QueryPayload): Promise<QueryResult> {
  const response = await apiClient.post<QueryResult>("/query", payload);
  return response.data;
}
