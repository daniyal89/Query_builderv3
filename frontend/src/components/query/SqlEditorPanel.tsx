import React from "react";
import type { QueryEngine } from "../../types/connection.types";
import type { QuerySourceMode } from "../../types/query.types";

interface SqlEditorPanelProps {
  engine: QueryEngine;
  sourceMode: QuerySourceMode;
  sqlText: string;
  generatedSql: string;
  isSqlDetached: boolean;
  isPreviewLoading: boolean;
  previewError: string | null;
  runError: string | null;
  isRunning: boolean;
  canRunBuilder: boolean;
  onSelectSourceMode: (mode: QuerySourceMode) => void;
  onResetFromBuilder: () => void;
  onSqlChange: (sql: string) => void;
  onRun: () => void;
}

function getStatusText(sourceMode: QuerySourceMode, isSqlDetached: boolean): string {
  if (sourceMode === "builder") {
    return "Builder SQL is active. Editing the SQL below will switch to manual mode.";
  }
  if (isSqlDetached) {
    return "Manual SQL mode is active. The editor is detached from the visual builder.";
  }
  return "Manual SQL mode is active and still matches the current builder output.";
}

export const SqlEditorPanel: React.FC<SqlEditorPanelProps> = ({
  engine,
  sourceMode,
  sqlText,
  generatedSql,
  isSqlDetached,
  isPreviewLoading,
  previewError,
  runError,
  isRunning,
  canRunBuilder,
  onSelectSourceMode,
  onResetFromBuilder,
  onSqlChange,
  onRun,
}) => {
  const canResetFromBuilder = generatedSql.trim().length > 0;
  const canRunManual = sqlText.trim().length > 0;

  return (
    <div className="mb-6 rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-800">SQL Preview &amp; Editor</h3>
          <p className="mt-1 text-xs text-gray-500">
            {getStatusText(sourceMode, isSqlDetached)}
          </p>
        </div>

        <div className="flex rounded-lg bg-gray-100 p-1">
          <button
            onClick={() => onSelectSourceMode("builder")}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
              sourceMode === "builder"
                ? "bg-white text-gray-900 shadow"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            Builder SQL
          </button>
          <button
            onClick={() => onSelectSourceMode("manual")}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
              sourceMode === "manual"
                ? "bg-white text-gray-900 shadow"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            Manual SQL
          </button>
        </div>
      </div>

      <div className="p-4">
        {engine === "oracle" && (
          <div className="mb-4 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
            Marcadose is read-only. Only single-statement `SELECT` or `WITH ... SELECT` SQL is allowed, even in
            manual mode.
          </div>
        )}

        {previewError && (
          <div className="mb-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            {previewError}
          </div>
        )}

        {runError && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {runError}
          </div>
        )}

        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            {isPreviewLoading ? "Refreshing SQL preview..." : "Editable SQL"}
          </span>
          <span className="text-xs text-gray-400">
            {sourceMode === "builder" ? "Run uses builder output" : "Run uses editor text"}
          </span>
        </div>

        <textarea
          value={sqlText}
          onChange={(event) => onSqlChange(event.target.value)}
          className="min-h-[220px] w-full rounded border border-gray-300 bg-gray-50 p-3 font-mono text-sm text-gray-800 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
          placeholder={
            sourceMode === "manual"
              ? "Write SQL directly here."
              : "Select a table and configure the builder to generate SQL."
          }
          spellCheck={false}
        />

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="text-xs text-gray-500">
            {sourceMode === "manual" && isSqlDetached
              ? "Reset from Builder to resync the editor."
              : "Builder changes auto-refresh the SQL preview when possible."}
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={onResetFromBuilder}
              disabled={!canResetFromBuilder}
              className="rounded border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Reset from Builder
            </button>
            <button
              onClick={onRun}
              disabled={isRunning || (sourceMode === "builder" ? !canRunBuilder : !canRunManual)}
              className="rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isRunning ? "Running..." : sourceMode === "builder" ? "Run Builder SQL" : "Run Manual SQL"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
