/**
 * PathInput.tsx — DuckDB file path input with validation.
 */
import React from "react";
import { pickSystemFile } from "../../api/systemApi";

interface PathInputProps {
  value: string;
  onChange: (path: string) => void;
  onConnect: () => void;
  isConnecting: boolean;
  error: string | null;
}

function cleanPath(rawPath: string): string {
  const trimmed = rawPath.trim();
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

export const PathInput: React.FC<PathInputProps> = ({
  value,
  onChange,
  onConnect,
  isConnecting,
  error,
}) => {
  return (
    <div className="bg-white shadow rounded-lg p-6 max-w-2xl mx-auto mt-8">
      <h2 className="text-xl font-semibold text-gray-800 mb-4">Connect to Database</h2>
      <div className="flex space-x-4">
        <div className="flex-grow">
          <input
            type="text"
            className="w-full border border-gray-300 rounded px-4 py-2 focus:outline-none focus:border-indigo-500 font-mono text-sm"
            placeholder="e.g. C:\data\database.duckdb"
            value={value}
            onChange={(e) => onChange(cleanPath(e.target.value))}
            onKeyDown={(e) => e.key === "Enter" && onConnect()}
            disabled={isConnecting}
          />
        </div>
        <button
          onClick={async () => {
            const path = await pickSystemFile("duckdb");
            if (path) onChange(cleanPath(path));
          }}
          disabled={isConnecting}
          className="bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 font-medium py-2 px-4 rounded disabled:opacity-50 transition-colors whitespace-nowrap"
        >
          Browse...
        </button>
        <button
          onClick={onConnect}
          disabled={isConnecting || !value.trim()}
          className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2 px-6 rounded disabled:opacity-50 transition-colors"
        >
          {isConnecting ? "Connecting..." : "Connect"}
        </button>
      </div>
      {error && (
        <div className="mt-4 bg-red-50 text-red-700 px-4 py-3 rounded text-sm relative">
          <strong className="font-semibold mr-2">Connection failed:</strong>
          <span className="block sm:inline">{error}</span>
        </div>
      )}
    </div>
  );
};
