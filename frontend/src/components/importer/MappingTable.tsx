/**
 * MappingTable.tsx — CSV-to-DuckDB column mapping interface.
 *
 * Two-column table: CSV header → DuckDB column dropdown for each field.
 * Includes a "skip" checkbox per row to exclude columns from import.
 *
 * Props:
 *   csvHeaders: string[]                        — Headers from the CSV file.
 *   dbColumns: ColumnDetail[]                   — Available columns in the target table.
 *   mappings: ColumnMapping[]                   — Current column mapping state.
 *   onUpdate: (index, mapping) => void          — Update a mapping row.
 */

import React from "react";
import type { ColumnMapping } from "../../types/importer.types";

interface ColumnDetail {
  name: string;
}

interface MappingTableProps {
  csvHeaders: string[];
  dbColumns: ColumnDetail[];
  mappings: ColumnMapping[];
  onUpdate: (index: number, mapping: Partial<ColumnMapping>) => void;
}

export const MappingTable: React.FC<MappingTableProps> = ({ csvHeaders, dbColumns, mappings, onUpdate }) => {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full text-xs">
        <thead className="bg-slate-50">
          <tr>
            <th className="px-3 py-2 text-left font-semibold text-slate-700">CSV column</th>
            <th className="px-3 py-2 text-left font-semibold text-slate-700">DB column</th>
            <th className="px-3 py-2 text-left font-semibold text-slate-700">Skip</th>
          </tr>
        </thead>
        <tbody>
          {csvHeaders.map((csvColumn, index) => {
            const mapping = mappings[index] ?? { csvColumn, dbColumn: "", skip: false };
            return (
              <tr key={csvColumn} className="border-t">
                <td className="px-3 py-2 text-slate-700">{csvColumn}</td>
                <td className="px-3 py-2">
                  <select
                    className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
                    value={mapping.dbColumn}
                    onChange={(e) => onUpdate(index, { dbColumn: e.target.value })}
                  >
                    <option value="">Select column</option>
                    {dbColumns.map((column) => (
                      <option key={column.name} value={column.name}>
                        {column.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={mapping.skip}
                    onChange={(e) => onUpdate(index, { skip: e.target.checked })}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
