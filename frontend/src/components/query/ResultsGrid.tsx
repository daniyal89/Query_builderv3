/**
 * ResultsGrid.tsx — Query results table with CSV/Excel download.
 */
import React from "react";
import type { QueryResult } from "../../types/query.types";

interface ResultsGridProps {
  result: QueryResult | null;
  isLoading: boolean;
}

async function downloadCSV(result: QueryResult) {
  const escape = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const header = result.columns.join(",");
  const rows = result.rows.map((row) => row.map(escape).join(","));
  const csv = [header, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });

  try {
    if ("showSaveFilePicker" in window) {
      // @ts-ignore
      const handle = await window.showSaveFilePicker({
        suggestedName: "query_results.csv",
        types: [{ description: "CSV File", accept: { "text/csv": [".csv"] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    }
  } catch (err: any) {
    if (err.name !== "AbortError") console.error("Failed to save file using picker:", err);
    return;
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "query_results.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export const ResultsGrid: React.FC<ResultsGridProps> = ({ result, isLoading }) => {
  if (isLoading) {
    return (
      <div className="mt-8 flex items-center justify-center h-48 bg-white rounded-lg border border-gray-200">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto mb-3"></div>
          <p className="text-gray-500 text-sm">Executing query...</p>
        </div>
      </div>
    );
  }

  if (!result) return null;

  if (result.columns.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h3 className="text-sm font-semibold text-gray-700">Execution Result</h3>
        <p className="mt-2 text-sm text-gray-600">
          {result.message || "Statement executed successfully."}
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
      {/* Header bar */}
      <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 className="font-semibold text-gray-700 text-sm">Results</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            {result.rows.length} of {result.total} rows
            {result.truncated && <span className="ml-1 text-amber-600 font-medium">(limited — increase limit to see more)</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => void downloadCSV(result)}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium bg-green-600 text-white rounded hover:bg-green-700 transition"
          >
            ↓ CSV
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
        <table className="min-w-full text-sm divide-y divide-gray-200">
          <thead className="bg-gray-50 sticky top-0 z-10">
            <tr>
              {result.columns.map((col, idx) => (
                <th
                  key={idx}
                  className="px-4 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider whitespace-nowrap border-b border-gray-200 bg-gray-50"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-100">
            {result.rows.map((row, rowIdx) => (
              <tr key={rowIdx} className={rowIdx % 2 === 0 ? "bg-white" : "bg-gray-50/50"}>
                {row.map((cell, colIdx) => (
                  <td
                    key={colIdx}
                    className="px-4 py-2 text-xs text-gray-900 whitespace-nowrap max-w-xs overflow-hidden text-ellipsis"
                    title={cell !== null && cell !== undefined ? String(cell) : "null"}
                  >
                    {cell !== null && cell !== undefined ? (
                      String(cell)
                    ) : (
                      <span className="text-gray-300 italic">null</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
            {result.rows.length === 0 && (
              <tr>
                <td
                  colSpan={result.columns.length}
                  className="px-4 py-10 text-center text-gray-400 italic"
                >
                  No rows returned for this query.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
