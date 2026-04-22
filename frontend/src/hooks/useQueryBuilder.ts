/**
 * useQueryBuilder.ts â€” Hook managing query composition, SQL preview, and execution state.
 */
import { useCallback, useEffect, useState } from "react";
import { executeQuery as executeQueryApi, previewQuery as previewQueryApi } from "../api/queryApi";
import type { QueryEngine } from "../types/connection.types";
import type {
  FilterCondition,
  PivotConfig,
  QueryPayload,
  QueryResult,
  QuerySourceMode,
  QueryState,
  SortClause,
} from "../types/query.types";

const genId = () => Math.random().toString(36).substring(2, 11);
const NO_VALUE_OPERATORS = ["IS NULL", "IS NOT NULL"];

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
  toggleGroupBy: (col: string) => void;
  setAggregate: (column: string, func: "SUM" | "COUNT" | "AVG" | "MIN" | "MAX") => void;
  removeAggregate: (column: string) => void;
  setMode: (mode: "LIST" | "REPORT") => void;
  setPivotConfig: (config: Partial<PivotConfig>) => void;
  setLimitRows: (limit: number) => void;
  setSourceMode: (mode: QuerySourceMode) => void;
  updateSqlText: (sql: string) => void;
  resetSqlToBuilder: () => void;
  executeQuery: () => Promise<QueryResult | undefined>;
  reset: () => void;
}

const initialState: QueryBuilderState = {
  table: "",
  selectedColumns: [],
  filters: [],
  sort: [],
  groupBy: [],
  aggregates: [],
  limitRows: 1000,
  offset: 0,
  mode: "LIST",
  pivotConfig: { rows: [], columns: [], values: "", func: "SUM" },
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

function buildBuilderPayload(state: QueryBuilderState, engine: QueryEngine): QueryPayload {
  return {
    execution_mode: "builder",
    engine,
    table: state.table,
    select: state.selectedColumns,
    filters: getValidFilters(state.filters),
    sort: state.sort,
    group_by: state.groupBy,
    aggregates: state.aggregates,
    limit_rows: state.limitRows,
    offset: state.offset,
    mode: state.mode,
    pivot: state.mode === "REPORT" ? state.pivotConfig : undefined,
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

    const timer = window.setTimeout(async () => {
      setState((prev) => ({ ...prev, isPreviewLoading: true, previewError: null }));
      try {
        const preview = await previewQueryApi(buildBuilderPayload(state, engine));
        if (cancelled) return;
        setState((prev) => {
          const shouldSyncEditor =
            prev.sourceMode === "builder" || !prev.isSqlDetached || prev.sqlText.trim() === "";
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
          sqlText:
            prev.sourceMode === "builder" || !prev.isSqlDetached ? "" : prev.sqlText,
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
    state.groupBy,
    state.aggregates,
    state.limitRows,
    state.offset,
    state.mode,
    state.pivotConfig,
  ]);

  const setTable = useCallback((tableName: string) => {
    setState((prev) => ({
      ...initialState,
      table: tableName,
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
      filters: prev.filters.map((filter) => (filter.id === id ? { ...filter, ...updates } : filter)),
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

  const executeQuery = useCallback(async () => {
    const isBuilderMode = state.sourceMode === "builder";
    if (isBuilderMode && !state.table) {
      setState((prev) => ({ ...prev, error: "Please select a table before running the visual builder." }));
      return undefined;
    }
    if (!isBuilderMode && !state.sqlText.trim()) {
      setState((prev) => ({ ...prev, error: "Please enter SQL before running the manual editor." }));
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
            limit_rows: state.limitRows,
            offset: state.offset,
            mode: "LIST",
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
    setState(initialState);
  }, []);

  return {
    state,
    setTable,
    toggleColumn,
    addFilter,
    updateFilter,
    removeFilter,
    setSort,
    toggleGroupBy,
    setAggregate,
    removeAggregate,
    setMode,
    setPivotConfig,
    setLimitRows,
    setSourceMode,
    updateSqlText,
    resetSqlToBuilder,
    executeQuery,
    reset,
  };
}
