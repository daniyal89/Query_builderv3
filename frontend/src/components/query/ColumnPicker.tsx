/**
 * ColumnPicker.tsx — Multi-select checklist for the SELECT clause.
 */

import React, { useDeferredValue, useMemo, useState } from "react";
import type { QueryColumnOption } from "../../types/query.types";

interface ColumnPickerProps {
  columns: QueryColumnOption[];
  selectedColumns: string[];
  onToggleColumn: (col: string) => void;
}

export const ColumnPicker: React.FC<ColumnPickerProps> = ({ columns, selectedColumns, onToggleColumn }) => {
  const [searchTerm, setSearchTerm] = useState("");
  const deferredSearchTerm = useDeferredValue(searchTerm);
  const normalizedSearchTerm = deferredSearchTerm.trim().toLowerCase();
  const visibleColumns = useMemo(() => {
    if (columns.length <= 20 || !normalizedSearchTerm) {
      return columns;
    }
    return columns.filter((column) => {
      const haystack = `${column.label} ${column.dtype}`.toLowerCase();
      return haystack.includes(normalizedSearchTerm);
    });
  }, [columns, normalizedSearchTerm]);
  const allVisibleSelected =
    visibleColumns.length > 0 && visibleColumns.every((column) => selectedColumns.includes(column.key));

  const toggleAll = () => {
    if (allVisibleSelected) {
      visibleColumns.forEach((column) => {
        if (selectedColumns.includes(column.key)) onToggleColumn(column.key);
      });
    } else {
      visibleColumns.forEach((column) => {
        if (!selectedColumns.includes(column.key)) onToggleColumn(column.key);
      });
    }
  };

  return (
    <div className="bg-white p-3 border border-gray-200 rounded shadow-sm mb-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-gray-700 text-sm">Select Columns</h3>
        <button
          onClick={toggleAll}
          className="text-xs text-indigo-600 hover:underline"
          disabled={visibleColumns.length === 0}
        >
          {allVisibleSelected ? "Deselect Visible" : "Select Visible"}
        </button>
      </div>
      <div className="mb-3">
        {columns.length > 20 && (
          <input
            type="text"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            className="w-full rounded border border-gray-300 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Search columns..."
          />
        )}
        <p className="mt-1 text-xs text-gray-400">
          Showing {visibleColumns.length} of {columns.length} columns
        </p>
      </div>
      <div className="max-h-56 overflow-y-auto space-y-1 pr-1">
        {visibleColumns.map((column) => (
          <label
            key={column.key}
            className="flex items-center space-x-2 text-sm cursor-pointer hover:bg-gray-50 px-2 py-1 rounded"
          >
            <input
              type="checkbox"
              checked={selectedColumns.includes(column.key)}
              onChange={() => onToggleColumn(column.key)}
              className="flex-shrink-0 rounded text-indigo-600"
            />
            <span className="font-mono text-xs text-gray-800 break-all">{column.label}</span>
          </label>
        ))}
        {columns.length === 0 && (
          <p className="text-xs text-gray-400 italic px-2">No columns available</p>
        )}
        {columns.length > 0 && visibleColumns.length === 0 && (
          <p className="text-xs text-gray-400 italic px-2">No columns match your search.</p>
        )}
      </div>
    </div>
  );
};

