import React, { useEffect, useMemo, useState } from "react";
import {
  BuildDuckDbJobStatusResponse,
  CsvParquetJobStatusResponse,
  getBuildDuckDbJobStatus,
  getCsvToParquetJobStatus,
  startBuildDuckDbJob,
  stopBuildDuckDbJob,
  startCsvToParquetJob,
  stopCsvToParquetJob,
} from "../api/sidebarToolsApi";
import { pickSystemFile, pickSystemFolder, pickSystemSavePath } from "../api/systemApi";

interface FieldProps {
  label: string;
  help: string;
  children: React.ReactNode;
}

const PARQUET_FORM_STORAGE_KEY = "sidebar_tools_parquet_form_v1";
const PARQUET_JOB_STORAGE_KEY = "sidebar_tools_parquet_job_v1";
const BUILD_FORM_STORAGE_KEY = "sidebar_tools_build_form_v1";
const BUILD_STATUS_STORAGE_KEY = "sidebar_tools_build_status_v1";
const UPPCL_PRESET_STORAGE_KEY = "sidebar_tools_uppcl_preset_paths_v1";
const DATA_TOOLS_HISTORY_STORAGE_KEY = "sidebar_tools_job_history_v1";

type UppclPresetPaths = {
  build_db_path: string;
  build_input_path: string;
  parquet_input_path: string;
  parquet_output_path: string;
};

type PersistedParquetJobState = {
  jobId: string | null;
  status: CsvParquetJobStatusResponse | null;
  message: string;
};

type PersistedBuildJobState = {
  jobId: string | null;
  status: BuildDuckDbJobStatusResponse | null;
  message: string;
};

type ToolHistoryItem = {
  id: string;
  tool: "build" | "parquet";
  status: string;
  message: string;
  timestamp: string;
  run_seconds?: number | null;
};

function isTransientPollTimeout(error: any): boolean {
  const code = typeof error?.code === "string" ? error.code : "";
  const message = typeof error?.message === "string" ? error.message.toLowerCase() : "";
  return code === "ECONNABORTED" || message.includes("timeout");
}

function isParquetTerminalStatus(status: CsvParquetJobStatusResponse | null): boolean {
  return status?.status === "completed" || status?.status === "failed" || status?.status === "cancelled";
}

function readInitialParquetForm() {
  const fallback = {
    input_path: "./data/MAR_2026/*.csv.gz",
    output_path: "./parquet/MAR_2026",
    compression: "zstd",
    hir_file: "",
    supp_mapper_file: "",
  };
  try {
    const raw = window.localStorage.getItem(PARQUET_FORM_STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<typeof fallback>;
    return {
      input_path: typeof parsed.input_path === "string" ? parsed.input_path : fallback.input_path,
      output_path: typeof parsed.output_path === "string" ? parsed.output_path : fallback.output_path,
      compression: typeof parsed.compression === "string" ? parsed.compression : fallback.compression,
      hir_file: typeof parsed.hir_file === "string" ? parsed.hir_file : fallback.hir_file,
      supp_mapper_file: typeof parsed.supp_mapper_file === "string" ? parsed.supp_mapper_file : fallback.supp_mapper_file,
    };
  } catch {
    return fallback;
  }
}

function readInitialParquetJobState(): { jobId: string | null; status: CsvParquetJobStatusResponse | null; message: string } {
  try {
    const raw = window.localStorage.getItem(PARQUET_JOB_STORAGE_KEY);
    if (!raw) return { jobId: null, status: null, message: "" };
    const parsed = JSON.parse(raw) as Partial<PersistedParquetJobState>;
    const jobId = typeof parsed.jobId === "string" && parsed.jobId.trim() ? parsed.jobId : null;
    const status = parsed.status ?? null;
    const message = typeof parsed.message === "string" ? parsed.message : "";
    return {
      jobId: jobId && !isParquetTerminalStatus(status as CsvParquetJobStatusResponse | null) ? jobId : null,
      status,
      message,
    };
  } catch {
    return { jobId: null, status: null, message: "" };
  }
}

function readInitialBuildForm(): {
  db_path: string;
  input_path: string;
  object_name: string;
  object_type: "TABLE" | "VIEW";
  replace: boolean;
  month_label: string;
} {
  const fallback: {
    db_path: string;
    input_path: string;
    object_name: string;
    object_type: "TABLE" | "VIEW";
    replace: boolean;
    month_label: string;
  } = {
    db_path: "./monthly.duckdb",
    input_path: "./data/MAR_2026/*.csv.gz",
    object_name: "MASTER_MAR_2026",
    object_type: "TABLE",
    replace: true,
    month_label: "MAR_2026",
  };
  try {
    const raw = window.localStorage.getItem(BUILD_FORM_STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<typeof fallback>;
    return {
      db_path: typeof parsed.db_path === "string" ? parsed.db_path : fallback.db_path,
      input_path: typeof parsed.input_path === "string" ? parsed.input_path : fallback.input_path,
      object_name: typeof parsed.object_name === "string" ? parsed.object_name : fallback.object_name,
      object_type: parsed.object_type === "VIEW" ? "VIEW" : "TABLE",
      replace: typeof parsed.replace === "boolean" ? parsed.replace : fallback.replace,
      month_label: typeof parsed.month_label === "string" ? parsed.month_label : fallback.month_label,
    };
  } catch {
    return fallback;
  }
}

function normalizeMonthSuffix(monthLabel: string): string {
  return monthLabel.trim().toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function isBuildTerminalStatus(status: BuildDuckDbJobStatusResponse | null): boolean {
  return status?.status === "completed" || status?.status === "failed" || status?.status === "cancelled";
}

function formatDuration(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const hh = Math.floor(safe / 3600);
  const mm = Math.floor((safe % 3600) / 60);
  const ss = safe % 60;
  if (hh > 0) return `${hh}h ${mm}m ${ss}s`;
  if (mm > 0) return `${mm}m ${ss}s`;
  return `${ss}s`;
}

function parseIsoDate(value?: string | null): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function calculateRunSeconds(startedAt?: string | null, finishedAt?: string | null, nowMs?: number): number | null {
  const start = parseIsoDate(startedAt);
  if (!start) return null;
  const end = parseIsoDate(finishedAt) ?? new Date(nowMs ?? Date.now());
  return Math.max(0, Math.floor((end.getTime() - start.getTime()) / 1000));
}

function readInitialBuildStatus(): { jobId: string | null; status: BuildDuckDbJobStatusResponse | null; message: string } {
  try {
    const raw = window.localStorage.getItem(BUILD_STATUS_STORAGE_KEY);
    if (!raw) return { jobId: null, status: null, message: "" };
    const parsed = JSON.parse(raw) as Partial<PersistedBuildJobState>;
    const jobId = typeof parsed.jobId === "string" && parsed.jobId.trim() ? parsed.jobId : null;
    const status = parsed.status ?? null;
    return {
      jobId: jobId && !isBuildTerminalStatus(status as BuildDuckDbJobStatusResponse | null) ? jobId : null,
      status,
      message: typeof parsed.message === "string" ? parsed.message : "",
    };
  } catch {
    return { jobId: null, status: null, message: "" };
  }
}

function getDefaultUppclPresetPaths(): UppclPresetPaths {
  return {
    build_db_path: "G:/MASTER/uppcl_latest.duckdb",
    build_input_path: "G:/MASTER_PARQUET/MAR_2026/**/*.parquet",
    parquet_input_path: "G:/MASTER/MAR_2026/*.csv.gz",
    parquet_output_path: "G:/MASTER_PARQUET/MAR_2026",
  };
}

function readInitialUppclPresetPaths(): UppclPresetPaths {
  const fallback = getDefaultUppclPresetPaths();
  try {
    const raw = window.localStorage.getItem(UPPCL_PRESET_STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<UppclPresetPaths>;
    return {
      build_db_path: typeof parsed.build_db_path === "string" ? parsed.build_db_path : fallback.build_db_path,
      build_input_path: typeof parsed.build_input_path === "string" ? parsed.build_input_path : fallback.build_input_path,
      parquet_input_path: typeof parsed.parquet_input_path === "string" ? parsed.parquet_input_path : fallback.parquet_input_path,
      parquet_output_path: typeof parsed.parquet_output_path === "string" ? parsed.parquet_output_path : fallback.parquet_output_path,
    };
  } catch {
    return fallback;
  }
}

function readInitialToolHistory(): ToolHistoryItem[] {
  try {
    const raw = window.localStorage.getItem(DATA_TOOLS_HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ToolHistoryItem[];
    return Array.isArray(parsed) ? parsed.slice(0, 10) : [];
  } catch {
    return [];
  }
}

const Field: React.FC<FieldProps> = ({ label, help, children }) => (
  <div className="space-y-1">
    <label className="block text-sm font-semibold text-slate-700">{label}</label>
    {children}
    <p className="text-xs text-slate-500">{help}</p>
  </div>
);

export const SidebarToolsPage: React.FC = () => {
  const initialBuildForm = useMemo(() => readInitialBuildForm(), []);
  const initialBuildStatus = useMemo(() => readInitialBuildStatus(), []);
  const initialUppclPresetPaths = useMemo(() => readInitialUppclPresetPaths(), []);
  const initialParquetForm = useMemo(() => readInitialParquetForm(), []);
  const initialParquetJobState = useMemo(() => readInitialParquetJobState(), []);
  const initialToolHistory = useMemo(() => readInitialToolHistory(), []);
  const [buildForm, setBuildForm] = useState({
    db_path: initialBuildForm.db_path,
    input_path: initialBuildForm.input_path,
    object_name: initialBuildForm.object_name,
    object_type: initialBuildForm.object_type,
    replace: initialBuildForm.replace,
    month_label: initialBuildForm.month_label,
  });
  const [parquetForm, setParquetForm] = useState({
    input_path: initialParquetForm.input_path,
    output_path: initialParquetForm.output_path,
    compression: initialParquetForm.compression,
    hir_file: initialParquetForm.hir_file,
    supp_mapper_file: initialParquetForm.supp_mapper_file,
  });
  const [buildMessage, setBuildMessage] = useState(initialBuildStatus.message);
  const [buildJobId, setBuildJobId] = useState<string | null>(initialBuildStatus.jobId);
  const [buildStatus, setBuildStatus] = useState<BuildDuckDbJobStatusResponse | null>(initialBuildStatus.status);
  const [parquetMessage, setParquetMessage] = useState(initialParquetJobState.message);
  const [parquetJobId, setParquetJobId] = useState<string | null>(initialParquetJobState.jobId);
  const [parquetStatus, setParquetStatus] = useState<CsvParquetJobStatusResponse | null>(initialParquetJobState.status);
  const [statusNote, setStatusNote] = useState("Use labels below and fill full paths before running.");
  const [uppclPresetPaths, setUppclPresetPaths] = useState<UppclPresetPaths>(initialUppclPresetPaths);
  const [toolHistory, setToolHistory] = useState<ToolHistoryItem[]>(initialToolHistory);
  const [nowMs, setNowMs] = useState<number>(Date.now());
  const isParquetRunning = parquetStatus?.status === "queued" || parquetStatus?.status === "running" || parquetStatus?.status === "cancelling";
  const isBuildRunning = buildStatus?.status === "queued" || buildStatus?.status === "running" || buildStatus?.status === "cancelling";
  const buildRunSeconds = calculateRunSeconds(buildStatus?.started_at, buildStatus?.finished_at, nowMs);
  const parquetRunSeconds = calculateRunSeconds(parquetStatus?.started_at, parquetStatus?.finished_at, nowMs);
  const parquetProgress = useMemo(() => {
    if (!parquetStatus || parquetStatus.total_files <= 0) return 0;
    return Math.min(100, Math.round((parquetStatus.processed_files / parquetStatus.total_files) * 100));
  }, [parquetStatus]);

  useEffect(() => {
    window.localStorage.setItem(BUILD_FORM_STORAGE_KEY, JSON.stringify(buildForm));
  }, [buildForm]);

  useEffect(() => {
    if (!buildJobId && !buildStatus && !buildMessage.trim()) {
      window.localStorage.removeItem(BUILD_STATUS_STORAGE_KEY);
      return;
    }
    const payload: PersistedBuildJobState = {
      jobId: buildJobId,
      status: buildStatus,
      message: buildMessage,
    };
    window.localStorage.setItem(BUILD_STATUS_STORAGE_KEY, JSON.stringify(payload));
  }, [buildJobId, buildStatus, buildMessage]);

  useEffect(() => {
    window.localStorage.setItem(UPPCL_PRESET_STORAGE_KEY, JSON.stringify(uppclPresetPaths));
  }, [uppclPresetPaths]);

  useEffect(() => {
    window.localStorage.setItem(DATA_TOOLS_HISTORY_STORAGE_KEY, JSON.stringify(toolHistory.slice(0, 10)));
  }, [toolHistory]);

  useEffect(() => {
    if (!isBuildRunning && !isParquetRunning) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isBuildRunning, isParquetRunning]);

  useEffect(() => {
    window.localStorage.setItem(PARQUET_FORM_STORAGE_KEY, JSON.stringify(parquetForm));
  }, [parquetForm]);

  useEffect(() => {
    if (!parquetJobId && !parquetStatus && !parquetMessage.trim()) {
      window.localStorage.removeItem(PARQUET_JOB_STORAGE_KEY);
      return;
    }
    const payload: PersistedParquetJobState = {
      jobId: parquetJobId,
      status: parquetStatus,
      message: parquetMessage,
    };
    window.localStorage.setItem(PARQUET_JOB_STORAGE_KEY, JSON.stringify(payload));
  }, [parquetJobId, parquetStatus, parquetMessage]);

  useEffect(() => {
    if (!parquetJobId) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await getCsvToParquetJobStatus(parquetJobId);
        setParquetStatus(latest);
        if (latest.status === "completed" || latest.status === "failed" || latest.status === "cancelled") {
          setParquetJobId(null);
          const finalMessage = latest.message + (latest.output_path ? ` Output: ${latest.output_path}` : "");
          setParquetMessage(finalMessage);
          setToolHistory((current) => [{ id: `${Date.now()}-parquet`, tool: "parquet" as const, status: latest.status, message: finalMessage, timestamp: new Date().toISOString(), run_seconds: calculateRunSeconds(latest.started_at, latest.finished_at) }, ...current].slice(0, 10));
        }
      } catch (error: any) {
        if (isTransientPollTimeout(error)) {
          setParquetMessage("Status refresh timed out. Job is still running; retrying automatically...");
          return;
        }
        const detail = error?.response?.data?.detail || error?.message || "Failed to fetch conversion status.";
        setParquetMessage(detail);
        setParquetJobId(null);
        setParquetStatus((previous) =>
          previous
            ? {
                ...previous,
                status: "failed",
                message:
                  error?.response?.status === 404
                    ? "Background CSV→Parquet job was not found. Start a new conversion."
                    : detail,
              }
            : null,
        );
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [parquetJobId]);

  useEffect(() => {
    if (!buildJobId) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await getBuildDuckDbJobStatus(buildJobId);
        setBuildStatus(latest);
        if (latest.status === "completed" || latest.status === "failed" || latest.status === "cancelled") {
          setBuildJobId(null);
          const finalMessage = latest.message + (latest.output_path ? ` Output: ${latest.output_path}` : "");
          setBuildMessage(finalMessage);
          setToolHistory((current) => [{ id: `${Date.now()}-build`, tool: "build" as const, status: latest.status, message: finalMessage, timestamp: new Date().toISOString(), run_seconds: calculateRunSeconds(latest.started_at, latest.finished_at) }, ...current].slice(0, 10));
        }
      } catch (error: any) {
        if (isTransientPollTimeout(error)) {
          setBuildMessage("Status refresh timed out. Build is still running; retrying automatically...");
          return;
        }
        const detail = error?.response?.data?.detail || error?.message || "Failed to fetch build status.";
        setBuildMessage(detail);
        setBuildJobId(null);
        setBuildStatus((previous) =>
          previous
            ? {
                ...previous,
                status: "failed",
                message: error?.response?.status === 404 ? "Background build job not found. Start a new build." : detail,
              }
            : null,
        );
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [buildJobId]);

  const applyUppclPreset = () => {
    const monthLabel = "MAR_2026";
    setBuildForm({
      db_path: uppclPresetPaths.build_db_path,
      input_path: uppclPresetPaths.build_input_path,
      object_name: `MASTER_${normalizeMonthSuffix(monthLabel)}`,
      object_type: "TABLE",
      replace: true,
      month_label: monthLabel,
    });
    setParquetForm({
      input_path: uppclPresetPaths.parquet_input_path,
      output_path: uppclPresetPaths.parquet_output_path,
      compression: "snappy",
      hir_file: "",
      supp_mapper_file: "",
    });
    setStatusNote("UPPCL preset applied. Adjust month/path values if needed.");
  };

  const resetUppclPresetPaths = () => {
    const defaults = getDefaultUppclPresetPaths();
    setUppclPresetPaths(defaults);
    setStatusNote("UPPCL preset paths reset to defaults.");
  };

  const runBuild = async () => {
    if (!buildForm.db_path.trim() || !buildForm.input_path.trim() || !buildForm.object_name.trim()) {
      setBuildMessage("Pre-check failed: db path, input path and object name are required.");
      return;
    }

    const monthSuffix = normalizeMonthSuffix(buildForm.month_label);
    const objectName = buildForm.object_name.trim();
    if (objectName.toLowerCase() === "master" && monthSuffix) {
      setBuildMessage(
        `Safety check: use a month-specific object name like MASTER_${monthSuffix} to avoid replacing another month's master.`
      );
      return;
    }

    setBuildMessage("");
    try {
      const started = await startBuildDuckDbJob({
        ...buildForm,
        object_name: objectName,
      });
      setBuildJobId(started.job_id);
      setBuildStatus({
        job_id: started.job_id,
        status: "queued",
        message: started.message,
        progress_percent: 0,
      });
      setBuildMessage(`Build DuckDB job started. Job ID: ${started.job_id}`);
    } catch (error: any) {
      const errorMessage = error?.response?.data?.detail || error?.message || "Build failed.";
      setBuildMessage(errorMessage);
      setBuildStatus((previous) => (previous ? { ...previous, status: "failed", message: errorMessage } : null));
    }
  };

  const stopBuild = async () => {
    if (!buildJobId) return;
    try {
      const stopped = await stopBuildDuckDbJob(buildJobId);
      setBuildStatus(stopped);
      setBuildMessage(stopped.message);
    } catch (error: any) {
      setBuildMessage(error?.response?.data?.detail || error?.message || "Unable to stop build.");
    }
  };

  const runParquet = async () => {
    if (!parquetForm.input_path.trim() || !parquetForm.output_path.trim()) {
      setParquetMessage("Pre-check failed: input and output paths are required.");
      return;
    }
    setParquetMessage("");
    try {
      const started = await startCsvToParquetJob({
        ...parquetForm,
        hir_file: parquetForm.hir_file.trim() || undefined,
        supp_mapper_file: parquetForm.supp_mapper_file.trim() || undefined,
      });
      setParquetJobId(started.job_id);
      setParquetStatus({
        job_id: started.job_id,
        status: "queued",
        message: started.message,
        processed_files: 0,
        total_files: 0,
        skipped_files: 0,
      });
      setParquetMessage(`CSV→Parquet job started. Job ID: ${started.job_id}`);
    } catch (error: any) {
      setParquetMessage(error?.response?.data?.detail || error?.message || "Conversion failed.");
    }
  };

  const stopParquet = async () => {
    if (!parquetJobId) return;
    try {
      const stopped = await stopCsvToParquetJob(parquetJobId);
      setParquetStatus(stopped);
      setParquetMessage(stopped.message);
    } catch (error: any) {
      setParquetMessage(error?.response?.data?.detail || error?.message || "Unable to stop conversion.");
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      {(isBuildRunning || isParquetRunning) && (
        <div className="sticky top-2 z-20 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-xs text-indigo-800 shadow-sm">
          Active: {isBuildRunning ? `Build (${buildStatus?.status ?? "running"})` : ""}{isBuildRunning && isParquetRunning ? " | " : ""}{isParquetRunning ? `CSV→Parquet (${parquetStatus?.status ?? "running"})` : ""}
          <p className="mt-1 text-indigo-700">
            Runtime: {isBuildRunning && buildRunSeconds !== null ? `Build ${formatDuration(buildRunSeconds)}` : ""}{isBuildRunning && isParquetRunning ? " | " : ""}{isParquetRunning && parquetRunSeconds !== null ? `CSV→Parquet ${formatDuration(parquetRunSeconds)}` : ""}
          </p>
        </div>
      )}
      {(buildStatus?.status === "failed" || parquetStatus?.status === "failed") && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <p className="font-semibold">Error summary</p>
          {buildStatus?.status === "failed" && <p>Build: {buildMessage}</p>}
          {parquetStatus?.status === "failed" && <p>CSV→Parquet: {parquetMessage}</p>}
        </div>
      )}
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
        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-semibold text-slate-800">UPPCL preset path settings</p>
          <p className="mt-1 text-xs text-slate-500">Update once here. Apply button will use these saved values.</p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <input
              className="w-full rounded border p-2 text-sm"
              value={uppclPresetPaths.build_db_path}
              onChange={(e) => setUppclPresetPaths((p) => ({ ...p, build_db_path: e.target.value }))}
              placeholder="Build DB path"
            />
            <input
              className="w-full rounded border p-2 text-sm"
              value={uppclPresetPaths.build_input_path}
              onChange={(e) => setUppclPresetPaths((p) => ({ ...p, build_input_path: e.target.value }))}
              placeholder="Build input path/glob"
            />
            <input
              className="w-full rounded border p-2 text-sm"
              value={uppclPresetPaths.parquet_input_path}
              onChange={(e) => setUppclPresetPaths((p) => ({ ...p, parquet_input_path: e.target.value }))}
              placeholder="Parquet input path/glob"
            />
            <input
              className="w-full rounded border p-2 text-sm"
              value={uppclPresetPaths.parquet_output_path}
              onChange={(e) => setUppclPresetPaths((p) => ({ ...p, parquet_output_path: e.target.value }))}
              placeholder="Parquet output path"
            />
          </div>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={resetUppclPresetPaths}
              className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
            >
              Reset preset paths
            </button>
          </div>
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
                  const path = await pickSystemFile("data");
                  if (path) setBuildForm((p) => ({ ...p, input_path: path }));
                }}
                className="rounded border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                File...
              </button>
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
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button onClick={runBuild} disabled={isBuildRunning} className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-60">
            {isBuildRunning ? "Running..." : "Run Build DuckDB"}
          </button>
          {isBuildRunning && (
            <button onClick={stopBuild} disabled={buildStatus?.status === "cancelling"} className="rounded border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-60">
              {buildStatus?.status === "cancelling" ? "Stopping..." : "Stop build"}
            </button>
          )}
        </div>
        <div className="mt-3 rounded-xl border border-blue-200 bg-white p-4 text-sm text-slate-700 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-base font-semibold text-slate-900">Build DuckDB status</p>
              <p className="text-xs text-slate-500">{buildStatus?.message || "No build run yet."}</p>
            </div>
            <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700">{buildStatus?.status ?? "idle"}</span>
          </div>
          <div className="mt-3 h-3 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full bg-blue-600 transition-all"
              style={{ width: `${buildStatus?.progress_percent ?? 0}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-slate-500">Progress and active job state are persisted across route changes.</p>
          {buildRunSeconds !== null && <p className="mt-1 text-xs text-slate-500">Runtime: {formatDuration(buildRunSeconds)}</p>}
        </div>
        <pre className="mt-3 overflow-x-auto rounded bg-slate-950 p-3 text-xs text-slate-100">{`python build_duckdb.py --db "${buildForm.db_path}" --input "${buildForm.input_path}" --object-name ${buildForm.object_name} --object-type ${buildForm.object_type}${buildForm.replace ? " --replace" : ""}${buildForm.month_label ? ` --month-label ${buildForm.month_label}` : ""}`}</pre>
        {buildMessage && <p className="mt-2 text-sm text-slate-700">{buildMessage}</p>}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">2) Convert CSV/GZ to Parquet</h2>
        <p className="mt-2 text-sm text-slate-600">Run now from UI, or use script path: <code>csv_to_parquet.py</code></p>
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
          <Field label="Output parquet folder path" help="Example: G:/MASTER_PARQUET/MAR_2026 (single file also supports .parquet path)">
            <div className="flex gap-2">
              <input
                className="w-full rounded border p-2 md:col-span-2"
                value={parquetForm.output_path}
                onChange={(e) => setParquetForm((p) => ({ ...p, output_path: e.target.value }))}
              />
              <button
                type="button"
                onClick={async () => {
                  const folder = await pickSystemFolder();
                  if (folder) setParquetForm((p) => ({ ...p, output_path: folder }));
                }}
                className="rounded border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Folder...
              </button>
              <button
                type="button"
                onClick={async () => {
                  const path = await pickSystemSavePath("master.parquet", ".parquet");
                  if (path) setParquetForm((p) => ({ ...p, output_path: path }));
                }}
                className="rounded border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                File...
              </button>
            </div>
          </Field>
          <Field label="Compression codec" help="Recommended: snappy or zstd">
            <input className="w-full rounded border p-2" value={parquetForm.compression} onChange={(e) => setParquetForm((p) => ({ ...p, compression: e.target.value }))} />
          </Field>
          <Field label="HIR lookup Excel (optional)" help="When provided with suppMapper, conversion enriches rows and adds LOAD_KW.">
            <div className="flex gap-2">
              <input className="w-full rounded border p-2" value={parquetForm.hir_file} onChange={(e) => setParquetForm((p) => ({ ...p, hir_file: e.target.value }))} />
              <button
                type="button"
                onClick={async () => {
                  const path = await pickSystemFile("data");
                  if (path) setParquetForm((p) => ({ ...p, hir_file: path }));
                }}
                className="rounded border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                File...
              </button>
            </div>
          </Field>
          <Field label="suppMapper Excel (optional)" help="When provided with HIR, joins SUPPLY_TYPE and adds CATEGORY columns.">
            <div className="flex gap-2">
              <input className="w-full rounded border p-2" value={parquetForm.supp_mapper_file} onChange={(e) => setParquetForm((p) => ({ ...p, supp_mapper_file: e.target.value }))} />
              <button
                type="button"
                onClick={async () => {
                  const path = await pickSystemFile("data");
                  if (path) setParquetForm((p) => ({ ...p, supp_mapper_file: path }));
                }}
                className="rounded border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                File...
              </button>
            </div>
          </Field>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button onClick={runParquet} disabled={isParquetRunning} className="rounded bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60">
            {isParquetRunning ? "Running..." : "Run CSV → Parquet"}
          </button>
          {isParquetRunning && (
            <button onClick={stopParquet} disabled={parquetStatus?.status === "cancelling"} className="rounded border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-60">
              {parquetStatus?.status === "cancelling" ? "Stopping..." : "Stop conversion"}
            </button>
          )}
        </div>
        <pre className="mt-3 overflow-x-auto rounded bg-slate-950 p-3 text-xs text-slate-100">{`python csv_to_parquet.py --input "${parquetForm.input_path}" --output "${parquetForm.output_path}" --compression ${parquetForm.compression}${parquetForm.hir_file ? ` --hir-file "${parquetForm.hir_file}"` : ""}${parquetForm.supp_mapper_file ? ` --supp-mapper-file "${parquetForm.supp_mapper_file}"` : ""}`}</pre>
        {parquetStatus && (
          <div className="mt-3 rounded-xl border border-indigo-200 bg-white p-4 text-sm text-slate-700 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-base font-semibold text-slate-900">CSV→Parquet status</p>
                <p className="text-xs text-slate-500">{parquetStatus.message}</p>
              </div>
              <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700">{parquetStatus.status}</span>
            </div>
            <div className="mt-3 h-3 w-full overflow-hidden rounded-full bg-slate-100">
              <div className="h-full bg-indigo-600 transition-all" style={{ width: `${parquetProgress}%` }} />
            </div>
            <div className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-4">
              <div><span className="font-semibold text-slate-800">Total:</span> {parquetStatus.total_files}</div>
              <div><span className="font-semibold text-slate-800">Processed:</span> {parquetStatus.processed_files}</div>
              <div><span className="font-semibold text-slate-800">Skipped:</span> {parquetStatus.skipped_files}</div>
              <div><span className="font-semibold text-slate-800">Progress:</span> {parquetProgress}%</div>
            </div>
            {parquetRunSeconds !== null && <p className="mt-2 text-xs text-slate-500">Runtime: {formatDuration(parquetRunSeconds)}</p>}
            {parquetStatus.current_file && <p className="mt-2 break-all text-xs text-slate-500">Current file: {parquetStatus.current_file}</p>}
          </div>
        )}
        {parquetMessage && <p className="mt-2 text-sm text-slate-700">{parquetMessage}</p>}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Recent job history</h2>
        {toolHistory.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No completed jobs yet.</p>
        ) : (
          <div className="mt-3 space-y-2">
            {toolHistory.map((item) => (
              <div key={item.id} className="rounded border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700">
                <span className="font-semibold uppercase">{item.tool}</span> • {item.status} • {new Date(item.timestamp).toLocaleString()}{typeof item.run_seconds === "number" ? ` • Runtime: ${formatDuration(item.run_seconds)}` : ""}
                <p className="mt-1 break-all">{item.message}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
