/**
 * BinColumnBuilder.tsx — UI for creating bin/bucket computed columns.
 *
 * Lets users define numeric or date-range bins (e.g., "0-3 months", "3-6 months")
 * and generates a CaseExpression object that the existing CASE pipeline processes.
 */
import React, { useCallback, useMemo, useState } from "react";
import type { CaseExpression, QueryColumnOption } from "../../types/query.types";
import { SearchableSelect } from "./SearchableSelect";

type BinType = "numeric" | "date_months";

interface BinRow {
  id: string;
  min: string;
  max: string;
  label: string;
}

interface BinPreset {
  name: string;
  binType: BinType;
  alias: string;
  rows: Omit<BinRow, "id">[];
  elseLabel: string;
}

const genId = () => Math.random().toString(36).substring(2, 11);

const PRESETS: BinPreset[] = [
  {
    name: "Payment Aging (Months)",
    binType: "date_months",
    alias: "PAYMENT_AGING",
    rows: [
      { min: "0", max: "3", label: "0-3 months" },
      { min: "3", max: "6", label: "3-6 months" },
      { min: "6", max: "12", label: "6-12 months" },
    ],
    elseLabel: "12+ months",
  },
  {
    name: "Quarterly Aging",
    binType: "date_months",
    alias: "QUARTERLY_AGING",
    rows: [
      { min: "0", max: "3", label: "Q1 (0-3 months)" },
      { min: "3", max: "6", label: "Q2 (3-6 months)" },
      { min: "6", max: "9", label: "Q3 (6-9 months)" },
      { min: "9", max: "12", label: "Q4 (9-12 months)" },
    ],
    elseLabel: "Over 1 year",
  },
  {
    name: "Amount Bins (Small)",
    binType: "numeric",
    alias: "AMOUNT_BIN",
    rows: [
      { min: "0", max: "1000", label: "0-1K" },
      { min: "1000", max: "5000", label: "1K-5K" },
      { min: "5000", max: "10000", label: "5K-10K" },
    ],
    elseLabel: "10K+",
  },
  {
    name: "Amount Bins (Large)",
    binType: "numeric",
    alias: "AMOUNT_BIN",
    rows: [
      { min: "0", max: "10000", label: "0-10K" },
      { min: "10000", max: "50000", label: "10K-50K" },
      { min: "50000", max: "100000", label: "50K-1L" },
      { min: "100000", max: "500000", label: "1L-5L" },
    ],
    elseLabel: "5L+",
  },
];

const DEFAULT_ROWS: Omit<BinRow, "id">[] = [
  { min: "0", max: "3", label: "0-3 months" },
  { min: "3", max: "6", label: "3-6 months" },
  { min: "6", max: "12", label: "6-12 months" },
];

interface BinColumnBuilderProps {
  columns: QueryColumnOption[];
  onApplyBin: (expr: CaseExpression) => void;
}

export const BinColumnBuilder: React.FC<BinColumnBuilderProps> = ({
  columns,
  onApplyBin,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedColumn, setSelectedColumn] = useState("");
  const [binType, setBinType] = useState<BinType>("date_months");
  const [alias, setAlias] = useState("BIN_COLUMN");
  const [binRows, setBinRows] = useState<BinRow[]>(() =>
    DEFAULT_ROWS.map((r) => ({ ...r, id: genId() }))
  );
  const [elseLabel, setElseLabel] = useState("Other");
  const [showPresets, setShowPresets] = useState(false);

  const columnOptions = useMemo(
    () =>
      columns.map((column) => ({
        value: column.key,
        label: column.label,
        description: column.dtype,
      })),
    [columns]
  );

  const addRow = useCallback(() => {
    setBinRows((prev) => [...prev, { id: genId(), min: "", max: "", label: "" }]);
  }, []);

  const removeRow = useCallback((id: string) => {
    setBinRows((prev) => (prev.length <= 1 ? prev : prev.filter((r) => r.id !== id)));
  }, []);

  const updateRow = useCallback((id: string, field: keyof Omit<BinRow, "id">, value: string) => {
    setBinRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, [field]: value } : r))
    );
  }, []);

  const applyPreset = useCallback((preset: BinPreset) => {
    setBinType(preset.binType);
    setAlias(preset.alias);
    setBinRows(preset.rows.map((r) => ({ ...r, id: genId() })));
    setElseLabel(preset.elseLabel);
    setShowPresets(false);
  }, []);

  const handleApply = useCallback(() => {
    if (!selectedColumn.trim() || !alias.trim()) return;

    const validRows = binRows.filter(
      (r) => r.min.trim() !== "" && r.max.trim() !== "" && r.label.trim() !== ""
    );
    if (validRows.length === 0) return;

    // Build a CaseExpression from bin rows.
    // For date_months, the WHEN condition checks DATEDIFF/MONTHS_BETWEEN on the column.
    // For numeric, it checks the raw column value with BETWEEN.
    //
    // Since the existing CaseExpression model uses column + operator + value for each branch,
    // and BETWEEN is a supported operator, we can use it directly for numeric bins.
    //
    // For date_months, we need a different approach: the column itself becomes a date-diff
    // expression. We'll encode this by creating a special column reference that the backend
    // interprets. However, since modifying the backend model is out of scope, we'll use
    // a pragmatic approach: generate the full CASE SQL as a raw expression.
    //
    // Actually, re-thinking: the CaseExpression model has `column` + `operator` + `value`
    // per branch. For numeric bins, we can use the column directly with BETWEEN.
    // For date_months bins, we need the condition to be on the month-difference, not the
    // raw column. The cleanest zero-backend-change approach is:
    //
    // We generate CaseExpression branches with BETWEEN operator on the raw column for
    // numeric type. For date_months, since the CASE builder doesn't support function-wrapped
    // columns natively, we'll generate the CASE expression with numeric BETWEEN conditions
    // and add a special hint in the alias. But this won't work properly.
    //
    // Better approach: For date_months bins, we use the BETWEEN operator but the "column"
    // field references a SQL expression. Let's check if the backend's _resolve_column_expression
    // can handle this... it can't, it expects real column names.
    //
    // Pragmatic solution: For BOTH types, generate CaseExpression branches using BETWEEN.
    // For date_months, the user should have a column that already contains the month diff
    // value, OR we add a function column first (DATEDIFF) and then bin on that.
    // 
    // Simplest working approach: always use BETWEEN on the selected column.
    // For date columns, the user selects a numeric column that represents months
    // (or we auto-create a DATEDIFF function column as a helper).
    //
    // Let's go with the simplest: the bin always uses BETWEEN on the selected column.
    // The "date_months" type is just a UI hint that affects presets and labels.
    // Users pick their date-diff column (or we help them create one).

    const caseExpr: CaseExpression = {
      id: genId(),
      alias: alias.trim(),
      branches: [
        {
          id: genId(),
          column: selectedColumn,
          operator: "IS NULL" as const,
          value: "",
          thenType: "literal" as const,
          thenValue: "99. Unknown / Invalid",
        },
        ...validRows.map((row, index) => ({
          id: genId(),
          column: selectedColumn,
          operator: ">=" as const,
          value: row.min.trim(),
          secondOperator: "<" as const,
          secondValue: row.max.trim(),
          thenType: "literal" as const,
          thenValue: `${String(index + 1).padStart(2, "0")}. ${row.label.trim()}`,
        })),
      ],
      elseType: "literal",
      elseValue: `${String(validRows.length + 1).padStart(2, "0")}. ${elseLabel.trim() || "Other"}`,
    };

    onApplyBin(caseExpr);

    // Reset form
    setSelectedColumn("");
    setAlias("BIN_COLUMN");
    setBinRows(DEFAULT_ROWS.map((r) => ({ ...r, id: genId() })));
    setElseLabel("Other");
    setIsOpen(false);
  }, [selectedColumn, alias, binRows, elseLabel, onApplyBin]);

  const isValid = useMemo(() => {
    if (!selectedColumn.trim() || !alias.trim()) return false;
    return binRows.some(
      (r) => r.min.trim() !== "" && r.max.trim() !== "" && r.label.trim() !== ""
    );
  }, [selectedColumn, alias, binRows]);

  if (!isOpen) {
    return (
      <div className="bg-white p-4 border border-gray-200 rounded shadow-sm mb-4">
        <div className="flex justify-between items-center">
          <h3 className="font-semibold text-gray-700">Bin / Bucket Columns</h3>
          <button
            onClick={() => setIsOpen(true)}
            className="bg-amber-50 text-amber-700 px-2 py-1 rounded text-sm hover:bg-amber-100"
          >
            + Add Bin Column
          </button>
        </div>
        <p className="text-sm text-gray-500 italic mt-1">
          Group a column into labeled ranges (e.g., 0-3 months, 3-6 months).
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-amber-300 rounded shadow-sm mb-4 overflow-hidden">
      {/* Header */}
      <div className="bg-amber-50 px-4 py-3 border-b border-amber-200">
        <div className="flex justify-between items-center">
          <h3 className="font-semibold text-amber-900">New Bin Column</h3>
          <button
            onClick={() => setIsOpen(false)}
            className="text-gray-400 hover:text-gray-600 font-bold text-sm p-1"
            title="Cancel"
          >
            ×
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Column + Alias row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Source Column</label>
            <SearchableSelect
              options={columnOptions}
              value={selectedColumn}
              onChange={setSelectedColumn}
              placeholder="Select column..."
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Bin Type</label>
            <select
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              value={binType}
              onChange={(e) => setBinType(e.target.value as BinType)}
            >
              <option value="numeric">Numeric (raw value ranges)</option>
              <option value="date_months">Date (months ago — use with DATEDIFF column)</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Output Alias</label>
            <input
              type="text"
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
              placeholder="BIN_COLUMN"
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
            />
          </div>
        </div>

        {/* Presets */}
        <div>
          <button
            onClick={() => setShowPresets(!showPresets)}
            className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
          >
            <span>{showPresets ? "▼" : "▶"}</span>
            <span>Presets</span>
          </button>
          {showPresets && (
            <div className="mt-2 flex flex-wrap gap-2">
              {PRESETS.map((preset) => (
                <button
                  key={preset.name}
                  onClick={() => applyPreset(preset)}
                  className="rounded border border-gray-300 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors"
                >
                  {preset.name}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Bin Rows Table */}
        <div>
          <h4 className="text-xs font-semibold text-gray-600 mb-2">Bin Ranges</h4>
          <div className="border border-gray-200 rounded overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-3 py-1.5 text-xs font-semibold text-gray-600 w-24">From (≥)</th>
                  <th className="text-left px-3 py-1.5 text-xs font-semibold text-gray-600 w-24">To (&lt;)</th>
                  <th className="text-left px-3 py-1.5 text-xs font-semibold text-gray-600">Label</th>
                  <th className="w-8"></th>
                </tr>
              </thead>
              <tbody>
                {binRows.map((row) => (
                  <tr key={row.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-2 py-1">
                      <input
                        type="number"
                        className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
                        placeholder="0"
                        value={row.min}
                        onChange={(e) => updateRow(row.id, "min", e.target.value)}
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        type="number"
                        className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
                        placeholder="100"
                        value={row.max}
                        onChange={(e) => updateRow(row.id, "max", e.target.value)}
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        type="text"
                        className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
                        placeholder="Label for this range"
                        value={row.label}
                        onChange={(e) => updateRow(row.id, "label", e.target.value)}
                      />
                    </td>
                    <td className="px-1 py-1 text-center">
                      <button
                        onClick={() => removeRow(row.id)}
                        className="text-red-400 hover:text-red-600 font-bold text-sm p-1"
                        title="Remove row"
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            onClick={addRow}
            className="mt-2 text-sm text-blue-600 hover:text-blue-800"
          >
            + Add Bin Row
          </button>
        </div>

        {/* Else Label */}
        <div className="flex items-center gap-3">
          <label className="text-sm font-semibold text-gray-600 whitespace-nowrap">ELSE (default):</label>
          <input
            type="text"
            className="border border-gray-300 rounded px-2 py-1 text-sm flex-1"
            placeholder="Other"
            value={elseLabel}
            onChange={(e) => setElseLabel(e.target.value)}
          />
        </div>

        {/* Apply button */}
        <div className="flex justify-end gap-2 pt-2 border-t border-gray-200">
          <button
            onClick={() => setIsOpen(false)}
            className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 rounded border border-gray-300 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleApply}
            disabled={!isValid}
            className={`px-4 py-1.5 text-sm font-medium rounded ${
              isValid
                ? "bg-amber-600 text-white hover:bg-amber-700"
                : "bg-gray-200 text-gray-400 cursor-not-allowed"
            }`}
          >
            Apply Bin Column
          </button>
        </div>
      </div>
    </div>
  );
};
