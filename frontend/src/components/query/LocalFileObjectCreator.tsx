import React, { useEffect, useMemo, useState } from "react";
import { createLocalFileObject } from "../../api/localObjectApi";
import { pickSystemFile } from "../../api/systemApi";
import type { LocalFileObjectType } from "../../types/localObject.types";

interface LocalFileObjectCreatorProps {
  onCreated: () => Promise<unknown> | unknown;
}

function inferObjectName(filePath: string): string {
  const fileName = filePath.split(/[\\/]/).pop() || "";
  const withoutExtension = fileName.replace(/\.[^.]+$/, "");
  const normalized = withoutExtension.replace(/[^A-Za-z0-9_]/g, "_").replace(/_+/g, "_");
  const trimmed = normalized.replace(/^_+|_+$/g, "");
  if (!trimmed) {
    return "";
  }
  return /^[A-Za-z_]/.test(trimmed) ? trimmed : `file_${trimmed}`;
}

function getExtension(filePath: string): string {
  return (filePath.match(/\.([^.\\/]+)$/)?.[1] || "").toLowerCase();
}

export const LocalFileObjectCreator: React.FC<LocalFileObjectCreatorProps> = ({ onCreated }) => {
  const [filePath, setFilePath] = useState("");
  const [objectName, setObjectName] = useState("");
  const [objectNameTouched, setObjectNameTouched] = useState(false);
  const [objectType, setObjectType] = useState<LocalFileObjectType>("TABLE");
  const [replace, setReplace] = useState(false);
  const [header, setHeader] = useState(true);
  const [sheetName, setSheetName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const extension = useMemo(() => getExtension(filePath), [filePath]);
  const isExcel = extension === "xlsx" || extension === "xls";

  useEffect(() => {
    if (!objectNameTouched) {
      setObjectName(inferObjectName(filePath));
    }
  }, [filePath, objectNameTouched]);

  const handleCreate = async () => {
    setIsCreating(true);
    setMessage(null);
    setError(null);

    try {
      const response = await createLocalFileObject({
        file_path: filePath,
        object_name: objectName,
        object_type: objectType,
        replace,
        header,
        sheet_name: sheetName.trim() || null,
      });
      await onCreated();
      setMessage(response.message);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || "Failed to create local object.");
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="mb-4 rounded border border-emerald-200 bg-emerald-50/70 p-4 shadow-sm">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-emerald-950">Create From File</h3>
        <p className="mt-1 text-xs text-emerald-800">
          Local only. Create a DuckDB table or view from CSV, TSV, or XLSX using a full file path.
        </p>
      </div>

      <label className="mb-3 block">
        <span className="mb-1 block text-xs font-semibold text-gray-700">File path</span>
        <div className="flex gap-2">
          <input
            type="text"
            value={filePath}
            onChange={(event) => setFilePath(event.target.value)}
            className="w-full rounded border border-gray-300 bg-white px-2 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
            placeholder="C:\\data\\source.xlsx or C:\\data\\source.csv"
          />
          <button
            type="button"
            onClick={async () => {
              const path = await pickSystemFile("data");
              if (path) {
                setFilePath(path);
                if (!objectNameTouched) setObjectName(inferObjectName(path));
              }
            }}
            className="rounded border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-700 transition hover:bg-gray-50 whitespace-nowrap"
          >
            Browse...
          </button>
        </div>
      </label>

      <label className="mb-3 block">
        <span className="mb-1 block text-xs font-semibold text-gray-700">Table/View name</span>
        <input
          type="text"
          value={objectName}
          onChange={(event) => {
            setObjectNameTouched(true);
            setObjectName(event.target.value);
          }}
          className="w-full rounded border border-gray-300 bg-white px-2 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
          placeholder="new_local_table"
        />
      </label>

      <div className="mb-3 grid grid-cols-2 gap-2">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-gray-700">Create as</span>
          <select
            value={objectType}
            onChange={(event) => setObjectType(event.target.value as LocalFileObjectType)}
            className="w-full rounded border border-gray-300 bg-white px-2 py-2 text-xs"
          >
            <option value="TABLE">Table</option>
            <option value="VIEW">View</option>
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-gray-700">Header row</span>
          <select
            value={header ? "yes" : "no"}
            onChange={(event) => setHeader(event.target.value === "yes")}
            className="w-full rounded border border-gray-300 bg-white px-2 py-2 text-xs"
          >
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
      </div>

      {isExcel && (
        <label className="mb-3 block">
          <span className="mb-1 block text-xs font-semibold text-gray-700">Sheet name optional</span>
          <input
            type="text"
            value={sheetName}
            onChange={(event) => setSheetName(event.target.value)}
            className="w-full rounded border border-gray-300 bg-white px-2 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
            placeholder="Leave blank for first sheet"
          />
        </label>
      )}

      <label className="mb-3 flex items-center gap-2 text-xs text-gray-700">
        <input
          type="checkbox"
          checked={replace}
          onChange={(event) => setReplace(event.target.checked)}
          className="rounded text-emerald-600"
        />
        Replace if it already exists
      </label>

      {extension === "xls" && (
        <div className="mb-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          DuckDB reads `.xlsx`, not legacy `.xls`. Save the workbook as `.xlsx` first.
        </div>
      )}

      {error && <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}
      {message && (
        <div className="mb-3 rounded border border-emerald-200 bg-white px-3 py-2 text-xs text-emerald-700">
          {message}
        </div>
      )}

      <button
        type="button"
        onClick={handleCreate}
        disabled={isCreating || !filePath.trim() || !objectName.trim()}
        className="w-full rounded bg-emerald-700 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isCreating ? "Creating..." : `Create ${objectType.toLowerCase()}`}
      </button>
    </div>
  );
};
