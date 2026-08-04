/**
 * ResultsGrid.tsx - Query results table with CSV download.
 *
 * The grid renders at most UI_DISPLAY_LIMIT rows; the full result set stays
 * available for CSV export. That cap is what keeps the DOM small, so no row
 * virtualization is involved.
 */
import React, { useMemo, useState } from "react";
import type { QueryResult } from "../../types/query.types";
import { ExportModal } from "./ExportModal";

interface ResultsGridProps {
  result: QueryResult | null;
  isLoading: boolean;
  isUnlimited?: boolean;
  onExportAll?: (onProgress?: (progressEvent: any) => void) => Promise<QueryResult | undefined>;
  onStartLargeExport?: (outputPath: string) => Promise<any>;
}

const LARGE_EXPORT_THRESHOLD = 200000;

/** Max rows displayed in the UI grid — all rows still available for CSV export. */
const UI_DISPLAY_LIMIT = 50;

const GRID_MAX_HEIGHT = 600;

function buildCSVBlob(result: QueryResult): Blob {
  const escape = (value: unknown) => `"${String(value ?? "").replace(/"/g, '""')}"`;
  const header = result.columns.join(",");
  const rows = result.rows.map((row) => row.map(escape).join(","));
  const csv = [header, ...rows].join("\n");
  return new Blob([csv], { type: "text/csv;charset=utf-8;" });
}

async function saveBlob(blob: Blob, suggestedName: string) {
  try {
    if ("showSaveFilePicker" in window) {
      // @ts-expect-error showSaveFilePicker is not typed in libdom for all targets
      const handle = await window.showSaveFilePicker({
        suggestedName,
        types: [{ description: "CSV File", accept: { "text/csv": [".csv"] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    }
  } catch (error: any) {
    if (error.name === "AbortError") {
      return; // User cancelled the picker, stop here
    }
    console.warn("Failed to save file using picker, falling back to anchor download:", error);
    // Fall back to anchor click
  }

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = suggestedName;
  anchor.click();
  URL.revokeObjectURL(url);
}

export const ResultsGrid: React.FC<ResultsGridProps> = ({ result, isLoading, isUnlimited, onExportAll, onStartLargeExport }) => {
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState("");
  const [showExportModal, setShowExportModal] = useState(false);

  // Cap rows shown in UI to UI_DISPLAY_LIMIT; full result.rows kept for CSV
  const displayRows = useMemo(
    () => (result ? result.rows.slice(0, UI_DISPLAY_LIMIT) : []),
    [result],
  );
  const displayRowCount = displayRows.length;

  const handleExportCSV = async () => {
    if (!result) return;

    // ── Large export → open the Export Modal ──
    // Use result.rows.length or isUnlimited to determine if we should bypass the browser memory
    if ((isUnlimited || result.rows.length >= LARGE_EXPORT_THRESHOLD) && onStartLargeExport) {
      setShowExportModal(true);
      return;
    }

    // ── Medium export: total > displayed but < threshold ──
    if (onExportAll && result.total > result.rows.length) {
      setIsExporting(true);
      setExportProgress("Fetching...");
      try {
        const fullResult = await onExportAll((progressEvent) => {
          if (progressEvent.loaded) {
            const mb = (progressEvent.loaded / 1024 / 1024).toFixed(1);
            setExportProgress(`${mb} MB`);
          }
        });
        if (fullResult) {
          setExportProgress("Building CSV...");
          await new Promise((resolve) => setTimeout(resolve, 50));
          const blob = buildCSVBlob(fullResult);
          await saveBlob(blob, "query_results_full.csv");
        }
      } finally {
        setIsExporting(false);
        setExportProgress("");
      }
      return;
    }

    // ── Small export: export what we have ──
    setIsExporting(true);
    setExportProgress("Building CSV...");
    await new Promise((resolve) => setTimeout(resolve, 50));
    try {
      const blob = buildCSVBlob(result);
      await saveBlob(blob, "query_results.csv");
    } finally {
      setIsExporting(false);
      setExportProgress("");
    }
  };

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
            Showing {Math.min(displayRowCount, result.rows.length)} of {result.rows.length.toLocaleString()} rows
            {result.rows.length > displayRowCount && (
              <span className="ml-1 text-indigo-600 font-medium">
                — CSV will export all {result.rows.length.toLocaleString()} rows
              </span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => void handleExportCSV()}
            disabled={isExporting}
            className="inline-flex items-center gap-1 rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-green-700 disabled:opacity-50 disabled:cursor-wait"
          >
            {isExporting ? (
              <>
                <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                {exportProgress || "Exporting..."}
              </>
            ) : (
              <>
                CSV
                {result.rows.length > displayRowCount && (
                  <span className="text-[10px] opacity-80">
                    (All {result.rows.length.toLocaleString()})
                  </span>
                )}
              </>
            )}
          </button>
        </div>
      </div>

      <div
        data-testid="results-grid-scroll"
        className="overflow-x-auto overflow-y-auto"
        style={{ maxHeight: `${GRID_MAX_HEIGHT}px` }}
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
            {displayRows.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className={rowIndex % 2 === 0 ? "bg-white" : "bg-gray-50/50"}
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
          </tbody>
        </table>
      </div>

      {/* Export Modal for large datasets */}
      {onStartLargeExport && (
        <ExportModal
          open={showExportModal}
          totalRows={result.rows.length}
          onClose={() => setShowExportModal(false)}
          onStartExport={onStartLargeExport}
        />
      )}
    </div>
  );
};
