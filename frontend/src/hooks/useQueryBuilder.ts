/**
 * useQueryBuilder.ts — Hook managing query composition and execution state.
 */
import { useState, useCallback } from "react";
import type { QueryState, QueryResult, FilterCondition, SortClause } from "../types/query.types";
import { executeQuery as executeQueryApi } from "../api/queryApi";

const genId = () => Math.random().toString(36).substring(2, 11);

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
};

export function useQueryBuilder(): UseQueryBuilderReturn {
  const [state, setState] = useState<QueryBuilderState>(initialState);

  const setTable = useCallback((tableName: string) => {
    setState({ ...initialState, table: tableName });
  }, []);

  const toggleColumn = useCallback((columnName: string) => {
    setState((prev) => ({
      ...prev,
      selectedColumns: prev.selectedColumns.includes(columnName)
        ? prev.selectedColumns.filter((c) => c !== columnName)
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
      filters: prev.filters.map((f) => (f.id === id ? { ...f, ...updates } : f)),
    }));
  }, []);

  const removeFilter = useCallback((id: string) => {
    setState((prev) => ({
      ...prev,
      filters: prev.filters.filter((f) => f.id !== id),
    }));
  }, []);

  const setSort = useCallback((sort: SortClause[]) => {
    setState((prev) => ({ ...prev, sort }));
  }, []);

  const toggleGroupBy = useCallback((col: string) => {
    setState((prev) => {
      const isGrouped = prev.groupBy.includes(col);
      const newGroupBy = isGrouped
        ? prev.groupBy.filter((c) => c !== col)
        : [...prev.groupBy, col];
        
      // If we remove grouping, we might want to clean up aggregates, but let's keep them for simplicity.
      // If a column is added to groupBy, it shouldn't be in aggregates.
      const newAggs = isGrouped ? prev.aggregates : prev.aggregates.filter(a => a.column !== col);

      return {
        ...prev,
        groupBy: newGroupBy,
        aggregates: newAggs,
      };
    });
  }, []);

  const setAggregate = useCallback((column: string, func: "SUM" | "COUNT" | "AVG" | "MIN" | "MAX") => {
    setState((prev) => {
      const existing = prev.aggregates.find(a => a.column === column);
      if (existing) {
        return { ...prev, aggregates: prev.aggregates.map(a => a.column === column ? { ...a, func } : a) };
      }
      return { ...prev, aggregates: [...prev.aggregates, { column, func }] };
    });
  }, []);

  const removeAggregate = useCallback((column: string) => {
    setState((prev) => ({
      ...prev,
      aggregates: prev.aggregates.filter(a => a.column !== column)
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

  const executeQuery = useCallback(async () => {
    if (!state.table) return;
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const validFilters = state.filters
        .filter((f) => f.column && (["IS NULL", "IS NOT NULL"].includes(f.operator) || f.value !== ""))
        .map(({ id, ...rest }) => rest);

      const payload = {
        table: state.table,
        select: state.selectedColumns,
        filters: validFilters,
        sort: state.sort,
        group_by: state.groupBy,
        aggregates: state.aggregates,
        limit_rows: state.limitRows,
        offset: state.offset,
        mode: state.mode,
        pivot: state.mode === "REPORT" ? state.pivotConfig : undefined,
      };

      const result = await executeQueryApi(payload);
      setState((prev) => ({ ...prev, result, isLoading: false }));
      return result;
    } catch (err: any) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err?.response?.data?.detail || err.message || "Query failed",
      }));
    }
  }, [state]);

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
    executeQuery,
    reset,
  };
}
