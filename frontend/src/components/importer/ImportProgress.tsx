/**
 * ImportProgress.tsx — Import progress indicator.
 *
 * Shows a progress bar and status messages during the CSV bulk-insert
 * operation. Displays final success/error summary when complete.
 *
 * Props:
 *   isImporting: boolean            — Whether the import is in progress.
 *   result: ImportResult | null     — Final import outcome, or null if pending.
 */

import React from "react";
import type { ImportResult } from "../../types/importer.types";

interface ImportProgressProps {
  isImporting: boolean;
  result: ImportResult | null;
}

export const ImportProgress: React.FC<ImportProgressProps> = ({ isImporting, result }) => {
  const progress = isImporting ? 65 : result ? 100 : 0;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-sm font-semibold text-slate-900">Import progress</p>
      <div className="mt-2 h-2 w-full overflow-hidden rounded bg-slate-100">
        <div className="h-full bg-emerald-600 transition-all" style={{ width: `${progress}%` }} />
      </div>
      <p className="mt-2 text-xs text-slate-600">
        {isImporting ? "Import is running..." : result ? "Import completed." : "Waiting to start import."}
      </p>
      {result && (
        <div className="mt-2 text-xs text-slate-700">
          <p>Inserted: {result.rowsInserted}</p>
          <p>Skipped: {result.rowsSkipped}</p>
          <p>Target: {result.targetTable}</p>
        </div>
      )}
    </section>
  );
};
