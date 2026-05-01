import React, { useMemo } from "react";
import type { FunctionColumn, QueryColumnOption, SqlFunction } from "../../types/query.types";
import { SearchableSelect } from "./SearchableSelect";

interface FunctionColumnBuilderProps {
  functionColumns: FunctionColumn[];
  columns: QueryColumnOption[];
  onAddFunctionColumn: () => void;
  onUpdateFunctionColumn: (id: string, updates: Partial<FunctionColumn>) => void;
  onRemoveFunctionColumn: (id: string) => void;
}

const SQL_FUNCTIONS: { value: SqlFunction; label: string; description: string }[] = [
  { value: "SUM", label: "SUM", description: "Total of numeric values" },
  { value: "COUNT", label: "COUNT", description: "Number of rows/values" },
  { value: "AVG", label: "AVG", description: "Average of numeric values" },
  { value: "MIN", label: "MIN", description: "Minimum value" },
  { value: "MAX", label: "MAX", description: "Maximum value" },
  { value: "COUNT_DISTINCT", label: "COUNT DISTINCT", description: "Number of unique values" },
  { value: "COALESCE", label: "COALESCE", description: "First non-null value" },
];

export const FunctionColumnBuilder: React.FC<FunctionColumnBuilderProps> = ({
  functionColumns,
  columns,
  onAddFunctionColumn,
  onUpdateFunctionColumn,
  onRemoveFunctionColumn,
}) => {
  const columnOptions = useMemo(
    () => [
      { value: "*", label: "* (All Rows)", description: "Any column" },
      ...columns.map((column) => ({
        value: column.key,
        label: column.label,
        description: column.dtype,
      })),
    ],
    [columns]
  );

  return (
    <div className="bg-white p-4 border border-gray-200 rounded shadow-sm mb-4">
      <div className="flex justify-between items-center mb-2">
        <h3 className="font-semibold text-gray-700">Function Columns</h3>
        <button
          onClick={onAddFunctionColumn}
          className="bg-blue-50 text-blue-600 px-2 py-1 rounded text-sm hover:bg-blue-100"
        >
          + Add Function Column
        </button>
      </div>
      <div>
        {functionColumns.length === 0 ? (
          <p className="text-sm text-gray-500 italic">No function columns defined.</p>
        ) : (
          functionColumns.map((fcol) => (
            <div key={fcol.id} className="border border-gray-200 rounded mb-3 bg-gray-50 p-3 shadow-sm">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex flex-col">
                  <label className="text-xs font-semibold text-gray-600 mb-1">Alias</label>
                  <input
                    type="text"
                    className="border border-gray-300 rounded px-2 py-1.5 text-sm w-40"
                    placeholder="E.g., Total_Amount"
                    value={fcol.alias}
                    onChange={(e) => onUpdateFunctionColumn(fcol.id, { alias: e.target.value })}
                  />
                </div>
                <div className="flex flex-col">
                  <label className="text-xs font-semibold text-gray-600 mb-1">Function</label>
                  <select
                    className="border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
                    value={fcol.func}
                    onChange={(e) =>
                      onUpdateFunctionColumn(fcol.id, {
                        func: e.target.value as SqlFunction,
                        column: e.target.value === "COUNT" ? "*" : fcol.column,
                      })
                    }
                  >
                    {SQL_FUNCTIONS.map((f) => (
                      <option key={f.value} value={f.value} title={f.description}>
                        {f.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col">
                  <label className="text-xs font-semibold text-gray-600 mb-1">Target Column</label>
                  <div className="w-56">
                    <SearchableSelect
                      options={columnOptions}
                      value={fcol.column}
                      onChange={(col) => onUpdateFunctionColumn(fcol.id, { column: col })}
                      placeholder="Select column..."
                    />
                  </div>
                </div>

                {fcol.func === "COALESCE" && (
                  <>
                    <span className="text-gray-400 mt-5">,</span>
                    <div className="flex flex-col">
                      <label className="text-xs font-semibold text-gray-600 mb-1">Fallback Column</label>
                      <div className="w-56">
                        <SearchableSelect
                          options={columnOptions.filter((o) => o.value !== "*")}
                          value={fcol.secondColumn || ""}
                          onChange={(col) => onUpdateFunctionColumn(fcol.id, { secondColumn: col })}
                          placeholder="Select column..."
                        />
                      </div>
                    </div>
                  </>
                )}
                <button
                  onClick={() => onRemoveFunctionColumn(fcol.id)}
                  className="mt-5 p-1.5 text-sm font-bold text-red-400 hover:text-red-600 rounded self-start"
                  title="Remove Function Column"
                >
                  ×
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
