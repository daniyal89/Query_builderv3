"""Sidebar-6 tooling endpoints."""

from __future__ import annotations

import re
import glob
from pathlib import Path

import duckdb
from fastapi import APIRouter, HTTPException, status

from backend.models.sidebar_tools import BuildDuckDbRequest, CsvToParquetRequest, SidebarToolResponse

router = APIRouter()
VALID_OBJECT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sql_string_literal(value: str) -> str:
    return f"'{value.replace(chr(39), chr(39) * 2)}'"


def _resolve_relation_sql(input_path: str) -> str:
    lowered = input_path.lower()
    input_path_sql = _sql_string_literal(input_path)

    if ".parquet" in lowered:
        return f"read_parquet({input_path_sql})"
    if ".csv" in lowered or ".tsv" in lowered or lowered.endswith(".gz") or ".gz" in lowered:
        return f"read_csv_auto({input_path_sql}, union_by_name = true, filename = true)"

    matches = glob.glob(input_path, recursive=True)
    if matches:
        sample = matches[0].lower()
        if sample.endswith(".parquet"):
            return f"read_parquet({input_path_sql})"
        if (
            sample.endswith(".csv")
            or sample.endswith(".csv.gz")
            or sample.endswith(".tsv")
            or sample.endswith(".gz")
        ):
            return f"read_csv_auto({input_path_sql}, union_by_name = true, filename = true)"

    return f"read_csv_auto({input_path_sql}, union_by_name = true, filename = true)"


def _resolve_existing_input_glob(input_path: str) -> str:
    cleaned = input_path.strip().strip('"').strip("'")
    normalized_path = cleaned.replace("\\", "/")
    normalized_as_path = Path(normalized_path).expanduser()

    if normalized_as_path.is_file():
        return str(normalized_as_path)

    if normalized_as_path.is_dir():
        for candidate in ("*.csv.gz", "*.gz", "*.csv", "*.tsv", "*.txt"):
            pattern = str((normalized_as_path / candidate).as_posix())
            if glob.glob(pattern, recursive=True):
                return pattern

    matches = glob.glob(normalized_path, recursive=True)
    if matches:
        return normalized_path

    if ".csv.gz" in normalized_path.lower():
        fallbacks = [
            re.sub(r"\.csv\.gz", ".gz", normalized_path, flags=re.IGNORECASE),
            re.sub(r"\.csv\.gz", ".csv", normalized_path, flags=re.IGNORECASE),
        ]
        for fallback in fallbacks:
            fallback_matches = glob.glob(fallback, recursive=True)
            if fallback_matches:
                return fallback

    raise ValueError(f"No files found that match the pattern '{cleaned}'.")


@router.post("/sidebar-tools/build-duckdb", response_model=SidebarToolResponse)
async def build_duckdb(payload: BuildDuckDbRequest) -> SidebarToolResponse:
    try:
        if not VALID_OBJECT_NAME.fullmatch(payload.object_name):
            raise ValueError("object_name must start with letter/_ and use only letters, numbers, underscore.")

        db_path = Path(payload.db_path).expanduser().resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        object_sql = f'"{payload.object_name.replace(chr(34), chr(34) * 2)}"'
        resolved_input = _resolve_existing_input_glob(payload.input_path)
        relation_sql = _resolve_relation_sql(resolved_input)
        with duckdb.connect(str(db_path)) as conn:
            if payload.replace:
                conn.execute(f"DROP VIEW IF EXISTS {object_sql}")
                conn.execute(f"DROP TABLE IF EXISTS {object_sql}")

            conn.execute(f"CREATE {payload.object_type} {object_sql} AS SELECT * FROM {relation_sql}")

        month_text = f" for {payload.month_label}" if payload.month_label else ""
        return SidebarToolResponse(
            message=f"Created {payload.object_type} {payload.object_name}{month_text}.",
            output_path=str(db_path),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sidebar-tools/csv-to-parquet", response_model=SidebarToolResponse)
async def csv_to_parquet(payload: CsvToParquetRequest) -> SidebarToolResponse:
    try:
        resolved_input = _resolve_existing_input_glob(payload.input_path)
        output_path = Path(payload.output_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        input_path_sql = _sql_string_literal(resolved_input)
        output_path_sql = _sql_string_literal(str(output_path))
        compression_sql = _sql_string_literal(payload.compression)
        with duckdb.connect() as conn:
            conn.execute(
                f"COPY (SELECT * FROM read_csv_auto({input_path_sql}, union_by_name = true, filename = true)) "
                f"TO {output_path_sql} (FORMAT PARQUET, COMPRESSION {compression_sql})"
            )
        return SidebarToolResponse(
            message="Parquet conversion completed successfully.",
            output_path=str(output_path),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
