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
        for candidate in ("**/*.csv.gz", "**/*.gz", "**/*.csv", "**/*.tsv", "**/*.txt"):
            pattern = str((normalized_as_path / candidate).as_posix())
            if glob.glob(pattern, recursive=True):
                return pattern

    matches = glob.glob(normalized_path, recursive=True)
    if matches:
        return normalized_path

    if "/*." in normalized_path:
        recursive_variant = normalized_path.replace("/*.", "/**/*.")
        recursive_matches = glob.glob(recursive_variant, recursive=True)
        if recursive_matches:
            return recursive_variant

    if ".csv.gz" in normalized_path.lower():
        fallbacks = [
            re.sub(r"\.csv\.gz", ".gz", normalized_path, flags=re.IGNORECASE),
            re.sub(r"\.csv\.gz", ".csv", normalized_path, flags=re.IGNORECASE),
        ]
        for fallback in fallbacks:
            fallback_matches = glob.glob(fallback, recursive=True)
            if fallback_matches:
                return fallback
            if "/*." in fallback:
                recursive_fallback = fallback.replace("/*.", "/**/*.")
                recursive_fallback_matches = glob.glob(recursive_fallback, recursive=True)
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
        matched_files = _list_matching_input_files(resolved_input)
        if not matched_files:
            raise ValueError(f"No readable files matched '{resolved_input}'.")

        compression_sql = _sql_string_literal(payload.compression)

        # Single-file mode keeps backward compatibility when output is an explicit parquet file.
        if len(matched_files) == 1 and output_path.suffix.lower() == ".parquet":
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
        with duckdb.connect() as conn:
            for source_file in matched_files:
                target_file = _parquet_target_for_input(output_root, input_root, source_file)
                target_file.parent.mkdir(parents=True, exist_ok=True)
                relation_sql = _resolve_csv_parquet_read_sql(str(source_file))
                target_sql = _sql_string_literal(str(target_file))
                conn.execute(
                    f"COPY (SELECT * FROM {relation_sql}) "
                    f"TO {target_sql} (FORMAT PARQUET, COMPRESSION {compression_sql})"
                )
                converted_count += 1

        return SidebarToolResponse(
            message=f"Parquet conversion completed successfully for {converted_count} file(s).",
            output_path=str(output_root),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
