"""
oracle.py â€” Marcadose Oracle connection and schema endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import get_connected_oracle, get_oracle_service
from backend.models.connection import OracleConnectionRequest, OracleConnectionResponse
from backend.models.schema import ColumnDetail, TableMetadata
from backend.services.oracle_service import OracleService

router = APIRouter()


@router.post(
    "/oracle/connect",
    response_model=OracleConnectionResponse,
    summary="Connect to the Marcadose Oracle database",
)
async def connect_to_oracle(
    payload: OracleConnectionRequest,
    oracle: OracleService = Depends(get_oracle_service),
) -> OracleConnectionResponse:
    try:
        tables_count = oracle.connect(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return OracleConnectionResponse(
        status="connected",
        tables_count=tables_count,
        message=f"Connected to Marcadose. Found {tables_count} table(s)/view(s).",
        schema_name=oracle.schema_name,
    )


@router.get(
    "/oracle/tables",
    response_model=list[TableMetadata],
    summary="List Oracle tables and views for the connected Marcadose schema",
)
async def list_oracle_tables(
    oracle: OracleService = Depends(get_connected_oracle),
) -> list[TableMetadata]:
    return oracle.list_tables()


@router.get(
    "/oracle/tables/{table_name}/columns",
    response_model=list[ColumnDetail],
    summary="Get Oracle column details for a specific Marcadose table or view",
)
async def get_oracle_table_columns(
    table_name: str,
    oracle: OracleService = Depends(get_connected_oracle),
) -> list[ColumnDetail]:
    try:
        return oracle.get_columns(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
