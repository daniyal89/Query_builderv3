/**
 * RowReconciliation.tsx - Shows where every source row ended up.
 *
 * The pipeline used to report "completed successfully" while silently dropping
 * rows, so a run is only trustworthy if the numbers balance. This renders that
 * balance and shouts when they don't.
 */
import React from "react";
import type {
  DataQuality,
  FileRowAudit,
  RowReconciliation as Reconciliation,
} from "../../api/sidebarToolsApi";

interface RowReconciliationProps {
  reconciliation?: Reconciliation;
  dataQuality?: DataQuality;
  rowAudit?: FileRowAudit[];
  auditTruncated?: boolean;
}

const TONE: Record<DataQuality, string> = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-900",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  loss: "border-red-300 bg-red-50 text-red-800",
};

function count(value: number): string {
  return value.toLocaleString();
}

/** Roll every file's per-reason quarantine counts into one histogram. */
function quarantineReasons(rowAudit: FileRowAudit[]): [string, number][] {
  const totals: Record<string, number> = {};
  for (const entry of rowAudit) {
    for (const [reason, n] of Object.entries(entry.quarantine_reasons ?? {})) {
      totals[reason] = (totals[reason] ?? 0) + n;
    }
  }
  return Object.entries(totals).sort((a, b) => b[1] - a[1]);
}

export const RowReconciliation: React.FC<RowReconciliationProps> = ({
  reconciliation,
  dataQuality = "ok",
  rowAudit = [],
  auditTruncated = false,
}) => {
  if (!reconciliation || reconciliation.source_rows === 0) return null;

  const { source_rows, written_rows, reused_rows, quarantined_rows, unaccounted_rows } =
    reconciliation;
  const reasons = quarantineReasons(rowAudit);
  const failures = rowAudit.filter((entry) => entry.outcome === "failed");
  const quarantineFiles = rowAudit.filter((entry) => entry.quarantine_file);

  return (
    <div className={`mt-3 rounded-xl border p-3 text-xs ${TONE[dataQuality]}`}>
      <p className="font-semibold">
        Source {count(source_rows)} &rarr; Written {count(written_rows)}
        {reused_rows > 0 && <> &middot; Reused {count(reused_rows)}</>}
        {quarantined_rows > 0 && <> &middot; Quarantined {count(quarantined_rows)}</>}
      </p>

      {unaccounted_rows > 0 ? (
        <p className="mt-1 font-bold">
          Row loss: {count(unaccounted_rows)} row(s) unaccounted for.
        </p>
      ) : (
        <p className="mt-1 opacity-80">Every source row is accounted for.</p>
      )}

      {reasons.length > 0 && (
        <p className="mt-1">
          <span className="font-semibold">Quarantined because:</span>{" "}
          {reasons.map(([reason, n], index) => (
            <span key={reason}>
              {index > 0 ? ", " : ""}
              {reason}: {count(n)}
            </span>
          ))}
        </p>
      )}

      {failures.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer font-semibold">
            {failures.length} file(s) failed
          </summary>
          <ul className="mt-1 space-y-0.5">
            {failures.slice(0, 10).map((entry) => (
              <li key={entry.source_file} className="break-all">
                {entry.source_file} — {entry.reason}
                {entry.source_rows > 0 && <> ({count(entry.source_rows)} rows)</>}
              </li>
            ))}
            {failures.length > 10 && <li>… and {failures.length - 10} more</li>}
          </ul>
        </details>
      )}

      {reconciliation.discrepancies.length > 0 && (
        <details className="mt-2" open>
          <summary className="cursor-pointer font-semibold">Unbalanced files</summary>
          <ul className="mt-1 space-y-0.5">
            {reconciliation.discrepancies.slice(0, 5).map((line) => (
              <li key={line} className="break-all">
                {line}
              </li>
            ))}
            {reconciliation.discrepancies.length > 5 && (
              <li>… and {reconciliation.discrepancies.length - 5} more</li>
            )}
          </ul>
        </details>
      )}

      {quarantineFiles.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer font-semibold">
            Rejected rows kept for inspection
          </summary>
          <ul className="mt-1 space-y-0.5">
            {quarantineFiles.slice(0, 10).map((entry) => (
              <li key={entry.quarantine_file} className="break-all">
                {entry.quarantine_file}
              </li>
            ))}
          </ul>
        </details>
      )}

      {auditTruncated && (
        <p className="mt-1 opacity-70">
          Per-file detail truncated; totals above cover the whole run.
        </p>
      )}
    </div>
  );
};
