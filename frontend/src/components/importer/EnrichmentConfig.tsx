// @ts-nocheck
import React, { useState } from "react";
import { useConnection } from "../../hooks/useConnection";
import type { OutputFormat, UploadSheetsResponse } from "../../types/merge.types";

interface EnrichmentConfigProps {
  uploadResult: UploadSheetsResponse;
  uploadedFile?: File | null;
  onSubmit: (
    masterTable: string,
    fetchColumns: string[],
    outputFormat: OutputFormat,
    dbPath: string,
    mergedFile: File,
    mappedAcctIdCol: string,
    mappedSecondaryCol: string,
    secondaryColType: string
  ) => void;
  isLoading: boolean;
}

export const EnrichmentConfig: React.FC<EnrichmentConfigProps> = ({
  uploadResult,
  uploadedFile,
  onSubmit,
  isLoading,
}) => {
  const { tables } = useConnection();
  const [masterTable, setMasterTable] = useState<string>("master");
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("xlsx");
  const [dbPath, setDbPath] = useState<string>("C:\\Users\\aimld\\uppcl_latest.duckdb");
  const [mappedAcctIdCol, setMappedAcctIdCol] = useState<string>("");
  const [mappedSecondaryCol, setMappedSecondaryCol] = useState<string>("");
  const [secondaryColType, setSecondaryColType] = useState<"DISCOM" | "DIV_CODE">("DISCOM");
  const [columnsToFetch, setColumnsToFetch] = useState<string[]>([]);

  const availableMasterColumns =
    tables?.find((table) => table.table_name === masterTable)?.columns.map((column) => column.name) || [];

  const handleToggleFetchColumn = (column: string) => {
    setColumnsToFetch((prev) =>
      prev.includes(column) ? prev.filter((item) => item !== column) : [...prev, column]
    );
  };

  const handleSubmit = () => {
    if (!masterTable) {
      alert("Master Table name is required.");
      return;
    }
    if (!mappedAcctIdCol) {
      alert("Please map the ACCT_ID column.");
      return;
    }
    if (!mappedSecondaryCol) {
      alert(`Please map the ${secondaryColType} column.`);
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
      mappedAcctIdCol,
      mappedSecondaryCol,
      secondaryColType
    );
  };

  const uniqueUploadColumns = Array.from(new Set(uploadResult.detected_columns.map((column) => column.name)));

  return (
    <div className="enrichment-config rounded-lg bg-white p-6 shadow">
      <h3 className="mb-4 text-xl font-bold">Phase 3: Enrich Data</h3>

      <div className="mb-6 rounded border border-green-200 bg-green-50 p-4 text-green-800">
        <p className="flex justify-between text-sm font-medium">
          <span>File uploaded successfully. Ready for enrichment.</span>
          <span className="font-semibold">{uploadedFile?.name}</span>
        </p>
      </div>

      <div className="mb-6">
        <label className="mb-1 block text-sm font-medium text-gray-700">Local DuckDB File Path</label>
        <input
          type="text"
          value={dbPath}
          onChange={(event) => setDbPath(event.target.value)}
          className="w-full rounded border border-gray-300 p-2 font-mono text-sm"
          placeholder="e.g., C:\\Users\\aimld\\uppcl_latest.duckdb"
        />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-8 border-t border-gray-200 pt-6 md:grid-cols-2">
        <div>
          <h4 className="mb-3 font-semibold text-gray-800">Key Mapping (Uploaded File)</h4>
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">Map to ACCT_ID *</label>
            <select
              value={mappedAcctIdCol}
              onChange={(event) => setMappedAcctIdCol(event.target.value)}
              className="w-full rounded border border-gray-300 p-2 text-sm"
            >
              <option value="">-- Select Column --</option>
              {uniqueUploadColumns.map((column) => (
                <option key={column} value={column}>
                  {column}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Map Secondary Key *</label>
            <div className="mb-2 flex gap-4">
              <label className="flex cursor-pointer items-center gap-1 text-sm">
                <input
                  type="radio"
                  name="secondaryType"
                  value="DISCOM"
                  checked={secondaryColType === "DISCOM"}
                  onChange={() => setSecondaryColType("DISCOM")}
                  className="text-indigo-600"
                />
                DISCOM
              </label>
              <label className="flex cursor-pointer items-center gap-1 text-sm">
                <input
                  type="radio"
                  name="secondaryType"
                  value="DIV_CODE"
                  checked={secondaryColType === "DIV_CODE"}
                  onChange={() => setSecondaryColType("DIV_CODE")}
                  className="text-indigo-600"
                />
                DIV_CODE
              </label>
            </div>
            <select
              value={mappedSecondaryCol}
              onChange={(event) => setMappedSecondaryCol(event.target.value)}
              className="w-full rounded border border-gray-300 p-2 text-sm"
            >
              <option value="">-- Select Column --</option>
              {uniqueUploadColumns.map((column) => (
                <option key={column} value={column}>
                  {column}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <h4 className="mb-3 font-semibold text-gray-800">Fetch Columns (From Master)</h4>
          <div className="h-48 overflow-y-auto rounded border border-gray-300 bg-gray-50 p-3">
            {availableMasterColumns.length === 0 ? (
              <p className="text-sm italic text-gray-500">
                No columns found. Please ensure the database is connected.
              </p>
            ) : (
              availableMasterColumns.map((column) => (
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

      <button
        onClick={handleSubmit}
        disabled={
          isLoading ||
          !mappedAcctIdCol ||
          !mappedSecondaryCol ||
          columnsToFetch.length === 0 ||
          !dbPath ||
          !uploadedFile
        }
        className="mt-4 w-full rounded bg-indigo-600 px-4 py-3 font-bold text-white shadow transition hover:bg-indigo-700 disabled:opacity-50"
      >
        {isLoading ? "Enriching Data..." : "Enrich & Generate File"}
      </button>
    </div>
  );
};
