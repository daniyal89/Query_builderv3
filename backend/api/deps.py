"""
deps.py â€” Shared FastAPI dependencies injected via Depends().
"""

from fastapi import HTTPException, status

from backend.services.bi_phase1_service import BIPhase1Service
from backend.services.duckdb_service import DuckDBService
from backend.services.oracle_service import OracleService

_duckdb_service = DuckDBService()
_bi_phase1_service = BIPhase1Service(_duckdb_service)
_oracle_service = OracleService()


def get_db_service() -> DuckDBService:
    return _duckdb_service


def get_bi_phase1_service() -> BIPhase1Service:
    return _bi_phase1_service


def get_connected_db() -> DuckDBService:
    if not _duckdb_service.is_connected:
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
