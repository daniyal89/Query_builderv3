"""
deps.py — Shared FastAPI dependencies injected via Depends().

Provides request-scoped resources such as the active DuckDB connection
to endpoint handlers without coupling them to the service layer directly.
"""

from fastapi import HTTPException, status

from backend.services.duckdb_service import DuckDBService

# Module-level singleton — lives for the entire process lifetime.
# This is appropriate because we maintain a single DuckDB connection
# at a time (user connects to one database file).
_db_service = DuckDBService()


def get_db_service() -> DuckDBService:
    """Return the global DuckDBService singleton.

    Unlike get_connected_db(), this does NOT enforce that a connection
    is active. Use this when the endpoint itself manages the connection
    (e.g., the /connect endpoint).
    """
    return _db_service


def get_connected_db() -> DuckDBService:
    """Return the DuckDBService singleton, raising 503 if not connected.

    Use this dependency on endpoints that require an active database
    connection (e.g., /tables, /query, /upload-csv).

    Raises:
        HTTPException 503: If no database is currently connected.
    """
    if not _db_service.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No database connected. Use POST /api/duckdb/connect first.",
        )
    return _db_service
