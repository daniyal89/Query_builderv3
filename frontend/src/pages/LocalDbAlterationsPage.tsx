import React, { useEffect, useState } from "react";
import { pickSystemFile, pickSystemSavePath } from "../api/systemApi";
import { StatusAlert } from "../components/common/StatusAlert";
import {
  AlterDbDerivedPayload,
  AlterDbJobStatusResponse,
  AlterDbJoinPayload,
  AlterDbDropPayload,
  getAlterDbStatus,
  startAlterDbDerived,
  startAlterDbJoin,
  startAlterDbDrop,
  stopAlterDbJob,
} from "../api/alterDbApi";

const ALTER_DB_STORAGE_KEY = "alter_db_page_state_v2";

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

interface FieldProps {
  label: string;
  help?: string;
  children: React.ReactNode;
}

const Field: React.FC<FieldProps> = ({ label, help, children }) => (
  <div className="space-y-1">
    <label className="block text-sm font-semibold text-slate-700">{label}</label>
    {children}
    {help && <p className="text-xs text-slate-500">{help}</p>}
  </div>
);

function readInitialState() {
  try {
    const raw = window.localStorage.getItem(ALTER_DB_STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return {
    mode: "derived" as "derived" | "join" | "drop",
    db_path: "",
    table_name: "",
    new_column_name: "",
    column_type: "VARCHAR",
    sql_formula: "",
    file_path: "",
    join_master_col: "",
    join_file_col: "",
    value_file_col: "",
  };
}

export const LocalDbAlterationsPage: React.FC = () => {
  const [form, setForm] = useState(readInitialState());
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<AlterDbJobStatusResponse | null>(null);
  const [message, setMessage] = useState("");
  const [nowMs, setNowMs] = useState<number>(Date.now());

  const isRunning = status?.status === "queued" || status?.status === "running" || status?.status === "cancelling";
  const showSuccess = status?.status === "completed" && Boolean(message.trim());
  const showError = status?.status === "failed";
  const runSeconds = status?.started_at
    ? Math.max(0, Math.floor((status.finished_at ? new Date(status.finished_at).getTime() : nowMs) - new Date(status.started_at).getTime()) / 1000)
    : null;

  useEffect(() => {
    window.localStorage.setItem(ALTER_DB_STORAGE_KEY, JSON.stringify(form));
  }, [form]);

  useEffect(() => {
    if (!isRunning) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isRunning]);

  useEffect(() => {
    if (!jobId) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await getAlterDbStatus(jobId);
        setStatus(latest);
        if (latest.status === "completed" || latest.status === "failed" || latest.status === "cancelled") {
          setJobId(null);
          setMessage(latest.message);
        }
      } catch (error: any) {
        setJobId(null);
        setStatus((prev) => (prev ? { ...prev, status: "failed" } : null));
        setMessage(error?.response?.data?.detail || error?.message || "Failed to fetch status.");
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [jobId]);

  const updateForm = (updates: Partial<typeof form>) => setForm((prev: any) => ({ ...prev, ...updates }));

  const runDerived = async () => {
    if (!form.db_path.trim() || !form.table_name.trim() || !form.new_column_name.trim() || !form.sql_formula.trim()) {
      setMessage("Please fill in all required fields (DB Path, Table Name, Column Name, SQL Formula).");
      return;
    }
    setMessage("");
    try {
      const payload: AlterDbDerivedPayload = {
        db_path: form.db_path,
        table_name: form.table_name,
        new_column_name: form.new_column_name,
        column_type: form.column_type,
        sql_formula: form.sql_formula,
      };
      const res = await startAlterDbDerived(payload);
      setJobId(res.job_id);
      setStatus(res);
      setMessage(`Derived job started. Job ID: ${res.job_id}`);
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || "Failed to start job.");
    }
  };

  const runJoin = async () => {
    if (!form.db_path.trim() || !form.table_name.trim() || !form.new_column_name.trim() || !form.file_path.trim() || !form.join_master_col.trim() || !form.join_file_col.trim() || !form.value_file_col.trim()) {
      setMessage("Please fill in all required fields for the Join operation.");
      return;
    }
    setMessage("");
    try {
      const payload: AlterDbJoinPayload = {
        db_path: form.db_path,
        table_name: form.table_name,
        new_column_name: form.new_column_name,
        column_type: form.column_type,
        file_path: form.file_path,
        join_master_col: form.join_master_col,
        join_file_col: form.join_file_col,
        value_file_col: form.value_file_col,
      };
      const res = await startAlterDbJoin(payload);
      setJobId(res.job_id);
      setStatus(res);
      setMessage(`Join job started. Job ID: ${res.job_id}`);
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || "Failed to start job.");
    }
  };

  const runDrop = async () => {
    if (!form.db_path.trim() || !form.table_name.trim() || !form.new_column_name.trim()) {
      setMessage("Please fill in DB Path, Table Name, and Column Name to drop.");
      return;
    }
    setMessage("");
    try {
      const payload: AlterDbDropPayload = {
        db_path: form.db_path,
        table_name: form.table_name,
        column_name: form.new_column_name,
      };
      const res = await startAlterDbDrop(payload);
      setJobId(res.job_id);
      setStatus(res);
      setMessage(`Drop job started. Job ID: ${res.job_id}`);
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || "Failed to start job.");
    }
  };

  const stopJob = async () => {
    if (!jobId) return;
    try {
      const res = await stopAlterDbJob(jobId);
      setStatus(res);
      setMessage(res.message);
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || "Unable to stop job.");
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      {isRunning && (
        <div className="sticky top-2 z-20 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-xs text-indigo-800 shadow-sm">
          Active: Database Alteration ({status?.status ?? "running"})
          {runSeconds !== null && <p className="mt-1 text-indigo-700">Runtime: {formatDuration(runSeconds)}</p>}
        </div>
      )}
      {showError && (
        <StatusAlert tone="error" title="Job Failed">
          <p>{message}</p>
        </StatusAlert>
      )}
      {showSuccess && (
        <StatusAlert tone="success" title="Success">
          <p>{message}</p>
        </StatusAlert>
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Modify Local Master Table</h2>
        <p className="mt-1 text-sm text-slate-600">
          Permanently add or remove a column from an existing DuckDB database table.
        </p>

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <Field label="Target DuckDB file path" help="Example: G:/MASTER/uppcl_latest.duckdb">
            <div className="flex gap-2">
              <input className="w-full rounded border p-2" value={form.db_path} onChange={(e) => updateForm({ db_path: e.target.value })} />
              <button type="button" onClick={async () => { const path = await pickSystemSavePath("monthly.duckdb", ".duckdb"); if (path) updateForm({ db_path: path }); }} className="rounded border border-slate-300 bg-slate-50 px-3 text-sm font-medium hover:bg-slate-100">Browse...</button>
            </div>
          </Field>
          <Field label="Table Name" help="Example: MASTER_MAR_2026">
            <input className="w-full rounded border p-2" value={form.table_name} onChange={(e) => updateForm({ table_name: e.target.value })} />
          </Field>
          <Field label={form.mode === "drop" ? "Column Name to Drop" : "New Column Name"} help="The name of the column.">
            <input className="w-full rounded border p-2" value={form.new_column_name} onChange={(e) => updateForm({ new_column_name: e.target.value })} />
          </Field>
          {form.mode !== "drop" && (
            <Field label="Data Type" help="The SQL data type for the new column.">
              <select className="w-full rounded border p-2" value={form.column_type} onChange={(e) => updateForm({ column_type: e.target.value })}>
                <option value="VARCHAR">VARCHAR (Text)</option>
                <option value="INTEGER">INTEGER (Whole Number)</option>
                <option value="DOUBLE">DOUBLE (Decimal)</option>
                <option value="BOOLEAN">BOOLEAN (True/False)</option>
              </select>
            </Field>
          )}
        </div>

        <div className="mt-6 border-b border-slate-200">
          <div className="flex space-x-4">
            <button
              onClick={() => updateForm({ mode: "derived" })}
              className={`pb-2 text-sm font-medium ${form.mode === "derived" ? "border-b-2 border-indigo-600 text-indigo-600" : "text-slate-500 hover:text-slate-700"}`}
            >
              Derived Column (Formula)
            </button>
            <button
              onClick={() => updateForm({ mode: "join" })}
              className={`pb-2 text-sm font-medium ${form.mode === "join" ? "border-b-2 border-indigo-600 text-indigo-600" : "text-slate-500 hover:text-slate-700"}`}
            >
              Enrich from File (Join)
            </button>
            <button
              onClick={() => updateForm({ mode: "drop" })}
              className={`pb-2 text-sm font-medium ${form.mode === "drop" ? "border-b-2 border-red-600 text-red-600" : "text-slate-500 hover:text-slate-700"}`}
            >
              Drop Column
            </button>
          </div>
        </div>

        <div className="mt-6">
          {form.mode === "derived" && (
            <div className="space-y-4 rounded bg-slate-50 p-4 border border-slate-100">
              <Field label="SQL Formula" help="e.g. 1 + 1, or CONCAT(col1, '_', col2), or CASE WHEN col > 10 THEN 'High' ELSE 'Low' END">
                <textarea
                  rows={4}
                  className="w-full rounded border p-2 font-mono text-sm"
                  value={form.sql_formula}
                  onChange={(e) => updateForm({ sql_formula: e.target.value })}
                  placeholder="Enter standard DuckDB SQL..."
                />
              </Field>
            </div>
          )}

          {form.mode === "join" && (
            <div className="space-y-4 rounded bg-slate-50 p-4 border border-slate-100">
              <Field label="Source File (CSV/Excel)" help="The file containing the new data to pull in.">
                <div className="flex gap-2">
                  <input className="w-full rounded border p-2" value={form.file_path} onChange={(e) => updateForm({ file_path: e.target.value })} />
                  <button type="button" onClick={async () => { const path = await pickSystemFile(); if (path) updateForm({ file_path: path }); }} className="rounded border border-slate-300 bg-white px-3 text-sm font-medium hover:bg-slate-100">Browse...</button>
                </div>
              </Field>
              <div className="grid gap-4 md:grid-cols-3">
                <Field label="Master Table Key" help="Column in DuckDB to match on.">
                  <input className="w-full rounded border p-2" value={form.join_master_col} onChange={(e) => updateForm({ join_master_col: e.target.value })} />
                </Field>
                <Field label="File Key" help="Column in the File to match on.">
                  <input className="w-full rounded border p-2" value={form.join_file_col} onChange={(e) => updateForm({ join_file_col: e.target.value })} />
                </Field>
                <Field label="Value Column" help="Column in the File to pull data from.">
                  <input className="w-full rounded border p-2" value={form.value_file_col} onChange={(e) => updateForm({ value_file_col: e.target.value })} />
                </Field>
              </div>
            </div>
          )}

          {form.mode === "drop" && (
            <div className="rounded bg-red-50 p-4 border border-red-100">
              <p className="text-sm text-red-800 font-medium">Warning: This will permanently delete the specified column and all its data from the table.</p>
            </div>
          )}
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button
            onClick={form.mode === "derived" ? runDerived : form.mode === "join" ? runJoin : runDrop}
            disabled={isRunning}
            className={`rounded px-5 py-2 text-sm font-semibold text-white disabled:opacity-60 ${form.mode === "drop" ? "bg-red-600 hover:bg-red-700" : "bg-indigo-600 hover:bg-indigo-700"}`}
          >
            {isRunning ? "Executing..." : form.mode === "drop" ? "Drop Column" : `Run ${form.mode === "derived" ? "Derived Column" : "Join"}`}
          </button>
          {isRunning && (
            <button
              onClick={stopJob}
              disabled={status?.status === "cancelling"}
              className="rounded border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-60"
            >
              {status?.status === "cancelling" ? "Stopping..." : "Stop Job"}
            </button>
          )}
        </div>

        {status && (
          <div className="mt-4 rounded border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-slate-800">Job Progress</span>
              <span className="rounded-full bg-slate-200 px-2 py-1 text-xs font-semibold text-slate-700 uppercase">
                {status.status}
              </span>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-slate-200">
              <div
                className={`h-full transition-all ${showError ? "bg-red-500" : "bg-indigo-600"}`}
                style={{ width: `${status.progress_percent ?? 0}%` }}
              />
            </div>
            <div className="mt-2 flex justify-between text-xs text-slate-500">
              <span>{status.message}</span>
              <span>{status.progress_percent ?? 0}%</span>
            </div>
          </div>
        )}

        {message && !isRunning && !showSuccess && !showError && (
          <p className="mt-4 text-sm text-slate-700">{message}</p>
        )}
      </div>
    </div>
  );
};
