/**
 * QueryBuilderWorkspace.tsx — Reusable query builder UI for local DuckDB and Marcadose.
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

const MARCADOSE_DISCOMS = ["DVVNL", "PVVNL", "PUVNL", "MVVNL", "KESCO"];

const MONTH_INDEX_BY_SHORT_NAME: Record<string, number> = {
  jan: 0,
  feb: 1,
  mar: 2,
  apr: 3,
  may: 4,
  jun: 5,
  jul: 6,
  aug: 7,
  sep: 8,
  oct: 9,
  nov: 10,
  dec: 11,
};

function getCurrentMonthInput(): string {
  return new Date().toISOString().slice(0, 7);
}

function monthTagToInput(monthTag: string): string {
  const match = /^([a-z]{3})_(\d{4})$/i.exec(monthTag.trim());
  if (!match) return getCurrentMonthInput();

  const monthIndex = MONTH_INDEX_BY_SHORT_NAME[match[1].toLowerCase()];
  if (monthIndex === undefined) return getCurrentMonthInput();

  return `${match[2]}-${String(monthIndex + 1).padStart(2, "0")}`;
}

function monthInputToTag(monthInput: string): string {
  const [year, month] = monthInput.split("-");
  const date = new Date(Number(year), Number(month) - 1, 1);
  const monthName = date.toLocaleString("en-US", { month: "short" }).toLowerCase();
  return `${monthName}_${year}`;
}

function buildMarcadoseMasterTable(
  monthTag: string,
  discom: string,
  schemaName = "MERCADOS"
): string {
  return `${schemaName || "MERCADOS"}.CM_master_data_${monthTag}_${discom}`;
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
    setMarcadoseUnion,
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
        if (!previous || table.columns.length > 0) return table;
        return { ...table, columns: previous.columns };
      });
    });
  }, [tables]);

  useEffect(() => {
    if (engine !== "oracle") return;

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
            error?.response?.data?.detail ||
            error.message ||
            `Failed to load columns for ${tableName}`
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

  const marcadoseUnion = state.marcadoseUnion;

  const selectedMasterTable = buildMarcadoseMasterTable(
    marcadoseUnion.month_tag,
    marcadoseUnion.base_discom,
    marcadoseUnion.schema_name
  );

  useEffect(() => {
    if (engine !== "oracle" || !selectedMasterTable) return;

    setMetadataTables((previousTables) => {
      if (previousTables.some((table) => table.table_name === selectedMasterTable)) {
        return previousTables;
      }

      return [{ table_name: selectedMasterTable, columns: [], row_count: 0 }, ...previousTables];
    });
  }, [engine, selectedMasterTable]);

  useEffect(() => {
    if (engine === "oracle" && !state.table && selectedMasterTable) {
      setTable(selectedMasterTable);
    }
  }, [engine, selectedMasterTable, setTable, state.table]);

  const applyMarcadoseUnionUpdates = (updates: Partial<typeof marcadoseUnion>) => {
    const next = { ...marcadoseUnion, ...updates };

    const selectedDiscoms = next.discoms
      .map((discom) => discom.toUpperCase())
      .filter(
        (discom, index, values) =>
          MARCADOSE_DISCOMS.includes(discom) && values.indexOf(discom) === index
      );

    next.discoms = selectedDiscoms.length
      ? selectedDiscoms
      : [marcadoseUnion.base_discom || "DVVNL"];

    next.base_discom = next.base_discom.toUpperCase();

    if (!next.discoms.includes(next.base_discom)) {
      next.base_discom = next.discoms[0];
    }

    setMarcadoseUnion(next);
    setTable(buildMarcadoseMasterTable(next.month_tag, next.base_discom, next.schema_name));
  };

  const toggleMarcadoseDiscom = (discom: string) => {
    const selected = marcadoseUnion.discoms.includes(discom)
      ? marcadoseUnion.discoms.filter((item) => item !== discom)
      : [...marcadoseUnion.discoms, discom];

    applyMarcadoseUnionUpdates({
      discoms: selected,
      base_discom: selected[0] || discom,
    });
  };

  const insertMarcadosePlaceholder = () => {
    const separator = state.sqlText.trim() ? "\n" : "";
    updateSqlText(`${state.sqlText}${separator}{{MASTER_TABLE}}`);
  };

  const insertMarcadoseTemplate = () => {
    const template =
      state.mode === "REPORT"
        ? `SELECT
    '{{DISCOM}}' AS DISCOM,
    COUNT(ACCT_ID) AS TOTAL_COUNT
FROM {{MASTER_TABLE}} m
WHERE 1 = 1`
        : `SELECT
    '{{DISCOM}}' AS DISCOM,
    m.*
FROM {{MASTER_TABLE}} m
WHERE 1 = 1`;

    updateSqlText(template);
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-3xl font-bold text-gray-900">{title}</h1>
            {engine === "oracle" && (
              <p className="mt-2 text-sm text-amber-700">
                Marcadose is read-only. Fetch List, Generate Report, and manual SQL all run as
                SELECT-only Oracle queries.
              </p>
            )}
          </div>

          <div className="flex rounded-lg bg-gray-200 p-1">
            <button
              onClick={() => setMode("LIST")}
              className={`rounded-md px-4 py-2 text-sm font-semibold transition ${state.mode === "LIST"
                  ? "bg-white text-gray-900 shadow"
                  : "text-gray-500 hover:text-gray-700"
                }`}
            >
              Fetch List
            </button>
            <button
              onClick={() => setMode("REPORT")}
              className={`rounded-md px-4 py-2 text-sm font-semibold transition ${state.mode === "REPORT"
                  ? "bg-white text-gray-900 shadow"
                  : "text-gray-500 hover:text-gray-700"
                }`}
            >
              Generate Report
            </button>
          </div>
        </div>

        {engine === "oracle" && (
          <div className="mb-6 rounded-lg border border-amber-200 bg-white p-4 shadow-sm">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-700">
                  Marcadose Monthly Master Table
                </h2>
                <p className="mt-1 text-xs text-gray-500">
                  Select month and DISCOM once. Use{" "}
                  <span className="font-mono">{"{{MASTER_TABLE}}"}</span> and{" "}
                  <span className="font-mono">{"{{DISCOM}}"}</span> in manual SQL, or use builder
                  mode with the selected master table.
                </p>
              </div>

              <label className="flex items-center gap-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800">
                <input
                  type="checkbox"
                  checked={marcadoseUnion.enabled}
                  onChange={(event) =>
                    applyMarcadoseUnionUpdates({ enabled: event.target.checked })
                  }
                />
                Apply UNION ALL
              </label>
            </div>

            <div className="grid gap-4 lg:grid-cols-[180px,minmax(0,1fr),minmax(280px,1fr)]">
              <div>
                <label className="mb-1 block text-xs font-semibold text-gray-600">Month</label>
                <input
                  type="month"
                  value={monthTagToInput(marcadoseUnion.month_tag)}
                  onChange={(event) =>
                    applyMarcadoseUnionUpdates({
                      month_tag: monthInputToTag(event.target.value),
                    })
                  }
                  className="w-full rounded border border-gray-300 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
                <p className="mt-1 text-xs text-gray-400">Tag: {marcadoseUnion.month_tag}</p>
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <label className="block text-xs font-semibold text-gray-600">DISCOM</label>
                  <button
                    type="button"
                    onClick={() =>
                      applyMarcadoseUnionUpdates({
                        enabled: true,
                        discoms: [...MARCADOSE_DISCOMS],
                        base_discom: "DVVNL",
                      })
                    }
                    className="text-xs font-semibold text-amber-700 hover:text-amber-900"
                  >
                    Select all
                  </button>
                </div>

                <div className="flex flex-wrap gap-2">
                  {MARCADOSE_DISCOMS.map((discom) => (
                    <label
                      key={discom}
                      className={`flex items-center gap-2 rounded border px-3 py-2 text-sm ${marcadoseUnion.discoms.includes(discom)
                          ? "border-amber-300 bg-amber-50 text-amber-900"
                          : "border-gray-200 bg-gray-50 text-gray-600"
                        }`}
                    >
                      <input
                        type="checkbox"
                        checked={marcadoseUnion.discoms.includes(discom)}
                        onChange={() => toggleMarcadoseDiscom(discom)}
                      />
                      {discom}
                    </label>
                  ))}
                </div>

                <p className="mt-2 text-xs text-gray-500">
                  Base table: <span className="font-mono">{selectedMasterTable}</span>
                </p>
              </div>

              <div className="rounded border border-gray-200 bg-gray-50 p-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Mode behavior
                </div>
                <p className="mt-2 text-xs text-gray-600">
                  Fetch List unions row-level lists. Generate Report unions summary SQL and can
                  append a grand total.
                </p>

                {state.mode === "REPORT" && (
                  <label className="mt-3 flex items-center gap-2 text-sm text-gray-700">
                    <input
                      type="checkbox"
                      checked={marcadoseUnion.add_grand_total}
                      onChange={(event) =>
                        applyMarcadoseUnionUpdates({ add_grand_total: event.target.checked })
                      }
                    />
                    Add Grand Total row
                  </label>
                )}

                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={insertMarcadoseTemplate}
                    className="rounded bg-amber-600 px-3 py-2 text-xs font-semibold text-white shadow hover:bg-amber-700"
                  >
                    Insert {state.mode === "REPORT" ? "Report" : "List"} Template
                  </button>
                  <button
                    type="button"
                    onClick={insertMarcadosePlaceholder}
                    className="rounded border border-gray-300 px-3 py-2 text-xs font-semibold text-gray-700 hover:bg-white"
                  >
                    Insert Table Placeholder
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

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
                <SortControl sortRules={state.sort} columns={availableColumns} onChange={setSort} />

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
              canRunBuilder={
                !!state.table &&
                !!state.generatedSql &&
                !state.previewError &&
                !state.isPreviewLoading
              }
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