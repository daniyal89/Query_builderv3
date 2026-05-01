import type { TableMetadata } from "../types/schema.types";
import type { JoinClause, QueryColumnOption } from "../types/query.types";

export function normalizeJoinAlias(value: string): string {
  const lastSegment = (value || "").trim().split(".").pop() || "";
  const cleaned = lastSegment.replace(/[^A-Za-z0-9_]/g, "_");
  if (!cleaned) {
    return "";
  }
  return /^[A-Za-z_]/.test(cleaned) ? cleaned : `j_${cleaned}`;
}

export function getJoinReferenceName(join: Pick<JoinClause, "table" | "alias">): string {
  return join.alias.trim() || join.table.trim();
}

export function buildSuggestedJoinAlias(
  tableName: string,
  joins: Array<Pick<JoinClause, "id" | "table" | "alias">>,
  currentJoinId?: string,
  baseTableName?: string,
): string {
  const baseAlias = normalizeJoinAlias(tableName) || "join_ref";
  const usedReferences = new Set<string>();

  if (baseTableName?.trim()) {
    usedReferences.add(baseTableName.trim());
  }

  joins.forEach((join) => {
    if (currentJoinId && join.id === currentJoinId) {
      return;
    }
    const reference = getJoinReferenceName(join);
    if (reference) {
      usedReferences.add(reference);
    }
  });

  let candidate = baseAlias;
  let suffix = 2;

  while (usedReferences.has(candidate)) {
    candidate = `${baseAlias}_${suffix}`;
    suffix += 1;
  }

  return candidate;
}

export function buildColumnKey(referenceName: string, columnName: string): string {
  return `${referenceName}.${columnName}`;
}

export function getReferencedTable(columnRef: string): string | null {
  const separatorIndex = columnRef.lastIndexOf(".");
  if (separatorIndex <= 0) {
    return null;
  }
  return columnRef.slice(0, separatorIndex);
}

export function buildColumnOptionsForTable(table?: TableMetadata, referenceName?: string): QueryColumnOption[] {
  if (!table) {
    return [];
  }

  const resolvedReference = (referenceName || table.table_name).trim();

  return table.columns.map((column) => ({
    key: buildColumnKey(resolvedReference, column.name),
    label: `${resolvedReference}.${column.name}`,
    tableName: resolvedReference,
    sourceTableName: table.table_name,
    referenceName: resolvedReference,
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
  const options: QueryColumnOption[] = [];
  options.push(...buildColumnOptionsForTable(tableMap.get(baseTableName), baseTableName));

  joins
    .filter((join) => join.table.trim() !== "")
    .forEach((join) => {
      options.push(...buildColumnOptionsForTable(tableMap.get(join.table), getJoinReferenceName(join)));
    });

  return options;
}
