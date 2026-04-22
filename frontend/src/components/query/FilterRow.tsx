/**
 * FilterRow.tsx — Single filter condition row (vertical stacked layout).
 * Fixes the horizontal flex overflow that caused controls to be unclickable on wide screens.
 */

import React from "react";
import type { FilterCondition } from "../../types/query.types";

interface FilterRowProps {
  condition: FilterCondition;
  columns: string[];
  onChange: (id: string, updates: Partial<FilterCondition>) => void;
  onRemove: (id: string) => void;
}

const OPERATORS = ["=", "!=", ">", "<", ">=", "<=", "LIKE", "IN", "IS NULL", "IS NOT NULL"];
const NO_VALUE_OPS = ["IS NULL", "IS NOT NULL"];

export const FilterRow: React.FC<FilterRowProps> = ({ condition, columns, onChange, onRemove }) => {
  const needsValue = !NO_VALUE_OPS.includes(condition.operator);

  return (
    <div className="bg-gray-50 border border-gray-200 rounded p-2 mb-2">
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Where</span>
        <button
          onClick={() => onRemove(condition.id)}
          className="text-red-400 hover:text-red-600 text-sm font-bold leading-none"
          title="Remove filter"
        >
          ✕
        </button>
      </div>

      {/* Column */}
      <select
        value={condition.column}
        onChange={(e) => onChange(condition.id, { column: e.target.value })}
        className="w-full border border-gray-300 rounded px-2 py-1 text-sm mb-1 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
      >
        <option value="">-- Column --</option>
        {columns.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>

      {/* Operator */}
      <select
        value={condition.operator}
        onChange={(e) => onChange(condition.id, { operator: e.target.value as any })}
        className="w-full border border-gray-300 rounded px-2 py-1 text-sm mb-1 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
      >
        {OPERATORS.map((op) => (
          <option key={op} value={op}>{op}</option>
        ))}
      </select>

      {/* Value */}
      {needsValue && (
        <input
          type="text"
          value={condition.value ?? ""}
          onChange={(e) => onChange(condition.id, { value: e.target.value })}
          className="w-full border border-gray-300 rounded px-2 py-1 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="Value..."
        />
      )}
    </div>
  );
};
