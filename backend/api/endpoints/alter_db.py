"""
alter_db.py - Endpoints for altering local DuckDB databases.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, status
from pathlib import Path
import duckdb
import pandas as pd

from backend.models.alter_db import (
    AlterDbDerivedRequest,
    AlterDbJoinRequest,
    AlterDbDropRequest,
    AlterDbJobStatusResponse,
)
from backend.services.job_runtime import (
    BackgroundJobCancelled,
    BackgroundJobPolicy,
    job_runtime,
)
from backend.utils.logger import app_logger
from backend.utils.path_safety import sanitize_local_path_input

router = APIRouter()

ALTER_DB_JOB_TYPE = "alter_db.job"
ALTER_DB_POLICY = BackgroundJobPolicy(max_attempts=1, retry_backoff_seconds=1)

def _update_job(job_id: str, **updates) -> None:
    job_runtime.update_job(job_id, **updates)

def _qi(name: str) -> str:
    """Quote a SQL identifier (table/column name) to handle spaces and reserved words."""
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _run_alter_db_job(job_id: str, request: AlterDbDerivedRequest | AlterDbJoinRequest | AlterDbDropRequest) -> None:
    _update_job(job_id, progress_percent=0, message="Initializing database connection...")
    
    try:
        job_runtime.raise_if_cancelled(job_id)
        sanitized_db = sanitize_local_path_input(request.db_path, "db_path")
        if not Path(sanitized_db).exists():
            raise FileNotFoundError(f"Database not found: {sanitized_db}")

        _update_job(job_id, progress_percent=10, message="Connecting to DuckDB...")
        
        with duckdb.connect(database=sanitized_db, read_only=False) as conn:
            job_runtime.raise_if_cancelled(job_id)

            # A month stored as a view is not alterable, and DuckDB's own message
            # ("Can only modify view with ALTER VIEW statement") tells an operator
            # nothing about what to do instead. Refuse before touching anything.
            existing = conn.execute(
                "SELECT table_type FROM information_schema.tables "
                "WHERE table_schema = 'main' AND lower(table_name) = lower(?) LIMIT 1",
                [request.table_name.strip()],
            ).fetchone()
            if existing and existing[0] == "VIEW":
                raise ValueError(
                    f"'{request.table_name}' is a view over parquet files, not a table, so "
                    "its columns cannot be altered. Materialise that month first (Data "
                    "Tools -> Materialise), or add the column as a derived expression in "
                    "the query builder instead."
                )

            tbl = _qi(request.table_name)

            if isinstance(request, AlterDbDropRequest):
                col = _qi(request.column_name)
                _update_job(job_id, progress_percent=50, message=f"Dropping column {request.column_name}...")
                conn.execute(f"ALTER TABLE {tbl} DROP COLUMN {col}")
                _update_job(job_id, progress_percent=90, message="Column dropped.")
            else:
                col = _qi(request.new_column_name)
                # Step 1: Add the column
                _update_job(job_id, progress_percent=20, message=f"Adding column {request.new_column_name}...")
                try:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {request.column_type}")
                except duckdb.CatalogException as e:
                    if "already exists" not in str(e).lower():
                        raise
                    _update_job(job_id, progress_percent=20, message=f"Column {request.new_column_name} already exists. Proceeding to update...")

                job_runtime.raise_if_cancelled(job_id)

                # Step 2: Update the column
                if isinstance(request, AlterDbDerivedRequest):
                    _update_job(job_id, progress_percent=50, message="Executing SQL formula update...")
                    update_sql = f"UPDATE {tbl} SET {col} = {request.sql_formula}"
                    conn.execute(update_sql)
                    
                elif isinstance(request, AlterDbJoinRequest):
                    _update_job(job_id, progress_percent=40, message="Loading external file...")
                    sanitized_file = sanitize_local_path_input(request.file_path, "file_path")
                    if not Path(sanitized_file).exists():
                        raise FileNotFoundError(f"Join file not found: {sanitized_file}")
                    
                    if Path(sanitized_file).suffix.lower() == ".csv":
                        df = pd.read_csv(sanitized_file, dtype=str, encoding_errors="replace", low_memory=False, on_bad_lines="skip")
                    else:
                        df = pd.read_excel(sanitized_file, dtype=str)
                        
                    job_runtime.raise_if_cancelled(job_id)
                    _update_job(job_id, progress_percent=60, message="Registering file in memory...")
                    conn.register("incoming_data", df)
                    
                    master_key = _qi(request.join_master_col)
                    file_key = _qi(request.join_file_col)
                    value_col = _qi(request.value_file_col)
                    
                    _update_job(job_id, progress_percent=70, message="Executing JOIN update...")
                    update_sql = f"""
                        UPDATE {tbl}
                        SET {col} = incoming_data.{value_col}
                        FROM incoming_data
                        WHERE {tbl}.{master_key} = incoming_data.{file_key}
                    """
                    conn.execute(update_sql)
                
        if job_runtime.is_cancelled(job_id):
            _update_job(job_id, status="cancelled", message="Stop requested. Finished but marked cancelled.", progress_percent=100, finished_at=datetime.now().isoformat(timespec="seconds"))
            return

        _update_job(job_id, status="completed", message="Successfully altered table.", progress_percent=100, finished_at=datetime.now().isoformat(timespec="seconds"))
        
    except BackgroundJobCancelled:
        _update_job(job_id, status="cancelled", message="Job cancelled.", finished_at=datetime.now().isoformat(timespec="seconds"))
    except Exception as exc:
        _update_job(job_id, status="failed", message=str(exc), finished_at=datetime.now().isoformat(timespec="seconds"))


def _start_job(request: AlterDbDerivedRequest | AlterDbJoinRequest | AlterDbDropRequest, message: str) -> AlterDbJobStatusResponse:
    job_id = uuid.uuid4().hex
    job_runtime.start_job(
        job_type=ALTER_DB_JOB_TYPE,
        job_id=job_id,
        initial_snapshot={
            "job_id": job_id,
            "status": "queued",
            "message": message,
            "progress_percent": 0,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        },
        payload=request.model_dump(mode="json"),
        policy=ALTER_DB_POLICY,
        worker=lambda running_job_id: _run_alter_db_job(running_job_id, request),
    )
    return AlterDbJobStatusResponse(
        job_id=job_id,
        status="queued",
        message=message,
        progress_percent=0
    )


@router.post("/alter-db/join/start", response_model=AlterDbJobStatusResponse)
def start_alter_db_join(request: AlterDbJoinRequest):
    return _start_job(request, "Alter table join job started.")

@router.post("/alter-db/derived/start", response_model=AlterDbJobStatusResponse)
def start_alter_db_derived(request: AlterDbDerivedRequest):
    return _start_job(request, "Alter table derived job started.")

@router.post("/alter-db/drop/start", response_model=AlterDbJobStatusResponse)
def start_alter_db_drop(request: AlterDbDropRequest):
    return _start_job(request, "Alter table drop job started.")

@router.get("/alter-db/status/{job_id}", response_model=AlterDbJobStatusResponse)
def get_alter_db_status(job_id: str):
    job = job_runtime.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return AlterDbJobStatusResponse(**job)

@router.post("/alter-db/stop/{job_id}", response_model=AlterDbJobStatusResponse)
def stop_alter_db_job(job_id: str):
    job = job_runtime.stop_job(job_id, "Stop requested. Cancelling job...")
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return AlterDbJobStatusResponse(**job)


@router.get("/alter-db/metadata/tables")
def get_alter_db_tables(db_path: str) -> list[str]:
    sanitized_db = sanitize_local_path_input(db_path, "db_path")
    if not Path(sanitized_db).exists():
        return []
        
    try:
        from backend.api.deps import get_db_service
        svc = get_db_service()
        
        # If already connected to this DB, reuse connection
        if svc.is_connected and svc._db_path and Path(svc._db_path).resolve() == Path(sanitized_db).resolve():
            tables = svc._conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' AND table_type = 'BASE TABLE' "
                "ORDER BY table_name"
            ).fetchall()
            return [t[0] for t in tables]
            
        # Otherwise open read-only
        with duckdb.connect(database=sanitized_db, read_only=True) as conn:
            tables = conn.execute(
                # BASE TABLE only: a view cannot be ALTERed, so offering one here
                # just leads to a failed job several clicks later.
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' AND table_type = 'BASE TABLE' "
                "ORDER BY table_name"
            ).fetchall()
            return [t[0] for t in tables]
    except Exception as e:
        app_logger.warning(f"Failed to list tables for alter-db metadata: {e}")
        return []

@router.get("/alter-db/metadata/columns")
def get_alter_db_columns(db_path: str, table_name: str) -> list[str]:
    sanitized_db = sanitize_local_path_input(db_path, "db_path")
    if not Path(sanitized_db).exists() or not table_name:
        return []
        
    try:
        from backend.api.deps import get_db_service
        svc = get_db_service()
        
        # If already connected to this DB, reuse connection
        if svc.is_connected and svc._db_path and Path(svc._db_path).resolve() == Path(sanitized_db).resolve():
            columns = svc._conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'main' AND table_name = ?", [table_name]).fetchall()
            return [c[0] for c in columns]
            
        with duckdb.connect(database=sanitized_db, read_only=True) as conn:
            columns = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'main' AND table_name = ?", [table_name]).fetchall()
            return [c[0] for c in columns]
    except Exception as e:
        app_logger.warning(f"Failed to list columns for alter-db metadata: {e}")
        return []

@router.get("/alter-db/metadata/file-columns")
def get_alter_db_file_columns(file_path: str) -> list[str]:
    sanitized_file = sanitize_local_path_input(file_path, "file_path")
    path_obj = Path(sanitized_file)
    if not path_obj.exists() or not path_obj.is_file():
        return []
    
    try:
        if path_obj.suffix.lower() == ".csv":
            import pandas as pd
            df = pd.read_csv(sanitized_file, nrows=0)
            return list(df.columns)
        elif path_obj.suffix.lower() in [".xlsx", ".xls"]:
            import pandas as pd
            df = pd.read_excel(sanitized_file, nrows=0)
            return list(df.columns)
        return []
    except Exception as e:
        app_logger.warning(f"Failed to read file columns for alter-db metadata: {e}")
        return []
