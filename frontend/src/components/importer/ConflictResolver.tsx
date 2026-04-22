import React, { useState } from "react";
import type { UploadSheetsResponse, ColumnResolution, CompositeKey } from "../../types/merge.types";

interface ConflictResolverProps {
  uploadResult: UploadSheetsResponse;
  onSubmit: (resolutions: ColumnResolution[], compositeKey: CompositeKey) => void;
  isLoading: boolean;
}

export const ConflictResolver: React.FC<ConflictResolverProps> = ({ uploadResult, onSubmit, isLoading }) => {
  const [resolutions, setResolutions] = useState<Record<string, ColumnResolution>>({});
  const [compositeKey, setCompositeKey] = useState<CompositeKey | "">("");

  const handleResolutionChange = (
    fileName: string,
    colName: string,
    action: "map" | "ignore",
    standardName?: string
  ) => {
    const key = `${fileName}::${colName}`;
    setResolutions((prev) => ({
      ...prev,
      [key]: {
        source_file: fileName,
        source_column: colName,
        action,
        standard_name: standardName,
      },
    }));
  };

  const handleSubmit = () => {
    if (!compositeKey) {
      alert("Please select a Composite PK Strategy.");
      return;
    }
    
    // Convert object to array. We must ensure every detected column has an explicit resolution
    // For simplicity, any untouched column defaults to mapped with its own name.
    const finalResolutions: ColumnResolution[] = uploadResult.detected_columns.map(col => {
      const key = `${col.source_file}::${col.name}`;
      return resolutions[key] || {
        source_file: col.source_file,
        source_column: col.name,
        action: "map",
        standard_name: col.name
      };
    });

    onSubmit(finalResolutions, compositeKey as CompositeKey);
  };

  return (
    <div className="conflict-resolver p-6 bg-white rounded-lg shadow">
      <h3 className="text-xl font-bold mb-4">Phase 2: Resolve Conflicts</h3>
      
      {uploadResult.conflicts.length > 0 && (
        <div className="mb-6 p-4 bg-yellow-50 border border-yellow-200 rounded text-yellow-800">
          <p className="font-semibold mb-2">⚠️ Mismatched columns detected across sheets:</p>
          <ul className="list-disc pl-5 text-sm">
            {uploadResult.conflicts.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
      )}

      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Master Table Match Strategy (Composite Key)
        </label>
        <select
          value={compositeKey}
          onChange={(e) => setCompositeKey(e.target.value as CompositeKey)}
          className="border border-gray-300 rounded p-2 w-full max-w-sm"
        >
          <option value="" disabled>Select a composite key...</option>
          <option value="Acc_id+DISCOM">Acc_id + DISCOM</option>
          <option value="Acc_id+DIV_CODE">Acc_id + DIV_CODE</option>
        </select>
      </div>

      <div className="overflow-x-auto mb-6 border border-gray-200 rounded">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Source File</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Column Name</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Sample Data</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Action</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Standard Name</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {uploadResult.detected_columns.map((col, idx) => {
              const resKey = `${col.source_file}::${col.name}`;
              const currentRes = resolutions[resKey];
              const isIgnored = currentRes?.action === "ignore";
              const stdName = currentRes?.standard_name || col.name;

              return (
                <tr key={idx} className={isIgnored ? "opacity-50 bg-gray-50" : ""}>
                  <td className="px-4 py-3">{col.source_file}</td>
                  <td className="px-4 py-3 font-medium">{col.name}</td>
                  <td className="px-4 py-3 text-gray-500 truncate max-w-xs" title={col.sample_values.join(", ")}>
                    {col.sample_values.slice(0, 3).join(", ")}
                  </td>
                  <td className="px-4 py-3">
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={isIgnored}
                        onChange={(e) => handleResolutionChange(col.source_file, col.name, e.target.checked ? "ignore" : "map", col.name)}
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      <span>Ignore</span>
                    </label>
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="text"
                      value={isIgnored ? "" : stdName}
                      disabled={isIgnored}
                      onChange={(e) => handleResolutionChange(col.source_file, col.name, "map", e.target.value)}
                      className="border border-gray-300 rounded p-1 w-full disabled:bg-gray-100"
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <button
        onClick={handleSubmit}
        disabled={isLoading || !compositeKey}
        className="w-full bg-blue-600 text-white px-4 py-2 rounded shadow hover:bg-blue-700 disabled:opacity-50 transition"
      >
        {isLoading ? "Merging..." : "Confirm & Merge Sheets"}
      </button>
    </div>
  );
};
