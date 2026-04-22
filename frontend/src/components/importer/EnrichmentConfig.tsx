// @ts-nocheck
import React, { useState } from "react";
import type { MergeSheetsResponse, OutputFormat } from "../../types/merge.types";

interface EnrichmentConfigProps {
  mergeResult: MergeSheetsResponse;
  onSubmit: (masterTable: string, fetchColumns: string[], outputFormat: OutputFormat, dbPath: string, mergedFile: File) => void;
  isLoading: boolean;
}

export const EnrichmentConfig: React.FC<EnrichmentConfigProps> = ({ mergeResult, onSubmit, isLoading }) => {
  const [masterTable, setMasterTable] = useState<string>("master");
  const [targetColumn, setTargetColumn] = useState<string>("");
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("xlsx");
  const [dbPath, setDbPath] = useState<string>("");
  const [mergedFile, setMergedFile] = useState<File | null>(null);

  const handleSubmit = () => {
    if (!masterTable) {
      alert("Master Table name is required.");
      return;
    }
    if (!targetColumn) {
      alert("Please specify a target column to fetch.");
      return;
    }
    if (!dbPath) {
      alert("Please specify the Local DuckDB file path.");
      return;
    }
    if (!mergedFile) {
      alert("Please upload a merged CSV/Excel file for testing Phase 3.");
      return;
    }
    onSubmit(masterTable, [targetColumn], outputFormat, dbPath, mergedFile);
  };

  return (
    <div className="enrichment-config p-6 bg-white rounded-lg shadow">
      <h3 className="text-xl font-bold mb-4">Phase 3: Enrich Data</h3>
      
      <div className="mb-6 bg-green-50 text-green-800 p-4 border border-green-200 rounded">
        <p className="font-medium text-sm">
          ✓ Sheets successfully resolved. (Ready for Enrichment)
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Local DuckDB File Path
          </label>
          <input
            type="text"
            value={dbPath}
            onChange={(e) => setDbPath(e.target.value)}
            className="border border-gray-300 rounded p-2 w-full text-sm font-mono"
            placeholder="e.g., C:\Users\aimld\uppcl_latest.duckdb"
          />
        </div>

        <div className="col-span-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Merged Dataset File (Temp Workaround)
          </label>
          <input
            type="file"
            accept=".csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel"
            onChange={(e) => setMergedFile(e.target.files?.[0] || null)}
            className="border border-gray-300 rounded p-1 w-full text-sm bg-white"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Column to Fetch (from 'master' table)
          </label>
          <input
            type="text"
            value={targetColumn}
            onChange={(e) => setTargetColumn(e.target.value)}
            className="border border-gray-300 rounded p-2 w-full text-sm mb-1"
            placeholder="e.g., LATEST_BILL_AMT"
          />
        </div>
      </div>

      <button
        onClick={handleSubmit}
        disabled={isLoading || !targetColumn || !dbPath || !mergedFile}
        className="w-full bg-indigo-600 text-white px-4 py-2 rounded shadow hover:bg-indigo-700 disabled:opacity-50 transition"
      >
        {isLoading ? "Enriching Data..." : "Enrich & Generate File"}
      </button>
    </div>
  );
};
