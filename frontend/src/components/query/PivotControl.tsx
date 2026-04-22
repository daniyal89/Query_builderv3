/**
 * PivotControl.tsx — UI for configuring the Pivot Table (Report) mode.
 */
import React from "react";
import type { PivotConfig } from "../../types/query.types";

interface PivotControlProps {
  columns: string[];
  config: PivotConfig;
  onChange: (config: Partial<PivotConfig>) => void;
}

export const PivotControl: React.FC<PivotControlProps> = ({ columns, config, onChange }) => {
  const toggleArrayItem = (arr: string[], item: string) =>
    arr.includes(item) ? arr.filter((i) => i !== item) : [...arr, item];

  return (
    <div className="bg-white border text-sm border-gray-200 rounded shadow-sm mb-4 divide-y divide-gray-100">
      
      {/* Rows Configuration */}
      <div className="p-4">
        <h3 className="font-semibold text-gray-700 mb-2">1. Row Labels (Group vertically)</h3>
        <div className="max-h-32 overflow-y-auto space-y-1 bg-gray-50 p-2 border border-gray-200 rounded">
          {columns.map((c) => (
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
        </div>
      </div>

      {/* Columns Configuration */}
      <div className="p-4">
        <h3 className="font-semibold text-gray-700 mb-2">2. Column Labels (Pivot horizontally)</h3>
        <div className="max-h-32 overflow-y-auto space-y-1 bg-gray-50 p-2 border border-gray-200 rounded">
          {columns.map((c) => (
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
        </div>
      </div>

      {/* Values & Function */}
      <div className="p-4 bg-indigo-50/30">
        <h3 className="font-semibold text-gray-700 mb-2">3. Values & Aggregation</h3>
        <div className="flex space-x-2">
          <div className="flex-1">
            <label className="block text-xs font-semibold text-gray-600 mb-1">Value Field</label>
            <select
              value={config.values}
              onChange={(e) => onChange({ values: e.target.value })}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs bg-white focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">-- Select Field --</option>
              {columns.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="w-1/3">
            <label className="block text-xs font-semibold text-gray-600 mb-1">Function</label>
            <select
              value={config.func}
              onChange={(e) => onChange({ func: e.target.value as any })}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs bg-white focus:ring-1 focus:ring-indigo-500"
            >
              <option value="SUM">SUM</option>
              <option value="COUNT">COUNT</option>
              <option value="AVG">AVG</option>
              <option value="MIN">MIN</option>
              <option value="MAX">MAX</option>
            </select>
          </div>
        </div>
      </div>

    </div>
  );
};
