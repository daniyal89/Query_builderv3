/**
 * QueryBuilderWorkspace.tsx â€” Reusable query builder UI for local DuckDB and Marcadose.
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getColumns } from "../../api/schemaApi";
import { useQueryBuilder } from "../../hooks/useQueryBuilder";
import type { QueryEngine } from "../../types/connection.types";
import type { TableMetadata } from "../../types/schema.types";
import { buildColumnOptionsForQuery } from "../../utils/queryBuilderColumns";
import { ColumnPicker } from "./ColumnPicker";
import { FilterPanel } from "./FilterPanel";
import { JoinComposer } from "./JoinComposer";
import { LocalFileObjectCreator } from "./LocalFileObjectCreator";
import { PivotControl } from "./PivotControl";
import { ResultsGrid } from "./ResultsGrid";
import { SortControl } from "./SortControl";
import { SqlEditorPanel } from "./SqlEditorPanel";
import { TableSelector } from "./TableSelector";

interface QueryBuilderWorkspaceProps {
  engine: QueryEngine;
  title: string;
  tables: TableMetadata[];
  onLocalSchemaChanged?: () => Promise<unknown> | unknown;
}

export const QueryBuilderWorkspace: React.FC<QueryBuilderWorkspaceProps> = ({
  engine,
  title,
  tables,
  onLocalSchemaChanged,
}) => {
  const [searchParams] = useSearchParams();
  const initialTable = searchParams.get("table");
  const [metadataTables, setMetadataTables] = useState<TableMetadata[]>(tables || []);
  const [columnLoadError, setColumnLoadError] = useState<string | null>(null);
  const loadingColumnTablesRef = useRef<Set<string>>(new Set());
  const loadedColumnTablesRef = useRef<Set<string>>(new Set());

  const {
    state,
    setTable,
    toggleColumn,
    addFilter,
    updateFilter,
    removeFilter,
    setSort,
    addJoin,
    updateJoin,
    removeJoin,
    addJoinCondition,
    updateJoinCondition,
    removeJoinCondition,
    setMode,
    setPivotConfig,
    setLimitRows,
    setSourceMode,
    updateSqlText,
    resetSqlToBuilder,
    executeQuery,
  } = useQueryBuilder(engine);

  useEffect(() => {
    setMetadataTables((previousTables) => {
      const previousByName = new Map(previousTables.map((table) => [table.table_name, table]));
      return (tables || []).map((table) => {
        const previous = previousByName.get(table.table_name);
        if (!previous || table.columns.length > 0) {
          return table;
        }
        return { ...table, columns: previous.columns };
      });
    });
  }, [tables]);

  useEffect(() => {
    if (engine !== "oracle") {
      return;
    }

    const tableNames = [
      state.table,
      ...state.joins.map((join) => join.table),
    ].filter((tableName) => tableName.trim() !== "");
    const tableMap = new Map(metadataTables.map((table) => [table.table_name, table]));

    tableNames.forEach((tableName) => {
      const table = tableMap.get(tableName);
      if (
        !table ||
        table.columns.length > 0 ||
        loadingColumnTablesRef.current.has(tableName) ||
        loadedColumnTablesRef.current.has(tableName)
      ) {
        return;
      }

      loadingColumnTablesRef.current.add(tableName);
      setColumnLoadError(null);
      getColumns(tableName, engine)
        .then((columns) => {
          loadedColumnTablesRef.current.add(tableName);
          setMetadataTables((previousTables) =>
            previousTables.map((candidate) =>
              candidate.table_name === tableName ? { ...candidate, columns } : candidate
            )
          );
        })
        .catch((error: any) => {
          setColumnLoadError(
            error?.response?.data?.detail || error.message || `Failed to load columns for ${tableName}`
          );
        })
        .finally(() => {
          loadingColumnTablesRef.current.delete(tableName);
        });
    });
  }, [engine, metadataTables, state.joins, state.table]);

  const availableColumns = useMemo(
    () => buildColumnOptionsForQuery(state.table, state.joins, metadataTables),
    [state.table, state.joins, metadataTables]
  );
  const reportColumns = availableColumns;
  const availableColumnNames = useMemo(
    () => reportColumns.map((column) => column.key),
    [reportColumns]
  );
  const shouldShowSelectTableHint =
    !state.table && state.sourceMode === "builder" && !state.sqlText.trim();

  useEffect(() => {
    if (initialTable && !state.table) {
      setTable(initialTable);
    }
  }, [initialTable, state.table, setTable]);

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-3xl font-bold text-gray-900">{title}</h1>
            {engine === "oracle" && (
              <p className="mt-2 text-sm text-amber-700">
                Marcadose is read-only. Fetch List, Generate Report, and manual SQL all run as SELECT-only Oracle
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
              className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
                state.mode === "REPORT"
                  ? "bg-white text-gray-900 shadow"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Generate Report
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(360px,420px),minmax(0,1fr)]">
          <div className="min-w-0">
            {engine === "duckdb" && onLocalSchemaChanged && (
              <LocalFileObjectCreator onCreated={onLocalSchemaChanged} />
            )}

            <TableSelector tables={metadataTables || []} activeTable={state.table} onSelect={setTable} />

            {columnLoadError && (
              <div className="mb-4 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                {columnLoadError}
              </div>
            )}

            {state.table && (
              <JoinComposer
                baseTable={state.table}
                joins={state.joins}
                tables={metadataTables}
                onAddJoin={addJoin}
                onUpdateJoin={updateJoin}
                onRemoveJoin={removeJoin}
                onAddCondition={addJoinCondition}
                onUpdateCondition={updateJoinCondition}
                onRemoveCondition={removeJoinCondition}
              />
            )}

            {state.table && state.mode === "LIST" && (
              <>
                <ColumnPicker
                  columns={availableColumns}
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
                  columns={availableColumns}
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

            {state.table && state.mode === "REPORT" && (
              <>
                <PivotControl
                  columns={availableColumnNames}
                  config={state.pivotConfig}
                  onChange={setPivotConfig}
                />
                <FilterPanel
                  filters={state.filters}
                  columns={reportColumns}
                  onAddFilter={addFilter}
                  onUpdateFilter={updateFilter}
                  onRemoveFilter={removeFilter}
                />
              </>
            )}
          </div>

          <div className="min-w-0">
            <SqlEditorPanel
              engine={engine}
              queryMode={state.mode}
              sourceMode={state.sourceMode}
              sqlText={state.sqlText}
              generatedSql={state.generatedSql}
              isSqlDetached={state.isSqlDetached}
              isPreviewLoading={state.isPreviewLoading}
              previewError={state.previewError}
              runError={state.error}
              isRunning={state.isLoading}
              canRunBuilder={!!state.table && !!state.generatedSql && !state.previewError && !state.isPreviewLoading}
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
