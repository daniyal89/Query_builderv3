/**
 * FilterRow.tsx â€” Single filter condition row.
 *
 * Chooses a simpler operator set based on the selected column type so the
 * filter UI stays useful without overwhelming users.
 */

import React, { useMemo } from "react";
import type { FilterCondition, FilterOperator, QueryColumnOption } from "../../types/query.types";
import { SearchableSelect } from "./SearchableSelect";

interface FilterRowProps {
  condition: FilterCondition;
  columns: QueryColumnOption[];
  onChange: (id: string, updates: Partial<FilterCondition>) => void;
  onRemove: (id: string) => void;
}

const NO_VALUE_OPERATORS: FilterOperator[] = ["IS NULL", "IS NOT NULL"];
const COMMON_OPERATORS: FilterOperator[] = ["=", "!=", "IS NULL", "IS NOT NULL"];
const TEXT_OPERATORS: FilterOperator[] = [
  "CONTAINS",
  "NOT CONTAINS",
  "STARTS WITH",
  "ENDS WITH",
  "LIKE",
  "NOT LIKE",
  "IN",
  "NOT IN",
];
const RANGE_OPERATORS: FilterOperator[] = [">", "<", ">=", "<=", "BETWEEN", "NOT BETWEEN", "IN", "NOT IN"];

function getColumnFamily(dtype?: string, columnName?: string): "text" | "number" | "date" | "boolean" | "other" {
  const normalizedType = dtype?.toUpperCase() ?? "";
  const normalizedName = columnName?.toUpperCase() ?? "";

  // Check name first if it clearly indicates a date, because some DBs store dates as generic VARCHAR
  if (/(DATE|TIME|TIMESTAMP)/.test(normalizedName)) return "date";

  if (!normalizedType) return "other";
  if (/(DATE|TIME|TIMESTAMP)/.test(normalizedType)) return "date";
  if (/(CHAR|TEXT|STRING|CLOB|VARCHAR|UUID|JSON)/.test(normalizedType)) return "text";
  if (/(INT|DECIMAL|NUMERIC|DOUBLE|FLOAT|REAL|HUGEINT|BIGINT|SMALLINT|TINYINT)/.test(normalizedType)) return "number";
  if (/BOOL/.test(normalizedType)) return "boolean";
  return "other";
}

function getOperatorsForColumn(column?: QueryColumnOption): FilterOperator[] {
  const family = getColumnFamily(column?.dtype, column?.columnName || column?.label || column?.key);
  if (family === "text") return [...COMMON_OPERATORS, ...TEXT_OPERATORS];
  if (family === "number" || family === "date") return [...COMMON_OPERATORS, ...RANGE_OPERATORS];
  if (family === "boolean") return [...COMMON_OPERATORS, "IN", "NOT IN"];
  return [...COMMON_OPERATORS, ...RANGE_OPERATORS];
}

function getValuePlaceholder(operator: FilterOperator): string {
  if (operator === "IN" || operator === "NOT IN") return "value1, value2, value3";
  if (operator === "BETWEEN" || operator === "NOT BETWEEN") return "start, end";
  if (operator === "LIKE" || operator === "NOT LIKE") return "SQL pattern, e.g. A%";
  if (operator === "CONTAINS" || operator === "NOT CONTAINS") return "Text to find";
  if (operator === "STARTS WITH") return "Beginning text";
  if (operator === "ENDS WITH") return "Ending text";
  return "Value";
}

function getValueHint(operator: FilterOperator): string | null {
  if (operator === "IN" || operator === "NOT IN") return "Use commas to separate multiple values.";
  if (operator === "BETWEEN" || operator === "NOT BETWEEN") return "Use two values separated by a comma.";
  if (operator === "LIKE" || operator === "NOT LIKE") return "You can use % and _ as SQL wildcards.";
  return null;
}

export const FilterRow: React.FC<FilterRowProps> = ({ condition, columns, onChange, onRemove }) => {
  const selectedColumn = useMemo(
    () => columns.find((column) => column.key === condition.column),
    [columns, condition.column]
  );
  const columnOptions = useMemo(
    () =>
      columns.map((column) => ({
        value: column.key,
        label: column.label,
        description: column.dtype,
      })),
    [columns]
  );
  const availableOperators = useMemo(
    () => getOperatorsForColumn(selectedColumn),
    [selectedColumn]
  );
  const operator = availableOperators.includes(condition.operator) ? condition.operator : availableOperators[0];
  const needsValue = !NO_VALUE_OPERATORS.includes(operator);
  const hint = getValueHint(operator);

  const isDate = getColumnFamily(selectedColumn?.dtype, selectedColumn?.columnName || selectedColumn?.label || selectedColumn?.key) === "date";
  const isSingleValue = !operator.includes("BETWEEN") && !operator.includes("IN");
  const inputType = isDate && isSingleValue ? "date" : "text";

  const handleColumnChange = (columnName: string) => {
    const nextColumn = columns.find((column) => column.key === columnName);
    const nextOperators = getOperatorsForColumn(nextColumn);
    const nextOperator = nextOperators.includes(condition.operator) ? condition.operator : nextOperators[0];
    onChange(condition.id, {
      column: columnName,
      operator: nextOperator,
      value: NO_VALUE_OPERATORS.includes(nextOperator) ? "" : condition.value,
    });
  };

  const handleOperatorChange = (nextOperator: FilterOperator) => {
    onChange(condition.id, {
      operator: nextOperator,
      value: NO_VALUE_OPERATORS.includes(nextOperator) ? "" : condition.value,
    });
  };

  return (
    <div className="mb-3 rounded border border-gray-200 bg-gray-50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">Where</span>
        <button
          onClick={() => onRemove(condition.id)}
          className="text-sm font-bold leading-none text-red-400 hover:text-red-600"
          title="Remove filter"
        >
          ×
        </button>
      </div>

      <SearchableSelect
        value={condition.column}
        options={columnOptions}
        onChange={handleColumnChange}
        placeholder="-- Column --"
        searchPlaceholder="Search filter columns..."
        emptyMessage="No filter columns match your search."
        className="mb-2"
      />

      <select
        value={operator}
        onChange={(e) => handleOperatorChange(e.target.value as FilterOperator)}
        className="mb-2 w-full rounded border border-gray-300 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
      >
        {availableOperators.map((availableOperator) => (
          <option key={availableOperator} value={availableOperator}>
            {availableOperator}
          </option>
        ))}
      </select>

      {needsValue && (
        <>
          {isDate && (operator === "BETWEEN" || operator === "NOT BETWEEN") ? (
            <div className="flex items-center gap-2 w-full">
              <input
                type="date"
                value={(condition.value ?? "").split(",")[0]?.trim() ?? ""}
                onChange={(e) => {
                  const parts = (condition.value ?? "").split(",");
                  const end = parts.length > 1 ? parts[1].trim() : "";
                  onChange(condition.id, { value: `${e.target.value}, ${end}` });
                }}
                className="w-full rounded border border-gray-300 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <span className="text-gray-500 text-xs">to</span>
              <input
                type="date"
                value={(condition.value ?? "").split(",")[1]?.trim() ?? ""}
                onChange={(e) => {
                  const parts = (condition.value ?? "").split(",");
                  const start = parts.length > 0 ? parts[0].trim() : "";
                  onChange(condition.id, { value: `${start}, ${e.target.value}` });
                }}
                className="w-full rounded border border-gray-300 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          ) : (
            <input
              type={inputType}
              value={condition.value ?? ""}
              onChange={(e) => onChange(condition.id, { value: e.target.value })}
              className="w-full rounded border border-gray-300 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder={getValuePlaceholder(operator)}
            />
          )}
          {hint && <p className="mt-1 text-xs text-gray-500">{hint}</p>}
        </>
      )}
    </div>
  );
};
