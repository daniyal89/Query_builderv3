/**
 * ColumnPicker.tsx — Multi-select checklist for the SELECT clause.
 */

import React from "react";

interface ColumnPickerProps {
  columns: string[];
  selectedColumns: string[];
  onToggleColumn: (col: string) => void;
}

export const ColumnPicker: React.FC<ColumnPickerProps> = ({ columns, selectedColumns, onToggleColumn }) => {
  const allSelected = columns.length > 0 && selectedColumns.length === columns.length;

  const toggleAll = () => {
    if (allSelected) {
      columns.forEach(c => {
        if (selectedColumns.includes(c)) onToggleColumn(c);
      });
    } else {
      columns.forEach(c => {
        if (!selectedColumns.includes(c)) onToggleColumn(c);
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
        >
          {allSelected ? "Deselect All" : "Select All"}
        </button>
      </div>
      <div className="max-h-56 overflow-y-auto space-y-1 pr-1">
        {columns.map((c) => (
          <label
            key={c}
            className="flex items-center space-x-2 text-sm cursor-pointer hover:bg-gray-50 px-2 py-1 rounded"
          >
            <input
              type="checkbox"
              checked={selectedColumns.includes(c)}
              onChange={() => onToggleColumn(c)}
              className="flex-shrink-0 rounded text-indigo-600"
            />
            <span className="font-mono text-xs text-gray-800 break-all">{c}</span>
          </label>
        ))}
        {columns.length === 0 && (
          <p className="text-xs text-gray-400 italic px-2">No columns available</p>
        )}
      </div>
    </div>
  );
};

