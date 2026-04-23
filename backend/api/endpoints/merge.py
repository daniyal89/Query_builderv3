from collections import Counter
import io
import json
from typing import List
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.api.deps import get_connected_db
from backend.models.merge import (
    ConflictResolutionMap,
    DetectedColumn,
    EnrichmentResponse,
    FolderMergeRequest,
    FolderMergeResponse,
    MergeSheetsResponse,
    UploadSheetsResponse,
)
from backend.services.duckdb_service import DuckDBService
from backend.services.merge_service import MergeService

router = APIRouter()


@router.post(
    "/upload-sheets",
    response_model=UploadSheetsResponse,
    summary="Upload multiple files/sheets and detect columns",
)
async def upload_sheets(
    files: List[UploadFile] = File(
        ..., description="One or more Excel (.xlsx) or CSV files to merge."
    ),
    db: DuckDBService = Depends(get_connected_db),
) -> UploadSheetsResponse:
    del db

    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    file_ids: list[str] = []
    all_columns: list[DetectedColumn] = []
    col_name_counter: Counter = Counter()

    for uploaded_file in files:
        file_id = str(uuid.uuid4())[:8]
        file_ids.append(file_id)
        filename = uploaded_file.filename or "unknown"
        contents = await uploaded_file.read()

        try:
            if filename.lower().endswith(".csv"):
                sheets = {"Sheet1": pd.read_csv(io.BytesIO(contents), nrows=100)}
            elif filename.lower().endswith((".xls", ".xlsx")):
                workbook = pd.ExcelFile(io.BytesIO(contents))
                sheets = {
                    name: pd.read_excel(workbook, sheet_name=name, nrows=100)
                    for name in workbook.sheet_names
                }
            else:
                raise ValueError(f"Unsupported file type: {filename}")
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Error reading {filename}: {exc}",
            ) from exc

        for sheet_name, dataframe in sheets.items():
            for column in dataframe.columns:
                column_name = str(column)
                col_name_counter[column_name] += 1
                samples = dataframe[column].dropna().astype(str).head(5).tolist()
                all_columns.append(
                    DetectedColumn(
                        name=column_name,
                        source_file=filename,
                        source_sheet=sheet_name,
                        sample_values=samples,
                    )
                )

    conflicts = [name for name, count in col_name_counter.items() if count > 1]

    return UploadSheetsResponse(
        file_ids=file_ids,
        detected_columns=all_columns,
        conflicts=conflicts,
    )


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
    del payload
    del db
    # TODO: Load uploaded files by file_ids, apply resolutions,
    # concatenate into a single DataFrame, store as temp table,
    # and return merge_id plus preview.
    raise HTTPException(status_code=501, detail="Merge sheets flow is not implemented yet.")


@router.post(
    "/merge-folder",
    response_model=FolderMergeResponse,
    summary="Merge all supported files from a local folder and save the result",
)
def merge_folder(payload: FolderMergeRequest) -> FolderMergeResponse:
    try:
        result = MergeService.merge_folder(
            source_folder=payload.source_folder,
            output_path=payload.output_path,
            include_subfolders=payload.include_subfolders,
        )
        return FolderMergeResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {exc}") from exc


@router.post(
    "/enrich-data",
    summary="Join uploaded data against the Master Table and produce downloadable Excel file",
    description=(
        "Performs a LEFT JOIN of the uploaded dataframe against the specified "
        "Master Table using the composite key. Appends the requested fetch_columns "
        "and produces a downloadable Excel file with stats in the response headers."
    ),
)
async def enrich_data(
    file: UploadFile = File(..., description="The merged Excel or CSV file to enrich"),
    db_path: str = Form(..., description="Absolute path to the DuckDB file"),
    master_table: str = Form(..., description="DuckDB table to use as the enrichment source"),
    fetch_columns: str = Form(
        ..., description="JSON encoded array of column names to fetch from the Master Table"
    ),
    composite_key: str = Form(..., description="Secondary key strategy (e.g. DISCOM or DIV_CODE)"),
    mapped_acct_id_col: str = Form(..., description="Uploaded column mapped to ACCT_ID"),
    mapped_secondary_col: str = Form(..., description="Uploaded column mapped to secondary key"),
    db: DuckDBService = Depends(get_connected_db),
) -> StreamingResponse:
    del db_path
    try:
        try:
            columns_to_fetch = json.loads(fetch_columns)
        except json.JSONDecodeError as exc:
            raise ValueError("fetch_columns must be a valid JSON array") from exc

        filename = (file.filename or "").lower()
        contents = await file.read()

        if filename.endswith(".csv"):
            dataframe = pd.read_csv(io.BytesIO(contents))
        elif filename.endswith((".xls", ".xlsx")):
            dataframe = pd.read_excel(io.BytesIO(contents))
        else:
            raise ValueError("Unsupported file format. Please upload CSV or Excel.")

        result_df, stats = MergeService.process_enrichment(
            merged_df=dataframe,
            conn=db._conn,
            master_table=master_table,
            fetch_columns=columns_to_fetch,
            mapped_acct_id_col=mapped_acct_id_col,
            mapped_secondary_col=mapped_secondary_col,
            secondary_key_type=composite_key,
        )

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            result_df.to_excel(writer, index=False)
        output.seek(0)

        headers = {
            "Content-Disposition": 'attachment; filename="enriched_data.xlsx"',
            "X-Matched-Rows": str(stats.get("matched_rows", 0)),
            "X-Unmatched-Rows": str(stats.get("unmatched_rows", 0)),
            "X-Total-Rows": str(stats.get("total_rows", 0)),
            "Access-Control-Expose-Headers": (
                "X-Matched-Rows, X-Unmatched-Rows, X-Total-Rows, Content-Disposition"
            ),
        }

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {exc}") from exc
