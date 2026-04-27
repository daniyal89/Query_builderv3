import React, { useEffect, useMemo, useState } from "react";
import { getDriveAuthStatus, getDriveJobStatus, loginGoogleDrive, startDriveUpload, stopDriveJob } from "../api/driveApi";
import { pickSystemFile, pickSystemFolder } from "../api/systemApi";
import type { DriveAuthConfig, DriveAuthMode, DriveAuthStatusResponse, DriveJobStatusResponse } from "../types/drive.types";

const STORAGE_KEY = "drive_upload_master_form_v2";
const JOB_STORAGE_KEY = "drive_upload_master_job_v1";

function getErrorMessage(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail === "string"
  ) {
    return (error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "Google Drive upload failed.";
  }
  if (error instanceof Error && error.message.trim()) return error.message;
  return "Google Drive upload failed.";
}

type FormState = {
  authMode: DriveAuthMode;
  serviceAccountJsonPath: string;
  localFolder: string;
  parentFolderId: string;
  rootFolderName: string;
  skipExisting: boolean;
  maxWorkers: number;
  showAdvanced: boolean;
};

const defaultState: FormState = {
  authMode: "oauth",
  serviceAccountJsonPath: "",
  localFolder: "",
  parentFolderId: "",
  rootFolderName: "",
  skipExisting: true,
  maxWorkers: 3,
  showAdvanced: false,
};

function readInitialState(): FormState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState;
    return { ...defaultState, ...(JSON.parse(raw) as Partial<FormState>), authMode: "oauth" };
  } catch {
    return defaultState;
  }
}

type PersistedJobState = {
  jobId: string;
  status: DriveJobStatusResponse | null;
};

function isTerminalStatus(status: DriveJobStatusResponse | null): boolean {
  return status?.status === "completed" || status?.status === "failed" || status?.status === "cancelled";
}

function readInitialJobState(): { jobId: string | null; status: DriveJobStatusResponse | null; isLoading: boolean } {
  try {
    const raw = window.localStorage.getItem(JOB_STORAGE_KEY);
    if (!raw) return { jobId: null, status: null, isLoading: false };
    const parsed = JSON.parse(raw) as Partial<PersistedJobState>;
    const jobId = typeof parsed.jobId === "string" && parsed.jobId.trim() ? parsed.jobId : null;
    const status = parsed.status ?? null;
    return { jobId, status, isLoading: Boolean(jobId) && !isTerminalStatus(status as DriveJobStatusResponse | null) };
  } catch {
    return { jobId: null, status: null, isLoading: false };
  }
}

function buildAuth(state: FormState): DriveAuthConfig {
  return {
    mode: state.authMode === "service_account" ? "service_account" : "oauth",
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
          <h3 className="text-lg font-semibold text-slate-900">Upload status</h3>
          <p className="text-sm text-slate-600">{status.message || status.status}</p>
        </div>
        <span className="rounded-full bg-indigo-100 px-3 py-1 text-sm font-semibold text-indigo-700">{status.status}</span>
      </div>
      <div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full bg-indigo-600 transition-all" style={{ width: `${percent}%` }} />
      </div>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-5">
        <div><b>Total</b><br />{status.total_items}</div>
        <div><b>Processed</b><br />{status.processed_items}</div>
        <div><b>Uploaded</b><br />{status.uploaded_items}</div>
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
          <p className="mt-1 text-sm text-slate-600">{authStatus?.message || "Click Sign in with Google before upload, or start upload and the browser login will open when needed."}</p>
          <p className="mt-1 text-xs text-slate-500">OAuth JSON is not shown to users. Keep google_oauth_client.json once in the app config folder.</p>
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

export const UploadMasterDrivePage: React.FC = () => {
  const initial = useMemo(() => readInitialState(), []);
  const initialJobState = useMemo(() => readInitialJobState(), []);
  const [state, setState] = useState<FormState>(initial);
  const [jobId, setJobId] = useState<string | null>(initialJobState.jobId);
  const [status, setStatus] = useState<DriveJobStatusResponse | null>(initialJobState.status);
  const [authStatus, setAuthStatus] = useState<DriveAuthStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(initialJobState.isLoading);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  useEffect(() => {
    if (!jobId) {
      window.localStorage.removeItem(JOB_STORAGE_KEY);
      return;
    }
    const payload: PersistedJobState = { jobId, status };
    window.localStorage.setItem(JOB_STORAGE_KEY, JSON.stringify(payload));
  }, [jobId, status]);

  useEffect(() => {
    getDriveAuthStatus().then(setAuthStatus).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!jobId) return;
    setIsLoading(!isTerminalStatus(status));
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getDriveJobStatus(jobId);
        if (cancelled) return;
        setStatus(next);
        if (isTerminalStatus(next)) {
          setIsLoading(false);
          setJobId(null);
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

  const canSubmit = state.localFolder.trim() !== "" && state.parentFolderId.trim() !== "" && !isLoading;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setIsLoading(true);
    try {
      const started = await startDriveUpload({
        auth: buildAuth(state),
        local_folder: state.localFolder.trim(),
        parent_folder_id: state.parentFolderId.trim(),
        root_folder_name: state.rootFolderName.trim() || null,
        skip_existing: state.skipExisting,
        max_workers: state.maxWorkers,
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
        <h1 className="text-3xl font-bold text-slate-900">Upload master in Drive</h1>
        <p className="mt-2 max-w-3xl text-slate-600">
          Upload the local MASTER folder tree to Google Drive. Normal users only sign in with Google. Service-account JSON remains available under Advanced.
        </p>
      </div>

      {error && <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      {state.authMode !== "service_account" && <GoogleAuthCard authStatus={authStatus} isSigningIn={isSigningIn} onSignIn={handleGoogleLogin} />}

      <form onSubmit={handleSubmit} className="space-y-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <section className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm font-medium text-slate-700">
            Local MASTER folder
            <div className="mt-1 flex gap-2">
              <input className="w-full rounded-md border px-3 py-2" value={state.localFolder} onChange={(e) => update("localFolder", e.target.value)} placeholder="G:\\MASTER\\MAR_2026" />
              <button type="button" className="rounded-md bg-slate-800 px-3 py-2 text-white" onClick={async () => { const path = await pickSystemFolder(); if (path) update("localFolder", path); }}>Browse</button>
            </div>
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Drive parent folder ID
            <input className="mt-1 w-full rounded-md border px-3 py-2" value={state.parentFolderId} onChange={(e) => update("parentFolderId", e.target.value)} placeholder="Paste parent folder ID" />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Root Drive folder name optional
            <input className="mt-1 w-full rounded-md border px-3 py-2" value={state.rootFolderName} onChange={(e) => update("rootFolderName", e.target.value)} placeholder="MASTER_DATA_2026_03" />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Parallel workers
            <input type="number" min={1} max={8} className="mt-1 w-full rounded-md border px-3 py-2" value={state.maxWorkers} onChange={(e) => update("maxWorkers", Number(e.target.value))} />
          </label>
        </section>

        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={state.skipExisting} onChange={(e) => update("skipExisting", e.target.checked)} />
          Skip files that already exist in Drive folder by name
        </label>

        <section className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <button type="button" className="text-sm font-semibold text-indigo-700" onClick={() => update("showAdvanced", !state.showAdvanced)}>
            {state.showAdvanced ? "Hide advanced authentication" : "Advanced authentication"}
          </button>
          {state.showAdvanced && (
            <div className="mt-4 space-y-4">
              <div className="flex flex-wrap gap-3 text-sm">
                <label className="flex items-center gap-2 rounded-lg border bg-white px-3 py-2">
                  <input type="radio" checked={state.authMode !== "service_account"} onChange={() => update("authMode", "oauth")} />
                  Google login OAuth
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
            {isLoading ? "Uploading..." : "Start Drive upload"}
          </button>
          {isLoading && (
            <button type="button" onClick={handleStop} disabled={status?.status === "cancelling"} className="rounded-lg border border-red-200 bg-white px-5 py-2.5 font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60">
              {status?.status === "cancelling" ? "Stopping..." : "Stop upload"}
            </button>
          )}
        </div>
      </form>

      <StatusCard status={status} />
    </div>
  );
};
