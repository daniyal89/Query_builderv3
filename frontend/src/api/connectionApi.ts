/**
 * connectionApi.ts â€” API calls for local DuckDB and Marcadose connections.
 */

import apiClient from "./client";
import type {
  ConnectionRequest,
  ConnectionResponse,
  OracleConnectionRequest,
  OracleConnectionResponse,
} from "../types/connection.types";

export async function connectDuckdb(payload: ConnectionRequest): Promise<ConnectionResponse> {
  const response = await apiClient.post<ConnectionResponse>("/duckdb/connect", payload);
  return response.data;
}

export async function connectOracle(payload: OracleConnectionRequest): Promise<OracleConnectionResponse> {
  const response = await apiClient.post<OracleConnectionResponse>("/oracle/connect", payload, {
    timeout: 120_000,
  });
  return response.data;
}
