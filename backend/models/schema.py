"""
schema.py — Pydantic schemas for DuckDB schema introspection.

Defines the structural models returned by the schema inspection endpoints:
GET /api/tables and GET /api/tables/{name}/columns.
"""

from typing import Any

from pydantic import BaseModel, Field


class ColumnDetail(BaseModel):
    """Descriptor for a single column within a DuckDB table."""

    name: str = Field(..., description="Column name as defined in the schema.")
    dtype: str = Field(..., description="DuckDB data type string (e.g., 'VARCHAR', 'INTEGER', 'TIMESTAMP').")
    nullable: bool = Field(default=True, description="Whether the column accepts NULL values.")


class TableMetadata(BaseModel):
    """Summary metadata for a single DuckDB table."""

    table_name: str = Field(..., description="Fully qualified table name.")
    columns: list[ColumnDetail] = Field(
        default_factory=list,
        description="Ordered list of column descriptors.",
    )
    row_count: int = Field(
        ...,
        description=(
            "Catalog row estimate. Exact for bulk-loaded tables, 0 for views (counting "
            "one means running it). Use /tables/{name}/row-count when it must be exact."
        ),
        ge=0,
    )
    object_type: str = Field(
        default="TABLE",
        description=(
            "TABLE or VIEW. A VIEW reads parquet where it lies, so it reports 0 rows "
            "here and its source folder has to stay put."
        ),
    )


class TableRowCount(BaseModel):
    """Exact row count for one object.

    Separate from :class:`TableMetadata` because getting it costs a full scan,
    while the ``row_count`` there is the catalog's free estimate.
    """

    table_name: str = Field(..., description="Object the count refers to.")
    row_count: int = Field(..., description="Exact COUNT(*) at the time of the call.", ge=0)


class MasterTable(BaseModel):
    """Generic representation of a data record from any DuckDB table.

    Designed to be a flexible, schema-agnostic model that can hold
    a single row of data from any table, with column names as keys
    and their corresponding values. Used for data preview, query results,
    and CSV import staging.
    """

    source_table: str = Field(..., description="Name of the originating DuckDB table.")
    row_index: int = Field(..., description="Zero-based position of this row in the result set.", ge=0)
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Column-name → value mapping for this row.",
    )
