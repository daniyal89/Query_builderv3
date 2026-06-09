import React, { useMemo, useState } from "react";
import { mergeFolderWithProgress } from "../api/mergeApi";
import type { MergeProgressEvent } from "../api/mergeApi";
import { pickSystemFolder, pickSystemSavePath } from "../api/systemApi";
import type { FolderMergeResponse } from "../types/merge.types";
import { StatusAlert } from "../components/common/StatusAlert";

function getErrorMessage(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail === "string"
  ) {
    return (error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "Merge failed.";
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return "Merge failed.";
}

interface ProgressState {
  stage: string;
  detail: string;
  current: number;
  total: number;
}

export const FolderMergePage: React.FC = () => {
  const [sourceFolder, setSourceFolder] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FolderMergeResponse | null>(null);
  const [progress, setProgress] = useState<ProgressState | null>(null);

  const canSubmit = useMemo(() => {
    return sourceFolder.trim() !== "" && outputPath.trim() !== "" && !isLoading;
  }, [sourceFolder, outputPath, isLoading]);

  const handleMerge = async () => {
    if (!canSubmit) return;

    setIsLoading(true);
    setError(null);
    setResult(null);
    setProgress(null);

    try {
      const response = await mergeFolderWithProgress(
        {
          source_folder: sourceFolder,
          output_path: outputPath,
          include_subfolders: includeSubfolders,
        },
        (event: MergeProgressEvent) => {
          setProgress({
            stage: event.stage,
            detail: event.detail,
            current: event.current,
            total: event.total,
          });
        },
      );
      setResult(response);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
      setProgress(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="rounded-2xl border border-indigo-100 bg-white p-6 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">Sidebar tool</p>
        <h1 className="mt-2 text-3xl font-bold text-gray-900">Folder Merge</h1>
        <p className="mt-3 max-w-3xl text-sm text-gray-600">
          Select one input folder, merge all supported files inside it, and save the final merged file to any custom
          location with any custom name.
        </p>
        <div className="mt-4 flex flex-wrap gap-2 text-xs text-gray-500">
          {[".csv", ".xlsx", ".xls", ".xlsb", ".gz", ".zip"].map((item) => (
            <span key={item} className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1">
              {item}
            </span>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="grid gap-6">
          <div>
            <label className="mb-2 block text-sm font-semibold text-gray-800">Input folder</label>
            <div className="flex flex-col gap-3 md:flex-row">
              <input
                type="text"
                value={sourceFolder}
                onChange={(event) => setSourceFolder(event.target.value)}
                placeholder="Select the folder that contains files to merge"
                className="w-full rounded-lg border border-gray-300 px-4 py-3 font-mono text-sm text-gray-700 focus:border-indigo-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={async () => {
                  const path = await pickSystemFolder();
                  if (path) setSourceFolder(path);
                }}
                disabled={isLoading}
                className="rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Browse folder
              </button>
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-gray-800">Save merged file as</label>
            <div className="flex flex-col gap-3 md:flex-row">
              <input
                type="text"
                value={outputPath}
                onChange={(event) => setOutputPath(event.target.value)}
                placeholder="Choose output file path, for example D:\\Output\\merged_output.csv"
                className="w-full rounded-lg border border-gray-300 px-4 py-3 font-mono text-sm text-gray-700 focus:border-indigo-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={async () => {
                  const path = await pickSystemSavePath("merged_output.csv", ".csv");
                  if (path) setOutputPath(path);
                }}
                disabled={isLoading}
                className="rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Choose save path
              </button>
            </div>
            <p className="mt-2 text-xs text-gray-500">
              Use .csv for very large merges or .xlsx when Excel output is needed.
            </p>
          </div>

          <label className="flex items-center gap-3 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={includeSubfolders}
              onChange={(event) => setIncludeSubfolders(event.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            Include subfolders recursively
          </label>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleMerge}
              disabled={!canSubmit}
              className="rounded-lg bg-indigo-600 px-5 py-3 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? "Merging files..." : "Start merge"}
            </button>
            <button
              type="button"
              onClick={() => {
                setSourceFolder("");
                setOutputPath("");
                setIncludeSubfolders(true);
                setError(null);
                setResult(null);
              }}
              disabled={isLoading}
              className="rounded-lg border border-gray-300 bg-white px-5 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Reset
            </button>
          </div>
        </div>
      </div>

      {isLoading && progress && (
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50 p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">
                {progress.stage === "discovery" && "Discovering files"}
                {progress.stage === "processing" && "Processing files"}
                {progress.stage === "concatenating" && "Concatenating data"}
                {progress.stage === "writing" && "Writing output"}
                {progress.stage === "done" && "Finishing up"}
              </p>
              <p className="mt-1 text-sm text-indigo-600">{progress.detail}</p>
            </div>
            {progress.total > 0 && (
              <p className="text-lg font-bold text-indigo-700">
                {progress.current} / {progress.total}
              </p>
            )}
          </div>
          <div className="mt-4 h-3 w-full overflow-hidden rounded-full bg-indigo-100">
            <div
              className="h-full rounded-full bg-indigo-600"
              style={{
                width: progress.total > 0
                  ? `${Math.round((progress.current / progress.total) * 100)}%`
                  : "100%",
                transition: "width 0.3s ease-in-out",
                animation: progress.total === 0 ? "pulse 2s ease-in-out infinite" : undefined,
              }}
            />
          </div>
          {progress.total > 0 && (
            <p className="mt-2 text-right text-xs text-indigo-500">
              {Math.round((progress.current / progress.total) * 100)}%
            </p>
          )}
        </div>
      )}

      {error && (
        <StatusAlert tone="error" title="Error">
          {error}
        </StatusAlert>
      )}

      {result && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 shadow-sm">
          <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">Merge complete</p>
          <h2 className="mt-2 text-2xl font-bold text-emerald-900">Merged file saved successfully</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl bg-white p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Source files</p>
              <p className="mt-2 text-2xl font-bold text-gray-900">{result.total_files}</p>
            </div>
            <div className="rounded-xl bg-white p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Merged items</p>
              <p className="mt-2 text-2xl font-bold text-gray-900">{result.merged_items}</p>
            </div>
            <div className="rounded-xl bg-white p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Rows written</p>
              <p className="mt-2 text-2xl font-bold text-gray-900">{result.total_rows}</p>
            </div>
            <div className="rounded-xl bg-white p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Columns written</p>
              <p className="mt-2 text-2xl font-bold text-gray-900">{result.total_columns}</p>
            </div>
          </div>

          <div className="mt-5 rounded-xl border border-emerald-100 bg-white p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Saved path</p>
            <p className="mt-2 break-all font-mono text-sm text-gray-800">{result.output_path}</p>
            <p className="mt-2 text-sm text-gray-500">Output format: {result.output_format.toUpperCase()}</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default FolderMergePage;