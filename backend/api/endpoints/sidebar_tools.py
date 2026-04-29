"""Sidebar-6 tooling endpoints."""

from __future__ import annotations

import re
import glob
import threading
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

import duckdb
from fastapi import APIRouter, HTTPException, status
from backend.services.error_log_service import ErrorLogService

from backend.models.sidebar_tools import (
    BuildDuckDbJobResponse,
    BuildDuckDbJobStartResponse,
    BuildDuckDbRequest,
    CsvToParquetJobResponse,
    CsvToParquetJobStartResponse,
    CsvToParquetRequest,
    SidebarToolResponse,
)

router = APIRouter()
VALID_OBJECT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CSV_PARQUET_JOBS: dict[str, dict[str, Any]] = {}
CSV_PARQUET_CANCEL_EVENTS: dict[str, threading.Event] = {}
CSV_PARQUET_JOBS_LOCK = threading.Lock()
BUILD_DUCKDB_JOBS: dict[str, dict[str, Any]] = {}
BUILD_DUCKDB_CANCEL_EVENTS: dict[str, threading.Event] = {}
BUILD_DUCKDB_JOBS_LOCK = threading.Lock()
MIN_PARQUET_FILE_BYTES = 16


def _previous_month_label(month_label: str) -> str | None:
    cleaned = (month_label or "").strip().upper()
    if not cleaned:
        return None
    try:
        parsed = datetime.strptime(cleaned, "%b_%Y")
    except ValueError:
        return None
    prev_month_last_day = parsed.replace(day=1) - timedelta(days=1)
    return prev_month_last_day.strftime("%b_%Y").upper()


def _archive_existing_master_if_needed(
    conn: duckdb.DuckDBPyConnection,
    object_name: str,
    object_type: str,
    month_label: str | None,
) -> None:
    if object_name.strip().lower() != "master" or object_type.upper() != "TABLE":
        return

    prev_label = _previous_month_label(month_label or "")
    if not prev_label:
        return

    existing = conn.execute(
        "SELECT table_type FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND lower(table_name) = 'master' LIMIT 1"
    ).fetchone()
    if not existing or existing[0] != "BASE TABLE":
        return

    archive_name = f"master_{prev_label}"
    _drop_existing_duckdb_object(conn, archive_name)
    conn.execute(f"ALTER TABLE \"master\" RENAME TO \"{archive_name}\"")




def _month_code_mmyy(month_label: str) -> str | None:
    cleaned = (month_label or "").strip().upper()
    if not cleaned:
        return None
    for fmt in ("%b_%Y", "%m%y"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.strftime("%m%y")
        except ValueError:
            continue
    return None


def _normalize_master_object_name(object_name: str, object_type: str, month_label: str | None) -> str:
    cleaned = (object_name or "").strip()
    if object_type.upper() not in {"TABLE", "VIEW"}:
        return cleaned

    lowered = cleaned.lower()
    if not (lowered == "master" or lowered.startswith("master_")):
        return cleaned

    month_code = _month_code_mmyy(month_label or "")
    if not month_code:
        raise ValueError("month_label is required for master table/view names and must be like MAR_2026 or 0326.")

    return f"Master_{month_code}"
def _sql_string_literal(value: str) -> str:
    return f"'{value.replace(chr(39), chr(39) * 2)}'"


def _is_readable_input_file(path_str: str) -> bool:
    path = Path(path_str)
    if not path.is_file():
        return False
    if path.suffix.lower() != ".parquet":
        return True
    if path.name.lower().startswith("tmp_"):
        return False
    try:
        return path.stat().st_size >= MIN_PARQUET_FILE_BYTES
    except OSError:
        return False


def _resolve_relation_sql(input_path: str) -> str:
    lowered = input_path.lower()
    input_path_sql = _sql_string_literal(input_path)

    if ".parquet" in lowered:
        return f"read_parquet({input_path_sql}, union_by_name = true)"
    if ".csv" in lowered or ".tsv" in lowered or lowered.endswith(".gz") or ".gz" in lowered:
        return f"read_csv_auto({input_path_sql}, union_by_name = true, filename = true)"

    matches = [item for item in glob.glob(input_path, recursive=True) if _is_readable_input_file(item)]
    if matches:
        sample = matches[0].lower()
        if sample.endswith(".parquet"):
            return f"read_parquet({input_path_sql}, union_by_name = true)"
        if (
            sample.endswith(".csv")
            or sample.endswith(".csv.gz")
            or sample.endswith(".tsv")
            or sample.endswith(".gz")
        ):
            return f"read_csv_auto({input_path_sql}, union_by_name = true, filename = true)"

    raise ValueError(f"No readable files matched '{input_path}'.")


def _resolve_csv_parquet_read_sql(input_path: str) -> str:
    input_path_sql = _sql_string_literal(input_path)
    return (
        f"read_csv({input_path_sql}, union_by_name = true, filename = true, auto_detect = true, "
        "all_varchar = true, sample_size = -1)"
    )


def _resolve_existing_input_glob(input_path: str) -> str:
    cleaned = input_path.replace("\u00A0", " ").strip().strip('"').strip("'")
    normalized_path = cleaned.replace("\\", "/")
    normalized_as_path = Path(normalized_path).expanduser()

    if normalized_as_path.is_file():
        return str(normalized_as_path)

    if normalized_as_path.is_dir():
        for candidate in ("**/*.parquet", "**/*.csv.gz", "**/*.gz", "**/*.csv", "**/*.tsv", "**/*.txt"):
            pattern = str((normalized_as_path / candidate).as_posix())
            if any(_is_readable_input_file(item) for item in glob.glob(pattern, recursive=True)):
                return pattern

    matches = [item for item in glob.glob(normalized_path, recursive=True) if _is_readable_input_file(item)]
    if matches:
        return normalized_path

    if "/*." in normalized_path:
        recursive_variant = normalized_path.replace("/*.", "/**/*.")
        recursive_matches = [item for item in glob.glob(recursive_variant, recursive=True) if _is_readable_input_file(item)]
        if recursive_matches:
            return recursive_variant

    if "/*" in normalized_path and "**" not in normalized_path:
        recursive_any_variant = normalized_path.replace("/*", "/**/*")
        recursive_any_matches = [
            item for item in glob.glob(recursive_any_variant, recursive=True) if _is_readable_input_file(item)
        ]
        if recursive_any_matches:
            return recursive_any_variant

    if ".csv.gz" in normalized_path.lower():
        fallbacks = [
            re.sub(r"\.csv\.gz", ".gz", normalized_path, flags=re.IGNORECASE),
            re.sub(r"\.csv\.gz", ".csv", normalized_path, flags=re.IGNORECASE),
        ]
        for fallback in fallbacks:
            fallback_matches = glob.glob(fallback, recursive=True)
            if any(_is_readable_input_file(item) for item in fallback_matches):
                return fallback
            if "/*." in fallback:
                recursive_fallback = fallback.replace("/*.", "/**/*.")
                recursive_fallback_matches = [
                    item for item in glob.glob(recursive_fallback, recursive=True) if _is_readable_input_file(item)
                ]
                if recursive_fallback_matches:
                    return recursive_fallback

    raise ValueError(f"No files found that match the pattern '{cleaned}'.")


def _list_matching_input_files(pattern: str) -> list[Path]:
    files = [Path(item).expanduser().resolve() for item in glob.glob(pattern, recursive=True)]
    return [item for item in files if item.is_file()]


def _infer_input_root(pattern: str, files: list[Path]) -> Path:
    wildcard_index = min(
        [index for index in (pattern.find("*"), pattern.find("?"), pattern.find("[")) if index != -1],
        default=-1,
    )
    if wildcard_index != -1:
        prefix = pattern[:wildcard_index]
        root = Path(prefix).expanduser()
        while root.name and any(char in root.name for char in ["*", "?", "["]):
            root = root.parent
        if root.exists():
            return root.resolve()

    if files:
        return files[0].parent
    return Path(pattern).expanduser().resolve().parent


def _parquet_target_for_input(output_root: Path, input_root: Path, source_file: Path) -> Path:
    try:
        relative = source_file.relative_to(input_root)
    except ValueError:
        relative = source_file.name
    target = output_root / relative
    if target.suffix.lower() == ".gz":
        target = target.with_suffix("")
    return target.with_suffix(".parquet")


def _build_csv_to_parquet_targets(payload: CsvToParquetRequest) -> tuple[list[Path], Path, Path, Path | None]:
    resolved_input = _resolve_existing_input_glob(payload.input_path)
    output_path = Path(payload.output_path).expanduser().resolve()
    matched_files = _list_matching_input_files(resolved_input)
    if not matched_files:
        raise ValueError(f"No readable files matched '{resolved_input}'.")

    if len(matched_files) == 1 and output_path.suffix.lower() == ".parquet":
        return matched_files, output_path.parent, matched_files[0].parent, output_path

    output_root = output_path if output_path.suffix.lower() != ".parquet" else output_path.parent
    input_root = _infer_input_root(resolved_input, matched_files)
    return matched_files, output_root, input_root, None


def _update_csv_job(job_id: str, **updates: Any) -> None:
    with CSV_PARQUET_JOBS_LOCK:
        if job_id not in CSV_PARQUET_JOBS:
            return
        CSV_PARQUET_JOBS[job_id].update(updates)


def _update_build_job(job_id: str, **updates: Any) -> None:
    with BUILD_DUCKDB_JOBS_LOCK:
        if job_id not in BUILD_DUCKDB_JOBS:
            return
        BUILD_DUCKDB_JOBS[job_id].update(updates)


def _drop_existing_duckdb_object(conn: duckdb.DuckDBPyConnection, object_name: str) -> None:
    existing = conn.execute(
        "SELECT table_type FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND lower(table_name) = lower(?) LIMIT 1",
        [object_name.strip()],
    ).fetchone()
    if not existing:
        return

    object_sql = f'"{object_name.replace(chr(34), chr(34) * 2)}"'
    if existing[0] == "VIEW":
        conn.execute(f"DROP VIEW {object_sql}")
    else:
        conn.execute(f"DROP TABLE {object_sql}")


def _execute_build_duckdb(payload: BuildDuckDbRequest) -> tuple[str, str]:
    normalized_object_name = _normalize_master_object_name(payload.object_name, payload.object_type, payload.month_label)
    if not VALID_OBJECT_NAME.fullmatch(normalized_object_name):
        raise ValueError("object_name must start with letter/_ and use only letters, numbers, underscore.")

    db_path = Path(payload.db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    object_sql = f'"{normalized_object_name.replace(chr(34), chr(34) * 2)}"'
    resolved_input = _resolve_existing_input_glob(payload.input_path)
    relation_sql = _resolve_relation_sql(resolved_input)

    with duckdb.connect(str(db_path)) as conn:
        if payload.replace:
            _drop_existing_duckdb_object(conn, normalized_object_name)
        conn.execute(f"CREATE {payload.object_type} {object_sql} AS SELECT * FROM {relation_sql}")

    month_text = f" for {payload.month_label}" if payload.month_label else ""
    return str(db_path), f"Created {payload.object_type} {normalized_object_name}{month_text}."


def _run_build_duckdb_job(job_id: str, payload: BuildDuckDbRequest) -> None:
    try:
        if BUILD_DUCKDB_CANCEL_EVENTS[job_id].is_set():
            _update_build_job(
                job_id,
                status="cancelled",
                message="Build cancelled before execution.",
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            return

        _update_build_job(job_id, status="running", progress_percent=25, message="Preparing build...")
        output_path, message = _execute_build_duckdb(payload)
        if BUILD_DUCKDB_CANCEL_EVENTS[job_id].is_set():
            _update_build_job(
                job_id,
                status="cancelled",
                message="Stop requested. Build finished but marked cancelled.",
                output_path=output_path,
                progress_percent=100,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            return
        _update_build_job(
            job_id,
            status="completed",
            message=message,
            output_path=output_path,
            progress_percent=100,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
    except Exception as exc:
        ErrorLogService.append(
            {
                "endpoint": "/api/sidebar-tools/build-duckdb/start",
                "method": "POST",
                "status_code": 500,
                "error": str(exc),
                "exception_type": type(exc).__name__,
                "job_id": job_id,
                "payload": payload.model_dump(),
                "stage": "background_worker",
            }
        )
        _update_build_job(
            job_id,
            status="failed",
            message=str(exc),
            progress_percent=100,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )


def _run_csv_to_parquet_job(job_id: str, payload: CsvToParquetRequest) -> None:
    try:
        files, output_root, input_root, single_target = _build_csv_to_parquet_targets(payload)
        output_root.mkdir(parents=True, exist_ok=True)
        compression_sql = _sql_string_literal(payload.compression)
        reported_output_path = str(single_target if single_target is not None else output_root)
        _update_csv_job(job_id, status="running", total_files=len(files), output_path=reported_output_path, skipped_files=0)
        skipped_files = 0

        with duckdb.connect() as conn:
            for index, source_file in enumerate(files, start=1):
                if CSV_PARQUET_CANCEL_EVENTS[job_id].is_set():
                    _update_csv_job(
                        job_id,
                        status="cancelled",
                        message="CSV→Parquet conversion stopped by user.",
                        finished_at=datetime.now().isoformat(timespec="seconds"),
                    )
                    return

                target_file = single_target if single_target is not None else _parquet_target_for_input(output_root, input_root, source_file)
                target_file.parent.mkdir(parents=True, exist_ok=True)
                if target_file.exists():
                    skipped_files += 1
                    _update_csv_job(
                        job_id,
                        processed_files=index,
                        skipped_files=skipped_files,
                        current_file=str(source_file),
                        message=f"Skipping existing parquet file ({index}/{len(files)}).",
                    )
                    continue
                relation_sql = _resolve_csv_parquet_read_sql(str(source_file))
                target_sql = _sql_string_literal(str(target_file))
                _update_csv_job(
                    job_id,
                    processed_files=index - 1,
                    skipped_files=skipped_files,
                    current_file=str(source_file),
                    message=f"Processing file {index}/{len(files)}...",
                )
                conn.execute(
                    f"COPY (SELECT * FROM {relation_sql}) "
                    f"TO {target_sql} (FORMAT PARQUET, COMPRESSION {compression_sql})"
                )
                _update_csv_job(job_id, processed_files=index, skipped_files=skipped_files)

        _update_csv_job(
            job_id,
            status="completed",
            current_file=None,
            message=(
                f"Parquet conversion completed successfully for {len(files)} file(s). "
                f"Skipped existing: {skipped_files}."
            ),
            finished_at=datetime.now().isoformat(timespec="seconds"),
            skipped_files=skipped_files,
        )
    except Exception as exc:
        ErrorLogService.append(
            {
                "endpoint": "/api/sidebar-tools/csv-to-parquet/start",
                "method": "POST",
                "status_code": 500,
                "error": str(exc),
                "exception_type": type(exc).__name__,
                "job_id": job_id,
                "payload": payload.model_dump(),
                "stage": "background_worker",
            }
        )
        _update_csv_job(
            job_id,
            status="failed",
            message=str(exc),
            current_file=None,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )


@router.post("/sidebar-tools/build-duckdb", response_model=SidebarToolResponse)
async def build_duckdb(payload: BuildDuckDbRequest) -> SidebarToolResponse:
    try:
        output_path, message = _execute_build_duckdb(payload)
        return SidebarToolResponse(message=message, output_path=output_path)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sidebar-tools/build-duckdb/start", response_model=BuildDuckDbJobStartResponse)
async def build_duckdb_start(payload: BuildDuckDbRequest) -> BuildDuckDbJobStartResponse:
    job_id = uuid.uuid4().hex
    with BUILD_DUCKDB_JOBS_LOCK:
        BUILD_DUCKDB_CANCEL_EVENTS[job_id] = threading.Event()
        BUILD_DUCKDB_JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "message": "Build job queued.",
            "output_path": None,
            "progress_percent": 0,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        }

    threading.Thread(target=_run_build_duckdb_job, args=(job_id, payload), daemon=True).start()
    return BuildDuckDbJobStartResponse(job_id=job_id, status="queued", message="Build DuckDB job started.")


@router.get("/sidebar-tools/build-duckdb/status/{job_id}", response_model=BuildDuckDbJobResponse)
async def build_duckdb_status(job_id: str) -> BuildDuckDbJobResponse:
    with BUILD_DUCKDB_JOBS_LOCK:
        job = BUILD_DUCKDB_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build DuckDB job not found.")
        return BuildDuckDbJobResponse(**job)


@router.post("/sidebar-tools/build-duckdb/stop/{job_id}", response_model=BuildDuckDbJobResponse)
async def build_duckdb_stop(job_id: str) -> BuildDuckDbJobResponse:
    with BUILD_DUCKDB_JOBS_LOCK:
        job = BUILD_DUCKDB_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build DuckDB job not found.")
        if job["status"] in {"completed", "failed", "cancelled"}:
            return BuildDuckDbJobResponse(**job)
        BUILD_DUCKDB_CANCEL_EVENTS[job_id].set()
        job["status"] = "cancelling"
        job["message"] = "Stop requested. Waiting for operation to finish..."
        return BuildDuckDbJobResponse(**job)


@router.post("/sidebar-tools/csv-to-parquet", response_model=SidebarToolResponse)
async def csv_to_parquet(payload: CsvToParquetRequest) -> SidebarToolResponse:
    try:
        resolved_input = _resolve_existing_input_glob(payload.input_path)
        output_path = Path(payload.output_path).expanduser().resolve()
        matched_files = _list_matching_input_files(resolved_input)
        if not matched_files:
            raise ValueError(f"No readable files matched '{resolved_input}'.")

        compression_sql = _sql_string_literal(payload.compression)

        # Single-file mode keeps backward compatibility when output is an explicit parquet file.
        if len(matched_files) == 1 and output_path.suffix.lower() == ".parquet":
            if output_path.exists():
                return SidebarToolResponse(
                    message="Skipped conversion because output parquet already exists.",
                    output_path=str(output_path),
                )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path_sql = _sql_string_literal(str(output_path))
            relation_sql = _resolve_csv_parquet_read_sql(str(matched_files[0]))
            with duckdb.connect() as conn:
                conn.execute(
                    f"COPY (SELECT * FROM {relation_sql}) "
                    f"TO {output_path_sql} (FORMAT PARQUET, COMPRESSION {compression_sql})"
                )
            return SidebarToolResponse(
                message="Parquet conversion completed successfully.",
                output_path=str(output_path),
            )

        # Multi-file mode writes parquet files preserving input relative folder structure.
        output_root = output_path if output_path.suffix.lower() != ".parquet" else output_path.parent
        output_root.mkdir(parents=True, exist_ok=True)
        input_root = _infer_input_root(resolved_input, matched_files)

        converted_count = 0
        skipped_count = 0
        with duckdb.connect() as conn:
            for source_file in matched_files:
                target_file = _parquet_target_for_input(output_root, input_root, source_file)
                target_file.parent.mkdir(parents=True, exist_ok=True)
                if target_file.exists():
                    skipped_count += 1
                    continue
                relation_sql = _resolve_csv_parquet_read_sql(str(source_file))
                target_sql = _sql_string_literal(str(target_file))
                conn.execute(
                    f"COPY (SELECT * FROM {relation_sql}) "
                    f"TO {target_sql} (FORMAT PARQUET, COMPRESSION {compression_sql})"
                )
                converted_count += 1

        return SidebarToolResponse(
            message=f"Parquet conversion completed successfully for {converted_count} file(s). Skipped existing: {skipped_count}.",
            output_path=str(output_root),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sidebar-tools/csv-to-parquet/start", response_model=CsvToParquetJobStartResponse)
async def csv_to_parquet_start(payload: CsvToParquetRequest) -> CsvToParquetJobStartResponse:
    try:
        files, output_root, _, single_target = _build_csv_to_parquet_targets(payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    with CSV_PARQUET_JOBS_LOCK:
        CSV_PARQUET_CANCEL_EVENTS[job_id] = threading.Event()
        CSV_PARQUET_JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "message": "CSV→Parquet conversion queued.",
            "processed_files": 0,
            "total_files": len(files),
            "skipped_files": 0,
            "current_file": None,
            "output_path": str(single_target if single_target is not None else output_root),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        }

    threading.Thread(target=_run_csv_to_parquet_job, args=(job_id, payload), daemon=True).start()
    return CsvToParquetJobStartResponse(job_id=job_id, status="queued", message="CSV→Parquet job started.")


@router.get("/sidebar-tools/csv-to-parquet/status/{job_id}", response_model=CsvToParquetJobResponse)
async def csv_to_parquet_status(job_id: str) -> CsvToParquetJobResponse:
    with CSV_PARQUET_JOBS_LOCK:
        job = CSV_PARQUET_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSV→Parquet job not found.")
        return CsvToParquetJobResponse(**job)


@router.post("/sidebar-tools/csv-to-parquet/stop/{job_id}", response_model=CsvToParquetJobResponse)
async def csv_to_parquet_stop(job_id: str) -> CsvToParquetJobResponse:
    with CSV_PARQUET_JOBS_LOCK:
        job = CSV_PARQUET_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSV→Parquet job not found.")
        if job["status"] in {"completed", "failed", "cancelled"}:
            return CsvToParquetJobResponse(**job)
        CSV_PARQUET_CANCEL_EVENTS[job_id].set()
        job["status"] = "cancelling"
        job["message"] = "Stop requested. Waiting for current file to finish..."
        return CsvToParquetJobResponse(**job)
