"""
schema.py — DuckDB schema introspection endpoints.

GET  /api/tables                   → List all tables with row counts.
GET  /api/tables/{name}/columns    → List columns and types for a specific table.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import get_connected_db
from backend.models.schema import TableMetadata, ColumnDetail
from backend.services.duckdb_service import DuckDBService

router = APIRouter()


@router.get(
    "/tables",
    response_model=list[TableMetadata],
    summary="List all tables in the connected database",
)
async def list_tables(
    db: DuckDBService = Depends(get_connected_db),
) -> list[TableMetadata]:
    """Return metadata for every user table in the active DuckDB connection.

    Returns:
        Ordered list of TableMetadata objects.
    """
    return db.list_tables()


@router.get(
    "/tables/{table_name}/columns",
    response_model=list[ColumnDetail],
    summary="Get column details for a specific table",
)
async def get_table_columns(
    table_name: str,
    db: DuckDBService = Depends(get_connected_db),
) -> list[ColumnDetail]:
    """Return column names and data types for the specified table.

    Args:
        table_name: Name of the target table.

    Returns:
        Ordered list of ColumnDetail objects.

    Raises:
        HTTPException 404: If the table does not exist.
    """
    try:
        return db.get_columns(table_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
