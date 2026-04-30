/**
 * PreviewGrid.tsx — CSV data preview before import.
 *
 * Shows the first N rows of the parsed CSV for user verification.
 * Read-only table with the remapped column names as headers.
 *
 * Props:
 *   preview: CSVPreview | null     — Parsed CSV preview data.
 */

import React from "react";
import type { CSVPreview } from "../../types/importer.types";

interface PreviewGridProps {
  preview: CSVPreview | null;
}

export const PreviewGrid: React.FC<PreviewGridProps> = ({ preview }) => {
  if (!preview) {
    return <p className="text-sm text-slate-500">Upload a CSV to see preview rows.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full text-xs">
        <thead className="bg-slate-50">
          <tr>
            {preview.headers.map((header) => (
              <th key={header} className="border-b px-3 py-2 text-left font-semibold text-slate-700">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row, idx) => (
            <tr key={`row-${idx}`} className="odd:bg-white even:bg-slate-50/50">
              {row.map((value, colIdx) => (
                <td key={`cell-${idx}-${colIdx}`} className="border-b px-3 py-2 text-slate-700">
                  {value}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
