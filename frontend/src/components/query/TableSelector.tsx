/**
 * TableSelector.tsx — Dropdown to pick the target table for a query.
 *
 * Props:
 *   tables: TableMetadata[]          — Available tables.
 *   selected: string                 — Currently selected table name.
 *   onSelect: (tableName) => void    — Callback when selection changes.
 */

import React, { useDeferredValue, useMemo, useState } from "react";
import type { TableMetadata } from "../../types/schema.types";

interface TableSelectorProps {
  tables: TableMetadata[];
  activeTable: string | null;
  onSelect: (tableName: string) => void;
}

export const TableSelector: React.FC<TableSelectorProps> = ({ tables, activeTable, onSelect }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const deferredSearchTerm = useDeferredValue(searchTerm);
  const normalizedSearchTerm = deferredSearchTerm.trim().toLowerCase();
  const activeTableMetadata = tables.find((table) => table.table_name === activeTable);
  const visibleTables = useMemo(() => {
    if (tables.length <= 20 || !normalizedSearchTerm) {
      return tables;
    }
    return tables.filter((table) => table.table_name.toLowerCase().includes(normalizedSearchTerm));
  }, [normalizedSearchTerm, tables]);

  const handleSelect = (tableName: string) => {
    onSelect(tableName);
    setIsOpen(false);
    setSearchTerm("");
  };
  const formatColumnCount = (table: TableMetadata) =>
    table.columns.length > 0 ? `${table.columns.length} columns` : "columns load on select";

  return (
    <div className="mb-4 rounded border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <label className="block text-sm font-semibold text-gray-700">Select Target Table</label>
          <p className="mt-1 text-xs text-gray-400">{tables.length} tables/views available</p>
        </div>
        <button
          type="button"
          onClick={() => setIsOpen((current) => !current)}
          disabled={tables.length === 0}
          className="shrink-0 rounded border border-indigo-200 px-2 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isOpen ? "Hide" : "Browse"}
        </button>
      </div>

      <button
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        disabled={tables.length === 0}
        className="w-full rounded border border-gray-300 bg-white px-3 py-2 text-left text-sm text-gray-900 transition hover:border-indigo-300 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:cursor-not-allowed disabled:bg-gray-50"
      >
        <span className="block truncate font-mono">
          {activeTableMetadata
            ? `${activeTableMetadata.table_name} (${formatColumnCount(activeTableMetadata)})`
            : "-- Select a Table --"}
        </span>
      </button>

      {isOpen && (
        <div className="mt-3 rounded border border-gray-200 bg-gray-50 p-2">
          {tables.length > 20 && (
            <input
              type="text"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              className="mb-2 w-full rounded border border-gray-300 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="Search tables, e.g. CM_MASTER..."
            />
          )}

          <div className="max-h-72 space-y-1 overflow-y-auto pr-1">
            {visibleTables.map((table) => (
              <button
                key={table.table_name}
                type="button"
                onClick={() => handleSelect(table.table_name)}
                className={`w-full rounded px-2 py-2 text-left text-xs transition ${
                  table.table_name === activeTable
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-gray-800 hover:bg-indigo-50"
                }`}
              >
                <span className="block break-all font-mono">{table.table_name}</span>
                <span className={table.table_name === activeTable ? "text-indigo-100" : "text-gray-400"}>
                  {formatColumnCount(table)}
                </span>
              </button>
            ))}

            {visibleTables.length === 0 && (
              <p className="px-2 py-4 text-center text-xs text-gray-400">No tables match your search.</p>
            )}
          </div>
        </div>
      )}

      {tables.length === 0 && (
        <p className="mt-2 text-xs text-amber-700">
          No objects were returned by the active connection. Reconnect after permissions or synonyms are available.
        </p>
      )}
    </div>
  );
};
