/**
 * AggregateControl.tsx — Assign aggregate functions to selected columns that are not grouped.
 */
import React from "react";
import type { AggregateRule } from "../../types/query.types";

interface AggregateControlProps {
  // Only the columns currently selected, and NOT in the groupBy list, should be available for aggregation
  availableColumns: string[];
  aggregates: AggregateRule[];
  setAggregate: (column: string, func: "SUM" | "COUNT" | "AVG" | "MIN" | "MAX") => void;
  removeAggregate: (column: string) => void;
  isGroupingActive: boolean;
}

export const AggregateControl: React.FC<AggregateControlProps> = ({
  availableColumns,
  aggregates,
  setAggregate,
  removeAggregate,
  isGroupingActive
}) => {
  if (!isGroupingActive || availableColumns.length === 0) {
    return null;
  }

  const handleFuncChange = (column: string, func: string) => {
    if (func === "") {
      removeAggregate(column);
    } else {
      setAggregate(column, func as any);
    }
  };

  return (
    <div className="bg-white p-3 border border-gray-200 rounded shadow-sm mb-4">
      <h3 className="font-semibold text-gray-700 text-sm mb-2">Aggregations</h3>
      <p className="text-xs text-gray-500 mb-2">Since you are grouping, non-grouped columns must be aggregated.</p>
      
      <div className="space-y-2">
        {availableColumns.map(col => {
          const currentAgg = aggregates.find(a => a.column === col)?.func || "";
          return (
            <div key={col} className="flex items-center justify-between bg-gray-50 p-1 rounded border border-gray-100">
              <span className="font-mono text-xs text-gray-800 break-all pl-1">{col}</span>
              <select
                value={currentAgg}
                onChange={(e) => handleFuncChange(col, e.target.value)}
                className="text-xs border border-gray-300 rounded px-1 py-0.5 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="">-- None --</option>
                <option value="SUM">SUM</option>
                <option value="COUNT">COUNT</option>
                <option value="AVG">AVG</option>
                <option value="MIN">MIN</option>
                <option value="MAX">MAX</option>
              </select>
            </div>
          );
        })}
      </div>
    </div>
  );
};
