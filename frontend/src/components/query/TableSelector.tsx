/**
 * TableSelector.tsx — Dropdown to pick the target table for a query.
 *
 * Props:
 *   tables: TableMetadata[]          — Available tables.
 *   selected: string                 — Currently selected table name.
 *   onSelect: (tableName) => void    — Callback when selection changes.
 */

import React from "react";
import type { TableMetadata } from "../../types/schema.types";

interface TableSelectorProps {
  tables: TableMetadata[];
  activeTable: string | null;
  onSelect: (tableName: string) => void;
}

export const TableSelector: React.FC<TableSelectorProps> = ({ tables, activeTable, onSelect }) => {
  return (
    <div className="bg-white p-4 border border-gray-200 rounded shadow-sm mb-4">
      <label className="block text-sm font-semibold text-gray-700 mb-2">Select Target Table</label>
      <select
        value={activeTable || ""}
        onChange={(e) => onSelect(e.target.value)}
        className="w-full border border-gray-300 rounded p-2 focus:ring-indigo-500 focus:border-indigo-500"
      >
        <option value="" disabled>-- Select a Table --</option>
        {tables.map((t) => (
          <option key={t.table_name} value={t.table_name}>
            {t.table_name} ({t.columns.length} columns)
          </option>
        ))}
      </select>
    </div>
  );
};
