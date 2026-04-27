"""Local DuckDB object creation endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import get_connected_db
from backend.models.local_object import (
    FileObjectRequest,
    FileObjectResponse,
    FilePreviewRequest,
    FilePreviewResponse,
)
from backend.services.duckdb_service import DuckDBService

router = APIRouter()


@router.post(
    "/duckdb/file-object",
    response_model=FileObjectResponse,
    summary="Create a local DuckDB table or view from a CSV/TSV/XLSX file",
)
async def create_file_object(
    payload: FileObjectRequest,
    db: DuckDBService = Depends(get_connected_db),
) -> FileObjectResponse:
    try:
        metadata = db.create_object_from_file(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return FileObjectResponse(
        status="created",
        message=f"{payload.object_type.title()} '{metadata.table_name}' is ready in Local DuckDB.",
        object_name=metadata.table_name,
        object_type=payload.object_type,
        table=metadata,
    )


@router.post(
    "/duckdb/file-object/preview",
    response_model=FilePreviewResponse,
    summary="Preview top rows from a CSV/TSV/XLSX file before creating object",
)
async def preview_file_object_source(
    payload: FilePreviewRequest,
    db: DuckDBService = Depends(get_connected_db),
) -> FilePreviewResponse:
    try:
        return db.preview_file_source(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
