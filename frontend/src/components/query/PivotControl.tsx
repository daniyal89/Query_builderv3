/**
 * PivotControl.tsx — UI for configuring the Pivot Table (Report) mode.
 */
import React, { useDeferredValue, useMemo, useState } from "react";
import type { PivotConfig } from "../../types/query.types";
import { SearchableSelect } from "./SearchableSelect";

interface PivotControlProps {
  columns: string[];
  config: PivotConfig;
  onChange: (config: Partial<PivotConfig>) => void;
}

export const PivotControl: React.FC<PivotControlProps> = ({ columns, config, onChange }) => {
  const [rowSearchTerm, setRowSearchTerm] = useState("");
  const [columnSearchTerm, setColumnSearchTerm] = useState("");
  const deferredRowSearchTerm = useDeferredValue(rowSearchTerm);
  const deferredColumnSearchTerm = useDeferredValue(columnSearchTerm);
  const normalizedRowSearchTerm = deferredRowSearchTerm.trim().toLowerCase();
  const normalizedColumnSearchTerm = deferredColumnSearchTerm.trim().toLowerCase();
  const toggleArrayItem = (arr: string[], item: string) =>
    arr.includes(item) ? arr.filter((i) => i !== item) : [...arr, item];
  const visibleRowColumns = useMemo(
    () =>
      columns.length > 20 && normalizedRowSearchTerm
        ? columns.filter((column) => column.toLowerCase().includes(normalizedRowSearchTerm))
        : columns,
    [columns, normalizedRowSearchTerm]
  );
  const visiblePivotColumns = useMemo(
    () =>
      columns.length > 20 && normalizedColumnSearchTerm
        ? columns.filter((column) => column.toLowerCase().includes(normalizedColumnSearchTerm))
        : columns,
    [columns, normalizedColumnSearchTerm]
  );
  const valueFieldOptions = useMemo(
    () => columns.map((column) => ({ value: column, label: column })),
    [columns]
  );

  return (
    <div className="bg-white border text-sm border-gray-200 rounded shadow-sm mb-4 divide-y divide-gray-100">
      
      {/* Rows Configuration */}
      <div className="p-4">
        <h3 className="font-semibold text-gray-700 mb-2">1. Row Labels (Group vertically)</h3>
        {columns.length > 20 && (
          <input
            type="text"
            value={rowSearchTerm}
            onChange={(event) => setRowSearchTerm(event.target.value)}
            className="mb-2 w-full rounded border border-gray-300 bg-white px-2 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Search row label columns..."
          />
        )}
        <div className="max-h-32 overflow-y-auto space-y-1 bg-gray-50 p-2 border border-gray-200 rounded">
          {visibleRowColumns.map((c) => (
            <label key={`row-${c}`} className="flex items-center space-x-2 text-xs cursor-pointer hover:bg-gray-100 px-1 py-0.5 rounded">
              <input
                type="checkbox"
                checked={config.rows.includes(c)}
                onChange={() => onChange({ rows: toggleArrayItem(config.rows, c) })}
                className="rounded text-indigo-600"
              />
              <span className="font-mono text-gray-800 break-all">{c}</span>
            </label>
          ))}
          {visibleRowColumns.length === 0 && (
            <p className="px-2 py-4 text-center text-xs text-gray-400">No row label columns match your search.</p>
          )}
        </div>
      </div>

      {/* Columns Configuration */}
      <div className="p-4">
        <h3 className="font-semibold text-gray-700 mb-2">2. Column Labels (Pivot horizontally)</h3>
        {columns.length > 20 && (
          <input
            type="text"
            value={columnSearchTerm}
            onChange={(event) => setColumnSearchTerm(event.target.value)}
            className="mb-2 w-full rounded border border-gray-300 bg-white px-2 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Search pivot column labels..."
          />
        )}
        <div className="max-h-32 overflow-y-auto space-y-1 bg-gray-50 p-2 border border-gray-200 rounded">
          {visiblePivotColumns.map((c) => (
            <label key={`col-${c}`} className="flex items-center space-x-2 text-xs cursor-pointer hover:bg-gray-100 px-1 py-0.5 rounded">
              <input
                type="checkbox"
                checked={config.columns.includes(c)}
                onChange={() => onChange({ columns: toggleArrayItem(config.columns, c) })}
                className="rounded text-emerald-600"
              />
              <span className="font-mono text-gray-800 break-all">{c}</span>
            </label>
          ))}
          {visiblePivotColumns.length === 0 && (
            <p className="px-2 py-4 text-center text-xs text-gray-400">No pivot columns match your search.</p>
          )}
        </div>
      </div>

      {/* Values & Aggregation */}
      <div className="p-4 bg-indigo-50/30">
        <h3 className="font-semibold text-gray-700 mb-2 flex items-center justify-between">
          <span>3. Values & Aggregation</span>
          <button
            type="button"
            onClick={() => onChange({ aggregates: [...(config.aggregates || []), { column: "", func: "SUM" }] })}
            className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"></path></svg>
            Add Value
          </button>
        </h3>
        <div className="space-y-2">
          {(!config.aggregates || config.aggregates.length === 0) ? (
            <p className="text-xs text-gray-500 italic py-2">No values added. Click "Add Value" to define report metrics.</p>
          ) : config.aggregates.map((agg, idx) => (
            <div key={idx} className="flex space-x-2 items-end">
              <div className="flex-1">
                <label className="block text-[10px] font-semibold text-gray-500 mb-0.5 uppercase tracking-wider">Value Field {idx + 1}</label>
                <SearchableSelect
                  value={agg.column}
                  options={valueFieldOptions}
                  onChange={(val) => {
                    const newAggs = [...config.aggregates];
                    newAggs[idx] = { ...agg, column: val };
                    onChange({ aggregates: newAggs });
                  }}
                  placeholder="-- Select Field --"
                  searchPlaceholder="Search value fields..."
                  emptyMessage="No value fields match your search."
                />
              </div>
              <div className="w-1/3">
                <label className="block text-[10px] font-semibold text-gray-500 mb-0.5 uppercase tracking-wider">Function</label>
                <select
                  value={agg.func}
                  onChange={(e) => {
                    const newAggs = [...config.aggregates];
                    newAggs[idx] = { ...agg, func: e.target.value as any };
                    onChange({ aggregates: newAggs });
                  }}
                  className="w-full border border-gray-300 rounded px-2 py-[7px] text-xs bg-white focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="SUM">SUM</option>
                  <option value="COUNT">COUNT</option>
                  <option value="AVG">AVG</option>
                  <option value="MIN">MIN</option>
                  <option value="MAX">MAX</option>
                </select>
              </div>
              <button
                type="button"
                onClick={() => {
                  const newAggs = config.aggregates.filter((_, i) => i !== idx);
                  onChange({ aggregates: newAggs });
                }}
                className="mb-[1px] p-1.5 text-gray-400 hover:text-red-500 rounded hover:bg-red-50 transition-colors"
                title="Remove Value"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
              </button>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
};
