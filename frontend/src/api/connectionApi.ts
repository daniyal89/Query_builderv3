/**
 * connectionApi.ts — API calls for DuckDB connection management.
 */

import apiClient from "./client";
import type { ConnectionRequest, ConnectionResponse } from "../types/connection.types";

export async function connect(payload: ConnectionRequest): Promise<ConnectionResponse> {
  const response = await apiClient.post<ConnectionResponse>("/duckdb/connect", payload);
  return response.data;
}
