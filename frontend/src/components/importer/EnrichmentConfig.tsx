// @ts-nocheck
import React, { useEffect, useMemo, useState } from "react";
import { useConnection } from "../../hooks/useConnection";
import { pickSystemFile } from "../../api/systemApi";
import type { JoinKeyMapping, OutputFormat, UploadSheetsResponse } from "../../types/merge.types";

interface EnrichmentConfigProps {
  uploadResult: UploadSheetsResponse;
  uploadedFile?: File | null;
  onSubmit: (
    masterTable: string,
    fetchColumns: string[],
    outputFormat: OutputFormat,
    dbPath: string,
    mergedFile: File,
    joinKeys: JoinKeyMapping[]
  ) => void;
  onCancel?: () => void;
  isLoading: boolean;
  enrichProgress?: string | null;
}

export const EnrichmentConfig: React.FC<EnrichmentConfigProps> = ({
  uploadResult,
  uploadedFile,
  onSubmit,
  onCancel,
  isLoading,
  enrichProgress,
}) => {
  const {
    dbPath,
    setDbPath,
    tables,
    isConnected,
    isConnecting,
    error: connectionError,
    connect,
  } = useConnection();
  const [masterTable, setMasterTable] = useState<string>("master");
  const outputFormat: OutputFormat = "xlsx";
  const [joinKeys, setJoinKeys] = useState<JoinKeyMapping[]>([{ fileColumn: "", tableColumn: "" }]);
  const [columnsToFetch, setColumnsToFetch] = useState<string[]>([]);
  const [didAutoLoadOnMount, setDidAutoLoadOnMount] = useState(false);
  const [columnSearchQuery, setColumnSearchQuery] = useState("");

  const availableMasterColumns = useMemo(
    () => tables?.find((table) => table.table_name === masterTable)?.columns.map((column) => column.name) || [],
    [masterTable, tables]
  );

  /** Filtered columns based on search query */
  const filteredMasterColumns = useMemo(() => {
    if (!columnSearchQuery.trim()) return availableMasterColumns;
    const query = columnSearchQuery.trim().toLowerCase();
    return availableMasterColumns.filter((col) => col.toLowerCase().includes(query));
  }, [availableMasterColumns, columnSearchQuery]);

  useEffect(() => {
    if (tables.length === 0) return;

    const hasSelectedTable = tables.some((table) => table.table_name === masterTable);
    if (hasSelectedTable) return;

    const preferredTable = tables.find((table) => table.table_name.toLowerCase() === "master") ?? tables[0];
    setMasterTable(preferredTable.table_name);
  }, [masterTable, tables]);

  useEffect(() => {
    setColumnsToFetch((prev) => prev.filter((column) => availableMasterColumns.includes(column)));
  }, [availableMasterColumns]);

  useEffect(() => {
    if (didAutoLoadOnMount) return;
    setDidAutoLoadOnMount(true);

    if (dbPath && !isConnected && !isConnecting) {
      void connect();
    }
  }, [connect, dbPath, didAutoLoadOnMount, isConnected, isConnecting]);

  const handleToggleFetchColumn = (column: string) => {
    setColumnsToFetch((prev) =>
      prev.includes(column) ? prev.filter((item) => item !== column) : [...prev, column]
    );
  };

  const handleSelectAll = () => {
    setColumnsToFetch([...availableMasterColumns]);
  };

  const handleDeselectAll = () => {
    setColumnsToFetch([]);
  };

  const handleSubmit = () => {
    if (!masterTable) {
      alert("Master Table name is required.");
      return;
    }
    if (joinKeys.some(k => !k.fileColumn || !k.tableColumn)) {
      alert("Please complete all join key mappings, or remove empty ones.");
      return;
    }
    if (joinKeys.length === 0) {
      alert("Please add at least one join key mapping.");
      return;
    }
    if (columnsToFetch.length === 0) {
      alert("Please select at least one column to fetch.");
      return;
    }
    if (!dbPath) {
      alert("Please specify the Local DuckDB file path.");
      return;
    }
    if (!uploadedFile) {
      alert("Uploaded file is missing. Please restart the wizard.");
      return;
    }
    onSubmit(
      masterTable,
      columnsToFetch,
      outputFormat,
      dbPath,
      uploadedFile,
      joinKeys
    );
  };

  const handleAddJoinKey = () => setJoinKeys(prev => [...prev, { fileColumn: "", tableColumn: "" }]);
  const handleRemoveJoinKey = (index: number) => setJoinKeys(prev => prev.filter((_, i) => i !== index));
  const handleUpdateJoinKey = (index: number, field: keyof JoinKeyMapping, value: string) => {
    setJoinKeys(prev => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const uniqueUploadColumns = Array.from(new Set(uploadResult.detected_columns.map((column) => column.name)));

  const allSelected = availableMasterColumns.length > 0 && columnsToFetch.length === availableMasterColumns.length;
  const someSelected = columnsToFetch.length > 0 && columnsToFetch.length < availableMasterColumns.length;

  return (
    <div className="enrichment-config rounded-lg bg-white p-6 shadow">
      <h3 className="mb-4 text-xl font-bold">Phase 3: Enrich Data</h3>

      <div className="mb-6 rounded border border-green-200 bg-green-50 p-4 text-green-800">
        <p className="flex justify-between text-sm font-medium">
          <span>File uploaded successfully. Ready for enrichment.</span>
          <span className="font-semibold">{uploadedFile?.name}</span>
        </p>
      </div>

      {/* Progress indicator during enrichment */}
      {isLoading && enrichProgress && (
        <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <div className="flex items-center gap-3">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
            <div className="flex-1">
              <p className="text-sm font-medium text-blue-800">{enrichProgress}</p>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-blue-100">
                <div className="h-full animate-pulse rounded-full bg-blue-500" style={{ width: "70%" }} />
              </div>
            </div>
          </div>
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="mt-3 rounded border border-red-300 bg-white px-4 py-1.5 text-sm font-semibold text-red-700 transition hover:bg-red-50"
            >
              ✕ Stop Enrichment
            </button>
          )}
        </div>
      )}

      <div className="mb-6">
        <div className="mb-1 flex items-center justify-between gap-3">
          <label className="block text-sm font-medium text-gray-700">Local DuckDB File Path</label>
          <span className={`text-xs font-medium ${isConnected ? "text-green-700" : "text-gray-500"}`}>
            {isConnected ? "Connected and ready to load master columns" : "Disconnected"}
          </span>
        </div>
        <div className="flex flex-col gap-3 md:flex-row">
          <div className="flex w-full gap-2 md:w-auto md:flex-1">
            <input
              type="text"
              value={dbPath}
              onChange={(event) => setDbPath(event.target.value)}
              className="w-full rounded border border-gray-300 p-2 font-mono text-sm"
              placeholder="e.g., C:\Users\aimld\your_data.duckdb"
            />
            <button
              type="button"
              onClick={async () => {
                const path = await pickSystemFile("duckdb");
                if (path) setDbPath(path);
              }}
              className="rounded border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 whitespace-nowrap"
            >
              Browse...
            </button>
          </div>
          <button
            type="button"
            onClick={() => void connect()}
            disabled={isConnecting || !dbPath}
            className="rounded border border-indigo-200 px-4 py-2 text-sm font-semibold text-indigo-700 transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isConnecting ? "Loading..." : isConnected ? "Reload Master Columns" : "Connect & Load Columns"}
          </button>
        </div>
        {connectionError && <p className="mt-2 text-sm text-red-600">{connectionError}</p>}
        {!connectionError && (
          <p className="mt-2 text-sm text-gray-500">
            The master-column list is loaded from the DuckDB file path above.
          </p>
        )}
      </div>

      <div className="mb-6 grid grid-cols-1 gap-8 border-t border-gray-200 pt-6 md:grid-cols-2">
        <div>
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">Source Table In DuckDB *</label>
            <select
              value={masterTable}
              onChange={(event) => setMasterTable(event.target.value)}
              className="w-full rounded border border-gray-300 p-2 text-sm"
              disabled={!isConnected || tables.length === 0}
            >
              {tables.length === 0 && <option value="">-- Connect DuckDB First --</option>}
              {tables.map((table) => (
                <option key={table.table_name} value={table.table_name}>
                  {table.table_name} ({table.columns.length} columns)
                </option>
              ))}
            </select>
          </div>

          <div className="mb-3 flex items-center justify-between">
            <h4 className="font-semibold text-gray-800">Dynamic Key Mapping</h4>
            <button
              onClick={handleAddJoinKey}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
            >
              + Add Key
            </button>
          </div>
          <div className="flex flex-col gap-3">
            {joinKeys.map((keyMap, idx) => (
              <div key={idx} className="flex flex-col gap-2 rounded border border-gray-200 bg-gray-50 p-3 relative">
                {joinKeys.length > 1 && (
                  <button
                    onClick={() => handleRemoveJoinKey(idx)}
                    className="absolute -right-2 -top-2 rounded-full border border-gray-200 bg-white px-2 py-0.5 text-xs text-red-500 hover:bg-red-50"
                  >
                    x
                  </button>
                )}
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">File Column</label>
                  <select
                    value={keyMap.fileColumn}
                    onChange={(e) => handleUpdateJoinKey(idx, "fileColumn", e.target.value)}
                    className="w-full rounded border border-gray-300 p-1.5 text-sm"
                  >
                    <option value="">-- Select File Column --</option>
                    {uniqueUploadColumns.map((column) => (
                      <option key={column} value={column}>{column}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">Master Table Column</label>
                  <select
                    value={keyMap.tableColumn}
                    onChange={(e) => handleUpdateJoinKey(idx, "tableColumn", e.target.value)}
                    className="w-full rounded border border-gray-300 p-1.5 text-sm"
                    disabled={!isConnected || availableMasterColumns.length === 0}
                  >
                    <option value="">-- Select Table Column --</option>
                    {availableMasterColumns.map((column) => (
                      <option key={column} value={column}>{column}</option>
                    ))}
                  </select>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-3 flex items-center justify-between">
            <h4 className="font-semibold text-gray-800">
              Fetch Columns (From Master)
              {availableMasterColumns.length > 0 && (
                <span className="ml-2 text-xs font-normal text-gray-500">
                  {columnsToFetch.length}/{availableMasterColumns.length} selected
                </span>
              )}
            </h4>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={allSelected ? handleDeselectAll : handleSelectAll}
                disabled={availableMasterColumns.length === 0}
                className="rounded border border-indigo-200 bg-white px-2.5 py-1 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {allSelected ? "Deselect All" : "Select All"}
              </button>
            </div>
          </div>

          {/* Column search box */}
          <div className="mb-2">
            <input
              type="text"
              value={columnSearchQuery}
              onChange={(e) => setColumnSearchQuery(e.target.value)}
              placeholder="🔍 Search columns..."
              className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm placeholder-gray-400 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
            />
          </div>

          <div className="h-48 overflow-y-auto rounded border border-gray-300 bg-gray-50 p-3">
            {availableMasterColumns.length === 0 ? (
              <p className="text-sm italic text-gray-500">
                {isConnected
                  ? "No columns found for the selected DuckDB table. Choose another table if needed."
                  : "No columns found. Connect the DuckDB file above to load the selected table schema."}
              </p>
            ) : filteredMasterColumns.length === 0 ? (
              <p className="text-sm italic text-gray-500">
                No columns match "{columnSearchQuery}". Try a different search.
              </p>
            ) : (
              filteredMasterColumns.map((column) => (
                <label
                  key={column}
                  className="mb-1.5 flex cursor-pointer items-center gap-2 rounded p-1 hover:bg-gray-100"
                >
                  <input
                    type="checkbox"
                    checked={columnsToFetch.includes(column)}
                    onChange={() => handleToggleFetchColumn(column)}
                    className="rounded text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="truncate text-sm text-gray-700">{column}</span>
                </label>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={handleSubmit}
          disabled={
            isLoading ||
            joinKeys.some(k => !k.fileColumn || !k.tableColumn) ||
            joinKeys.length === 0 ||
            columnsToFetch.length === 0 ||
            !dbPath ||
            !uploadedFile ||
            !isConnected
          }
          className="rounded bg-indigo-600 px-4 py-3 font-bold text-white shadow transition hover:bg-indigo-700 disabled:opacity-50"
        >
          {isLoading ? "Enriching Data..." : "Enrich & Generate File"}
        </button>
        {isLoading && onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-red-300 bg-white px-4 py-3 font-semibold text-red-700 transition hover:bg-red-50"
          >
            ✕ Stop
          </button>
        )}
      </div>
      <p className="mt-3 text-sm text-gray-500">
        Large files or wide Excel exports can take a few minutes to process and download.
      </p>
    </div>
  );
};
