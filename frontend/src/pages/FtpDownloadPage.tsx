import React, { useMemo, useState } from "react";
import { startFtpDownload } from "../api/ftpApi";
import { pickSystemFolder } from "../api/systemApi";
import type { FTPDownloadProfile, FTPDownloadResponse } from "../types/ftp.types";

function getErrorMessage(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail === "string"
  ) {
    return (error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "FTP download failed.";
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return "FTP download failed.";
}

const PRESET_USERS: Record<string, string> = {
  MVVNL: "mvftpreport",
  DVVNL: "dvftpreport",
  PVVNL: "pvftpreport",
  PuVNL: "puftpreport",
  KESCO: "ksftpreport",
};

const MASTER_PRESET: FTPDownloadProfile[] = ["MVVNL", "DVVNL", "PVVNL", "PuVNL", "KESCO"].map((name) => ({
  name,
  username: PRESET_USERS[name],
  password: "",
  remote_dir: "/01-MASTER_DATA/{MONTH}/",
  local_subfolder: `{MONTH}/${name}`,
}));

const BILLED_PRESET: FTPDownloadProfile[] = ["MVVNL", "DVVNL", "PVVNL", "PuVNL", "KESCO"].map((name) => ({
  name,
  username: PRESET_USERS[name],
  password: "",
  remote_dir: "/03_CSV_BILLED/{DATE}/",
  local_subfolder: `{MONTH}/{DATE}/${name}`,
}));

const EMPTY_PROFILE: FTPDownloadProfile = {
  name: "",
  username: "",
  password: "",
  remote_dir: "",
  local_subfolder: "{PROFILE}",
};

export const FtpDownloadPage: React.FC = () => {
  const [host, setHost] = useState("ftp.uppclonline.com");
  const [port, setPort] = useState(21);
  const [outputRoot, setOutputRoot] = useState("");
  const [fileSuffix, setFileSuffix] = useState(".gz");
  const [maxWorkers, setMaxWorkers] = useState(3);
  const [maxRetries, setMaxRetries] = useState(3);
  const [retryDelaySeconds, setRetryDelaySeconds] = useState(5);
  const [timeoutSeconds, setTimeoutSeconds] = useState(30);
  const [passiveMode, setPassiveMode] = useState(true);
  const [skipExisting, setSkipExisting] = useState(true);
  const [profiles, setProfiles] = useState<FTPDownloadProfile[]>([{ ...EMPTY_PROFILE }]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FTPDownloadResponse | null>(null);

  const canSubmit = useMemo(() => {
    const hasHost = host.trim() !== "";
    const hasOutput = outputRoot.trim() !== "";
    const hasValidProfiles = profiles.every(
      (profile) =>
        profile.name.trim() !== "" &&
        profile.username.trim() !== "" &&
        profile.password.trim() !== "" &&
        profile.remote_dir.trim() !== ""
    );
    return hasHost && hasOutput && hasValidProfiles && !isLoading;
  }, [host, outputRoot, profiles, isLoading]);

  const updateProfile = (index: number, field: keyof FTPDownloadProfile, value: string) => {
    setProfiles((current) =>
      current.map((profile, currentIndex) =>
        currentIndex === index ? { ...profile, [field]: value } : profile
      )
    );
  };

  const resetForm = () => {
    setHost("ftp.uppclonline.com");
    setPort(21);
    setOutputRoot("");
    setFileSuffix(".gz");
    setMaxWorkers(3);
    setMaxRetries(3);
    setRetryDelaySeconds(5);
    setTimeoutSeconds(30);
    setPassiveMode(true);
    setSkipExisting(true);
    setProfiles([{ ...EMPTY_PROFILE }]);
    setError(null);
    setResult(null);
  };

  const handleDownload = async () => {
    if (!canSubmit) return;

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await startFtpDownload({
        host,
        port,
        output_root: outputRoot,
        file_suffix: fileSuffix,
        max_workers: maxWorkers,
        max_retries: maxRetries,
        retry_delay_seconds: retryDelaySeconds,
        timeout_seconds: timeoutSeconds,
        passive_mode: passiveMode,
        skip_existing: skipExisting,
        profiles,
      });
      setResult(response);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="rounded-2xl border border-sky-100 bg-white p-6 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-sky-600">Sidebar tool</p>
        <h1 className="mt-2 text-3xl font-bold text-gray-900">FTP Download</h1>
        <p className="mt-3 max-w-4xl text-sm text-gray-600">
          Download all files from one or more FTP folders into a local output root. Use tokens exactly like your manual
          scripts: <span className="font-mono">{`{DATE}`}</span>, <span className="font-mono">{`{MONTH}`}</span>,{" "}
          <span className="font-mono">{`{PROFILE}`}</span>.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => setProfiles(MASTER_PRESET.map((item) => ({ ...item })))}
            className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-2 text-sm font-semibold text-sky-700 hover:bg-sky-100"
          >
            Load Master preset
          </button>
          <button
            type="button"
            onClick={() => setProfiles(BILLED_PRESET.map((item) => ({ ...item })))}
            className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-100"
          >
            Load Billed preset
          </button>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_1.35fr]">
        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold text-gray-900">FTP settings</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">FTP host</label>
              <input
                type="text"
                value={host}
                onChange={(event) => setHost(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">Port</label>
              <input
                type="number"
                value={port}
                onChange={(event) => setPort(Number(event.target.value) || 21)}
                className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <div className="md:col-span-2">
              <label className="mb-2 block text-sm font-semibold text-gray-800">Output root folder</label>
              <div className="flex flex-col gap-3 md:flex-row">
                <input
                  type="text"
                  value={outputRoot}
                  onChange={(event) => setOutputRoot(event.target.value)}
                  placeholder="Example: G:\\MASTER or G:\\BILLED"
                  className="w-full rounded-lg border border-gray-300 px-4 py-3 font-mono text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={async () => {
                    const path = await pickSystemFolder();
                    if (path) setOutputRoot(path);
                  }}
                  disabled={isLoading}
                  className="rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Browse folder
                </button>
              </div>
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">File suffix</label>
              <input
                type="text"
                value={fileSuffix}
                onChange={(event) => setFileSuffix(event.target.value)}
                placeholder=".gz"
                className="w-full rounded-lg border border-gray-300 px-4 py-3 font-mono text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">Workers per profile</label>
              <input
                type="number"
                min={1}
                max={16}
                value={maxWorkers}
                onChange={(event) => setMaxWorkers(Math.max(1, Number(event.target.value) || 1))}
                className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">Retries</label>
              <input
                type="number"
                min={1}
                max={10}
                value={maxRetries}
                onChange={(event) => setMaxRetries(Math.max(1, Number(event.target.value) || 1))}
                className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">Retry delay seconds</label>
              <input
                type="number"
                min={0}
                max={120}
                value={retryDelaySeconds}
                onChange={(event) => setRetryDelaySeconds(Math.max(0, Number(event.target.value) || 0))}
                className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold text-gray-800">Timeout seconds</label>
              <input
                type="number"
                min={5}
                max={600}
                value={timeoutSeconds}
                onChange={(event) => setTimeoutSeconds(Math.max(5, Number(event.target.value) || 5))}
                className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-2">
            <label className="flex items-center gap-3 rounded-lg border border-gray-200 px-4 py-3 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={passiveMode}
                onChange={(event) => setPassiveMode(event.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-sky-600 focus:ring-sky-500"
              />
              Use passive mode
            </label>
            <label className="flex items-center gap-3 rounded-lg border border-gray-200 px-4 py-3 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={skipExisting}
                onChange={(event) => setSkipExisting(event.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-sky-600 focus:ring-sky-500"
              />
              Skip existing files with same size
            </label>
          </div>
        </div>

        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-gray-900">FTP profiles</h2>
              <p className="mt-1 text-sm text-gray-500">One row per DISCOM or FTP login.</p>
            </div>
            <button
              type="button"
              onClick={() => setProfiles((current) => [...current, { ...EMPTY_PROFILE }])}
              disabled={isLoading}
              className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Add profile
            </button>
          </div>

          <div className="mt-5 space-y-4">
            {profiles.map((profile, index) => (
              <div key={`${index}-${profile.name}`} className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <div>
                    <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-gray-600">
                      Profile name
                    </label>
                    <input
                      type="text"
                      value={profile.name}
                      onChange={(event) => updateProfile(index, "name", event.target.value)}
                      placeholder="KESCO"
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-gray-600">
                      Username
                    </label>
                    <input
                      type="text"
                      value={profile.username}
                      onChange={(event) => updateProfile(index, "username", event.target.value)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-gray-600">
                      Password
                    </label>
                    <input
                      type="password"
                      value={profile.password}
                      onChange={(event) => updateProfile(index, "password", event.target.value)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
                    />
                  </div>
                  <div className="xl:col-span-2">
                    <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-gray-600">
                      Remote folder
                    </label>
                    <input
                      type="text"
                      value={profile.remote_dir}
                      onChange={(event) => updateProfile(index, "remote_dir", event.target.value)}
                      placeholder="/01-MASTER_DATA/{MONTH}/"
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-mono text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-gray-600">
                      Local subfolder
                    </label>
                    <input
                      type="text"
                      value={profile.local_subfolder ?? ""}
                      onChange={(event) => updateProfile(index, "local_subfolder", event.target.value)}
                      placeholder="{MONTH}/{PROFILE}"
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-mono text-sm text-gray-700 focus:border-sky-500 focus:outline-none"
                    />
                  </div>
                </div>
                <div className="mt-3 flex justify-end">
                  <button
                    type="button"
                    onClick={() => setProfiles((current) => current.filter((_, currentIndex) => currentIndex !== index))}
                    disabled={isLoading || profiles.length === 1}
                    className="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-5 rounded-xl border border-amber-100 bg-amber-50 p-4 text-sm text-amber-800">
            Tokens available in remote folder and local subfolder: <span className="font-mono">{`{DATE}`}</span>,{" "}
            <span className="font-mono">{`{MONTH}`}</span>, <span className="font-mono">{`{PROFILE}`}</span>.
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleDownload}
              disabled={!canSubmit}
              className="rounded-lg bg-sky-600 px-5 py-3 text-sm font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? "Downloading files..." : "Start FTP download"}
            </button>
            <button
              type="button"
              onClick={resetForm}
              disabled={isLoading}
              className="rounded-lg border border-gray-300 bg-white px-5 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Reset
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 shadow-sm">
          <span className="font-semibold">Error:</span> {error}
        </div>
      )}

      {result && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 shadow-sm">
          <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">FTP download complete</p>
          <h2 className="mt-2 text-2xl font-bold text-emerald-900">Download summary</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl bg-white p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Profiles</p>
              <p className="mt-2 text-2xl font-bold text-gray-900">{result.total_profiles}</p>
            </div>
            <div className="rounded-xl bg-white p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Files found</p>
              <p className="mt-2 text-2xl font-bold text-gray-900">{result.total_files_found}</p>
            </div>
            <div className="rounded-xl bg-white p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Downloaded</p>
              <p className="mt-2 text-2xl font-bold text-gray-900">{result.total_downloaded_files}</p>
            </div>
            <div className="rounded-xl bg-white p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Skipped / Failed</p>
              <p className="mt-2 text-2xl font-bold text-gray-900">
                {result.total_skipped_files} / {result.total_failed_files}
              </p>
            </div>
          </div>

          <div className="mt-5 rounded-xl border border-emerald-100 bg-white p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Output root</p>
            <p className="mt-2 break-all font-mono text-sm text-gray-800">{result.output_root}</p>
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            {result.profile_results.map((profileResult) => (
              <div
                key={`${profileResult.profile_name}-${profileResult.remote_dir}`}
                className="rounded-xl border border-emerald-100 bg-white p-4 shadow-sm"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-bold text-gray-900">{profileResult.profile_name}</h3>
                    <p className="mt-1 break-all font-mono text-xs text-gray-500">{profileResult.remote_dir}</p>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${
                      profileResult.failed_files > 0 ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
                    }`}
                  >
                    {profileResult.failed_files > 0 ? "Completed with errors" : "Completed"}
                  </span>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-lg bg-gray-50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Found</p>
                    <p className="mt-1 text-xl font-bold text-gray-900">{profileResult.found_files}</p>
                  </div>
                  <div className="rounded-lg bg-gray-50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Downloaded</p>
                    <p className="mt-1 text-xl font-bold text-gray-900">{profileResult.downloaded_files}</p>
                  </div>
                  <div className="rounded-lg bg-gray-50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Skipped</p>
                    <p className="mt-1 text-xl font-bold text-gray-900">{profileResult.skipped_files}</p>
                  </div>
                  <div className="rounded-lg bg-gray-50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Failed</p>
                    <p className="mt-1 text-xl font-bold text-gray-900">{profileResult.failed_files}</p>
                  </div>
                </div>
                <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Local folder</p>
                  <p className="mt-2 break-all font-mono text-xs text-gray-700">{profileResult.local_dir}</p>
                </div>
                {profileResult.errors.length > 0 && (
                  <div className="mt-4 rounded-lg border border-red-100 bg-red-50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-red-700">Errors</p>
                    <ul className="mt-2 space-y-1 text-xs text-red-700">
                      {profileResult.errors.map((item, index) => (
                        <li key={`${profileResult.profile_name}-error-${index}`} className="break-all">
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
