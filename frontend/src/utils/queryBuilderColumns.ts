import type { TableMetadata } from "../types/schema.types";
import type { JoinClause, QueryColumnOption } from "../types/query.types";

export function buildColumnKey(tableName: string, columnName: string): string {
  return `${tableName}.${columnName}`;
}

export function getReferencedTable(columnRef: string): string | null {
  const separatorIndex = columnRef.lastIndexOf(".");
  if (separatorIndex <= 0) {
    return null;
  }
  return columnRef.slice(0, separatorIndex);
}

export function buildColumnOptionsForTable(table?: TableMetadata): QueryColumnOption[] {
  if (!table) {
    return [];
  }

  return table.columns.map((column) => ({
    key: buildColumnKey(table.table_name, column.name),
    label: `${table.table_name}.${column.name}`,
    tableName: table.table_name,
    columnName: column.name,
    dtype: column.dtype,
    nullable: column.nullable,
  }));
}

export function buildColumnOptionsForQuery(
  baseTableName: string,
  joins: JoinClause[],
  tables: TableMetadata[]
): QueryColumnOption[] {
  if (!baseTableName) {
    return [];
  }

  const tableMap = new Map(tables.map((table) => [table.table_name, table]));
  const orderedTableNames = [
    baseTableName,
    ...joins.map((join) => join.table).filter((tableName) => tableName.trim() !== ""),
  ];

  const seen = new Set<string>();
  const options: QueryColumnOption[] = [];

  orderedTableNames.forEach((tableName) => {
    if (seen.has(tableName)) {
      return;
    }
    seen.add(tableName);
    options.push(...buildColumnOptionsForTable(tableMap.get(tableName)));
  });

  return options;
}
