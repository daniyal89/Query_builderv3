import React, { useMemo, useState } from "react";
import type { CaseExpression, CaseWhenBranch, FilterOperator, QueryColumnOption } from "../../types/query.types";
import { SearchableSelect } from "./SearchableSelect";
import {
  NO_VALUE_OPERATORS,
  getColumnFamily,
  getOperatorsForColumn,
  getValueHint,
  getValuePlaceholder,
} from "../../utils/filterUtils";

interface CaseWhenRowProps {
  branch: CaseWhenBranch;
  columns: QueryColumnOption[];
  onChange: (branchId: string, updates: Partial<CaseWhenBranch>) => void;
  onRemove: (branchId: string) => void;
}

const CaseWhenRow: React.FC<CaseWhenRowProps> = ({ branch, columns, onChange, onRemove }) => {
  const selectedColumn = useMemo(
    () => columns.find((column) => column.key === branch.column),
    [columns, branch.column]
  );
  const columnOptions = useMemo(
    () =>
      columns.map((column) => ({
        value: column.key,
        label: column.label,
        description: column.dtype,
      })),
    [columns]
  );
  const availableOperators = useMemo(
    () => getOperatorsForColumn(selectedColumn),
    [selectedColumn]
  );
  const operator = availableOperators.includes(branch.operator) ? branch.operator : availableOperators[0];
  const needsValue = !NO_VALUE_OPERATORS.includes(operator);
  const hint = getValueHint(operator);

  const isDate = getColumnFamily(selectedColumn?.dtype, selectedColumn?.columnName || selectedColumn?.label || selectedColumn?.key) === "date";
  const isSingleValue = !operator.includes("BETWEEN") && !operator.includes("IN");
  const inputType = isDate && isSingleValue ? "date" : "text";

  const handleColumnChange = (columnName: string) => {
    const nextColumn = columns.find((column) => column.key === columnName);
    const nextOperators = getOperatorsForColumn(nextColumn);
    const nextOperator = nextOperators.includes(branch.operator) ? branch.operator : nextOperators[0];

    onChange(branch.id, {
      column: columnName,
      operator: nextOperator,
      value: NO_VALUE_OPERATORS.includes(nextOperator) ? "" : branch.value,
    });
  };

  return (
    <div className="flex flex-col gap-1 mb-2 bg-gray-50 p-2 rounded border border-gray-200">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-gray-600 w-12">WHEN</span>
        <div className="w-56">
          <SearchableSelect
            options={columnOptions}
            value={branch.column}
            onChange={handleColumnChange}
            placeholder="Select column..."
          />
        </div>
        <select
          className="border border-gray-300 rounded px-2 py-1 text-sm bg-white"
          value={operator}
          onChange={(e) =>
            onChange(branch.id, {
              operator: e.target.value as FilterOperator,
              value: NO_VALUE_OPERATORS.includes(e.target.value as FilterOperator) ? "" : branch.value,
            })
          }
        >
          {availableOperators.map((op) => (
            <option key={op} value={op}>
              {op}
            </option>
          ))}
        </select>
        {needsValue && (
          <input
            type={inputType}
            className="border border-gray-300 rounded px-2 py-1 text-sm flex-1 min-w-[150px]"
            placeholder={getValuePlaceholder(operator)}
            value={branch.value}
            onChange={(e) => onChange(branch.id, { value: e.target.value })}
          />
        )}
        <button
          onClick={() => onRemove(branch.id)}
          className="p-1 text-sm font-bold text-red-400 hover:text-red-600 rounded"
          title="Remove condition"
        >
          ×
        </button>
      </div>
      {hint && needsValue && <p className="text-xs text-gray-500 ml-16">{hint}</p>}
      <div className="flex items-center gap-2 mt-1">
        <span className="text-sm font-semibold text-gray-600 w-12 text-right">THEN</span>
        <select
          className="border border-gray-300 rounded px-2 py-1 text-sm bg-white"
          value={branch.thenType}
          onChange={(e) =>
            onChange(branch.id, {
              thenType: e.target.value as "literal" | "column",
              thenValue: "",
            })
          }
        >
          <option value="literal">Literal</option>
          <option value="column">Column</option>
        </select>
        {branch.thenType === "literal" ? (
          <input
            type="text"
            className="border border-gray-300 rounded px-2 py-1 text-sm flex-1"
            placeholder="Result value (e.g. 'Paid', 1)"
            value={branch.thenValue}
            onChange={(e) => onChange(branch.id, { thenValue: e.target.value })}
          />
        ) : (
          <div className="flex-1">
            <SearchableSelect
              options={columnOptions}
              value={branch.thenValue}
              onChange={(col) => onChange(branch.id, { thenValue: col })}
              placeholder="Select column..."
            />
          </div>
        )}
      </div>
    </div>
  );
};

interface CaseExpressionCardProps {
  expr: CaseExpression;
  columns: QueryColumnOption[];
  onUpdate: (id: string, updates: Partial<CaseExpression>) => void;
  onRemove: (id: string) => void;
  onAddBranch: (caseId: string) => void;
  onUpdateBranch: (caseId: string, branchId: string, updates: Partial<CaseWhenBranch>) => void;
  onRemoveBranch: (caseId: string, branchId: string) => void;
}

const CaseExpressionCard: React.FC<CaseExpressionCardProps> = ({
  expr,
  columns,
  onUpdate,
  onRemove,
  onAddBranch,
  onUpdateBranch,
  onRemoveBranch,
}) => {
  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <div className="border border-gray-200 rounded mb-3 bg-white shadow-sm overflow-hidden">
      <div className="bg-gray-50 px-3 py-2 border-b border-gray-200">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2 flex-1">
            <button onClick={() => setIsExpanded(!isExpanded)} className="text-gray-500 hover:text-gray-700 font-bold w-4">
              {isExpanded ? "▼" : "▶"}
            </button>
            <span className="text-sm font-medium text-gray-700">Alias:</span>
            <input
              type="text"
              className="border border-gray-300 rounded px-2 py-1 text-sm flex-1 max-w-[200px]"
              placeholder="Computed_Column_Name"
              value={expr.alias}
              onChange={(e) => onUpdate(expr.id, { alias: e.target.value })}
              onClick={(e) => e.stopPropagation()}
            />
          </div>
          <button onClick={() => onRemove(expr.id)} className="text-red-400 hover:text-red-600 font-bold p-1 text-sm">
            ×
          </button>
        </div>
        <div className="flex items-center gap-2 mt-2 ml-6">
          <span className="text-xs font-medium text-gray-600">Wrap in Function:</span>
          <select
            className="border border-gray-300 rounded px-2 py-1 text-xs bg-white"
            value={expr.aggregateFunc || ""}
            onChange={(e) =>
              onUpdate(expr.id, {
                aggregateFunc: (e.target.value as any) || undefined,
              })
            }
            onClick={(e) => e.stopPropagation()}
          >
            <option value="">None</option>
            <option value="SUM">SUM</option>
            <option value="COUNT">COUNT</option>
            <option value="AVG">AVG</option>
            <option value="MIN">MIN</option>
            <option value="MAX">MAX</option>
          </select>
          {expr.aggregateFunc && (
            <span className="text-xs text-gray-400 italic">
              {expr.aggregateFunc}(CASE ... END)
            </span>
          )}
        </div>
      </div>
      
      {isExpanded && (
        <div className="p-3">
          {expr.branches.map((branch) => (
            <CaseWhenRow
              key={branch.id}
              branch={branch}
              columns={columns}
              onChange={(branchId, updates) => onUpdateBranch(expr.id, branchId, updates)}
              onRemove={(branchId) => onRemoveBranch(expr.id, branchId)}
            />
          ))}
          
          <div className="flex justify-start mb-4 mt-2">
            <button
              onClick={() => onAddBranch(expr.id)}
              className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              <span>+ Add WHEN condition</span>
            </button>
          </div>

          <div className="flex items-center gap-2 pt-3 border-t border-gray-200">
            <span className="text-sm font-semibold text-gray-600 w-12">ELSE</span>
            <select
              className="border border-gray-300 rounded px-2 py-1 text-sm bg-white"
              value={expr.elseType}
              onChange={(e) =>
                onUpdate(expr.id, {
                  elseType: e.target.value as "literal" | "column",
                  elseValue: "",
                })
              }
            >
              <option value="literal">Literal</option>
              <option value="column">Column</option>
            </select>
            {expr.elseType === "literal" ? (
              <input
                type="text"
                className="border border-gray-300 rounded px-2 py-1 text-sm flex-1"
                placeholder="Default result value"
                value={expr.elseValue}
                onChange={(e) => onUpdate(expr.id, { elseValue: e.target.value })}
              />
            ) : (
              <div className="flex-1">
                <SearchableSelect
                  options={columns.map((c) => ({ value: c.key, label: c.label, description: c.dtype }))}
                  value={expr.elseValue}
                  onChange={(col) => onUpdate(expr.id, { elseValue: col })}
                  placeholder="Select column..."
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

interface CaseExpressionBuilderProps {
  caseExpressions: CaseExpression[];
  columns: QueryColumnOption[];
  onAddCase: () => void;
  onUpdateCase: (id: string, updates: Partial<CaseExpression>) => void;
  onRemoveCase: (id: string) => void;
  onAddBranch: (caseId: string) => void;
  onUpdateBranch: (caseId: string, branchId: string, updates: Partial<CaseWhenBranch>) => void;
  onRemoveBranch: (caseId: string, branchId: string) => void;
}

export const CaseExpressionBuilder: React.FC<CaseExpressionBuilderProps> = ({
  caseExpressions,
  columns,
  onAddCase,
  onUpdateCase,
  onRemoveCase,
  onAddBranch,
  onUpdateBranch,
  onRemoveBranch,
}) => {
  return (
    <div className="bg-white p-4 border border-gray-200 rounded shadow-sm mb-4">
      <div className="flex justify-between items-center mb-2">
        <h3 className="font-semibold text-gray-700">Computed Columns (CASE)</h3>
        <button onClick={onAddCase} className="bg-blue-50 text-blue-600 px-2 py-1 rounded text-sm hover:bg-blue-100">
          + Add Computed Column
        </button>
      </div>
      <div>
        {caseExpressions.length === 0 ? (
          <p className="text-sm text-gray-500 italic">No computed columns defined.</p>
        ) : (
          caseExpressions.map((expr) => (
            <CaseExpressionCard
              key={expr.id}
              expr={expr}
              columns={columns}
              onUpdate={onUpdateCase}
              onRemove={onRemoveCase}
              onAddBranch={onAddBranch}
              onUpdateBranch={onUpdateBranch}
              onRemoveBranch={onRemoveBranch}
            />
          ))
        )}
      </div>
    </div>
  );
};
