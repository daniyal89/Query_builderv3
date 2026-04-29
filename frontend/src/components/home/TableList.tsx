/**
 * TableList.tsx — Connected database table overview.
 *
 * Renders each table as a card showing table name, column count,
 * and row count. Clicking a card navigates to the Query Builder
 * with that table pre-selected.
 */
import React from "react";
import { Link } from "react-router-dom";
import type { TableMetadata } from "../../types/schema.types";

interface TableListProps {
  tables: TableMetadata[];
  onDeleteTable?: (tableName: string) => Promise<void>;
}

export const TableList: React.FC<TableListProps> = ({ tables, onDeleteTable }) => {
  if (tables.length === 0) return null;

  return (
    <div className="max-w-6xl mx-auto mt-12 px-4">
      <h3 className="text-xl font-bold text-gray-800 mb-6">Available Tables ({tables.length})</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {tables.map((table) => (
          <div
            key={table.table_name}
            className="block bg-white rounded-lg border border-gray-200 shadow-sm hover:shadow-md hover:border-indigo-300 transition group p-5"
          >
            <div className="flex items-center justify-between mb-3">
              <Link to={`/query?table=${table.table_name}`} className="min-w-0">
                <h4 className="text-lg font-semibold text-gray-900 truncate group-hover:text-indigo-600">
                  {table.table_name}
                </h4>
              </Link>
              <span className="px-2 py-1 bg-indigo-50 text-indigo-700 text-xs font-medium rounded-full">
                {table.columns.length} cols
              </span>
            </div>
            <div className="text-sm text-gray-500 mb-3">
              <span className="font-medium text-gray-700">~{table.row_count.toLocaleString()}</span> rows
            </div>
            {onDeleteTable && (
              <button
                type="button"
                onClick={() => onDeleteTable(table.table_name)}
                className="rounded border border-rose-200 px-2 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-50"
              >
                Delete table/view
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
