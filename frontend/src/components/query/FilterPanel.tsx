/**
 * FilterPanel.tsx — Dynamic list of FilterRow components.
 *
 * Manages adding/removing filter rows and passes updates up to the
 * query builder state via callbacks.
 *
 * Props:
 *   filters: FilterCondition[]          — Current filter list.
 *   columns: ColumnDetail[]             — Available columns.
 *   onAdd: () => void                   — Add a new empty filter.
 *   onUpdate: (id, updates) => void     — Update a filter by ID.
 *   onRemove: (id) => void              — Remove a filter by ID.
 */

import React from "react";
import type { FilterCondition } from "../../types/query.types";
import { FilterRow } from "./FilterRow";

interface FilterPanelProps {
  filters: FilterCondition[];
  columns: string[];
  onAddFilter: () => void;
  onUpdateFilter: (id: string, updates: Partial<FilterCondition>) => void;
  onRemoveFilter: (id: string) => void;
}

export const FilterPanel: React.FC<FilterPanelProps> = ({ filters, columns, onAddFilter, onUpdateFilter, onRemoveFilter }) => {
  return (
    <div className="bg-white p-4 border border-gray-200 rounded shadow-sm mb-4">
      <div className="flex justify-between items-center mb-2">
        <h3 className="font-semibold text-gray-700">Filters</h3>
        <button onClick={onAddFilter} className="bg-blue-50 text-blue-600 px-2 py-1 rounded text-sm hover:bg-blue-100">
          + Add Filter
        </button>
      </div>
      <div>
        {filters.length === 0 ? (
          <p className="text-sm text-gray-500 italic">No filters applied.</p>
        ) : (
          filters.map((f) => (
            <FilterRow key={f.id} condition={f} columns={columns} onChange={onUpdateFilter} onRemove={onRemoveFilter} />
          ))
        )}
      </div>
    </div>
  );
};
