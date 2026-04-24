import React from "react";

export const SidebarToolsPage: React.FC = () => {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold text-slate-900">Sidebar-6 Data Tools</h1>
        <p className="mt-2 text-sm text-slate-600">
          Use these scripts to build DuckDB objects for older/current month files and to convert CSV/GZ files to
          Parquet.
        </p>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">1) Build DuckDB Table or View</h2>
        <p className="mt-2 text-sm text-slate-600">Script path: <code>build_duckdb.py</code></p>
        <pre className="mt-3 overflow-x-auto rounded bg-slate-950 p-4 text-xs text-slate-100">
{`python build_duckdb.py \\
  --db ./monthly.duckdb \\
  --input "./data/MAR_2026/*.csv.gz" \\
  --object-name MASTER_MAR_2026 \\
  --object-type TABLE \\
  --replace \\
  --month-label MAR_2026`}
        </pre>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">2) Convert CSV/GZ to Parquet</h2>
        <p className="mt-2 text-sm text-slate-600">Script path: <code>csv_to_prequat.py</code></p>
        <pre className="mt-3 overflow-x-auto rounded bg-slate-950 p-4 text-xs text-slate-100">
{`python csv_to_prequat.py \\
  --input "./data/MAR_2026/*.csv.gz" \\
  --output "./parquet/MAR_2026/master.parquet" \\
  --compression zstd`}
        </pre>
      </div>
    </div>
  );
};
