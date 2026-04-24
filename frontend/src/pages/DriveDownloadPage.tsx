import React, { useEffect, useMemo, useState } from "react";
import { getDriveAuthStatus, getDriveJobStatus, loginGoogleDrive, startDriveDownload, stopDriveJob } from "../api/driveApi";
import { pickSystemFile, pickSystemFolder } from "../api/systemApi";
import type { DriveAuthConfig, DriveAuthMode, DriveAuthStatusResponse, DriveJobStatusResponse } from "../types/drive.types";

const STORAGE_KEY = "drive_download_form_v2";

function getErrorMessage(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail === "string"
  ) {
    return (error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "Google Drive download failed.";
  }
  if (error instanceof Error && error.message.trim()) return error.message;
  return "Google Drive download failed.";
}

type FormState = {
  authMode: DriveAuthMode;
  serviceAccountJsonPath: string;
  driveLinkOrId: string;
  outputFolder: string;
  overwriteExisting: boolean;
  exportGoogleFiles: boolean;
  showAdvanced: boolean;
};

const defaultState: FormState = {
  authMode: "auto",
  serviceAccountJsonPath: "",
  driveLinkOrId: "",
  outputFolder: "",
  overwriteExisting: false,
  exportGoogleFiles: true,
  showAdvanced: false,
};

function readInitialState(): FormState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState;
    return { ...defaultState, ...(JSON.parse(raw) as Partial<FormState>), authMode: "auto" };
  } catch {
    return defaultState;
  }
}

function buildAuth(state: FormState): DriveAuthConfig {
  return {
    mode: state.authMode,
    oauth_client_json_path: null,
    token_json_path: null,
    service_account_json_path: state.authMode === "service_account" ? state.serviceAccountJsonPath.trim() || null : null,
  };
}

const StatusCard: React.FC<{ status: DriveJobStatusResponse | null }> = ({ status }) => {
  if (!status) return null;
  const percent = status.total_items > 0 ? Math.min(100, Math.round((status.processed_items / status.total_items) * 100)) : 0;
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-slate-900">Download status</h3>
          <p className="text-sm text-slate-600">{status.message || status.status}</p>
          {status.output_path && <p className="mt-1 text-xs text-slate-500">Saved to: {status.output_path}</p>}
        </div>
        <span className="rounded-full bg-indigo-100 px-3 py-1 text-sm font-semibold text-indigo-700">{status.status}</span>
      </div>
      <div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full bg-indigo-600 transition-all" style={{ width: `${percent}%` }} />
      </div>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-5">
        <div><b>Total</b><br />{status.total_items}</div>
        <div><b>Processed</b><br />{status.processed_items}</div>
        <div><b>Downloaded</b><br />{status.downloaded_items}</div>
        <div><b>Skipped</b><br />{status.skipped_items}</div>
        <div><b>Failed</b><br />{status.failed_items}</div>
      </div>
      {status.errors.length > 0 && (
        <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          <b>Errors</b>
          <ul className="mt-2 list-disc pl-5">
            {status.errors.slice(-8).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
};

const GoogleAuthCard: React.FC<{
  authStatus: DriveAuthStatusResponse | null;
  isSigningIn: boolean;
  onSignIn: () => void;
}> = ({ authStatus, isSigningIn, onSignIn }) => {
  const ready = Boolean(authStatus?.token_valid);
  const configured = Boolean(authStatus?.configured);
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Google account</h2>
          <p className="mt-1 text-sm text-slate-600">
            {authStatus?.message || "Public links will be tried first. Private links will ask for Google login only when needed."}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Normal users do not need to select OAuth JSON here. Keep google_oauth_client.json once in the app config folder.
          </p>
        </div>
        <button
          type="button"
          disabled={!configured || isSigningIn}
          onClick={onSignIn}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isSigningIn ? "Opening Google..." : ready ? "Signed in" : "Sign in with Google"}
        </button>
      </div>
    </section>
  );
};

export const DriveDownloadPage: React.FC = () => {
  const initial = useMemo(() => readInitialState(), []);
  const [state, setState] = useState<FormState>(initial);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<DriveJobStatusResponse | null>(null);
  const [authStatus, setAuthStatus] = useState<DriveAuthStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  useEffect(() => {
    getDriveAuthStatus().then(setAuthStatus).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getDriveJobStatus(jobId);
        if (cancelled) return;
        setStatus(next);
        if (next.status === "completed" || next.status === "failed" || next.status === "cancelled") {
          setIsLoading(false);
          getDriveAuthStatus().then(setAuthStatus).catch(() => undefined);
          return;
        }
        window.setTimeout(poll, 1500);
      } catch (err) {
        if (cancelled) return;
        setError(getErrorMessage(err));
        setIsLoading(false);
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [jobId]);

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setState((current) => ({ ...current, [key]: value }));
  };

  const handleGoogleLogin = async () => {
    setError(null);
    setIsSigningIn(true);
    try {
      const next = await loginGoogleDrive();
      setAuthStatus(next);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSigningIn(false);
    }
  };

  const canSubmit = state.driveLinkOrId.trim() !== "" && state.outputFolder.trim() !== "" && !isLoading;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setIsLoading(true);
    try {
      const started = await startDriveDownload({
        auth: buildAuth(state),
        drive_link_or_id: state.driveLinkOrId.trim(),
        output_folder: state.outputFolder.trim(),
        overwrite_existing: state.overwriteExisting,
        export_google_files: state.exportGoogleFiles,
      });
      setJobId(started.job_id);
    } catch (err) {
      setError(getErrorMessage(err));
      setIsLoading(false);
    }
  };

  const handleStop = async () => {
    if (!jobId) return;
    setError(null);
    try {
      const stopped = await stopDriveJob(jobId);
      setStatus(stopped);
      if (stopped.status === "cancelled" || stopped.status === "completed" || stopped.status === "failed") {
        setIsLoading(false);
      }
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Drive Download</h1>
        <p className="mt-2 max-w-3xl text-slate-600">
          Paste a Google Drive file or folder link. Public file links are downloaded without login. Private files and folders open Google login automatically when access is needed.
        </p>
      </div>

      {error && <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      <GoogleAuthCard authStatus={authStatus} isSigningIn={isSigningIn} onSignIn={handleGoogleLogin} />

      <form onSubmit={handleSubmit} className="space-y-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <section className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm font-medium text-slate-700 md:col-span-2">
            Drive link or ID
            <input className="mt-1 w-full rounded-md border px-3 py-2" value={state.driveLinkOrId} onChange={(e) => update("driveLinkOrId", e.target.value)} placeholder="Paste Google Drive folder/file link or ID" />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Download folder
            <div className="mt-1 flex gap-2">
              <input className="w-full rounded-md border px-3 py-2" value={state.outputFolder} onChange={(e) => update("outputFolder", e.target.value)} placeholder="G:\\DRIVE_DOWNLOADS" />
              <button type="button" className="rounded-md bg-slate-800 px-3 py-2 text-white" onClick={async () => { const path = await pickSystemFolder(); if (path) update("outputFolder", path); }}>Browse</button>
            </div>
          </label>
        </section>

        <div className="flex flex-wrap gap-5 text-sm text-slate-700">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={state.exportGoogleFiles} onChange={(e) => update("exportGoogleFiles", e.target.checked)} />
            Export Google Docs/Sheets/Slides
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={state.overwriteExisting} onChange={(e) => update("overwriteExisting", e.target.checked)} />
            Overwrite existing local files
          </label>
        </div>

        <section className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <button type="button" className="text-sm font-semibold text-indigo-700" onClick={() => update("showAdvanced", !state.showAdvanced)}>
            {state.showAdvanced ? "Hide advanced authentication" : "Advanced authentication"}
          </button>
          {state.showAdvanced && (
            <div className="mt-4 space-y-4">
              <div className="flex flex-wrap gap-3 text-sm">
                <label className="flex items-center gap-2 rounded-lg border bg-white px-3 py-2">
                  <input type="radio" checked={state.authMode === "auto"} onChange={() => update("authMode", "auto")} />
                  Auto: public first, then Google login
                </label>
                <label className="flex items-center gap-2 rounded-lg border bg-white px-3 py-2">
                  <input type="radio" checked={state.authMode === "service_account"} onChange={() => update("authMode", "service_account")} />
                  Optional service account
                </label>
              </div>
              {state.authMode === "service_account" && (
                <label className="block text-sm font-medium text-slate-700">
                  Service-account JSON path
                  <div className="mt-1 flex gap-2">
                    <input className="w-full rounded-md border px-3 py-2" value={state.serviceAccountJsonPath} onChange={(e) => update("serviceAccountJsonPath", e.target.value)} placeholder="service_account.json" />
                    <button type="button" className="rounded-md bg-slate-800 px-3 py-2 text-white" onClick={async () => { const path = await pickSystemFile("json"); if (path) update("serviceAccountJsonPath", path); }}>Browse</button>
                  </div>
                </label>
              )}
            </div>
          )}
        </section>

        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={!canSubmit} className="rounded-lg bg-indigo-600 px-5 py-2.5 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300">
            {isLoading ? "Downloading..." : "Start download"}
          </button>
          {isLoading && (
            <button type="button" onClick={handleStop} disabled={status?.status === "cancelling"} className="rounded-lg border border-red-200 bg-white px-5 py-2.5 font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60">
              {status?.status === "cancelling" ? "Stopping..." : "Stop download"}
            </button>
          )}
        </div>
      </form>

      <StatusCard status={status} />
    </div>
  );
};
