/**
 * GroupControl.tsx — Multi-select checklist for the GROUP BY clause.
 */
import React from "react";

interface GroupControlProps {
  columns: string[];
  groupByRules: string[];
  onChange: (col: string) => void;
}

export const GroupControl: React.FC<GroupControlProps> = ({ columns, groupByRules, onChange }) => {
  return (
    <div className="bg-white p-3 border border-gray-200 rounded shadow-sm mb-4">
      <h3 className="font-semibold text-gray-700 text-sm mb-2">Group By</h3>
      <div className="max-h-40 overflow-y-auto space-y-1 pr-1">
        {columns.map((c) => (
          <label
            key={c}
            className="flex items-center space-x-2 text-sm cursor-pointer hover:bg-gray-50 px-2 py-1 rounded"
          >
            <input
              type="checkbox"
              checked={groupByRules.includes(c)}
              onChange={() => onChange(c)}
              className="flex-shrink-0 rounded text-indigo-600"
            />
            <span className="font-mono text-xs text-gray-800 break-all">{c}</span>
          </label>
        ))}
        {columns.length === 0 && (
          <p className="text-xs text-gray-400 italic px-2">No columns available</p>
        )}
      </div>
    </div>
  );
};
