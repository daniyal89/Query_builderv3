"""
query.py — Pydantic schemas for the visual query builder.

Defines the structured query payload sent from the frontend and the
tabular result set returned by the backend after SQL execution.
"""

from __future__ import annotations

from typing import Any, Literal
import re

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
JOIN_ALIAS_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


class CaseWhenBranch(BaseModel):
    """A single WHEN ... THEN ... condition within a CASE expression."""

    column: str = Field(..., description="Column name to check.")
    operator: FilterOperator = Field(..., description="SQL comparison operator.")
    value: Any = Field(default="", description="Comparison value.")
    then_type: Literal["literal", "column"] = Field(default="literal", description="Type of the THEN value.")
    then_value: str = Field(..., description="Value or column to return if condition is met.")


class CaseExpression(BaseModel):
    """A computed column defined by a CASE WHEN ... ELSE ... END expression."""

    alias: str = Field(..., description="Name for the new computed column.")
    aggregate_func: Literal["SUM", "COUNT", "AVG", "MIN", "MAX"] | None = Field(
        default=None, description="Optional aggregate function to wrap the CASE statement."
    )
    branches: list[CaseWhenBranch] = Field(default_factory=list, description="WHEN conditions.")
    else_type: Literal["literal", "column"] = Field(default="literal", description="Type of the ELSE value.")
    else_value: str = Field(default="", description="Default value if no conditions are met.")


class FunctionColumn(BaseModel):
    """A standalone column with a SQL function applied."""

    func: Literal["SUM", "COUNT", "AVG", "MIN", "MAX", "COUNT_DISTINCT", "COALESCE"] = Field(
        ..., description="The SQL function to apply."
    )
    column: str = Field(..., description="The main column to apply the function to.")
    second_column: str | None = Field(default=None, description="Optional second column (used by COALESCE).")
    alias: str = Field(..., description="Alias for the computed function column.")


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
    alias: str | None = Field(
        default=None,
        description="Optional reference name used to distinguish repeated joins against the same table.",
    )
    join_type: JoinType = Field(default="INNER", description="Supported join type.")
    conditions: list[JoinCondition] = Field(default_factory=list, description="Equality predicates combined with AND.")

    def reference_name(self) -> str:
        return (self.alias or self.table).strip()

    @model_validator(mode="after")
    def validate_join(self) -> "JoinClause":
        if not self.table.strip():
            raise ValueError("Each join needs a target table.")
        if self.alias is not None:
            self.alias = self.alias.strip() or None
            if self.alias and not JOIN_ALIAS_PATTERN.fullmatch(self.alias):
                raise ValueError(
                    "Join alias must start with a letter or underscore and contain only letters, numbers, and underscores."
                )
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


class MarcadoseUnionConfig(BaseModel):
    """Monthly Marcadose master-table replacement and UNION ALL configuration."""

    enabled: bool = Field(default=True, description="Whether to expand the query across selected DISCOM tables.")
    month_tag: str = Field(default="", description="Monthly tag used in CM_master_data_<month>_<discom>.")
    discoms: list[str] = Field(default_factory=list, description="Selected DISCOM codes.")
    base_discom: str = Field(default="DVVNL", description="Single/base DISCOM used when union mode is off.")
    add_grand_total: bool = Field(default=True, description="Append a grand total row for Generate Report outputs.")
    schema_name: str = Field(default="MERCADOS", description="Oracle schema that owns monthly master tables.")

    @model_validator(mode="after")
    def validate_union_config(self) -> "MarcadoseUnionConfig":
        allowed = {"DVVNL", "PVVNL", "PUVNL", "MVVNL", "KESCO"}

        self.month_tag = self.month_tag.strip().lower()
        if self.month_tag and not re.fullmatch(r"[a-z]{3}_\d{4}", self.month_tag):
            raise ValueError("Marcadose month must use format like mar_2026.")

        self.schema_name = (self.schema_name or "MERCADOS").strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.schema_name):
            raise ValueError("Invalid Marcadose schema name.")

        normalized_discoms = []
        for discom in self.discoms:
            normalized = discom.strip().upper()
            if normalized not in allowed:
                raise ValueError(f"Unsupported DISCOM '{discom}'.")
            if normalized not in normalized_discoms:
                normalized_discoms.append(normalized)

        self.base_discom = (self.base_discom or "").strip().upper()
        if self.base_discom and self.base_discom not in allowed:
            raise ValueError(f"Unsupported base DISCOM '{self.base_discom}'.")

        if not normalized_discoms and self.base_discom:
            normalized_discoms = [self.base_discom]
        if normalized_discoms and self.base_discom not in normalized_discoms:
            self.base_discom = normalized_discoms[0]
        if not self.base_discom and normalized_discoms:
            self.base_discom = normalized_discoms[0]

        self.discoms = normalized_discoms
        return self


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
    limit_rows: int = Field(
        default=1000,
        description="Maximum rows to return. 0 means unlimited.",
        ge=0,
        le=50000,
    )
    offset: int = Field(default=0, description="Number of rows to skip for pagination.", ge=0)
    mode: Literal["LIST", "REPORT"] = Field(default="LIST", description="Operation mode of the query builder.")
    pivot: PivotConfig | None = Field(default=None, description="Pivot configuration used if mode is REPORT.")
    group_by: list[str] = Field(default_factory=list, description="Columns to GROUP BY.")
    aggregates: list[AggregateRule] = Field(default_factory=list, description="List of aggregations to apply.")
    case_expressions: list[CaseExpression] = Field(default_factory=list, description="Computed columns.")
    function_columns: list[FunctionColumn] = Field(default_factory=list, description="Stand-alone function columns.")
    sql: str | None = Field(default=None, description="Raw SQL text for direct SQL execution.")
    marcadose_union: MarcadoseUnionConfig | None = Field(
        default=None,
        description="Optional Marcadose monthly master table and UNION ALL controls.",
    )

    @model_validator(mode="after")
    def validate_execution_mode(self) -> "QueryPayload":
        if self.execution_mode == "builder" and not self.table.strip():
            raise ValueError("table is required when execution_mode='builder'.")
        if self.execution_mode == "sql" and not (self.sql or "").strip():
            raise ValueError("sql is required when execution_mode='sql'.")
        if self.execution_mode == "builder":
            seen_tables = {self.table.strip()}
            for join in self.joins:
                join_reference = join.reference_name()
                if join_reference in seen_tables:
                    raise ValueError("Each joined table alias/reference must be unique in the visual builder.")
                seen_tables.add(join_reference)
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
