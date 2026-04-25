"""Sidebar-6 tooling endpoints."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
from fastapi import APIRouter, HTTPException, status

from backend.models.sidebar_tools import BuildDuckDbRequest, CsvToParquetRequest, SidebarToolResponse

router = APIRouter()
VALID_OBJECT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sql_string_literal(value: str) -> str:
    return f"'{value.replace(chr(39), chr(39) * 2)}'"


@router.post("/sidebar-tools/build-duckdb", response_model=SidebarToolResponse)
async def build_duckdb(payload: BuildDuckDbRequest) -> SidebarToolResponse:
    try:
        if not VALID_OBJECT_NAME.fullmatch(payload.object_name):
            raise ValueError("object_name must start with letter/_ and use only letters, numbers, underscore.")

        db_path = Path(payload.db_path).expanduser().resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = duckdb.connect(str(db_path))
        object_sql = f'"{payload.object_name.replace(chr(34), chr(34) * 2)}"'

        if payload.replace:
            conn.execute(f"DROP VIEW IF EXISTS {object_sql}")
            conn.execute(f"DROP TABLE IF EXISTS {object_sql}")

        input_path_sql = _sql_string_literal(payload.input_path)
        if ".parquet" in payload.input_path.lower():
            relation_sql = f"read_parquet({input_path_sql})"
        else:
            relation_sql = f"read_csv_auto({input_path_sql}, union_by_name = true, filename = true)"

        conn.execute(f"CREATE {payload.object_type} {object_sql} AS SELECT * FROM {relation_sql}")
        conn.close()

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
        output_path = Path(payload.output_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        conn = duckdb.connect()
        input_path_sql = _sql_string_literal(payload.input_path)
        output_path_sql = _sql_string_literal(str(output_path))
        compression_sql = _sql_string_literal(payload.compression)
        conn.execute(
            f"COPY (SELECT * FROM read_csv_auto({input_path_sql}, union_by_name = true, filename = true)) "
            f"TO {output_path_sql} (FORMAT PARQUET, COMPRESSION {compression_sql})"
        )
        conn.close()
        return SidebarToolResponse(
            message="Parquet conversion completed successfully.",
            output_path=str(output_path),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
