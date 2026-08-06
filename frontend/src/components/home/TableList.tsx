/**
 * TableList.tsx — Connected database table overview.
 *
 * Renders each table as a card showing table name, column count,
 * and row count. Clicking a card navigates to the Query Builder
 * with that table pre-selected.
 */
import React from "react";
import { Link } from "react-router-dom";
import { useViewRowCounts, type ViewRowCount } from "../../hooks/useViewRowCounts";
import type { TableMetadata } from "../../types/schema.types";

interface TableListProps {
  tables: TableMetadata[];
  onDeleteTable?: (tableName: string) => Promise<void>;
  /** Scopes the row-count cache, so a different database never shows stale numbers. */
  dbPath?: string | null;
}

/** The row line differs by kind: a table's count is an estimate, a view's is exact. */
const RowCount: React.FC<{ table: TableMetadata; count: ViewRowCount | undefined }> = ({
  table,
  count,
}) => {
  if (table.object_type !== "VIEW") {
    // "~": the catalog estimate, which is what a table reports.
    return (
      <>
        <span className="font-medium text-gray-700">~{table.row_count.toLocaleString()}</span> rows
      </>
    );
  }
  if (!count || count.status === "loading") {
    return <span className="italic text-gray-400">Counting rows…</span>;
  }
  if (count.status === "ready") {
    // No "~": this one was counted, not estimated.
    return (
      <>
        <span className="font-medium text-gray-700">{count.rows.toLocaleString()}</span> rows
      </>
    );
  }
  return (
    <span className="font-medium text-rose-700" title={count.detail}>
      {count.status === "unavailable"
        ? "Source parquet files not found"
        : "Row count unavailable"}
    </span>
  );
};

export const TableList: React.FC<TableListProps> = ({ tables, onDeleteTable, dbPath }) => {
  const viewCounts = useViewRowCounts(tables, dbPath);

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
            {/* The name gets its own row. Sharing one with the badges truncated it to
                "Master_0..." — every month looked identical, which is the one thing this
                card has to get right. */}
            <Link to={`/query?table=${table.table_name}`} className="block">
              <h4
                className="text-lg font-semibold text-gray-900 break-words group-hover:text-indigo-600"
                title={table.table_name}
              >
                {table.table_name}
              </h4>
            </Link>
            <div className="mt-2 mb-3 flex flex-wrap items-center gap-1">
              {table.object_type && (
                <span
                  className={`px-2 py-1 text-xs font-medium rounded-full ${
                    table.object_type === "VIEW"
                      ? "bg-amber-50 text-amber-700"
                      : "bg-slate-100 text-slate-600"
                  }`}
                  title={
                    table.object_type === "VIEW"
                      ? "Reads this month's parquet files where they are — the folder must stay put."
                      : "Materialised inside the .duckdb file."
                  }
                >
                  {table.object_type}
                </span>
              )}
              <span className="px-2 py-1 bg-indigo-50 text-indigo-700 text-xs font-medium rounded-full">
                {table.columns.length} cols
              </span>
            </div>
            <div className="text-sm text-gray-500 mb-3">
              <RowCount table={table} count={viewCounts[table.table_name]} />
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
