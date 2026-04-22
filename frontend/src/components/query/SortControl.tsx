/**
 * SortControl.tsx — ORDER BY configuration.
 *
 * Column selector + ASC/DESC toggle for the sort directive.
 *
 * Props:
 *   columns: ColumnDetail[]         — Available columns.
 *   sort: SortClause[]              — Current sort configuration.
 *   onChange: (sort) => void         — Callback when sort changes.
 */

import React from "react";
import type { SortClause } from "../../types/query.types";

interface SortControlProps {
  sortRules: SortClause[];
  columns: string[];
  onChange: (sortRules: SortClause[]) => void;
}

export const SortControl: React.FC<SortControlProps> = ({ sortRules, columns, onChange }) => {
  const currentSort = sortRules[0] || { column: "", direction: "ASC" };

  const handleColumnChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const col = e.target.value;
    if (!col) onChange([]);
    else onChange([{ column: col, direction: currentSort.direction }]);
  };

  const handleDirectionChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    if (!currentSort.column) return;
    onChange([{ column: currentSort.column, direction: e.target.value as "ASC" | "DESC" }]);
  };

  return (
    <div className="bg-white p-4 border border-gray-200 rounded shadow-sm mb-4">
      <h3 className="font-semibold text-gray-700 mb-2">Order By</h3>
      <div className="flex space-x-2">
        <select
          value={currentSort.column}
          onChange={handleColumnChange}
          className="border border-gray-300 rounded p-2 flex-grow"
        >
          <option value="">None</option>
          {columns.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={currentSort.direction}
          onChange={handleDirectionChange}
          disabled={!currentSort.column}
          className="border border-gray-300 rounded p-2"
        >
          <option value="ASC">Ascending</option>
          <option value="DESC">Descending</option>
        </select>
      </div>
    </div>
  );
};
