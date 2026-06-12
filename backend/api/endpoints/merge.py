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
    DetectedColumn,
    EnrichmentResponse,
    FolderMergeRequest,
    FolderMergeResponse,
    UploadSheetsResponse,
)
from backend.services.duckdb_service import DuckDBService
from backend.services.merge_service import MergeService
from backend.utils.path_safety import sanitize_local_path_input
from backend.utils.upload_limits import enforce_total_upload_limit, read_upload_bytes

router = APIRouter()
MAX_UPLOAD_SHEETS_FILE_BYTES = 500 * 1024 * 1024
MAX_UPLOAD_SHEETS_TOTAL_BYTES = 1000 * 1024 * 1024
MAX_ENRICH_UPLOAD_BYTES = 500 * 1024 * 1024


@router.post(
    "/upload-sheets",
    response_model=UploadSheetsResponse,
    summary="Upload multiple files/sheets and detect columns",
)
async def upload_sheets(
    files: List[UploadFile] = File(
        ..., description="One or more Excel (.xlsx) or CSV files to merge."
    ),
) -> UploadSheetsResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    file_ids: list[str] = []
    all_columns: list[DetectedColumn] = []
    col_name_counter: Counter = Counter()
    total_upload_bytes = 0

    for uploaded_file in files:
        file_id = str(uuid.uuid4())[:8]
        file_ids.append(file_id)
        filename = uploaded_file.filename or "unknown"
        contents = await read_upload_bytes(
            uploaded_file,
            max_bytes=MAX_UPLOAD_SHEETS_FILE_BYTES,
            label=f"Uploaded file '{filename}'",
        )
        total_upload_bytes += len(contents)
        enforce_total_upload_limit(
            total_upload_bytes,
            MAX_UPLOAD_SHEETS_TOTAL_BYTES,
            "Combined upload size",
        )

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
    "/merge-folder",
    summary="Merge all supported files from a local folder (SSE progress stream)",
)
def merge_folder(payload: FolderMergeRequest) -> StreamingResponse:
    import queue
    import threading

    progress_queue: queue.Queue = queue.Queue()

    def _on_progress(*, stage: str, detail: str, current: int, total: int) -> None:
        progress_queue.put({"event": "progress", "stage": stage, "detail": detail, "current": current, "total": total})

    def _run_merge() -> None:
        try:
            result = MergeService.merge_folder(
                source_folder=payload.source_folder,
                output_path=payload.output_path,
                include_subfolders=payload.include_subfolders,
                on_progress=_on_progress,
            )
            progress_queue.put({"event": "result", "data": result})
        except ValueError as exc:
            progress_queue.put({"event": "error", "detail": str(exc)})
        except Exception as exc:
            progress_queue.put({"event": "error", "detail": f"Internal Server Error: {exc}"})

    def _event_generator():
        worker = threading.Thread(target=_run_merge, daemon=True)
        worker.start()

        while True:
            try:
                msg = progress_queue.get(timeout=120)
            except queue.Empty:
                # Send a keep-alive comment every 120s to prevent proxy timeouts
                yield ": keepalive\n\n"
                continue

            event_type = msg.get("event", "progress")
            payload_json = json.dumps(msg)
            yield f"event: {event_type}\ndata: {payload_json}\n\n"

            if event_type in ("result", "error"):
                break

        worker.join(timeout=5)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
    join_keys: str = Form(
        ..., description="JSON encoded array of join key mapping objects"
    ),
    output_format: str = Form(
        "xlsx", description="Output format: 'xlsx' or 'csv'"
    ),
    db: DuckDBService = Depends(get_connected_db),
) -> StreamingResponse:
    try:
        sanitize_local_path_input(db_path, "db_path")

        try:
            columns_to_fetch = json.loads(fetch_columns)
        except json.JSONDecodeError as exc:
            raise ValueError("fetch_columns must be a valid JSON array") from exc

        try:
            keys_to_join = json.loads(join_keys)
        except json.JSONDecodeError as exc:
            raise ValueError("join_keys must be a valid JSON array") from exc

        filename = (file.filename or "").lower()
        contents = await read_upload_bytes(file, max_bytes=MAX_ENRICH_UPLOAD_BYTES, label="Enrichment upload")

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
            join_keys=keys_to_join,
        )

        if result_df.empty and len(result_df.columns) == 0:
            raise ValueError("Enrichment produced no data. Check that your join keys match.")

        output = io.BytesIO()
        try:
            if output_format == "csv":
                result_df.to_csv(output, index=False, encoding="utf-8-sig")
                filename_ext = "csv"
                media_type = "text/csv"
            else:
                result_df.to_excel(
                    output, index=False, sheet_name="EnrichedData", engine="openpyxl"
                )
                filename_ext = "xlsx"
                media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except Exception as write_exc:
            raise ValueError(
                f"Failed to generate {output_format.upper()} output: {write_exc}"
            ) from write_exc
        output.seek(0)

        headers = {
            "Content-Disposition": f'attachment; filename="enriched_data.{filename_ext}"',
            "X-Matched-Rows": str(stats.get("matched_rows", 0)),
            "X-Unmatched-Rows": str(stats.get("unmatched_rows", 0)),
            "X-Total-Rows": str(stats.get("total_rows", 0)),
            "Access-Control-Expose-Headers": (
                "X-Matched-Rows, X-Unmatched-Rows, X-Total-Rows, Content-Disposition"
            ),
        }

        return StreamingResponse(
            output,
            media_type=media_type,
            headers=headers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {exc}") from exc
