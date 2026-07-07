/**
 * ExportModal.tsx — Modal for large CSV exports with native folder browser,
 * progress display, cancel button, and success/error states.
 */
import React, { useEffect, useRef, useState } from "react";

/* ── Types ─────────────────────────────────────────────────── */

export type ExportPhase =
  | "pick"       // User choosing path
  | "running"    // Export in progress
  | "completed"  // Done
  | "failed"     // Error
  | "cancelled"; // Cancelled by user

export interface ExportModalProps {
  open: boolean;
  totalRows: number;
  onClose: () => void;
  onStartExport: (outputPath: string) => Promise<any>;
}

/* ── Component ─────────────────────────────────────────────── */

export const ExportModal: React.FC<ExportModalProps> = ({
  open,
  totalRows,
  onClose,
  onStartExport,
}) => {
  /* export state */
  const [phase, setPhase] = useState<ExportPhase>("pick");
  const [progress, setProgress] = useState("");
  const [rowsWritten, setRowsWritten] = useState(0);
  const [outputPath, setOutputPath] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const jobIdRef = useRef<string | null>(null);
  const pollingRef = useRef(false);

  /* reset when opening */
  useEffect(() => {
    if (open) {
      setPhase("pick");
      setProgress("");
      setRowsWritten(0);
      setOutputPath(null);
      setErrorMsg("");
      jobIdRef.current = null;
    }
  }, [open]);

  /* pick file and start the export */
  const handlePickFileAndStart = async () => {
    try {
      const { pickSaveFile, getExportCsvStatus } = await import("../../api/exportApi");
      
      const selectedPath = await pickSaveFile("query_results.csv");
      if (!selectedPath) {
        // User cancelled the native dialog
        return;
      }

      setPhase("running");
      setProgress("Starting export job...");

      const response = await onStartExport(selectedPath);
      if (!response?.job_id) throw new Error("Failed to start export job");

      const jobId = response.job_id;
      jobIdRef.current = jobId;
      pollingRef.current = true;

      while (pollingRef.current) {
        await new Promise((r) => setTimeout(r, 1000));
        if (!pollingRef.current) break;

        const st = await getExportCsvStatus(jobId);

        if (st.status === "completed") {
          setRowsWritten(st.rows_written);
          setOutputPath(st.output_path);
          setProgress(
            `Done! ${st.rows_written.toLocaleString()} rows written.`
          );
          setPhase("completed");
          pollingRef.current = false;
          return;
        }

        if (st.status === "failed" || st.status === "cancelled") {
          throw new Error(st.message || "Export failed");
        }

        /* still running */
        const msg =
          st.rows_written > 0
            ? `Writing… ${st.rows_written.toLocaleString()} rows so far`
            : st.message || "Exporting…";
        setProgress(msg);
        setRowsWritten(st.rows_written);
      }
    } catch (err: any) {
      setErrorMsg(err.message || String(err));
      setPhase("failed");
      pollingRef.current = false;
    }
  };

  /* cancel the running export */
  const handleCancel = async () => {
    pollingRef.current = false;
    if (jobIdRef.current) {
      try {
        const { cancelExportCsv } = await import("../../api/exportApi");
        await cancelExportCsv(jobIdRef.current);
      } catch {
        /* best-effort */
      }
    }
    setPhase("cancelled");
    setProgress("Export cancelled.");
  };

  if (!open) return null;

  /* ── Render ──────────────────────────────────────────────── */
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
          <h2 className="text-base font-semibold text-gray-800">
            {phase === "pick" && "Export to CSV"}
            {phase === "running" && "Exporting…"}
            {phase === "completed" && "Export Complete"}
            {phase === "failed" && "Export Failed"}
            {phase === "cancelled" && "Export Cancelled"}
          </h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4">
          {/* ── PICK PHASE ─────────────────────────────── */}
          {phase === "pick" && (
            <div className="py-6 text-center">
              <p className="mb-4 text-sm text-gray-600">
                You are about to export <strong>{totalRows.toLocaleString()}</strong> rows to a CSV file.
              </p>
              <button
                onClick={handlePickFileAndStart}
                className="rounded bg-indigo-600 px-6 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-700 shadow-sm"
              >
                Choose Location & Export
              </button>
            </div>
          )}

          {/* ── RUNNING PHASE ──────────────────────────── */}
          {phase === "running" && (
            <div className="py-4 text-center">
              <div className="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-4 border-indigo-200 border-t-indigo-600" />
              <p className="text-sm font-medium text-gray-700">{progress}</p>
              {rowsWritten > 0 && (
                <p className="mt-1 text-xs text-gray-500">
                  {rowsWritten.toLocaleString()} rows written
                </p>
              )}
            </div>
          )}

          {/* ── COMPLETED PHASE ────────────────────────── */}
          {phase === "completed" && (
            <div className="py-4 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-2xl">
                ✓
              </div>
              <p className="text-sm font-semibold text-green-700">
                Export complete!
              </p>
              <p className="mt-1 text-xs text-gray-600">
                <strong>{rowsWritten.toLocaleString()}</strong> rows written to:
              </p>
              <p className="mt-1 break-all rounded bg-gray-50 px-3 py-1.5 text-xs font-mono text-gray-700 border border-gray-200">
                {outputPath}
              </p>
            </div>
          )}

          {/* ── FAILED PHASE ───────────────────────────── */}
          {phase === "failed" && (
            <div className="py-4 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-2xl">
                ✕
              </div>
              <p className="text-sm font-semibold text-red-700">
                Export failed
              </p>
              <p className="mt-2 break-all rounded bg-red-50 px-3 py-2 text-xs text-red-600 border border-red-200">
                {errorMsg}
              </p>
            </div>
          )}

          {/* ── CANCELLED PHASE ────────────────────────── */}
          {phase === "cancelled" && (
            <div className="py-4 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-amber-100 text-2xl">
                ⚠
              </div>
              <p className="text-sm font-semibold text-amber-700">
                Export was cancelled
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-5 py-3">
          {phase === "pick" && (
            <button
              onClick={onClose}
              className="rounded px-4 py-1.5 text-sm font-medium text-gray-600 transition hover:bg-gray-100"
            >
              Cancel
            </button>
          )}

          {phase === "running" && (
            <button
              onClick={() => void handleCancel()}
              className="rounded bg-red-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-red-700"
            >
              ■ Stop Export
            </button>
          )}

          {(phase === "completed" ||
            phase === "failed" ||
            phase === "cancelled") && (
            <button
              onClick={onClose}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-indigo-700"
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
