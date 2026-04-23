import React, { useMemo } from "react";
import type { TableMetadata } from "../../types/schema.types";
import type { JoinClause, JoinCondition, JoinType } from "../../types/query.types";
import { buildColumnOptionsForQuery, buildColumnOptionsForTable } from "../../utils/queryBuilderColumns";
import { SearchableSelect } from "./SearchableSelect";

const JOIN_TYPES: JoinType[] = ["INNER", "LEFT", "RIGHT"];

interface JoinComposerProps {
  baseTable: string;
  joins: JoinClause[];
  tables: TableMetadata[];
  onAddJoin: () => void;
  onUpdateJoin: (id: string, updates: Partial<Pick<JoinClause, "table" | "joinType">>) => void;
  onRemoveJoin: (id: string) => void;
  onAddCondition: (joinId: string) => void;
  onUpdateCondition: (joinId: string, conditionId: string, updates: Partial<JoinCondition>) => void;
  onRemoveCondition: (joinId: string, conditionId: string) => void;
}

export const JoinComposer: React.FC<JoinComposerProps> = ({
  baseTable,
  joins,
  tables,
  onAddJoin,
  onUpdateJoin,
  onRemoveJoin,
  onAddCondition,
  onUpdateCondition,
  onRemoveCondition,
}) => {
  const tableMap = useMemo(() => new Map(tables.map((table) => [table.table_name, table])), [tables]);

  return (
    <div className="mb-4 overflow-hidden rounded border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold text-gray-700">Joins</h3>
          <p className="mt-1 text-xs text-gray-500">
            Start from <span className="break-all font-mono">{baseTable}</span> and add ordered joins across the active
            engine.
          </p>
        </div>
        <button
          onClick={onAddJoin}
          className="shrink-0 whitespace-nowrap rounded bg-blue-50 px-2 py-1 text-sm text-blue-600 hover:bg-blue-100"
        >
          + Add Join
        </button>
      </div>

      {joins.length === 0 && (
        <p className="text-sm italic text-gray-500">
          No joins yet. Queries currently run only against the selected base table.
        </p>
      )}

      <div className="space-y-3">
        {joins.map((join, index) => {
          const leftOptions = buildColumnOptionsForQuery(baseTable, joins.slice(0, index), tables);
          const rightOptions = buildColumnOptionsForTable(tableMap.get(join.table));
          const usedTables = new Set(
            [baseTable, ...joins.filter((candidate) => candidate.id !== join.id).map((candidate) => candidate.table)].filter(
              (tableName) => tableName.trim() !== ""
            )
          );
          const availableJoinTargets = tables.filter(
            (table) => table.table_name === join.table || !usedTables.has(table.table_name)
          );
          const joinTableOptions = availableJoinTargets.map((table) => ({
            value: table.table_name,
            label: table.table_name,
            description: table.columns.length > 0 ? `${table.columns.length} columns` : "columns load on select",
          }));
          const leftColumnOptions = leftOptions.map((column) => ({
            value: column.key,
            label: column.label,
            description: column.dtype,
          }));
          const rightColumnOptions = rightOptions.map((column) => ({
            value: column.key,
            label: column.label,
            description: column.dtype,
          }));
          const isReady =
            join.table.trim() !== "" &&
            join.conditions.length > 0 &&
            join.conditions.every(
              (condition) => condition.leftColumn.trim() !== "" && condition.rightColumn.trim() !== ""
            );

          return (
            <div key={join.id} className="rounded border border-gray-200 bg-gray-50 p-3">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                    Join {index + 1}
                  </span>
                  <p className={`mt-1 text-xs ${isReady ? "text-emerald-700" : "text-amber-700"}`}>
                    {isReady ? "Ready for preview and execution." : "Select a table and at least one matching column pair."}
                  </p>
                </div>
                <button
                  onClick={() => onRemoveJoin(join.id)}
                  className="text-sm font-bold text-red-400 hover:text-red-600"
                  title="Remove join"
                >
                  ×
                </button>
              </div>

              <div className="mb-3 grid gap-2 sm:grid-cols-[130px,minmax(0,1fr)]">
                <select
                  value={join.joinType}
                  onChange={(event) => onUpdateJoin(join.id, { joinType: event.target.value as JoinType })}
                  className="w-full min-w-0 rounded border border-gray-300 bg-white px-2 py-2 text-sm"
                >
                  {JOIN_TYPES.map((joinType) => (
                    <option key={joinType} value={joinType}>
                      {joinType}
                    </option>
                  ))}
                </select>

                <SearchableSelect
                  value={join.table}
                  options={joinTableOptions}
                  onChange={(table) => onUpdateJoin(join.id, { table })}
                  placeholder="-- Select Join Table --"
                  searchPlaceholder="Search join tables..."
                  emptyMessage="No join tables match your search."
                />
              </div>

              <div className="space-y-2">
                {join.conditions.map((condition, conditionIndex) => (
                  <div key={condition.id} className="rounded border border-gray-200 bg-white p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Match {conditionIndex + 1}
                      </span>
                      <button
                        onClick={() => onRemoveCondition(join.id, condition.id)}
                        className="text-xs font-semibold text-red-500 hover:text-red-700"
                      >
                        Remove
                      </button>
                    </div>

                    <div className="grid gap-2">
                      <SearchableSelect
                        value={condition.leftColumn}
                        options={leftColumnOptions}
                        onChange={(leftColumn) =>
                          onUpdateCondition(join.id, condition.id, { leftColumn })
                        }
                        placeholder="-- Left Side Column --"
                        searchPlaceholder="Search left-side columns..."
                        emptyMessage="No left-side columns match your search."
                      />

                      <div className="flex items-center justify-center rounded border border-dashed border-gray-300 bg-gray-50 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Match equals
                      </div>

                      <SearchableSelect
                        value={condition.rightColumn}
                        options={rightColumnOptions}
                        onChange={(rightColumn) =>
                          onUpdateCondition(join.id, condition.id, { rightColumn })
                        }
                        disabled={!join.table}
                        placeholder="-- Joined Table Column --"
                        searchPlaceholder="Search joined table columns..."
                        emptyMessage="No joined-table columns match your search."
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-gray-500">
                  Later joins can reference the base table and any earlier joined table.
                </p>
                <button
                  onClick={() => onAddCondition(join.id)}
                  disabled={!join.table}
                  className="rounded border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  + Add Match
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
