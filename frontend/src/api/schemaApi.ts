/**
 * schemaApi.ts â€” API calls for engine-specific schema introspection.
 */

import apiClient from "./client";
import type { QueryEngine } from "../types/connection.types";
import type { ColumnDetail, TableMetadata } from "../types/schema.types";

function getTablesPath(engine: QueryEngine): string {
  return engine === "oracle" ? "/oracle/tables" : "/tables";
}

function getColumnsPath(engine: QueryEngine, tableName: string): string {
  return engine === "oracle" ? `/oracle/tables/${tableName}/columns` : `/tables/${tableName}/columns`;
}

export async function getTables(engine: QueryEngine = "duckdb"): Promise<TableMetadata[]> {
  const response = await apiClient.get<TableMetadata[]>(getTablesPath(engine), {
    timeout: engine === "oracle" ? 120_000 : undefined,
  });
  return response.data;
}

export async function getColumns(tableName: string, engine: QueryEngine = "duckdb"): Promise<ColumnDetail[]> {
  const response = await apiClient.get<ColumnDetail[]>(getColumnsPath(engine, tableName), {
    timeout: engine === "oracle" ? 120_000 : undefined,
  });
  return response.data;
}

export async function deleteLocalObject(objectName: string): Promise<{ status: string; message: string }> {
  const response = await apiClient.delete<{ status: string; message: string }>(
    `/duckdb/objects/${encodeURIComponent(objectName)}`,
  );
  return response.data;
}

const SYSTEM_API_BASE = "/api/system";

type SystemPathResponse = {
  path?: string | null;
};

async function postForPath(
  endpoint: string,
  payload: Record<string, unknown> = {},
): Promise<string | null> {
  const response = await fetch(`${SYSTEM_API_BASE}${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed for ${endpoint}`);
  }

  const data = (await response.json()) as SystemPathResponse;
  return data.path ?? null;
}

export async function pickSystemFile(): Promise<string | null> {
  return postForPath("/pick-file");
}

export async function pickSystemFolder(): Promise<string | null> {
  return postForPath("/pick-folder");
}

export async function pickSystemSavePath(
  defaultFileName = "merged_output.csv",
): Promise<string | null> {
  return postForPath("/pick-save-path", {
    default_file_name: defaultFileName,
  });
}
