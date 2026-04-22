/**
 * connection.types.ts â€” Shared connection interfaces for local DuckDB and Marcadose.
 */

import type { TableMetadata } from "./schema.types";

export type QueryEngine = "duckdb" | "oracle";

export interface ConnectionRequest {
  db_path: string;
}

export interface ConnectionResponse {
  status: "connected" | "error";
  db_path: string;
  tables_count: number;
  message: string;
}

export interface OracleConnectionRequest {
  host: string;
  port: number;
  sid: string;
  username: string;
  password: string;
}

export interface OracleConnectionResponse {
  status: "connected" | "error";
  tables_count: number;
  message: string;
  schema_name: string;
}

export interface MarcadoseCredentials {
  host: string;
  port: string;
  sid: string;
  username: string;
  password: string;
}

export interface DuckdbConnectionState {
  dbPath: string;
  isConnected: boolean;
  tables: TableMetadata[];
}

export interface MarcadoseConnectionState {
  credentials: MarcadoseCredentials;
  isConfigured: boolean;
  isConnected: boolean;
  tables: TableMetadata[];
  schemaName: string;
}
