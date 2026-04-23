/**
 * query.types.ts — TypeScript interfaces for the Query Builder state and API.
 *
 * Mirrors the backend's QueryPayload, QueryResult, FilterCondition,
 * and SortClause Pydantic models. Also defines the UI-specific QueryState
 * used to track the visual query builder's form state.
 */

import type { QueryEngine } from "./connection.types";

/** Valid SQL comparison operators for the filter builder. */
export type FilterOperator =
  | "="
  | "!="
  | ">"
  | "<"
  | ">="
  | "<="
  | "LIKE"
  | "NOT LIKE"
  | "IN"
  | "NOT IN"
  | "IS NULL"
  | "IS NOT NULL"
  | "BETWEEN"
  | "NOT BETWEEN"
  | "CONTAINS"
  | "NOT CONTAINS"
  | "STARTS WITH"
  | "ENDS WITH";

/** Sort direction options. */
export type SortDirection = "ASC" | "DESC";
export type JoinType = "INNER" | "LEFT" | "RIGHT";
export type QuerySourceMode = "builder" | "manual";
export type QueryExecutionMode = "builder" | "sql";

export interface QueryColumnOption {
  key: string;
  label: string;
  tableName: string;
  columnName: string;
  dtype: string;
  nullable: boolean;
}

/** A single WHERE-clause filter condition. */
export interface FilterCondition {
  /** Unique ID for React key prop and removal tracking. */
  id: string;
  /** Column name to filter on. */
  column: string;
  /** SQL comparison operator. */
  operator: FilterOperator;
  /** Comparison value; ignored for IS NULL / IS NOT NULL. */
  value: string;
}

/** A single ORDER BY sort directive. */
export interface SortClause {
  /** Column name to sort by. */
  column: string;
  /** Sort direction. */
  direction: SortDirection;
}

export interface JoinCondition {
  id: string;
  leftColumn: string;
  rightColumn: string;
}

export interface JoinClause {
  id: string;
  table: string;
  joinType: JoinType;
  conditions: JoinCondition[];
}

/**
 * UI state for the visual query builder page.
 *
 * This is the canonical state object managed by useQueryBuilder.
 * It tracks every aspect of the query composition form.
 */
export interface QueryState {
  /** Currently selected target table. */
  table: string;
  /** List of selected column names for the SELECT clause; empty = all (*). */
  selectedColumns: string[];
  /** Active filter conditions (ANDed together). */
  filters: FilterCondition[];
  /** Active sort directives applied in order. */
  sort: SortClause[];
  /** Join clauses applied to the base table. */
  joins: JoinClause[];
  /** Columns to GROUP BY. */
  groupBy: string[];
  /** Aggregate functions applied to columns. */
  aggregates: AggregateRule[];
  /** Maximum rows to retrieve. 0 means no limit. */
  limitRows: number;
  /** Pagination offset. */
  offset: number;
  /** Primary builder mode. */
  mode: "LIST" | "REPORT";
  /** Configurations for pivot operations. */
  pivotConfig: PivotConfig;
  /** Whether a query is currently being executed. */
  isLoading: boolean;
  /** Error message from the last failed query, or null. */
  error: string | null;
  /** Current execution source. */
  sourceMode: QuerySourceMode;
  /** Latest builder-generated SQL preview. */
  generatedSql: string;
  /** Editable SQL text shown in the editor. */
  sqlText: string;
  /** Whether the SQL editor has diverged from the visual builder. */
  isSqlDetached: boolean;
  /** Whether SQL preview is currently refreshing. */
  isPreviewLoading: boolean;
  /** Error message for SQL preview generation. */
  previewError: string | null;
}

/** Payload sent to POST /api/query. */
export interface QueryPayload {
  engine: QueryEngine;
  execution_mode?: QueryExecutionMode;
  table: string;
  select: string[];
  filters: Omit<FilterCondition, "id">[];
  sort: SortClause[];
  joins: Array<{
    table: string;
    join_type: JoinType;
    conditions: Array<{
      left_column: string;
      right_column: string;
    }>;
  }>;
  limit_rows: number;
  offset: number;
  mode: "LIST" | "REPORT";
  pivot?: PivotConfig;
  sql?: string;
  // legacy
  group_by: string[];
  aggregates: AggregateRule[];
}

export interface QueryPreview {
  sql: string;
  source_mode: QueryExecutionMode;
  can_sync_builder: boolean;
}

export interface PivotConfig {
  rows: string[];
  columns: string[];
  values: string;
  func: "SUM" | "COUNT" | "AVG" | "MIN" | "MAX";
}

export interface AggregateRule {
  column: string;
  func: "SUM" | "COUNT" | "AVG" | "MIN" | "MAX";
}

/** Tabular result set returned by POST /api/query. */
export interface QueryResult {
  /** Ordered list of column names in the result. */
  columns: string[];
  /** Row data as a list of value arrays. */
  rows: unknown[][];
  /** Total matching rows (before LIMIT/OFFSET). */
  total: number;
  /** True if the result was capped by the LIMIT. */
  truncated: boolean;
  /** SQL text that was executed. */
  executed_sql: string;
  /** Execution source mode. */
  source_mode: QueryExecutionMode;
  /** Optional execution status message. */
  message: string;
}
