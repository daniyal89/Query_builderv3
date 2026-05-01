/**
 * ResultsGrid.tsx - Query results table with CSV download and virtualized rows.
 */
import React, { useEffect, useMemo, useState } from "react";
import type { QueryResult } from "../../types/query.types";

interface ResultsGridProps {
  result: QueryResult | null;
  isLoading: boolean;
}

const VIRTUALIZATION_THRESHOLD = 120;
const VIRTUAL_ROW_HEIGHT = 40;
const VIRTUAL_VIEWPORT_HEIGHT = 600;
const VIRTUAL_OVERSCAN = 8;

async function downloadCSV(result: QueryResult) {
  const escape = (value: unknown) => `"${String(value ?? "").replace(/"/g, '""')}"`;
  const header = result.columns.join(",");
  const rows = result.rows.map((row) => row.map(escape).join(","));
  const csv = [header, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });

  try {
    if ("showSaveFilePicker" in window) {
      // @ts-expect-error showSaveFilePicker is not typed in libdom for all targets
      const handle = await window.showSaveFilePicker({
        suggestedName: "query_results.csv",
        types: [{ description: "CSV File", accept: { "text/csv": [".csv"] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    }
  } catch (error: any) {
    if (error.name !== "AbortError") {
      console.error("Failed to save file using picker:", error);
    }
    return;
  }

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "query_results.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

export const ResultsGrid: React.FC<ResultsGridProps> = ({ result, isLoading }) => {
  const [scrollTop, setScrollTop] = useState(0);

  useEffect(() => {
    setScrollTop(0);
  }, [result]);

  const rowCount = result?.rows.length ?? 0;
  const useVirtualization = rowCount >= VIRTUALIZATION_THRESHOLD;
  const visibleWindowSize =
    Math.ceil(VIRTUAL_VIEWPORT_HEIGHT / VIRTUAL_ROW_HEIGHT) + VIRTUAL_OVERSCAN * 2;
  const startIndex = useVirtualization
    ? Math.max(0, Math.floor(scrollTop / VIRTUAL_ROW_HEIGHT) - VIRTUAL_OVERSCAN)
    : 0;
  const endIndex = result
    ? useVirtualization
      ? Math.min(result.rows.length, startIndex + visibleWindowSize)
      : result.rows.length
    : 0;
  const topSpacerHeight = useVirtualization ? startIndex * VIRTUAL_ROW_HEIGHT : 0;
  const bottomSpacerHeight =
    result && useVirtualization
      ? Math.max(0, (result.rows.length - endIndex) * VIRTUAL_ROW_HEIGHT)
      : 0;

  const visibleRows = useMemo(
    () =>
      result
        ? result.rows.slice(startIndex, endIndex).map((row, visibleIndex) => ({
            absoluteIndex: startIndex + visibleIndex,
            row,
          }))
        : [],
    [endIndex, result, startIndex],
  );

  if (isLoading) {
    return (
      <div className="mt-8 flex h-48 items-center justify-center rounded-lg border border-gray-200 bg-white">
        <div className="text-center">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-b-2 border-indigo-600" />
          <p className="text-sm text-gray-500">Executing query...</p>
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
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 bg-gray-50 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-700">Results</h3>
          <p className="mt-0.5 text-xs text-gray-500">
            {result.rows.length} of {result.total} rows
            {result.truncated && (
              <span className="ml-1 font-medium text-amber-600">
                (limited - increase limit to see more)
              </span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {useVirtualization && (
            <span className="rounded-full bg-sky-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-sky-700">
              Windowed rendering
            </span>
          )}
          <button
            onClick={() => void downloadCSV(result)}
            className="inline-flex items-center gap-1 rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-green-700"
          >
            CSV
          </button>
        </div>
      </div>

      <div
        data-testid="results-grid-scroll"
        className="overflow-x-auto overflow-y-auto"
        style={
          useVirtualization
            ? { height: `${VIRTUAL_VIEWPORT_HEIGHT}px` }
            : { maxHeight: `${VIRTUAL_VIEWPORT_HEIGHT}px` }
        }
        onScroll={
          useVirtualization
            ? (event) => setScrollTop(event.currentTarget.scrollTop)
            : undefined
        }
      >
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="sticky top-0 z-10 bg-gray-50">
            <tr>
              {result.columns.map((column, index) => (
                <th
                  key={index}
                  className="whitespace-nowrap border-b border-gray-200 bg-gray-50 px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-600"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {useVirtualization && topSpacerHeight > 0 && (
              <tr aria-hidden="true">
                <td colSpan={result.columns.length} style={{ height: `${topSpacerHeight}px`, padding: 0 }} />
              </tr>
            )}

            {visibleRows.map(({ absoluteIndex, row }) => (
              <tr
                key={absoluteIndex}
                style={useVirtualization ? { height: `${VIRTUAL_ROW_HEIGHT}px` } : undefined}
                className={absoluteIndex % 2 === 0 ? "bg-white" : "bg-gray-50/50"}
              >
                {row.map((cell, columnIndex) => (
                  <td
                    key={columnIndex}
                    className="max-w-xs overflow-hidden px-4 py-2 text-xs text-gray-900 text-ellipsis whitespace-nowrap"
                    title={cell !== null && cell !== undefined ? String(cell) : "null"}
                  >
                    {cell !== null && cell !== undefined ? (
                      String(cell)
                    ) : (
                      <span className="italic text-gray-300">null</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}

            {result.rows.length === 0 && (
              <tr>
                <td
                  colSpan={result.columns.length}
                  className="px-4 py-10 text-center italic text-gray-400"
                >
                  No rows returned for this query.
                </td>
              </tr>
            )}

            {useVirtualization && bottomSpacerHeight > 0 && (
              <tr aria-hidden="true">
                <td
                  colSpan={result.columns.length}
                  style={{ height: `${bottomSpacerHeight}px`, padding: 0 }}
                />
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
