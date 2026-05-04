/**
 * useQueryBuilder.ts — Hook managing query composition, SQL preview, and execution state.
 */
import { useCallback, useEffect, useState } from "react";
import { executeQuery as executeQueryApi, previewQuery as previewQueryApi } from "../api/queryApi";
import type { QueryEngine } from "../types/connection.types";
import type {
  FilterCondition,
  JoinClause,
  JoinCondition,
  MarcadoseUnionConfig,
  PivotConfig,
  QueryPayload,
  QueryResult,
  QuerySourceMode,
  QueryState,
  SortClause,
  CaseExpression,
  CaseWhenBranch,
  FunctionColumn,
} from "../types/query.types";
import {
  buildSuggestedJoinAlias,
  getJoinReferenceName,
  getReferencedTable,
  normalizeJoinAlias,
} from "../utils/queryBuilderColumns";

const genId = () => Math.random().toString(36).substring(2, 11);
const NO_VALUE_OPERATORS = ["IS NULL", "IS NOT NULL"];
const MARCADOSE_DISCOMS = ["DVVNL", "PVVNL", "PUVNL", "MVVNL", "KESCO"];
const WORKSPACE_STATE_STORAGE_PREFIX = "qb:workspace-state:v1";

function getDefaultMonthTag(): string {
  const now = new Date();
  const monthName = now.toLocaleString("en-US", { month: "short" }).toLowerCase();
  return `${monthName}_${now.getFullYear()}`;
}

function createDefaultMarcadoseUnion(): MarcadoseUnionConfig {
  return {
    enabled: true,
    month_tag: getDefaultMonthTag(),
    discoms: [...MARCADOSE_DISCOMS],
    base_discom: "DVVNL",
    add_grand_total: true,
    schema_name: "MERCADOS",
  };
}

const createJoinCondition = (): JoinCondition => ({
  id: genId(),
  leftColumn: "",
  rightColumn: "",
});

const createJoin = (): JoinClause => ({
  id: genId(),
  table: "",
  alias: "",
  joinType: "INNER",
  conditions: [createJoinCondition()],
});

function normalizeJoinClauses(joins: JoinClause[], baseTable: string): JoinClause[] {
  const normalized: JoinClause[] = [];
  const usedReferences = new Set<string>();

  if (baseTable.trim()) {
    usedReferences.add(baseTable.trim());
  }

  joins.forEach((join) => {
    const nextTable = join.table.trim();
    const explicitAlias = normalizeJoinAlias(join.alias);
    let nextAlias = "";

    if (nextTable) {
      if (explicitAlias) {
        nextAlias = explicitAlias;
      } else if (usedReferences.has(nextTable)) {
        nextAlias = buildSuggestedJoinAlias(nextTable, normalized, join.id, baseTable);
      }
    }

    const normalizedJoin: JoinClause = {
      ...join,
      table: nextTable,
      alias: nextAlias,
      conditions: join.conditions.length > 0 ? join.conditions : [createJoinCondition()],
    };

    const nextReference = getJoinReferenceName(normalizedJoin);
    if (nextReference) {
      usedReferences.add(nextReference);
    }

    normalized.push(normalizedJoin);
  });

  return normalized;
}

function replaceTableReference(columnRef: string, previousReference: string, nextReference: string): string {
  const prefix = `${previousReference}.`;
  if (!columnRef.startsWith(prefix)) {
    return columnRef;
  }
  return `${nextReference}.${columnRef.slice(prefix.length)}`;
}

function renameTableReferences(
  state: QueryBuilderState,
  previousReference: string,
  nextReference: string
): QueryBuilderState {
  if (!previousReference || !nextReference || previousReference === nextReference) {
    return state;
  }

  const rename = (columnRef: string) =>
    replaceTableReference(columnRef, previousReference, nextReference);

  return {
    ...state,
    selectedColumns: state.selectedColumns.map(rename),
    filters: state.filters.map((filter) => ({
      ...filter,
      column: rename(filter.column),
    })),
    sort: state.sort.map((sortRule) => ({
      ...sortRule,
      column: rename(sortRule.column),
    })),
    joins: state.joins.map((join) => ({
      ...join,
      conditions: join.conditions.map((condition) => ({
        ...condition,
        leftColumn: rename(condition.leftColumn),
        rightColumn: rename(condition.rightColumn),
      })),
    })),
    groupBy: state.groupBy.map(rename),
    aggregates: state.aggregates.map((aggregate) => ({
      ...aggregate,
      column: rename(aggregate.column),
    })),
    caseExpressions: state.caseExpressions.map((expression) => ({
      ...expression,
      branches: expression.branches.map((branch) => ({
        ...branch,
        column: rename(branch.column),
        thenValue: branch.thenType === "column" ? rename(branch.thenValue) : branch.thenValue,
      })),
      elseValue: expression.elseType === "column" ? rename(expression.elseValue) : expression.elseValue,
    })),
    functionColumns: state.functionColumns.map((functionColumn) => ({
      ...functionColumn,
      column: rename(functionColumn.column),
      secondColumn: functionColumn.secondColumn ? rename(functionColumn.secondColumn) : functionColumn.secondColumn,
    })),
    pivotConfig: {
      ...state.pivotConfig,
      rows: state.pivotConfig.rows.map(rename),
      columns: state.pivotConfig.columns.map(rename),
      values: rename(state.pivotConfig.values),
    },
  };
}

function canRenameJoinReference(
  state: QueryBuilderState,
  joinId: string,
  nextReference: string
): boolean {
  if (!nextReference.trim()) {
    return false;
  }

  if (state.table.trim() === nextReference) {
    return false;
  }

  return state.joins.every(
    (join) => join.id === joinId || getJoinReferenceName(join) !== nextReference
  );
}

interface QueryBuilderState extends QueryState {
  result: QueryResult | null;
}

export interface UseQueryBuilderReturn {
  state: QueryBuilderState;
  setTable: (tableName: string) => void;
  toggleColumn: (columnName: string) => void;
  addFilter: () => void;
  updateFilter: (id: string, updates: Partial<FilterCondition>) => void;
  removeFilter: (id: string) => void;
  setSort: (sort: SortClause[]) => void;
  addJoin: () => void;
  updateJoin: (id: string, updates: Partial<Pick<JoinClause, "table" | "alias" | "joinType">>) => void;
  removeJoin: (id: string) => void;
  addJoinCondition: (joinId: string) => void;
  updateJoinCondition: (joinId: string, conditionId: string, updates: Partial<JoinCondition>) => void;
  removeJoinCondition: (joinId: string, conditionId: string) => void;
  toggleGroupBy: (col: string) => void;
  setAggregate: (column: string, func: "SUM" | "COUNT" | "AVG" | "MIN" | "MAX") => void;
  removeAggregate: (column: string) => void;
  addCaseExpression: () => void;
  updateCaseExpression: (id: string, updates: Partial<CaseExpression>) => void;
  removeCaseExpression: (id: string) => void;
  addCaseBranch: (caseId: string) => void;
  updateCaseBranch: (caseId: string, branchId: string, updates: Partial<CaseWhenBranch>) => void;
  removeCaseBranch: (caseId: string, branchId: string) => void;
  addFunctionColumn: () => void;
  updateFunctionColumn: (id: string, updates: Partial<FunctionColumn>) => void;
  removeFunctionColumn: (id: string) => void;
  setMode: (mode: "LIST" | "REPORT") => void;
  setPivotConfig: (config: Partial<PivotConfig>) => void;
  setMarcadoseUnion: (config: Partial<MarcadoseUnionConfig>) => void;
  setLimitRows: (limit: number) => void;
  setSourceMode: (mode: QuerySourceMode) => void;
  updateSqlText: (sql: string) => void;
  resetSqlToBuilder: () => void;
  applyState: (nextState: Partial<QueryState>) => void;
  executeQuery: () => Promise<QueryResult | undefined>;
  reset: () => void;
}

const initialState: QueryBuilderState = {
  table: "",
  selectedColumns: [],
  filters: [],
  sort: [],
  joins: [],
  groupBy: [],
  aggregates: [],
  caseExpressions: [],
  functionColumns: [],
  limitRows: 1000,
  offset: 0,
  mode: "LIST",
  pivotConfig: { rows: [], columns: [], values: "", func: "SUM" },
  marcadoseUnion: createDefaultMarcadoseUnion(),
  result: null,
  isLoading: false,
  error: null,
  sourceMode: "builder",
  generatedSql: "",
  sqlText: "",
  isSqlDetached: false,
  isPreviewLoading: false,
  previewError: null,
};

function getErrorMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object") {
    const message = typeof detail.message === "string" ? detail.message : fallback;
    const executedSql = typeof detail.executed_sql === "string" ? detail.executed_sql : "";
    return executedSql ? `${message}\n\nExecuted SQL:\n${executedSql}` : message;
  }
  return err?.message || fallback;
}

function getValidFilters(filters: FilterCondition[]): Omit<FilterCondition, "id">[] {
  return filters
    .filter((filter) => {
      if (!filter.column) return false;
      if (NO_VALUE_OPERATORS.includes(filter.operator)) return true;
      return typeof filter.value === "string" ? filter.value.trim() !== "" : filter.value !== "";
    })
    .map((filter) => {
      const { id, ...payload } = filter;
      void id;
      return payload;
    });
}

function getJoinPayloads(state: QueryBuilderState): QueryPayload["joins"] {
  return state.joins
    .filter((join) => join.table.trim() !== "")
    .map((join) => ({
      table: join.table,
      alias: join.alias.trim() || undefined,
      join_type: join.joinType,
      conditions: join.conditions.map((condition) => ({
        left_column: condition.leftColumn,
        right_column: condition.rightColumn,
      })),
    }));
}

function hasIncompleteConfiguredJoins(state: QueryBuilderState): boolean {
  return state.joins.some((join) => {
    if (!join.table.trim()) return false;
    if (!join.conditions.length) return true;

    return join.conditions.some(
      (condition) => !condition.leftColumn.trim() || !condition.rightColumn.trim()
    );
  });
}

function pruneRemovedTableReferences(
  state: QueryBuilderState,
  removedTables: Set<string>
): QueryBuilderState {
  if (removedTables.size === 0) return state;

  const hasRemovedTable = (columnRef: string) => {
    const tableName = getReferencedTable(columnRef);
    return !!tableName && removedTables.has(tableName);
  };

  return {
    ...state,
    selectedColumns: state.selectedColumns.filter((column) => !hasRemovedTable(column)),
    filters: state.filters.filter((filter) => !hasRemovedTable(filter.column)),
    sort: state.sort.filter((sort) => !hasRemovedTable(sort.column)),
    joins: state.joins
      .filter((join) => !removedTables.has(getJoinReferenceName(join)))
      .map((join) => ({
        ...join,
        conditions:
          join.conditions.length > 0
            ? join.conditions.map((condition) => ({
              ...condition,
              leftColumn: hasRemovedTable(condition.leftColumn) ? "" : condition.leftColumn,
              rightColumn: hasRemovedTable(condition.rightColumn) ? "" : condition.rightColumn,
            }))
            : [createJoinCondition()],
      })),
  };
}

function buildBuilderPayload(state: QueryBuilderState, engine: QueryEngine): QueryPayload {
  return {
    execution_mode: "builder",
    engine,
    table: state.table,
    select: state.selectedColumns,
    filters: getValidFilters(state.filters),
    sort: state.sort,
    joins: getJoinPayloads(state),
    group_by: state.groupBy,
    aggregates: state.aggregates,
    case_expressions: state.caseExpressions.map((expr) => ({
      alias: expr.alias,
      aggregate_func: expr.aggregateFunc,
      else_type: expr.elseType,
      else_value: expr.elseValue,
      branches: expr.branches.map((branch) => ({
        column: branch.column,
        operator: branch.operator,
        value: branch.value,
        then_type: branch.thenType,
        then_value: branch.thenValue,
      })),
    })),
    function_columns: state.functionColumns.map((col) => ({
      func: col.func,
      column: col.column,
      second_column: col.secondColumn,
      alias: col.alias,
    })),
    limit_rows: state.limitRows,
    offset: state.offset,
    mode: state.mode,
    pivot: state.mode === "REPORT" ? state.pivotConfig : undefined,
    marcadose_union: state.marcadoseUnion,
  };
}

type PersistableQueryBuilderState = Pick<
  QueryBuilderState,
  | "table"
  | "selectedColumns"
  | "filters"
  | "sort"
  | "joins"
  | "groupBy"
  | "aggregates"
  | "caseExpressions"
  | "functionColumns"
  | "limitRows"
  | "offset"
  | "mode"
  | "pivotConfig"
  | "marcadoseUnion"
  | "sourceMode"
  | "generatedSql"
  | "sqlText"
  | "isSqlDetached"
>;

function getWorkspaceStateStorageKey(engine: QueryEngine): string {
  return `${WORKSPACE_STATE_STORAGE_PREFIX}:${engine}`;
}

function toPersistableState(state: QueryBuilderState): PersistableQueryBuilderState {
  return {
    table: state.table,
    selectedColumns: state.selectedColumns,
    filters: state.filters,
    sort: state.sort,
    joins: state.joins,
    groupBy: state.groupBy,
    aggregates: state.aggregates,
    caseExpressions: state.caseExpressions,
    functionColumns: state.functionColumns,
    limitRows: state.limitRows,
    offset: state.offset,
    mode: state.mode,
    pivotConfig: state.pivotConfig,
    marcadoseUnion: state.marcadoseUnion,
    sourceMode: state.sourceMode,
    generatedSql: state.generatedSql,
    sqlText: state.sqlText,
    isSqlDetached: state.isSqlDetached,
  };
}

export function useQueryBuilder(engine: QueryEngine = "duckdb"): UseQueryBuilderReturn {
  const [state, setState] = useState<QueryBuilderState>(initialState);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(getWorkspaceStateStorageKey(engine));
      if (!raw) return;
      const persisted = JSON.parse(raw) as Partial<PersistableQueryBuilderState>;
      setState((previous) => ({
        ...previous,
        ...persisted,
        joins: normalizeJoinClauses(
          (persisted.joins as JoinClause[] | undefined) || previous.joins,
          String(persisted.table || previous.table || ""),
        ),
        marcadoseUnion: {
          ...createDefaultMarcadoseUnion(),
          ...(persisted.marcadoseUnion || {}),
        },
        result: null,
        isLoading: false,
        isPreviewLoading: false,
        error: null,
        previewError: null,
      }));
    } catch {
      // Ignore malformed persisted state and continue with defaults.
    }
  }, [engine]);

  useEffect(() => {
    const payload = toPersistableState(state);
    window.localStorage.setItem(getWorkspaceStateStorageKey(engine), JSON.stringify(payload));
  }, [engine, state]);

  useEffect(() => {
    let cancelled = false;

    if (!state.table) {
      setState((prev) => {
        const nextSqlText =
          prev.sourceMode === "builder" || !prev.isSqlDetached ? "" : prev.sqlText;

        if (
          prev.generatedSql === "" &&
          prev.previewError === null &&
          prev.isPreviewLoading === false &&
          prev.sqlText === nextSqlText
        ) {
          return prev;
        }

        return {
          ...prev,
          generatedSql: "",
          sqlText: nextSqlText,
          isPreviewLoading: false,
          previewError: null,
        };
      });
      return undefined;
    }

    if (hasIncompleteConfiguredJoins(state)) {
      setState((prev) => ({
        ...prev,
        generatedSql: "",
        sqlText: prev.sourceMode === "builder" || !prev.isSqlDetached ? "" : prev.sqlText,
        isPreviewLoading: false,
        previewError: "Complete the join column mapping before previewing SQL.",
      }));
      return undefined;
    }

    if (state.mode === "REPORT" && !state.pivotConfig.values.trim()) {
      setState((prev) => ({
        ...prev,
        generatedSql: "",
        sqlText: prev.sourceMode === "builder" || !prev.isSqlDetached ? "" : prev.sqlText,
        isPreviewLoading: false,
        previewError: "Select a Values field before generating a report.",
      }));
      return undefined;
    }

    const timer = window.setTimeout(async () => {
      setState((prev) => ({ ...prev, isPreviewLoading: true, previewError: null }));

      try {
        const preview = await previewQueryApi(buildBuilderPayload(state, engine));
        if (cancelled) return;

        setState((prev) => {
          const shouldSyncEditor =
            prev.sourceMode === "builder" ||
            !prev.isSqlDetached ||
            prev.sqlText.trim() === "";

          return {
            ...prev,
            generatedSql: preview.sql,
            sqlText: shouldSyncEditor ? preview.sql : prev.sqlText,
            isPreviewLoading: false,
            previewError: null,
          };
        });
      } catch (err: any) {
        if (cancelled) return;

        setState((prev) => ({
          ...prev,
          generatedSql: "",
          sqlText: prev.sourceMode === "builder" || !prev.isSqlDetached ? "" : prev.sqlText,
          isPreviewLoading: false,
          previewError: getErrorMessage(err, "Failed to generate SQL preview"),
        }));
      }
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [engine, state]);

  const setTable = useCallback((tableName: string) => {
    setState((prev) => ({
      ...initialState,
      table: tableName,
      mode: prev.mode,
      marcadoseUnion: prev.marcadoseUnion,
      sourceMode: prev.sourceMode,
      sqlText: prev.sourceMode === "manual" && prev.isSqlDetached ? prev.sqlText : "",
      isSqlDetached: prev.sourceMode === "manual" ? prev.isSqlDetached : false,
    }));
  }, []);

  const toggleColumn = useCallback((columnName: string) => {
    setState((prev) => ({
      ...prev,
      selectedColumns: prev.selectedColumns.includes(columnName)
        ? prev.selectedColumns.filter((column) => column !== columnName)
        : [...prev.selectedColumns, columnName],
    }));
  }, []);

  const addFilter = useCallback(() => {
    setState((prev) => ({
      ...prev,
      filters: [...prev.filters, { id: genId(), column: "", operator: "=", value: "" }],
    }));
  }, []);

  const updateFilter = useCallback((id: string, updates: Partial<FilterCondition>) => {
    setState((prev) => ({
      ...prev,
      filters: prev.filters.map((filter) =>
        filter.id === id ? { ...filter, ...updates } : filter
      ),
    }));
  }, []);

  const removeFilter = useCallback((id: string) => {
    setState((prev) => ({
      ...prev,
      filters: prev.filters.filter((filter) => filter.id !== id),
    }));
  }, []);

  const setSort = useCallback((sort: SortClause[]) => {
    setState((prev) => ({ ...prev, sort }));
  }, []);

  const addJoin = useCallback(() => {
    setState((prev) => ({
      ...prev,
      joins: [...prev.joins, createJoin()],
    }));
  }, []);

  const updateJoin = useCallback(
    (id: string, updates: Partial<Pick<JoinClause, "table" | "alias" | "joinType">>) => {
      setState((prev) => {
        const currentJoin = prev.joins.find((join) => join.id === id);
        if (!currentJoin) return prev;

        const tableChanged =
          updates.table !== undefined && updates.table !== currentJoin.table;
        const aliasChanged =
          updates.alias !== undefined && updates.alias !== currentJoin.alias;
        const currentReference = getJoinReferenceName(currentJoin);

        const nextState: QueryBuilderState = {
          ...prev,
          joins: normalizeJoinClauses(
            prev.joins.map((join) => {
              if (join.id !== id) return join;
              if (!tableChanged) {
                return { ...join, ...updates };
              }

              return {
                ...join,
                ...updates,
                alias: updates.alias ?? "",
                conditions: [createJoinCondition()],
              };
            }),
            prev.table,
          ),
        };
        const nextJoin = nextState.joins.find((join) => join.id === id);
        const nextReference = nextJoin ? getJoinReferenceName(nextJoin) : "";

        if (tableChanged && currentReference) {
          return pruneRemovedTableReferences(nextState, new Set([currentReference]));
        }

        if (
          aliasChanged &&
          currentReference &&
          nextReference &&
          currentReference !== nextReference &&
          canRenameJoinReference(nextState, id, nextReference)
        ) {
          return renameTableReferences(nextState, currentReference, nextReference);
        }

        return nextState;
      });
    },
    []
  );

  const removeJoin = useCallback((id: string) => {
    setState((prev) => {
      const removedJoin = prev.joins.find((join) => join.id === id);
      const removedReference = removedJoin ? getJoinReferenceName(removedJoin) : "";

      const nextState: QueryBuilderState = {
        ...prev,
        joins: prev.joins.filter((join) => join.id !== id),
      };

      if (!removedReference) return nextState;

      return pruneRemovedTableReferences(nextState, new Set([removedReference]));
    });
  }, []);

  const addJoinCondition = useCallback((joinId: string) => {
    setState((prev) => ({
      ...prev,
      joins: prev.joins.map((join) =>
        join.id === joinId
          ? { ...join, conditions: [...join.conditions, createJoinCondition()] }
          : join
      ),
    }));
  }, []);

  const updateJoinCondition = useCallback(
    (joinId: string, conditionId: string, updates: Partial<JoinCondition>) => {
      setState((prev) => ({
        ...prev,
        joins: prev.joins.map((join) =>
          join.id === joinId
            ? {
              ...join,
              conditions: join.conditions.map((condition) =>
                condition.id === conditionId ? { ...condition, ...updates } : condition
              ),
            }
            : join
        ),
      }));
    },
    []
  );

  const removeJoinCondition = useCallback((joinId: string, conditionId: string) => {
    setState((prev) => ({
      ...prev,
      joins: prev.joins.map((join) => {
        if (join.id !== joinId) return join;

        if (join.conditions.length === 1) {
          return { ...join, conditions: [createJoinCondition()] };
        }

        return {
          ...join,
          conditions: join.conditions.filter((condition) => condition.id !== conditionId),
        };
      }),
    }));
  }, []);

  const toggleGroupBy = useCallback((column: string) => {
    setState((prev) => {
      const isGrouped = prev.groupBy.includes(column);
      const groupBy = isGrouped
        ? prev.groupBy.filter((value) => value !== column)
        : [...prev.groupBy, column];

      return {
        ...prev,
        groupBy,
        aggregates: isGrouped
          ? prev.aggregates
          : prev.aggregates.filter((aggregate) => aggregate.column !== column),
      };
    });
  }, []);

  const setAggregate = useCallback(
    (column: string, func: "SUM" | "COUNT" | "AVG" | "MIN" | "MAX") => {
      setState((prev) => {
        const existing = prev.aggregates.find((aggregate) => aggregate.column === column);

        if (existing) {
          return {
            ...prev,
            aggregates: prev.aggregates.map((aggregate) =>
              aggregate.column === column ? { ...aggregate, func } : aggregate
            ),
          };
        }

        return {
          ...prev,
          aggregates: [...prev.aggregates, { column, func }],
        };
      });
    },
    []
  );

  const removeAggregate = useCallback((column: string) => {
    setState((prev) => ({
      ...prev,
      aggregates: prev.aggregates.filter((aggregate) => aggregate.column !== column),
    }));
  }, []);

  const addCaseExpression = useCallback(() => {
    setState((prev) => ({
      ...prev,
      caseExpressions: [
        ...prev.caseExpressions,
        {
          id: genId(),
          alias: `Computed_Column_${prev.caseExpressions.length + 1}`,
          branches: [
            {
              id: genId(),
              column: "",
              operator: "=",
              value: "",
              thenType: "literal",
              thenValue: "",
            },
          ],
          elseType: "literal",
          elseValue: "",
        },
      ],
    }));
  }, []);

  const updateCaseExpression = useCallback((id: string, updates: Partial<CaseExpression>) => {
    setState((prev) => ({
      ...prev,
      caseExpressions: prev.caseExpressions.map((expr) =>
        expr.id === id ? { ...expr, ...updates } : expr
      ),
    }));
  }, []);

  const removeCaseExpression = useCallback((id: string) => {
    setState((prev) => ({
      ...prev,
      caseExpressions: prev.caseExpressions.filter((expr) => expr.id !== id),
    }));
  }, []);

  const addCaseBranch = useCallback((caseId: string) => {
    setState((prev) => ({
      ...prev,
      caseExpressions: prev.caseExpressions.map((expr) =>
        expr.id === caseId
          ? {
              ...expr,
              branches: [
                ...expr.branches,
                { id: genId(), column: "", operator: "=", value: "", thenType: "literal", thenValue: "" },
              ],
            }
          : expr
      ),
    }));
  }, []);

  const updateCaseBranch = useCallback(
    (caseId: string, branchId: string, updates: Partial<CaseWhenBranch>) => {
      setState((prev) => ({
        ...prev,
        caseExpressions: prev.caseExpressions.map((expr) =>
          expr.id === caseId
            ? {
                ...expr,
                branches: expr.branches.map((branch) =>
                  branch.id === branchId ? { ...branch, ...updates } : branch
                ),
              }
            : expr
        ),
      }));
    },
    []
  );

  const removeCaseBranch = useCallback((caseId: string, branchId: string) => {
    setState((prev) => ({
      ...prev,
      caseExpressions: prev.caseExpressions.map((expr) => {
        if (expr.id !== caseId) return expr;
        if (expr.branches.length === 1) return expr; // Prevent deleting the last branch
        return {
          ...expr,
          branches: expr.branches.filter((branch) => branch.id !== branchId),
        };
      }),
    }));
  }, []);

  const addFunctionColumn = useCallback(() => {
    setState((prev) => ({
      ...prev,
      functionColumns: [
        ...prev.functionColumns,
        {
          id: genId(),
          func: "SUM",
          column: "",
          alias: `Func_Column_${prev.functionColumns.length + 1}`,
        },
      ],
    }));
  }, []);

  const updateFunctionColumn = useCallback((id: string, updates: Partial<FunctionColumn>) => {
    setState((prev) => ({
      ...prev,
      functionColumns: prev.functionColumns.map((col) =>
        col.id === id ? { ...col, ...updates } : col
      ),
    }));
  }, []);

  const removeFunctionColumn = useCallback((id: string) => {
    setState((prev) => ({
      ...prev,
      functionColumns: prev.functionColumns.filter((col) => col.id !== id),
    }));
  }, []);

  const setMode = useCallback((mode: "LIST" | "REPORT") => {
    setState((prev) => ({ ...prev, mode }));
  }, []);

  const setPivotConfig = useCallback((config: Partial<PivotConfig>) => {
    setState((prev) => ({
      ...prev,
      pivotConfig: { ...prev.pivotConfig, ...config },
    }));
  }, []);

  const setMarcadoseUnion = useCallback((config: Partial<MarcadoseUnionConfig>) => {
    setState((prev) => ({
      ...prev,
      marcadoseUnion: { ...prev.marcadoseUnion, ...config },
    }));
  }, []);

  const setLimitRows = useCallback((limitRows: number) => {
    setState((prev) => ({ ...prev, limitRows }));
  }, []);

  const setSourceMode = useCallback((mode: QuerySourceMode) => {
    setState((prev) => ({
      ...prev,
      sourceMode: mode,
      error: null,
      sqlText:
        mode === "builder"
          ? prev.generatedSql
          : prev.isSqlDetached
            ? prev.sqlText
            : prev.generatedSql || prev.sqlText,
      isSqlDetached: mode === "builder" ? false : prev.isSqlDetached,
    }));
  }, []);

  const updateSqlText = useCallback((sql: string) => {
    setState((prev) => {
      const isSqlDetached = sql !== prev.generatedSql;

      return {
        ...prev,
        sqlText: sql,
        sourceMode: isSqlDetached ? "manual" : prev.sourceMode,
        isSqlDetached,
        error: null,
      };
    });
  }, []);

  const resetSqlToBuilder = useCallback(() => {
    setState((prev) => ({
      ...prev,
      sourceMode: "builder",
      sqlText: prev.generatedSql,
      isSqlDetached: false,
      error: null,
    }));
  }, []);

  const applyState = useCallback((nextState: Partial<QueryState>) => {
    setState((prev) => ({
      ...prev,
      ...nextState,
      joins: normalizeJoinClauses((nextState.joins as JoinClause[] | undefined) || prev.joins, String(nextState.table || prev.table || "")),
      error: null,
      previewError: null,
      isLoading: false,
      isPreviewLoading: false,
    }));
  }, []);

  const executeQuery = useCallback(async () => {
    const isBuilderMode = state.sourceMode === "builder";

    if (isBuilderMode && !state.table) {
      setState((prev) => ({
        ...prev,
        error: "Please select a table before running the visual builder.",
      }));
      return undefined;
    }

    if (!isBuilderMode && !state.sqlText.trim()) {
      setState((prev) => ({
        ...prev,
        error: "Please enter SQL before running the manual editor.",
      }));
      return undefined;
    }

    if (isBuilderMode && hasIncompleteConfiguredJoins(state)) {
      setState((prev) => ({
        ...prev,
        error: "Complete the join column mapping before running the query.",
      }));
      return undefined;
    }

    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const payload: QueryPayload = isBuilderMode
        ? buildBuilderPayload(state, engine)
        : {
          execution_mode: "sql",
          engine,
          table: state.table,
          select: [],
          filters: [],
          sort: [],
          joins: [],
          limit_rows: state.limitRows,
          offset: state.offset,
          mode: state.mode,
          marcadose_union: state.marcadoseUnion,
          group_by: [],
          aggregates: [],
          sql: state.sqlText,
        };

      const result = await executeQueryApi(payload);

      setState((prev) => ({
        ...prev,
        result,
        isLoading: false,
        sqlText: result.executed_sql || prev.sqlText,
        generatedSql: isBuilderMode && result.executed_sql ? result.executed_sql : prev.generatedSql,
      }));

      return result;
    } catch (err: any) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: getErrorMessage(err, "Query failed"),
      }));
      return undefined;
    }
  }, [engine, state]);

  const reset = useCallback(() => {
    setState({ ...initialState, marcadoseUnion: createDefaultMarcadoseUnion() });
  }, []);

  return {
    state,
    setTable,
    toggleColumn,
    addFilter,
    updateFilter,
    removeFilter,
    setSort,
    addJoin,
    updateJoin,
    removeJoin,
    addJoinCondition,
    updateJoinCondition,
    removeJoinCondition,
    toggleGroupBy,
    setAggregate,
    removeAggregate,
    addCaseExpression,
    updateCaseExpression,
    removeCaseExpression,
    addCaseBranch,
    updateCaseBranch,
    removeCaseBranch,
    addFunctionColumn,
    updateFunctionColumn,
    removeFunctionColumn,
    setMode,
    setPivotConfig,
    setMarcadoseUnion,
    setLimitRows,
    setSourceMode,
    updateSqlText,
    resetSqlToBuilder,
    applyState,
    executeQuery,
    reset,
  };
}
