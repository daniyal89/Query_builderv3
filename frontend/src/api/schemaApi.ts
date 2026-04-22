/**
 * schemaApi.ts — API calls for DuckDB schema introspection.
 */

import apiClient from "./client";
import type { TableMetadata, ColumnDetail } from "../types/schema.types";

export async function getTables(): Promise<TableMetadata[]> {
  const response = await apiClient.get<TableMetadata[]>("/tables");
  return response.data;
}

export async function getColumns(tableName: string): Promise<ColumnDetail[]> {
  const response = await apiClient.get<ColumnDetail[]>(`/tables/${tableName}/columns`);
  return response.data;
}
