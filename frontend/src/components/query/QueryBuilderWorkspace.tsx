/**
 * QueryBuilderWorkspace.tsx â€” Reusable query builder UI for local DuckDB and Marcadose.
 */

import React, { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryBuilder } from "../../hooks/useQueryBuilder";
import type { QueryEngine } from "../../types/connection.types";
import type { TableMetadata } from "../../types/schema.types";
import { ColumnPicker } from "./ColumnPicker";
import { FilterPanel } from "./FilterPanel";
import { PivotControl } from "./PivotControl";
import { ResultsGrid } from "./ResultsGrid";
import { SortControl } from "./SortControl";
import { SqlEditorPanel } from "./SqlEditorPanel";
import { TableSelector } from "./TableSelector";

interface QueryBuilderWorkspaceProps {
  engine: QueryEngine;
  title: string;
  tables: TableMetadata[];
}

export const QueryBuilderWorkspace: React.FC<QueryBuilderWorkspaceProps> = ({
  engine,
  title,
  tables,
}) => {
  const [searchParams] = useSearchParams();
  const initialTable = searchParams.get("table");

  const {
    state,
    setTable,
    toggleColumn,
    addFilter,
    updateFilter,
    removeFilter,
    setSort,
    setMode,
    setPivotConfig,
    setLimitRows,
    setSourceMode,
    updateSqlText,
    resetSqlToBuilder,
    executeQuery,
  } = useQueryBuilder(engine);

  const activeTable = useMemo(
    () => tables.find((table) => table.table_name === state.table),
    [state.table, tables]
  );
  const availableColumns = activeTable?.columns ?? [];
  const availableColumnNames = useMemo(
    () => availableColumns.map((column) => column.name),
    [availableColumns]
  );
  const reportModeDisabled = engine === "oracle";
  const shouldShowSelectTableHint =
    !state.table && state.sourceMode === "builder" && !state.sqlText.trim();

  useEffect(() => {
    if (initialTable && !state.table) {
      setTable(initialTable);
    }
  }, [initialTable, state.table, setTable]);

  useEffect(() => {
    if (reportModeDisabled && state.mode === "REPORT") {
      setMode("LIST");
    }
  }, [reportModeDisabled, setMode, state.mode]);

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{title}</h1>
            {reportModeDisabled && (
              <p className="mt-2 text-sm text-amber-700">
                Report mode is not available for Marcadose yet. Use Fetch List or manual SQL for read-only Oracle
                queries.
              </p>
            )}
          </div>

          <div className="flex rounded-lg bg-gray-200 p-1">
            <button
              onClick={() => setMode("LIST")}
              className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
                state.mode === "LIST"
                  ? "bg-white text-gray-900 shadow"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Fetch List
            </button>
            <button
              onClick={() => setMode("REPORT")}
              disabled={reportModeDisabled}
              className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
                state.mode === "REPORT"
                  ? "bg-white text-gray-900 shadow"
                  : "text-gray-500 hover:text-gray-700"
              } disabled:cursor-not-allowed disabled:opacity-50`}
            >
              Generate Report
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
          <div className="lg:col-span-1">
            <TableSelector tables={tables || []} activeTable={state.table} onSelect={setTable} />

            {state.table && state.mode === "LIST" && (
              <>
                <ColumnPicker
                  columns={availableColumnNames}
                  selectedColumns={state.selectedColumns}
                  onToggleColumn={toggleColumn}
                />
                <FilterPanel
                  filters={state.filters}
                  columns={availableColumns}
                  onAddFilter={addFilter}
                  onUpdateFilter={updateFilter}
                  onRemoveFilter={removeFilter}
                />
                <SortControl
                  sortRules={state.sort}
                  columns={availableColumnNames}
                  onChange={setSort}
                />
                <div className="mb-4 rounded border border-gray-200 bg-white p-4 shadow-sm">
                  <label className="mb-1 block text-sm font-semibold text-gray-700">
                    Limit Rows
                  </label>
                  <p className="mb-2 text-xs text-gray-400">Set to 0 for No Limit</p>
                  <input
                    type="number"
                    value={state.limitRows}
                    onChange={(event) => setLimitRows(Number(event.target.value))}
                    className="w-full rounded border border-gray-300 p-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    min="0"
                  />
                </div>
              </>
            )}

            {state.table && state.mode === "REPORT" && !reportModeDisabled && (
              <>
                <PivotControl
                  columns={availableColumnNames}
                  config={state.pivotConfig}
                  onChange={setPivotConfig}
                />
                <FilterPanel
                  filters={state.filters}
                  columns={availableColumns}
                  onAddFilter={addFilter}
                  onUpdateFilter={updateFilter}
                  onRemoveFilter={removeFilter}
                />
              </>
            )}
          </div>

          <div className="lg:col-span-3">
            <SqlEditorPanel
              engine={engine}
              sourceMode={state.sourceMode}
              sqlText={state.sqlText}
              generatedSql={state.generatedSql}
              isSqlDetached={state.isSqlDetached}
              isPreviewLoading={state.isPreviewLoading}
              previewError={state.previewError}
              runError={state.error}
              isRunning={state.isLoading}
              canRunBuilder={!!state.table && !!state.generatedSql && !state.previewError}
              onSelectSourceMode={setSourceMode}
              onResetFromBuilder={resetSqlToBuilder}
              onSqlChange={updateSqlText}
              onRun={executeQuery}
            />

            {shouldShowSelectTableHint && (
              <div className="mb-6 flex h-64 items-center justify-center rounded-lg border-2 border-dashed border-gray-200 bg-white">
                <div className="text-center text-gray-400">
                  <p className="text-lg font-medium">Select a table to begin</p>
                  <p className="mt-1 text-sm">
                    Choose a table from the left panel to build a query, or switch to manual SQL.
                  </p>
                </div>
              </div>
            )}

            <ResultsGrid result={state.result} isLoading={state.isLoading} />
          </div>
        </div>
      </div>
    </div>
  );
};
