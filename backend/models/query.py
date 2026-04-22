"""
query.py — Pydantic schemas for the visual query builder.

Defines the structured query payload sent from the frontend and the
tabular result set returned by the backend after SQL execution.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class FilterCondition(BaseModel):
    """A single WHERE-clause predicate."""

    column: str = Field(..., description="Column name to filter on.")
    operator: Literal["=", "!=", ">", "<", ">=", "<=", "LIKE", "IN", "IS NULL", "IS NOT NULL"] = Field(
        ..., description="SQL comparison operator."
    )
    value: Any = Field(
        default=None,
        description="Comparison value; ignored for IS NULL / IS NOT NULL.",
    )


class SortClause(BaseModel):
    """A single ORDER BY directive."""

    column: str = Field(..., description="Column name to sort by.")
    direction: Literal["ASC", "DESC"] = Field(default="ASC", description="Sort direction.")


class QueryPayload(BaseModel):
    """Structured query definition sent from the frontend query builder."""

    table: str = Field(..., description="Target table name.")
    select: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Columns to include in the SELECT clause; ['*'] for all.",
    )
    filters: list[FilterCondition] = Field(
        default_factory=list,
        description="List of WHERE-clause conditions (ANDed together).",
    )
    limit_rows: int = Field(default=1000, description="Maximum rows to return. 0 means unlimited.", ge=0)
    offset: int = Field(default=0, description="Number of rows to skip for pagination.", ge=0)
    
    # Query Mode
    mode: Literal["LIST", "REPORT"] = Field(default="LIST", description="Operation mode of the query builder.")
    pivot: PivotConfig | None = Field(default=None, description="Pivot configuration used if mode is REPORT.")
    
    # Legacy fields
    group_by: list[str] = Field(default_factory=list, description="Columns to GROUP BY.")
    aggregates: list[AggregateRule] = Field(default_factory=list, description="List of aggregations to apply.")


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

class QueryResult(BaseModel):
    """Tabular result set returned after query execution."""

    columns: list[str] = Field(..., description="Ordered list of column names in the result.")
    rows: list[list[Any]] = Field(default_factory=list, description="Row data as a list of value arrays.")
    total: int = Field(..., description="Total matching rows (before LIMIT/OFFSET).", ge=0)
    truncated: bool = Field(default=False, description="True if the result was capped by the LIMIT.")
