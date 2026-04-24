import React, { useState } from "react";
import { runBuildDuckDb, runCsvToParquet } from "../api/sidebarToolsApi";

export const SidebarToolsPage: React.FC = () => {
  const [buildForm, setBuildForm] = useState({
    db_path: "./monthly.duckdb",
    input_path: "./data/MAR_2026/*.csv.gz",
    object_name: "MASTER_MAR_2026",
    object_type: "TABLE" as "TABLE" | "VIEW",
    replace: true,
    month_label: "MAR_2026",
  });
  const [parquetForm, setParquetForm] = useState({
    input_path: "./data/MAR_2026/*.csv.gz",
    output_path: "./parquet/MAR_2026/master.parquet",
    compression: "zstd",
  });
  const [buildMessage, setBuildMessage] = useState("");
  const [parquetMessage, setParquetMessage] = useState("");
  const [isBuildRunning, setIsBuildRunning] = useState(false);
  const [isParquetRunning, setIsParquetRunning] = useState(false);

  const runBuild = async () => {
    setIsBuildRunning(true);
    setBuildMessage("");
    try {
      const result = await runBuildDuckDb(buildForm);
      setBuildMessage(result.message + (result.output_path ? ` Output: ${result.output_path}` : ""));
    } catch (error: any) {
      setBuildMessage(error?.response?.data?.detail || error?.message || "Build failed.");
    } finally {
      setIsBuildRunning(false);
    }
  };

  const runParquet = async () => {
    setIsParquetRunning(true);
    setParquetMessage("");
    try {
      const result = await runCsvToParquet(parquetForm);
      setParquetMessage(result.message + (result.output_path ? ` Output: ${result.output_path}` : ""));
    } catch (error: any) {
      setParquetMessage(error?.response?.data?.detail || error?.message || "Conversion failed.");
    } finally {
      setIsParquetRunning(false);
    }
  };

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
        <p className="mt-2 text-sm text-slate-600">Run now from UI, or use script path: <code>build_duckdb.py</code></p>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <input className="rounded border p-2" placeholder="DB path" value={buildForm.db_path} onChange={(e) => setBuildForm((p) => ({ ...p, db_path: e.target.value }))} />
          <input className="rounded border p-2" placeholder="Input path / glob" value={buildForm.input_path} onChange={(e) => setBuildForm((p) => ({ ...p, input_path: e.target.value }))} />
          <input className="rounded border p-2" placeholder="Object name" value={buildForm.object_name} onChange={(e) => setBuildForm((p) => ({ ...p, object_name: e.target.value }))} />
          <select className="rounded border p-2" value={buildForm.object_type} onChange={(e) => setBuildForm((p) => ({ ...p, object_type: e.target.value as "TABLE" | "VIEW" }))}>
            <option value="TABLE">TABLE</option>
            <option value="VIEW">VIEW</option>
          </select>
          <input className="rounded border p-2" placeholder="Month label (optional)" value={buildForm.month_label} onChange={(e) => setBuildForm((p) => ({ ...p, month_label: e.target.value }))} />
          <label className="flex items-center gap-2 rounded border p-2 text-sm">
            <input type="checkbox" checked={buildForm.replace} onChange={(e) => setBuildForm((p) => ({ ...p, replace: e.target.checked }))} />
            Replace existing
          </label>
        </div>
        <button onClick={runBuild} disabled={isBuildRunning} className="mt-3 rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-60">
          {isBuildRunning ? "Running..." : "Run Build DuckDB"}
        </button>
        {buildMessage && <p className="mt-2 text-sm text-slate-700">{buildMessage}</p>}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">2) Convert CSV/GZ to Parquet</h2>
        <p className="mt-2 text-sm text-slate-600">Run now from UI, or use script path: <code>csv_to_prequat.py</code></p>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <input className="rounded border p-2 md:col-span-2" placeholder="Input CSV/GZ path or glob" value={parquetForm.input_path} onChange={(e) => setParquetForm((p) => ({ ...p, input_path: e.target.value }))} />
          <input className="rounded border p-2 md:col-span-2" placeholder="Output parquet file path" value={parquetForm.output_path} onChange={(e) => setParquetForm((p) => ({ ...p, output_path: e.target.value }))} />
          <input className="rounded border p-2" placeholder="Compression" value={parquetForm.compression} onChange={(e) => setParquetForm((p) => ({ ...p, compression: e.target.value }))} />
        </div>
        <button onClick={runParquet} disabled={isParquetRunning} className="mt-3 rounded bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60">
          {isParquetRunning ? "Running..." : "Run CSV → Parquet"}
        </button>
        {parquetMessage && <p className="mt-2 text-sm text-slate-700">{parquetMessage}</p>}
      </div>
    </div>
  );
};
