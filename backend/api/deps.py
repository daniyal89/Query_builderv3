"""
deps.py â€” Shared FastAPI dependencies injected via Depends().
"""

from fastapi import HTTPException, status

from backend.services import duckdb_handoff
from backend.services.duckdb_service import DuckDBService
from backend.services.oracle_service import OracleService

_duckdb_service = DuckDBService()
_oracle_service = OracleService()


def get_db_service() -> DuckDBService:
    return _duckdb_service


def get_connected_db() -> DuckDBService:
    if not _duckdb_service.is_connected:
        # A build holds the file exclusively and disconnects us for its duration.
        # Saying "no database connected" there reads as a crash; 409 says "retry".
        if duckdb_handoff.is_handed_off():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "A DuckDB build is running and holds the database exclusively. "
                    "This endpoint is available again as soon as the build finishes."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No database connected. Use POST /api/duckdb/connect first.",
        )
    return _duckdb_service


def get_oracle_service() -> OracleService:
    return _oracle_service


def get_connected_oracle() -> OracleService:
    if not _oracle_service.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No Marcadose database connected. Use POST /api/oracle/connect first.",
        )
    return _oracle_service
