import type { FilterOperator, QueryColumnOption } from "../types/query.types";

export const NO_VALUE_OPERATORS: FilterOperator[] = ["IS NULL", "IS NOT NULL"];
export const COMMON_OPERATORS: FilterOperator[] = ["=", "!=", "IS NULL", "IS NOT NULL"];
export const TEXT_OPERATORS: FilterOperator[] = [
  "CONTAINS",
  "NOT CONTAINS",
  "STARTS WITH",
  "ENDS WITH",
  "LIKE",
  "NOT LIKE",
  "IN",
  "NOT IN",
];
export const RANGE_OPERATORS: FilterOperator[] = [
  ">",
  "<",
  ">=",
  "<=",
  "BETWEEN",
  "NOT BETWEEN",
  "IN",
  "NOT IN",
];

export function getColumnFamily(dtype?: string, columnName?: string): "text" | "number" | "date" | "boolean" | "other" {
  const normalizedType = dtype?.toUpperCase() ?? "";
  const normalizedName = columnName?.toUpperCase() ?? "";

  if (/(DATE|TIME|TIMESTAMP)/.test(normalizedName)) return "date";

  if (!normalizedType) return "other";
  if (/(DATE|TIME|TIMESTAMP)/.test(normalizedType)) return "date";
  if (/(CHAR|TEXT|STRING|CLOB|VARCHAR|UUID|JSON)/.test(normalizedType)) return "text";
  if (/(INT|DECIMAL|NUMERIC|DOUBLE|FLOAT|REAL|HUGEINT|BIGINT|SMALLINT|TINYINT)/.test(normalizedType)) return "number";
  if (/BOOL/.test(normalizedType)) return "boolean";
  return "other";
}

export function getOperatorsForColumn(column?: QueryColumnOption): FilterOperator[] {
  const family = getColumnFamily(column?.dtype, column?.columnName || column?.label || column?.key);
  if (family === "text") return [...COMMON_OPERATORS, ...TEXT_OPERATORS];
  if (family === "number" || family === "date") return [...COMMON_OPERATORS, ...RANGE_OPERATORS];
  if (family === "boolean") return [...COMMON_OPERATORS, "IN", "NOT IN"];
  return [...COMMON_OPERATORS, ...RANGE_OPERATORS];
}

export function getValuePlaceholder(operator: FilterOperator): string {
  if (operator === "IN" || operator === "NOT IN") return "value1, value2, value3";
  if (operator === "BETWEEN" || operator === "NOT BETWEEN") return "start, end";
  if (operator === "LIKE" || operator === "NOT LIKE") return "SQL pattern, e.g. A%";
  if (operator === "CONTAINS" || operator === "NOT CONTAINS") return "Text to find";
  if (operator === "STARTS WITH") return "Beginning text";
  if (operator === "ENDS WITH") return "Ending text";
  return "Value";
}

export function getValueHint(operator: FilterOperator): string | null {
  if (operator === "IN" || operator === "NOT IN") return "Use commas to separate multiple values.";
  if (operator === "BETWEEN" || operator === "NOT BETWEEN") return "Use two values separated by a comma.";
  if (operator === "LIKE" || operator === "NOT LIKE") return "You can use % and _ as SQL wildcards.";
  return null;
}
