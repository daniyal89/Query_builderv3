import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  MasterSource,
  MonthlyAutomationConfig,
  MonthlyRunMarker,
  MonthlyRunPlan,
  MonthlyRunStatusResponse,
  getActiveMonthlyRun,
  getAutomationConfig,
  getMonthlyRunMarker,
  getMonthlyRunPlan,
  getMonthlyRunStatus,
  saveAutomationConfig,
  startMonthlyRun,
  stopMonthlyRun,
} from "../../api/monthlyRunApi";

const JOB_STORAGE_KEY = "monthly_run_job_v1";
const POLL_MS = 2000;
const CONFIG_RETRY_MS = 5000;
function stepLabel(step: string, source: MasterSource): string {
  if (step === "download") return source === "drive" ? "1 · Download from Google Drive" : "1 · Download from FTP";
  if (step === "upload") return "2 · Upload to Google Drive";
  return "3 · CSV → parquet → DuckDB view";
}

const SOURCE_OPTIONS: { value: MasterSource; label: string; help: string }[] = [
  { value: "ftp", label: "FTP server", help: "Download from FTP, then upload to Google Drive." },
  { value: "drive", label: "Google Drive", help: "Someone already uploaded this month; download it from Drive and skip the upload." },
];

function previousMonthInput(): string {
  const now = new Date();
  const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function errorText(error: unknown): string {
  const e = error as { normalizedMessage?: string; response?: { data?: { detail?: unknown } }; message?: string };
  const detail = e?.response?.data?.detail;
  if (detail && typeof detail === "object" && "message" in (detail as object)) {
    return String((detail as { message: string }).message);
  }
  if (typeof detail === "string") return detail;
  return e?.normalizedMessage || e?.message || "Request failed.";
}

function isActive(status: MonthlyRunStatusResponse | null): boolean {
  return status?.status === "queued" || status?.status === "running" || status?.status === "cancelling";
}

const STEP_CHIP: Record<string, string> = {
  pending: "bg-slate-100 text-slate-600",
  skipped: "bg-sky-100 text-sky-800",
  running: "bg-amber-100 text-amber-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
  cancelled: "bg-slate-200 text-slate-700",
};

function detailLine(step: string, detail: Record<string, unknown>): string | null {
  const n = (key: string) => (typeof detail[key] === "number" ? (detail[key] as number) : null);
  if (step === "download") {
    const found = n("total_files_found");
    if (found === null) return null;
    return `${(n("total_downloaded_files") ?? 0).toLocaleString()} downloaded, ${(n("total_skipped_files") ?? 0).toLocaleString()} already present, ${found.toLocaleString()} found`;
  }
  if (step === "upload") {
    const total = n("total_items");
    if (total === null) return null;
    return `${(n("processed_items") ?? 0).toLocaleString()} / ${total.toLocaleString()} files`;
  }
  const pct = n("overall_progress_percent");
  const phase = typeof detail.current_phase === "string" ? detail.current_phase : null;
  const rows = n("table_rows");
  if (rows !== null) return `${rows.toLocaleString()} rows`;
  if (pct !== null) return `${pct}%${phase ? ` · ${phase}` : ""}`;
  return null;
}

export const MonthlyRunCard: React.FC = () => {
  const [month, setMonth] = useState(previousMonthInput);
  // Where the month comes from. Starts from this computer's saved default and
  // is written back whenever a run starts with a different choice.
  const [source, setSource] = useState<MasterSource>("ftp");
  const [config, setConfig] = useState<MonthlyAutomationConfig | null>(null);
  const [configDirty, setConfigDirty] = useState(false);
  const [plan, setPlan] = useState<MonthlyRunPlan | null>(null);
  const [marker, setMarker] = useState<MonthlyRunMarker | null>(null);
  const [jobId, setJobId] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(JOB_STORAGE_KEY);
    } catch {
      return null;
    }
  });
  const [status, setStatus] = useState<MonthlyRunStatusResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const running = isActive(status);

  // Settings and whatever run is already in flight (another tab, or before a reload).
  // Keeps retrying while the backend is unreachable: the page is often opened
  // before the server has finished starting, and a card that gave up on its
  // first attempt would stay dead until someone thought to reload.
  const [configAttempt, setConfigAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const load = () => {
      getAutomationConfig()
        .then((loaded) => {
          if (cancelled) return;
          setConfig(loaded);
          setSource(loaded.master_source === "drive" ? "drive" : "ftp");
          setError(null);
          return getActiveMonthlyRun().then((active) => {
            if (cancelled || !active) return;
            setJobId(active.job_id);
            setStatus(active);
          });
        })
        .catch((err) => {
          if (cancelled) return;
          setError(`${errorText(err)} — is the backend running? Retrying every ${CONFIG_RETRY_MS / 1000}s.`);
          timer = window.setTimeout(load, CONFIG_RETRY_MS);
        });
    };
    load();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [configAttempt]);

  const refreshPlan = useCallback(() => {
    getMonthlyRunPlan(month).then(setPlan).catch(() => setPlan(null));
    getMonthlyRunMarker(month).then(setMarker).catch(() => setMarker(null));
  }, [month]);

  useEffect(() => {
    // Re-fetched when the settings arrive too, so a backend that came up late
    // still gets its plan and marker shown.
    if (!configDirty) refreshPlan();
  }, [refreshPlan, configDirty, config]);

  useEffect(() => {
    try {
      if (jobId) window.localStorage.setItem(JOB_STORAGE_KEY, jobId);
      else window.localStorage.removeItem(JOB_STORAGE_KEY);
    } catch {
      /* storage unavailable */
    }
  }, [jobId]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const latest = await getMonthlyRunStatus(jobId);
        if (cancelled) return;
        setStatus(latest);
        if (!isActive(latest)) {
          setJobId(null);
          setMessage(latest.message);
          refreshPlan();
        }
      } catch (err) {
        if (cancelled) return;
        setJobId(null);
        setError(errorText(err));
      }
    };
    tick();
    const timer = window.setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [jobId, refreshPlan]);

  const completedBefore = useMemo(
    () => Object.entries(marker?.steps ?? {}).filter(([, s]) => s.status === "completed").map(([name]) => name),
    [marker],
  );

  const run = async (fromScratch: boolean) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (config && (configDirty || (config.master_source ?? "ftp") !== source)) {
        // The chosen source becomes this computer's default for next time.
        const saved = await saveAutomationConfig({ ...config, master_source: source });
        setConfig(saved);
        setConfigDirty(false);
      }
      const started = await startMonthlyRun({ month, from_scratch: fromScratch, source });
      setJobId(started.job_id);
      setMessage(started.message);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (!jobId) return;
    try {
      setStatus(await stopMonthlyRun(jobId));
    } catch (err) {
      setError(errorText(err));
    }
  };

  const saveSettings = async () => {
    if (!config) return;
    setBusy(true);
    try {
      setConfig(await saveAutomationConfig(config));
      setConfigDirty(false);
      setMessage("Settings saved.");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const updateConfig = <K extends keyof MonthlyAutomationConfig>(key: K, value: MonthlyAutomationConfig[K]) => {
    setConfig((current) => (current ? { ...current, [key]: value } : current));
    setConfigDirty(true);
  };

  const steps = status?.steps ?? {};
  // Labels follow the run being shown; before a run starts, the chosen source.
  const shownSource: MasterSource = status?.source ?? source;
  const stepCount = shownSource === "drive" ? 2 : 3;

  return (
    <section className="rounded-2xl border border-indigo-200 bg-indigo-50/40 p-6 shadow-sm" aria-label="Monthly master run">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Monthly master run</h2>
          <p className="mt-1 text-sm text-slate-600">
            Downloads the month from FTP (or from Google Drive when someone already uploaded it), uploads it to Drive
            when it came from FTP, and builds it as a DuckDB view — one click, in order, with each step checked before
            the next starts.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowSettings((v) => !v)}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          {showSettings ? "Hide settings" : "Settings"}
        </button>
      </div>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">Month</span>
          <input
            type="month"
            value={month}
            disabled={running}
            onChange={(e) => setMonth(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            aria-label="Month"
          />
        </label>
        <fieldset className="block" disabled={running}>
          <legend className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">Get the month from</legend>
          <div className="flex flex-wrap gap-2">
            {SOURCE_OPTIONS.map((option) => (
              <label
                key={option.value}
                title={option.help}
                className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                  source === option.value ? "border-indigo-400 bg-white font-semibold text-indigo-800" : "border-slate-300 bg-white text-slate-700"
                } ${running ? "cursor-not-allowed opacity-60" : ""}`}
              >
                <input
                  type="radio"
                  name="monthly-run-source"
                  value={option.value}
                  checked={source === option.value}
                  onChange={() => setSource(option.value)}
                  className="accent-indigo-600"
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>
        {!running && completedBefore.length === 0 && (
          <button
            type="button"
            disabled={busy || !config}
            onClick={() => run(false)}
            className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            Run monthly master
          </button>
        )}
        {!running && completedBefore.length > 0 && (
          <>
            <button
              type="button"
              disabled={busy || !config}
              onClick={() => run(false)}
              className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:bg-slate-300"
            >
              Resume ({Math.min(completedBefore.length, stepCount)} of {stepCount} done)
            </button>
            <button
              type="button"
              disabled={busy || !config}
              onClick={() => {
                const again = source === "drive" ? "downloading from Drive again" : "re-uploading to Drive";
                if (window.confirm(`Run every step for ${plan?.token ?? month} again, including ${again}?`)) run(true);
              }}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Run again from scratch
            </button>
          </>
        )}
        {running && (
          <button
            type="button"
            onClick={stop}
            disabled={status?.status === "cancelling"}
            className="rounded-lg border border-rose-300 bg-white px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-60"
          >
            {status?.status === "cancelling" ? "Stopping…" : "Stop"}
          </button>
        )}
      </div>

      {plan && (
        <dl className="mt-3 grid gap-x-6 gap-y-1 text-xs text-slate-600 sm:grid-cols-2">
          {source === "ftp" && <div><dt className="inline font-semibold">FTP:</dt> <dd className="inline font-mono">{plan.remote_dir}</dd></div>}
          <div><dt className="inline font-semibold">{source === "drive" ? "Drive folder (source):" : "Drive folder:"}</dt> <dd className="inline font-mono">{plan.drive_root_name}</dd></div>
          <div><dt className="inline font-semibold">CSV:</dt> <dd className="inline font-mono">{plan.csv_dir}</dd></div>
          <div><dt className="inline font-semibold">Parquet:</dt> <dd className="inline font-mono">{plan.parquet_dir}</dd></div>
          <div className="sm:col-span-2"><dt className="inline font-semibold">DuckDB object:</dt> <dd className="inline font-mono">{plan.object_name}</dd></div>
        </dl>
      )}

      {showSettings && config && (
        <div className="mt-4 grid gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-2">
          {(
            [
              ["csv_root", "CSV root (month folder is added)"],
              ["parquet_root", "Parquet root (month folder is added)"],
              ["db_path", "DuckDB file"],
              ["drive_parent_folder_id", "Drive parent folder ID"],
              ["ftp_host", "FTP host"],
              ["drive_root_name_template", "Drive folder name template"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="block text-xs">
              <span className="mb-1 block font-semibold uppercase tracking-wide text-slate-600">{label}</span>
              <input
                type="text"
                value={String(config[key] ?? "")}
                onChange={(e) => updateConfig(key, e.target.value as never)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm"
              />
            </label>
          ))}
          <p className="text-xs text-slate-500 sm:col-span-2">
            FTP passwords are read from <span className="font-mono">config/ftp_profiles.json</span> on the server; Google
            uses the login saved by “Upload master in Drive”. The source chosen above is saved as this computer's default
            when a run starts.
          </p>
          <div className="sm:col-span-2">
            <button
              type="button"
              disabled={!configDirty || busy}
              onClick={saveSettings}
              className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-white disabled:bg-slate-300"
            >
              Save settings
            </button>
          </div>
        </div>
      )}

      {(status || completedBefore.length > 0) && (
        <ol className="mt-4 space-y-2">
          {(["download", "upload", "build"] as const).map((step) => {
            const live = steps[step];
            const prior = marker?.steps?.[step];
            const shown = live ?? prior;
            const chip = shown?.status ?? "pending";
            const line = shown ? detailLine(step, shown.detail ?? {}) : null;
            return (
              <li key={step} className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
                <span className="w-56 text-sm font-semibold text-slate-800">{stepLabel(step, shownSource)}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STEP_CHIP[chip] ?? STEP_CHIP.pending}`}>{chip}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-slate-600" title={shown?.message ?? ""}>
                  {shown?.message || ""}
                </span>
                {line && <span className="text-xs font-mono text-slate-500">{line}</span>}
              </li>
            );
          })}
        </ol>
      )}

      {status && !running && status.outcome && status.outcome !== "completed" && (
        <p className={`mt-3 text-sm ${status.outcome === "failed" ? "text-rose-700" : "text-amber-700"}`}>{status.message}</p>
      )}
      {status && !running && status.outcome === "completed" && <p className="mt-3 text-sm text-emerald-700">{status.message}</p>}
      {message && !status && <p className="mt-3 text-sm text-slate-700">{message}</p>}
      {error && (
        <p className="mt-3 text-sm text-rose-700">
          {error}
          {!config && (
            <>
              {" "}
              <button type="button" onClick={() => setConfigAttempt((n) => n + 1)} className="font-semibold underline">
                Retry now
              </button>
            </>
          )}
        </p>
      )}
    </section>
  );
};
