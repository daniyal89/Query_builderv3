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
import type { QueryColumnOption, SortClause } from "../../types/query.types";
import { SearchableSelect } from "./SearchableSelect";

interface SortControlProps {
  sortRules: SortClause[];
  columns: QueryColumnOption[];
  onChange: (sortRules: SortClause[]) => void;
}

export const SortControl: React.FC<SortControlProps> = ({ sortRules, columns, onChange }) => {
  const currentSort = sortRules[0] || { column: "", direction: "ASC" };

  const columnOptions = columns.map((column) => ({
    value: column.key,
    label: column.label,
    description: column.dtype,
  }));

  const handleColumnChange = (col: string) => {
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
      <div className="flex flex-wrap gap-2">
        <SearchableSelect
          value={currentSort.column}
          onChange={handleColumnChange}
          options={columnOptions}
          placeholder="None"
          searchPlaceholder="Search order-by columns..."
          emptyMessage="No order-by columns match your search."
          className="min-w-0 flex-1"
        />
        <select
          value={currentSort.direction}
          onChange={handleDirectionChange}
          disabled={!currentSort.column}
          className="rounded border border-gray-300 p-2"
        >
          <option value="ASC">Ascending</option>
          <option value="DESC">Descending</option>
        </select>
      </div>
    </div>
  );
};
