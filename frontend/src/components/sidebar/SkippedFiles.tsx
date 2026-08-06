/**
 * SkippedFiles.tsx - Which files were skipped, and why.
 *
 * The job reports skips as "<path> (REASON)" strings. Showing only the aggregated
 * count ("MISSING_ACCT_ID_COLUMN: 93") tells an operator something is wrong but
 * not which files to go and look at, so each reason expands to its file list.
 */
import React, { useMemo, useState } from "react";
import { BENIGN_REASONS, REASON_HELP } from "./skipReasons";

interface SkippedFilesProps {
  /** Raw `parquet_skipped_details` entries, each `"<path> (REASON)"`. */
  details?: string[];
}

function parse(details: string[]): Map<string, string[]> {
  const grouped = new Map<string, string[]>();
  for (const detail of details) {
    const match = detail.match(/\(([^)]+)\)\s*$/);
    const reason = match ? match[1] : "UNKNOWN";
    const file = match ? detail.slice(0, detail.lastIndexOf("(")).trim() : detail;
    const list = grouped.get(reason) ?? [];
    list.push(file);
    grouped.set(reason, list);
  }
  return grouped;
}

export const SkippedFiles: React.FC<SkippedFilesProps> = ({ details }) => {
  const grouped = useMemo(() => parse(details ?? []), [details]);
  const [expanded, setExpanded] = useState<string | null>(null);

  if (grouped.size === 0) return null;

  // Problems first — a real fault should not sit below 500 benign "already exists".
  const reasons = [...grouped.entries()].sort((a, b) => {
    const aBenign = BENIGN_REASONS.has(a[0]) ? 1 : 0;
    const bBenign = BENIGN_REASONS.has(b[0]) ? 1 : 0;
    return aBenign - bBenign || b[1].length - a[1].length;
  });

  return (
    <div className="mt-2 text-xs">
      <p className="font-semibold text-amber-700">Skipped files</p>
      <ul className="mt-1 space-y-1">
        {reasons.map(([reason, files]) => {
          const isOpen = expanded === reason;
          const benign = BENIGN_REASONS.has(reason);
          return (
            <li key={reason}>
              <button
                type="button"
                onClick={() => setExpanded(isOpen ? null : reason)}
                aria-expanded={isOpen}
                className={`w-full rounded px-2 py-1 text-left transition hover:brightness-95 ${
                  benign ? "bg-slate-100 text-slate-700" : "bg-amber-100 text-amber-900"
                }`}
              >
                <span className="font-semibold">{reason}</span>: {files.length}
                {REASON_HELP[reason] && (
                  <span className="ml-1 font-normal opacity-80">— {REASON_HELP[reason]}</span>
                )}
                <span className="ml-1 opacity-60">{isOpen ? "▾" : "▸"}</span>
              </button>

              {isOpen && (
                <div className="mt-1 rounded border border-slate-200 bg-white p-2">
                  <button
                    type="button"
                    className="mb-1 text-[11px] font-semibold text-indigo-600 hover:underline"
                    onClick={() => void navigator.clipboard?.writeText(files.join("\n"))}
                  >
                    Copy {files.length} path(s)
                  </button>
                  <ul className="max-h-48 space-y-0.5 overflow-y-auto font-mono text-[11px] text-slate-600">
                    {files.map((file) => (
                      <li key={file} className="break-all">
                        {file}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
};
