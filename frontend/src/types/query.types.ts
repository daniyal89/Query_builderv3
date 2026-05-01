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

export interface MarcadoseUnionConfig {
  enabled: boolean;
  month_tag: string;
  discoms: string[];
  base_discom: string;
  add_grand_total: boolean;
  schema_name: string;
}

export interface QueryColumnOption {
  key: string;
  label: string;
  tableName: string;
  sourceTableName: string;
  referenceName: string;
  columnName: string;
  dtype: string;
  nullable: boolean;
}

/** A single WHERE-clause filter condition. */
export interface FilterCondition {
  id: string;
  column: string;
  operator: FilterOperator;
  value: string;
}

export interface CaseWhenBranch {
  id: string;
  column: string;
  operator: FilterOperator;
  value: string;
  thenType: "literal" | "column";
  thenValue: string;
}

export interface CaseExpression {
  id: string;
  alias: string;
  aggregateFunc?: SqlFunction;
  branches: CaseWhenBranch[];
  elseType: "literal" | "column";
  elseValue: string;
}

export type SqlFunction =
  | "SUM"
  | "COUNT"
  | "AVG"
  | "MIN"
  | "MAX"
  | "COUNT_DISTINCT"
  | "COALESCE";

export interface FunctionColumn {
  id: string;
  func: SqlFunction;
  column: string;
  /** Second column for COALESCE(col1, col2). */
  secondColumn?: string;
  alias: string;
}

/** A single ORDER BY sort directive. */
export interface SortClause {
  column: string;
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
  alias: string;
  joinType: JoinType;
  conditions: JoinCondition[];
}

export interface QueryState {
  table: string;
  selectedColumns: string[];
  filters: FilterCondition[];
  sort: SortClause[];
  joins: JoinClause[];
  groupBy: string[];
  aggregates: AggregateRule[];
  caseExpressions: CaseExpression[];
  functionColumns: FunctionColumn[];
  limitRows: number;
  offset: number;
  mode: "LIST" | "REPORT";
  pivotConfig: PivotConfig;
  marcadoseUnion: MarcadoseUnionConfig;
  isLoading: boolean;
  error: string | null;
  sourceMode: QuerySourceMode;
  generatedSql: string;
  sqlText: string;
  isSqlDetached: boolean;
  isPreviewLoading: boolean;
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
    alias?: string;
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
  marcadose_union?: MarcadoseUnionConfig;
  group_by: string[];
  aggregates: AggregateRule[];
  case_expressions?: {
    alias: string;
    aggregate_func?: SqlFunction;
    else_type: "literal" | "column";
    else_value: string;
    branches: {
      column: string;
      operator: FilterOperator;
      value: string;
      then_type: "literal" | "column";
      then_value: string;
    }[];
  }[];
  function_columns?: {
    func: SqlFunction;
    column: string;
    second_column?: string;
    alias: string;
  }[];
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
  columns: string[];
  rows: unknown[][];
  total: number;
  truncated: boolean;
  executed_sql: string;
  source_mode: QueryExecutionMode;
  message: string;
}
