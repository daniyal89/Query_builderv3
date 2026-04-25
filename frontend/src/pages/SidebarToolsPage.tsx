import React, { useState } from "react";
import { runBuildDuckDb, runCsvToParquet } from "../api/sidebarToolsApi";
import { pickSystemFile, pickSystemFolder, pickSystemSavePath } from "../api/systemApi";

interface FieldProps {
  label: string;
  help: string;
  children: React.ReactNode;
}

const Field: React.FC<FieldProps> = ({ label, help, children }) => (
  <div className="space-y-1">
    <label className="block text-sm font-semibold text-slate-700">{label}</label>
    {children}
    <p className="text-xs text-slate-500">{help}</p>
  </div>
);

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
  const [statusNote, setStatusNote] = useState("Use labels below and fill full paths before running.");

  const applyUppclPreset = () => {
    setBuildForm({
      db_path: "G:/MASTER/uppcl_latest.duckdb",
      input_path: "G:/MASTER_PARQUET/MAR_2026/**/*.parquet",
      object_name: "master",
      object_type: "TABLE",
      replace: true,
      month_label: "MAR_2026",
    });
    setParquetForm({
      input_path: "G:/MASTER/MAR_2026/*.csv.gz",
      output_path: "G:/MASTER_PARQUET/MAR_2026/master.parquet",
      compression: "snappy",
    });
    setStatusNote("UPPCL preset applied. Adjust month/path values if needed.");
  };

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
        <h1 className="text-2xl font-semibold text-slate-900">Data Tools</h1>
        <p className="mt-2 text-sm text-slate-600">
          Use these tools to run Step-1 (CSV/GZ → Parquet) and Step-2 (Build DuckDB table/view). All fields below
          are now explicitly labeled so users can understand what each input means.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={applyUppclPreset}
            className="rounded border border-slate-300 bg-slate-50 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            Apply UPPCL default paths
          </button>
          <span className="inline-flex items-center rounded bg-blue-50 px-3 py-1.5 text-xs text-blue-700">
            {statusNote}
          </span>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">1) Build DuckDB Table or View</h2>
        <p className="mt-2 text-sm text-slate-600">Run now from UI, or use script path: <code>build_duckdb.py</code></p>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <Field label="DuckDB file path" help="Full target .duckdb file path. Example: G:/MASTER/uppcl_latest.duckdb">
            <div className="flex gap-2">
              <input
                className="w-full rounded border p-2"
                value={buildForm.db_path}
                onChange={(e) => setBuildForm((p) => ({ ...p, db_path: e.target.value }))}
              />
              <button
                type="button"
                onClick={async () => {
                  const path = await pickSystemSavePath("monthly.duckdb", ".duckdb");
                  if (path) setBuildForm((p) => ({ ...p, db_path: path }));
                }}
                className="rounded border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Browse...
              </button>
            </div>
          </Field>
          <Field label="Input parquet/csv path or glob" help="Supports wildcards. Example: G:/MASTER_PARQUET/MAR_2026/**/*.parquet">
            <div className="flex gap-2">
              <input
                className="w-full rounded border p-2"
                value={buildForm.input_path}
                onChange={(e) => setBuildForm((p) => ({ ...p, input_path: e.target.value }))}
              />
              <button
                type="button"
                onClick={async () => {
                  const folder = await pickSystemFolder();
                  if (folder) setBuildForm((p) => ({ ...p, input_path: `${folder}/*` }));
                }}
                className="rounded border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Folder...
              </button>
            </div>
          </Field>
          <Field label="Object name in DuckDB" help="Target table/view name. Example: master or master_MAR_2026">
            <input className="w-full rounded border p-2" value={buildForm.object_name} onChange={(e) => setBuildForm((p) => ({ ...p, object_name: e.target.value }))} />
          </Field>
          <Field label="Object type" help="Choose TABLE for materialized data, VIEW for virtual query object.">
            <select className="w-full rounded border p-2" value={buildForm.object_type} onChange={(e) => setBuildForm((p) => ({ ...p, object_type: e.target.value as "TABLE" | "VIEW" }))}>
              <option value="TABLE">TABLE</option>
              <option value="VIEW">VIEW</option>
            </select>
          </Field>
          <Field label="Month label (optional)" help="Used in success message only. Example: MAR_2026">
            <input className="w-full rounded border p-2" value={buildForm.month_label} onChange={(e) => setBuildForm((p) => ({ ...p, month_label: e.target.value }))} />
          </Field>
          <Field label="Replace existing object" help="If checked, existing table/view with same name is dropped first.">
            <label className="flex items-center gap-2 rounded border p-2 text-sm">
              <input type="checkbox" checked={buildForm.replace} onChange={(e) => setBuildForm((p) => ({ ...p, replace: e.target.checked }))} />
              Replace existing
            </label>
          </Field>
        </div>
        <button onClick={runBuild} disabled={isBuildRunning} className="mt-3 rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-60">
          {isBuildRunning ? "Running..." : "Run Build DuckDB"}
        </button>
        <pre className="mt-3 overflow-x-auto rounded bg-slate-950 p-3 text-xs text-slate-100">{`python build_duckdb.py --db "${buildForm.db_path}" --input "${buildForm.input_path}" --object-name ${buildForm.object_name} --object-type ${buildForm.object_type}${buildForm.replace ? " --replace" : ""}${buildForm.month_label ? ` --month-label ${buildForm.month_label}` : ""}`}</pre>
        {buildMessage && <p className="mt-2 text-sm text-slate-700">{buildMessage}</p>}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">2) Convert CSV/GZ to Parquet</h2>
        <p className="mt-2 text-sm text-slate-600">Run now from UI, or use script path: <code>csv_to_prequat.py</code></p>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <Field label="Input CSV/GZ path or glob" help="Example: G:/MASTER/MAR_2026/*.csv.gz">
            <div className="flex gap-2">
              <input
                className="w-full rounded border p-2 md:col-span-2"
                value={parquetForm.input_path}
                onChange={(e) => setParquetForm((p) => ({ ...p, input_path: e.target.value }))}
              />
              <button
                type="button"
                onClick={async () => {
                  const path = await pickSystemFile("data");
                  if (path) setParquetForm((p) => ({ ...p, input_path: path }));
                }}
                className="rounded border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                File...
              </button>
              <button
                type="button"
                onClick={async () => {
                  const folder = await pickSystemFolder();
                  if (folder) setParquetForm((p) => ({ ...p, input_path: `${folder}/*.csv.gz` }));
                }}
                className="rounded border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Folder...
              </button>
            </div>
          </Field>
          <Field label="Output parquet file path" help="Example: G:/MASTER_PARQUET/MAR_2026/master.parquet">
            <div className="flex gap-2">
              <input
                className="w-full rounded border p-2 md:col-span-2"
                value={parquetForm.output_path}
                onChange={(e) => setParquetForm((p) => ({ ...p, output_path: e.target.value }))}
              />
              <button
                type="button"
                onClick={async () => {
                  const path = await pickSystemSavePath("master.parquet", ".parquet");
                  if (path) setParquetForm((p) => ({ ...p, output_path: path }));
                }}
                className="rounded border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Browse...
              </button>
            </div>
          </Field>
          <Field label="Compression codec" help="Recommended: snappy or zstd">
            <input className="w-full rounded border p-2" value={parquetForm.compression} onChange={(e) => setParquetForm((p) => ({ ...p, compression: e.target.value }))} />
          </Field>
        </div>
        <button onClick={runParquet} disabled={isParquetRunning} className="mt-3 rounded bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60">
          {isParquetRunning ? "Running..." : "Run CSV → Parquet"}
        </button>
        <pre className="mt-3 overflow-x-auto rounded bg-slate-950 p-3 text-xs text-slate-100">{`python csv_to_prequat.py --input "${parquetForm.input_path}" --output "${parquetForm.output_path}" --compression ${parquetForm.compression}`}</pre>
        {parquetMessage && <p className="mt-2 text-sm text-slate-700">{parquetMessage}</p>}
      </div>
    </div>
  );
};
