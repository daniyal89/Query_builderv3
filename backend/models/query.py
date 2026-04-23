"""
query.py â€” Pydantic schemas for the visual query builder.

Defines the structured query payload sent from the frontend and the
tabular result set returned by the backend after SQL execution.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from backend.models.connection import EngineName


FilterOperator = Literal[
    "=",
    "!=",
    ">",
    "<",
    ">=",
    "<=",
    "LIKE",
    "NOT LIKE",
    "IN",
    "NOT IN",
    "IS NULL",
    "IS NOT NULL",
    "BETWEEN",
    "NOT BETWEEN",
    "CONTAINS",
    "NOT CONTAINS",
    "STARTS WITH",
    "ENDS WITH",
]

QueryExecutionMode = Literal["builder", "sql"]
JoinType = Literal["INNER", "LEFT", "RIGHT"]


class FilterCondition(BaseModel):
    """A single WHERE-clause predicate."""

    column: str = Field(..., description="Column name to filter on.")
    operator: FilterOperator = Field(..., description="SQL comparison operator.")
    value: Any = Field(
        default=None,
        description="Comparison value; ignored for IS NULL / IS NOT NULL.",
    )


class SortClause(BaseModel):
    """A single ORDER BY directive."""

    column: str = Field(..., description="Column name to sort by.")
    direction: Literal["ASC", "DESC"] = Field(default="ASC", description="Sort direction.")


class JoinCondition(BaseModel):
    """A single equality predicate within a JOIN clause."""

    left_column: str = Field(..., description="Qualified column on the left side of the join.")
    right_column: str = Field(..., description="Qualified column on the joined table side.")

    @model_validator(mode="after")
    def validate_columns(self) -> "JoinCondition":
        if not self.left_column.strip() or not self.right_column.strip():
            raise ValueError("Each join condition needs both a left column and a joined-table column.")
        return self


class JoinClause(BaseModel):
    """A JOIN clause attached to the query builder payload."""

    table: str = Field(..., description="Target table or view to join.")
    join_type: JoinType = Field(default="INNER", description="Supported join type.")
    conditions: list[JoinCondition] = Field(default_factory=list, description="Equality predicates combined with AND.")

    @model_validator(mode="after")
    def validate_join(self) -> "JoinClause":
        if not self.table.strip():
            raise ValueError("Each join needs a target table.")
        if not self.conditions:
            raise ValueError("Each join needs at least one matching column pair.")
        return self


class AggregateRule(BaseModel):
    """Legacy aggregation function applied to a column."""

    column: str = Field(..., description="Column name to aggregate.")
    func: Literal["SUM", "COUNT", "AVG", "MIN", "MAX"] = Field(..., description="SQL aggregate function.")


class PivotConfig(BaseModel):
    """Configuration for an Excel-style pivot table report."""

    rows: list[str] = Field(default_factory=list, description="Fields to group vertically.")
    columns: list[str] = Field(default_factory=list, description="Fields to pivot horizontally.")
    values: str = Field(..., description="Field to aggregate.")
    func: Literal["SUM", "COUNT", "AVG", "MIN", "MAX"] = Field(..., description="Function for aggregation.")


class QueryPayload(BaseModel):
    """Structured query definition sent from the frontend query builder."""

    execution_mode: QueryExecutionMode = Field(
        default="builder",
        description="Whether to execute builder-generated SQL or raw SQL text.",
    )
    engine: EngineName = Field(default="duckdb", description="Target execution engine.")
    table: str = Field(default="", description="Target table name.")
    select: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Columns to include in the SELECT clause; ['*'] for all.",
    )
    filters: list[FilterCondition] = Field(
        default_factory=list,
        description="List of WHERE-clause conditions (ANDed together).",
    )
    sort: list[SortClause] = Field(default_factory=list, description="List of ORDER BY clauses.")
    joins: list[JoinClause] = Field(default_factory=list, description="Ordered joins applied to the base table.")
    limit_rows: int = Field(default=1000, description="Maximum rows to return. 0 means unlimited.", ge=0)
    offset: int = Field(default=0, description="Number of rows to skip for pagination.", ge=0)
    mode: Literal["LIST", "REPORT"] = Field(default="LIST", description="Operation mode of the query builder.")
    pivot: PivotConfig | None = Field(default=None, description="Pivot configuration used if mode is REPORT.")
    group_by: list[str] = Field(default_factory=list, description="Columns to GROUP BY.")
    aggregates: list[AggregateRule] = Field(default_factory=list, description="List of aggregations to apply.")
    sql: str | None = Field(default=None, description="Raw SQL text for direct SQL execution.")

    @model_validator(mode="after")
    def validate_execution_mode(self) -> "QueryPayload":
        if self.execution_mode == "builder" and not self.table.strip():
            raise ValueError("table is required when execution_mode='builder'.")
        if self.execution_mode == "sql" and not (self.sql or "").strip():
            raise ValueError("sql is required when execution_mode='sql'.")
        if self.execution_mode == "builder":
            seen_tables = {self.table.strip()}
            for join in self.joins:
                if join.table in seen_tables:
                    raise ValueError("Each joined table can only be used once in the visual builder.")
                seen_tables.add(join.table)
        return self


class QueryPreview(BaseModel):
    """SQL preview returned for the active query workflow."""

    sql: str = Field(..., description="Engine-specific SQL text shown in the editor.")
    source_mode: QueryExecutionMode = Field(..., description="Preview source mode.")
    can_sync_builder: bool = Field(
        default=True,
        description="Whether the editor can still auto-sync from the visual builder.",
    )


class QueryResult(BaseModel):
    """Tabular result set returned after query execution."""

    columns: list[str] = Field(..., description="Ordered list of column names in the result.")
    rows: list[list[Any]] = Field(default_factory=list, description="Row data as a list of value arrays.")
    total: int = Field(..., description="Total matching rows (before LIMIT/OFFSET).", ge=0)
    truncated: bool = Field(default=False, description="True if the result was capped by the LIMIT.")
    executed_sql: str = Field(default="", description="SQL text that was executed.")
    source_mode: QueryExecutionMode = Field(default="builder", description="Execution source mode.")
    message: str = Field(default="", description="Optional execution status message.")
