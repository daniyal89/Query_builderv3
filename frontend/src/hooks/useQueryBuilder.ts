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
} from "../types/query.types";
import { getReferencedTable } from "../utils/queryBuilderColumns";

const genId = () => Math.random().toString(36).substring(2, 11);
const NO_VALUE_OPERATORS = ["IS NULL", "IS NOT NULL"];
const MARCADOSE_DISCOMS = ["DVVNL", "PVVNL", "PUVNL", "MVVNL", "KESCO"];

function getDefaultMonthTag(): string {
  const now = new Date();
  const monthName = now.toLocaleString("en-US", { month: "short" }).toLowerCase();
  return `${monthName}_${now.getFullYear()}`;
}

function createDefaultMarcadoseUnion(): MarcadoseUnionConfig {
  return {
    enabled: false,
    month_tag: getDefaultMonthTag(),
    discoms: [...MARCADOSE_DISCOMS],
    base_discom: "DVVNL",
    add_grand_total: false,
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
  joinType: "INNER",
  conditions: [createJoinCondition()],
});

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
  updateJoin: (id: string, updates: Partial<Pick<JoinClause, "table" | "joinType">>) => void;
  removeJoin: (id: string) => void;
  addJoinCondition: (joinId: string) => void;
  updateJoinCondition: (joinId: string, conditionId: string, updates: Partial<JoinCondition>) => void;
  removeJoinCondition: (joinId: string, conditionId: string) => void;
  toggleGroupBy: (col: string) => void;
  setAggregate: (column: string, func: "SUM" | "COUNT" | "AVG" | "MIN" | "MAX") => void;
  removeAggregate: (column: string) => void;
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
  return err?.response?.data?.detail || err?.message || fallback;
}

function getValidFilters(filters: FilterCondition[]): Omit<FilterCondition, "id">[] {
  return filters
    .filter((filter) => {
      if (!filter.column) return false;
      if (NO_VALUE_OPERATORS.includes(filter.operator)) return true;
      return typeof filter.value === "string" ? filter.value.trim() !== "" : filter.value !== "";
    })
    .map(({ id, ...rest }) => rest);
}

function getJoinPayloads(state: QueryBuilderState): QueryPayload["joins"] {
  return state.joins
    .filter((join) => join.table.trim() !== "")
    .map((join) => ({
      table: join.table,
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
      .filter((join) => !removedTables.has(join.table))
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
    limit_rows: state.limitRows,
    offset: state.offset,
    mode: state.mode,
    pivot: state.mode === "REPORT" ? state.pivotConfig : undefined,
    marcadose_union: state.marcadoseUnion,
  };
}

export function useQueryBuilder(engine: QueryEngine = "duckdb"): UseQueryBuilderReturn {
  const [state, setState] = useState<QueryBuilderState>(initialState);

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
  }, [
    engine,
    state.table,
    state.selectedColumns,
    state.filters,
    state.sort,
    state.joins,
    state.groupBy,
    state.aggregates,
    state.limitRows,
    state.offset,
    state.mode,
    state.pivotConfig,
    state.marcadoseUnion,
  ]);

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
    (id: string, updates: Partial<Pick<JoinClause, "table" | "joinType">>) => {
      setState((prev) => {
        const currentJoin = prev.joins.find((join) => join.id === id);
        if (!currentJoin) return prev;

        const tableChanged =
          updates.table !== undefined && updates.table !== currentJoin.table;

        const nextState: QueryBuilderState = {
          ...prev,
          joins: prev.joins.map((join) => {
            if (join.id !== id) return join;
            if (!tableChanged) return { ...join, ...updates };

            return {
              ...join,
              ...updates,
              conditions: [createJoinCondition()],
            };
          }),
        };

        if (!tableChanged || !currentJoin.table) return nextState;

        return pruneRemovedTableReferences(nextState, new Set([currentJoin.table]));
      });
    },
    []
  );

  const removeJoin = useCallback((id: string) => {
    setState((prev) => {
      const removedJoin = prev.joins.find((join) => join.id === id);

      const nextState: QueryBuilderState = {
        ...prev,
        joins: prev.joins.filter((join) => join.id !== id),
      };

      if (!removedJoin?.table) return nextState;

      return pruneRemovedTableReferences(nextState, new Set([removedJoin.table]));
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
