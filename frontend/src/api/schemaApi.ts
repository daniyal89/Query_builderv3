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
  const response = await apiClient.get<TableMetadata[]>(getTablesPath(engine));
  return response.data;
}

export async function getColumns(tableName: string, engine: QueryEngine = "duckdb"): Promise<ColumnDetail[]> {
  const response = await apiClient.get<ColumnDetail[]>(getColumnsPath(engine, tableName));
  return response.data;
}
