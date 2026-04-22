/**
 * connection.types.ts — TypeScript interfaces for the DuckDB connection workflow.
 *
 * Mirrors the backend's ConnectionRequest / ConnectionResponse Pydantic models.
 */

/** Payload sent to POST /api/duckdb/connect. */
export interface ConnectionRequest {
  /** Absolute filesystem path to the target .duckdb file. */
  db_path: string;
}

/** Response from a connection attempt. */
export interface ConnectionResponse {
  /** Connection outcome: 'connected' or 'error'. */
  status: "connected" | "error";
  /** Echo of the resolved database path. */
  db_path: string;
  /** Number of user tables found in the database. */
  tables_count: number;
  /** Human-readable status or error message. */
  message: string;
}
