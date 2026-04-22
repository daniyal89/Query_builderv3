"""
connection.py — DuckDB connection management endpoint.

POST /api/duckdb/connect
    Validates the supplied filesystem path, opens a DuckDB connection,
    and returns the connection status with a table count.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import get_db_service
from backend.models.connection import ConnectionRequest, ConnectionResponse
from backend.services.duckdb_service import DuckDBService

router = APIRouter()


@router.post(
    "/duckdb/connect",
    response_model=ConnectionResponse,
    summary="Connect to a local DuckDB file",
    description=(
        "Accepts an absolute path to a .duckdb file, validates it exists, "
        "opens a connection, and returns the number of discovered tables."
    ),
)
async def connect_to_duckdb(
    payload: ConnectionRequest,
    db: DuckDBService = Depends(get_db_service),
) -> ConnectionResponse:
    """Establish a connection to the specified DuckDB database file.

    Args:
        payload: ConnectionRequest containing the db_path.
        db: Injected DuckDBService singleton.

    Returns:
        ConnectionResponse with status, resolved path, tables_count, and message.
    """
    try:
        tables_count = db.connect(payload.db_path)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return ConnectionResponse(
        status="connected",
        db_path=payload.db_path,
        tables_count=tables_count,
        message=f"Successfully connected. Found {tables_count} table(s).",
    )
