"""
merge.py — Multi-sheet merge and enrichment endpoints.

Implements the three-phase flow defined in HANDOVER.md §8:
  POST /api/upload-sheets   → Parse uploaded files, detect columns & conflicts.
  POST /api/merge-sheets    → Accept conflict resolution, produce merged dataset.
  POST /api/enrich-data     → Join merged data against Master Table, return file.
"""

from typing import List

from fastapi import APIRouter, Depends, File, UploadFile

from backend.api.deps import get_connected_db
from backend.models.merge import (
    ConflictResolutionMap,
    EnrichmentRequest,
    EnrichmentResponse,
    MergeSheetsResponse,
    UploadSheetsResponse,
)
from backend.services.duckdb_service import DuckDBService

router = APIRouter()


# ───────────────────── Phase 1: Upload Sheets ─────────────────────


@router.post(
    "/upload-sheets",
    response_model=UploadSheetsResponse,
    summary="Upload multiple files/sheets and detect columns",
    description=(
        "Accepts one or more Excel/CSV files via multipart upload. "
        "Parses each file and sheet, extracts column headers with sample "
        "values, and identifies columns that conflict across files."
    ),
)
async def upload_sheets(
    files: List[UploadFile] = File(
        ..., description="One or more Excel (.xlsx) or CSV files to merge."
    ),
    db: DuckDBService = Depends(get_connected_db),
) -> UploadSheetsResponse:
    """Parse uploaded files and return detected columns with conflicts.

    Args:
        files: List of uploaded files (multipart/form-data).
        db: Injected DuckDBService for Master Table schema lookup.

    Returns:
        UploadSheetsResponse with file_ids, detected_columns, and conflicts.

    Raises:
        HTTPException 400: If no files are provided or files are invalid.
        HTTPException 503: If no database is connected.
    """
    # TODO: Parse each file/sheet, extract headers + sample values,
    #       identify conflicting column names, return response
    pass


# ───────────────────── Phase 2: Merge Sheets ─────────────────────


@router.post(
    "/merge-sheets",
    response_model=MergeSheetsResponse,
    summary="Apply conflict resolution and merge uploaded sheets",
    description=(
        "Accepts the ConflictResolutionMap from the UI, applies column "
        "renaming/ignoring, concatenates the resolved sheets into a single "
        "dataset, and returns a preview with the merge_id for enrichment."
    ),
)
async def merge_sheets(
    payload: ConflictResolutionMap,
    db: DuckDBService = Depends(get_connected_db),
) -> MergeSheetsResponse:
    """Apply column conflict resolution and produce the merged dataset.

    The ConflictResolutionMap must include resolutions for ALL detected
    columns. The composite_key columns (e.g., Acc_id + DISCOM) must be
    mapped — they cannot be ignored.

    Args:
        payload: ConflictResolutionMap with per-column resolution directives.
        db: Injected DuckDBService.

    Returns:
        MergeSheetsResponse with merged_columns, row count, preview, and merge_id.

    Raises:
        HTTPException 400: If composite key columns are missing or ignored.
        HTTPException 404: If any file_id from the upload step is not found.
        HTTPException 503: If no database is connected.
    """
    # TODO: Load uploaded files by file_ids, apply resolutions,
    #       concatenate into single DataFrame, store as temp table,
    #       return merge_id + preview
    pass


# ───────────────────── Phase 3: Enrich Data ─────────────────────

from fastapi import Form
from fastapi.responses import StreamingResponse
import pandas as pd
import io
from backend.services.merge_service import MergeService

@router.post(
    "/enrich-data",
    summary="Join uploaded data against the Master Table and produce downloadable Excel file",
    description=(
        "Performs a LEFT JOIN of the uploaded dataframe against the specified "
        "Master Table using the composite key. Appends the requested fetch_column "
        "and produces a downloadable Excel file with stats in the response headers."
    ),
)
async def enrich_data(
    file: UploadFile = File(..., description="The merged Excel or CSV file to enrich"),
    db_path: str = Form(..., description="Absolute path to the DuckDB file"),
    fetch_column: str = Form(..., description="Column name to fetch from the Master Table"),
    composite_key: str = Form(..., description="Composite key strategy (e.g. Acc_id+DISCOM)"),
) -> StreamingResponse:
    """Join data against the Master Table and stream the output file.
    
    Accepts a direct file upload for now as Phase 2 merge saving is unimplemented.
    Headers 'X-Matched-Rows' and 'X-Unmatched-Rows' are injected into the response.
    """
    try:
        # 1. Read file into Pandas DataFrame
        filename = file.filename.lower()
        contents = await file.read()
        
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        elif filename.endswith((".xls", ".xlsx")):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise ValueError("Unsupported file format. Please upload CSV or Excel.")

        # 2. Process enrichment logic
        result_df, stats = MergeService.process_enrichment(
            merged_df=df,
            db_path=db_path,
            fetch_column=fetch_column
        )

        # 3. Convert enriched DataFrame to an Excel byte stream
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            result_df.to_excel(writer, index=False)
        output.seek(0)
        
        headers = {
            "Content-Disposition": 'attachment; filename="enriched_data.xlsx"',
            "X-Matched-Rows": str(stats.get("matched_rows", 0)),
            "X-Unmatched-Rows": str(stats.get("unmatched_rows", 0)),
            "X-Total-Rows": str(stats.get("total_rows", 0)),
            # Expose headers so the frontend Axios client can read them
            "Access-Control-Expose-Headers": "X-Matched-Rows, X-Unmatched-Rows, X-Total-Rows, Content-Disposition"
        }

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )
        
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
