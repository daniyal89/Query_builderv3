/**
 * QueryBuilderPage.tsx — Visual query composer page.
 *
 * Assembles TableSelector, ColumnPicker, FilterPanel, SortControl,
 * and ResultsGrid into a cohesive query-building interface. Wired
 * to the useQueryBuilder hook for state management.
 */
import React, { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryBuilder } from "../hooks/useQueryBuilder";
import { useConnection } from "../hooks/useConnection";
import { TableSelector } from "../components/query/TableSelector";
import { ColumnPicker } from "../components/query/ColumnPicker";
import { FilterPanel } from "../components/query/FilterPanel";
import { SortControl } from "../components/query/SortControl";
import { GroupControl } from "../components/query/GroupControl";
import { AggregateControl } from "../components/query/AggregateControl";
import { PivotControl } from "../components/query/PivotControl";
import { ResultsGrid } from "../components/query/ResultsGrid";

export const QueryBuilderPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const initialTable = searchParams.get("table");

  const { tables } = useConnection();
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
    executeQuery,
  } = useQueryBuilder();

  const availableColumns: string[] = useMemo(() => {
    if (!state.table || !tables?.length) return [];
    const activeTable = tables.find((t) => t.table_name === state.table);
    return activeTable?.columns?.map((c) => c.name) ?? [];
  }, [state.table, tables]);

  useEffect(() => {
    if (initialTable && !state.table) {
      setTable(initialTable);
    }
  }, [initialTable, state.table, setTable]);

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-end mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Query Builder</h1>
          
          {/* Mode Switcher */}
          <div className="flex bg-gray-200 p-1 rounded-lg">
            <button
              onClick={() => setMode("LIST")}
              className={`px-4 py-2 text-sm font-semibold rounded-md transition ${state.mode === "LIST" ? "bg-white text-gray-900 shadow" : "text-gray-500 hover:text-gray-700"}`}
            >
              Fetch List
            </button>
            <button
              onClick={() => setMode("REPORT")}
              className={`px-4 py-2 text-sm font-semibold rounded-md transition ${state.mode === "REPORT" ? "bg-white text-gray-900 shadow" : "text-gray-500 hover:text-gray-700"}`}
            >
              Generate Report
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <div className="lg:col-span-1">
            <TableSelector
              tables={tables || []}
              activeTable={state.table}
              onSelect={setTable}
            />

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
                <div className="bg-white p-4 border border-gray-200 rounded shadow-sm mb-4">
                  <label className="block text-sm font-semibold text-gray-700 mb-1">Limit Rows</label>
                  <p className="text-xs text-gray-400 mb-2">Set to 0 for No Limit</p>
                  <input
                    type="number"
                    value={state.limitRows}
                    onChange={(e) => setLimitRows(Number(e.target.value))}
                    className="w-full border border-gray-300 rounded p-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    min="0"
                  />
                </div>
              </>
            )}

            {state.table && state.mode === "REPORT" && (
              <>
                <PivotControl
                  columns={availableColumns}
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

            {state.table && (
              <button
                onClick={executeQuery}
                disabled={state.isLoading}
                className="w-full bg-indigo-600 text-white font-bold py-3 rounded shadow hover:bg-indigo-700 disabled:opacity-50 transition"
              >
                {state.isLoading ? "Running..." : "▶ Run Query"}
              </button>
            )}

                {state.error && (
                  <div className="mt-4 p-3 bg-red-50 text-red-700 text-sm rounded border border-red-200">
                    {state.error}
                  </div>
                )}
              </>
            )}
          </div>

          <div className="lg:col-span-3">
            {!state.table && (
              <div className="flex items-center justify-center h-64 bg-white border-2 border-dashed border-gray-200 rounded-lg">
                <div className="text-center text-gray-400">
                  <p className="text-lg font-medium">Select a table to begin</p>
                  <p className="text-sm mt-1">Choose a table from the left panel to build your query</p>
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
