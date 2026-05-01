"""
importer.py — CSV upload and import endpoints.

POST /api/upload-csv
    Accepts a CSV file upload with a column mapping payload, parses the file,
    applies the mapping, and bulk-inserts into the specified DuckDB table.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from typing import List

from backend.api.deps import get_connected_db
from backend.models.importer import CSVMappingPayload, ImportResult
from backend.services.duckdb_service import DuckDBService
from backend.services.csv_import_service import CSVImportService
from backend.utils.upload_limits import read_upload_bytes

router = APIRouter()
MAX_PARSE_CSV_BYTES = 100 * 1024 * 1024

class ParseResult(BaseModel):
    file_id: str
    headers: List[str]
    preview: List[List[str]]

@router.post("/parse-csv", response_model=ParseResult)
async def parse_csv(
    file: UploadFile = File(..., description="The CSV file to parse.")
):
    try:
        filename = file.filename or "upload.csv"
        if not filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only .csv files are supported.")

        contents = await read_upload_bytes(file, max_bytes=MAX_PARSE_CSV_BYTES, label="CSV upload")
        file_id = CSVImportService.save_temp_file(contents, filename)
        headers = CSVImportService.parse_headers(file_id)
        preview = CSVImportService.preview_rows(file_id)
        return ParseResult(file_id=file_id, headers=headers, preview=preview)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/import-csv", response_model=ImportResult)
async def import_csv(
    payload: CSVMappingPayload,
    db: DuckDBService = Depends(get_connected_db)
):
    try:
        conn = db.get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Database not connected.")
        
    result = CSVImportService.import_csv(
        file_id=payload.file_id,
        target_table=payload.target_table,
        column_map=payload.column_map,
        db_conn=conn,
        create_if_missing=payload.create_table_if_missing
    )
    
    if result.errors:
        raise HTTPException(status_code=400, detail=" ".join(result.errors))
        
    return result
