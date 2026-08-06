"""
schema.py — DuckDB schema introspection endpoints.

GET  /api/tables                   → List all tables with estimated row counts.
GET  /api/tables/{name}/columns    → List columns and types for a specific table.
GET  /api/tables/{name}/row-count  → Exact COUNT(*) for one table.

These are ``def``, not ``async def``, on purpose: every handler calls blocking
DuckDB code, so declaring them async would run that work on the event loop and
freeze the whole app (static files and job polling included) for its duration.
Starlette runs plain ``def`` handlers in a threadpool instead.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import get_connected_db
from backend.models.schema import TableMetadata, ColumnDetail, TableRowCount
from backend.services.duckdb_service import DuckDBService, SourceUnavailableError

router = APIRouter()


@router.get(
    "/tables",
    response_model=list[TableMetadata],
    summary="List all tables in the connected database",
)
def list_tables(
    db: DuckDBService = Depends(get_connected_db),
) -> list[TableMetadata]:
    """Return metadata for every user table in the active DuckDB connection.

    ``row_count`` is the catalog's estimate — exact for bulk-loaded tables, and
    stale after a DELETE. Use ``/tables/{name}/row-count`` when it must be exact.

    Returns:
        Ordered list of TableMetadata objects.
    """
    return db.list_tables()


@router.get(
    "/tables/{table_name}/columns",
    response_model=list[ColumnDetail],
    summary="Get column details for a specific table",
)
def get_table_columns(
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


@router.get(
    "/tables/{table_name}/row-count",
    response_model=TableRowCount,
    summary="Get the exact row count for a specific table",
)
def get_table_row_count(
    table_name: str,
    db: DuckDBService = Depends(get_connected_db),
) -> TableRowCount:
    """Return an exact ``COUNT(*)`` for one table.

    This is a full scan, which is why it is not part of ``GET /tables``.

    Raises:
        HTTPException 404: If the table does not exist.
    """
    try:
        return TableRowCount(table_name=table_name, row_count=db.count_rows(table_name))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SourceUnavailableError as exc:
        # 424, not 500: the object exists and its definition is fine — the files it
        # reads are not reachable. The client can act on that; a 500 discards it.
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail=(
                f"'{table_name}' reads its rows from parquet files that could not be "
                f"opened. {exc}"
            ),
        ) from exc
