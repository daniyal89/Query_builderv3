"""Sidebar-6 tooling endpoints."""

from __future__ import annotations

import re
import glob
import gzip
import os
import time
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

import duckdb
import pandas as pd
from fastapi import APIRouter, HTTPException, Request, status
from backend.api.endpoints.mercados_schema import MERCADOS_SCHEMA
from backend.services.error_log_service import ErrorLogService
from backend.services.job_runtime import (
    BackgroundJobCancelled,
    BackgroundJobPolicy,
    job_runtime,
)

from backend.models.sidebar_tools import (
    BuildDuckDbJobResponse,
    BuildDuckDbJobStartResponse,
    BuildDuckDbRequest,
    CsvToParquetJobResponse,
    CsvToParquetJobStartResponse,
    CsvToParquetRequest,
    FullPipelineRequest,
    FullPipelineStartResponse,
    FullPipelineStatusResponse,
    SidebarToolResponse,
)
from backend.utils.path_safety import sanitize_local_path_input
from backend.utils.rate_limits import enforce_rate_limit
from backend.api.deps import get_db_service

router = APIRouter()
VALID_OBJECT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MIN_PARQUET_FILE_BYTES = 16
CSV_TO_PARQUET_JOB_TYPE = "sidebar.csv_to_parquet"
BUILD_DUCKDB_JOB_TYPE = "sidebar.build_duckdb"
CSV_TO_PARQUET_POLICY = BackgroundJobPolicy(max_attempts=2, retry_backoff_seconds=1)
BUILD_DUCKDB_POLICY = BackgroundJobPolicy(max_attempts=2, retry_backoff_seconds=1)
FULL_PIPELINE_JOB_TYPE = "sidebar.full_pipeline"
FULL_PIPELINE_POLICY = BackgroundJobPolicy(max_attempts=2, retry_backoff_seconds=1)


def _read_lookup_file(file_path: str) -> pd.DataFrame:
    sanitized_path = sanitize_local_path_input(file_path, "lookup_file")
    path = Path(sanitized_path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(sanitized_path, encoding="utf-8", encoding_errors="replace", low_memory=False)
    return pd.read_excel(sanitized_path)


def _normalize_identifier_like_value(value: Any) -> str:
    if pd.isna(value):
        return ""

    text = str(value).strip()
    if not text:
        return ""

    if re.fullmatch(r"-?\d+\.0+", text):
        return text.split(".", 1)[0]

    return text


def _normalize_identifier_like_series(series: pd.Series | Any) -> pd.Series:
    return pd.Series(series).map(_normalize_identifier_like_value)


def _load_lookup_tables(hir_file: str, supp_mapper_file: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    hir_raw = _read_lookup_file(hir_file)
    hir_raw["DIV_CODE"] = _normalize_identifier_like_series(hir_raw.get("DIV_CODE", ""))
    if "CIR_SP_ID" in hir_raw.columns:
        hir_raw["CIR_SP_ID"] = _normalize_identifier_like_series(hir_raw["CIR_SP_ID"])
    if "ZON_SP_ID" in hir_raw.columns:
        hir_raw["ZON_SP_ID"] = _normalize_identifier_like_series(hir_raw["ZON_SP_ID"])
    if "SDO_SP_ID" in hir_raw.columns:
        hir_raw["SDO_SP_ID"] = _normalize_identifier_like_series(hir_raw["SDO_SP_ID"])
    hir_div = hir_raw[["DIV_CODE", "DISCOM", "CIR_SP_ID", "ZON_SP_ID", "DIV_NAME", "CIRCLE_NAME", "ZONE_NAME"]].drop_duplicates("DIV_CODE")
    hir_sdo = hir_raw[["SDO_SP_ID", "SDO_NAME"]].rename(columns={"SDO_SP_ID": "SUB_DIV_CODE"}).drop_duplicates("SUB_DIV_CODE")

    supp = _read_lookup_file(supp_mapper_file)
    supp["SUPPLY_TYPE"] = _normalize_identifier_like_series(supp.get("SUPPLY_TYPE", ""))
    supp = supp.drop_duplicates("SUPPLY_TYPE")
    return hir_div, hir_sdo, supp


def _derive_category_from_supply_type(series: pd.Series) -> pd.Series:
    """Derive CATEGORY from SUPPLY_TYPE using the same CASE logic as the Oracle SQL.

    Rules:
      - H-prefixed codes  -> 'HV-' + first digit after 'H'
      - 100-107           -> 'LMV-10'
      - 11 + letter(s)    -> 'LMV-11'  (bare '11' stays 'LMV-1')
      - other numeric     -> 'LMV-' + first digit
      - everything else   -> 'UNMAPPED'
    """
    trimmed = series.astype(str).str.strip()
    result = pd.Series("UNMAPPED", index=series.index)

    # HV codes: starts with 'H', digit immediately after 'H'
    hv_mask = trimmed.str.match(r'^H', na=False)
    hv_digit = trimmed.str.extract(r'^H(\d)', expand=False)
    result = result.mask(hv_mask & hv_digit.notna(), 'HV-' + hv_digit)

    # Extract leading digit run
    leading_digits = trimmed.str.extract(r'^(\d+)', expand=False)
    has_leading = leading_digits.notna() & ~hv_mask

    # Exception 1: 100-107 -> LMV-10  (3-digit starting with '10')
    exc1_mask = has_leading & (leading_digits.str.len() == 3) & leading_digits.str.startswith('10')
    result = result.mask(exc1_mask, 'LMV-10')

    # Exception 2: leading digits == '11' AND there are trailing letters -> LMV-11
    trailing_letters = trimmed.str.extract(r'([A-Z]+)$', expand=False)
    exc2_mask = has_leading & (leading_digits == '11') & trailing_letters.notna()
    result = result.mask(exc2_mask, 'LMV-11')

    # Default rule: first digit of the leading digit run (skip exc1/exc2)
    default_mask = has_leading & ~exc1_mask & ~exc2_mask
    first_digit = leading_digits.str[:1]
    result = result.mask(default_mask, 'LMV-' + first_digit)

    return result


def _category_case_sql() -> str:
    """Return a DuckDB CASE expression that derives CATEGORY from SUPPLY_TYPE."""
    return r"""CASE
        WHEN TRIM(CAST("SUPPLY_TYPE" AS VARCHAR)) LIKE 'H%' THEN
            'HV-' || REGEXP_EXTRACT(TRIM(CAST("SUPPLY_TYPE" AS VARCHAR)), '^H(\d)', 1)
        WHEN LENGTH(REGEXP_EXTRACT(TRIM(CAST("SUPPLY_TYPE" AS VARCHAR)), '^[0-9]+')) = 3
             AND REGEXP_EXTRACT(TRIM(CAST("SUPPLY_TYPE" AS VARCHAR)), '^[0-9]+') LIKE '10%'
            THEN 'LMV-10'
        WHEN REGEXP_EXTRACT(TRIM(CAST("SUPPLY_TYPE" AS VARCHAR)), '^[0-9]+') = '11'
             AND REGEXP_EXTRACT(TRIM(CAST("SUPPLY_TYPE" AS VARCHAR)), '[A-Z]+$') IS NOT NULL
             AND REGEXP_EXTRACT(TRIM(CAST("SUPPLY_TYPE" AS VARCHAR)), '[A-Z]+$') != ''
            THEN 'LMV-11'
        WHEN REGEXP_EXTRACT(TRIM(CAST("SUPPLY_TYPE" AS VARCHAR)), '^[0-9]+') IS NOT NULL
             AND REGEXP_EXTRACT(TRIM(CAST("SUPPLY_TYPE" AS VARCHAR)), '^[0-9]+') != ''
            THEN 'LMV-' || SUBSTR(REGEXP_EXTRACT(TRIM(CAST("SUPPLY_TYPE" AS VARCHAR)), '^[0-9]+'), 1, 1)
        ELSE 'UNMAPPED'
    END AS CATEGORY"""


def _apply_csv_enrichment(source_file: Path, target_file: Path, compression: str, hir_div: pd.DataFrame, hir_sdo: pd.DataFrame, supp: pd.DataFrame) -> tuple[bool, int, str]:
    """Enrich a CSV and write to parquet. Returns (success, rows_written, skip_reason)."""
    try:
        df = pd.read_csv(source_file, encoding="utf-8", encoding_errors="replace")
    except pd.errors.EmptyDataError:
        try:
            df = pd.read_csv(source_file, encoding="latin-1")
        except Exception:
            return False, 0, "EMPTY_DATA_ERROR"
    except Exception as exc:
        return False, 0, f"READ_ERROR:{exc}"
        
    if df.empty or len(df.columns) == 0:
        return False, 0, "EMPTY_DATAFRAME"
    if "BILLED_AMOUNT" in df.columns and "TOTAL_AMT" not in df.columns:
        df["TOTAL_AMT"] = pd.to_numeric(df["BILLED_AMOUNT"], errors="coerce")
    if "SDO_CODE" in df.columns and "SUB_DIV_CODE" not in df.columns:
        df["SUB_DIV_CODE"] = _normalize_identifier_like_series(df["SDO_CODE"])
    df["ACCT_ID"] = _normalize_identifier_like_series(df.get("ACCT_ID", ""))
    df = df[df["ACCT_ID"].str.fullmatch(r"\d+", na=False)]
    if "DIV_CODE" in df.columns:
        df["DIV_CODE"] = _normalize_identifier_like_series(df["DIV_CODE"])
        df = df.merge(hir_div, on="DIV_CODE", how="left")
        
        import numpy as np
        conditions = [
            df["DIV_CODE"].str.startswith("DIV1", na=False),
            df["DIV_CODE"].str.startswith("DIV2", na=False),
            df["DIV_CODE"].str.startswith("DIV3", na=False),
            df["DIV_CODE"].str.startswith("DIV4", na=False),
            df["DIV_CODE"].str.startswith("DIV5", na=False),
        ]
        choices = ["PVVNL", "DVVNL", "MVVNL", "PuVNL", "KESCO"]
        derived_discom = np.select(conditions, choices, default=None)
        
        df["DISCOM"] = derived_discom
            
    if "SUB_DIV_CODE" in df.columns:
        df["SUB_DIV_CODE"] = _normalize_identifier_like_series(df["SUB_DIV_CODE"])
        df = df.merge(hir_sdo, on="SUB_DIV_CODE", how="left")
    if "SUPPLY_TYPE" in df.columns:
        df["SUPPLY_TYPE"] = _normalize_identifier_like_series(df["SUPPLY_TYPE"])
        df = df.merge(supp, on="SUPPLY_TYPE", how="left")
        df["CATEGORY"] = _derive_category_from_supply_type(df["SUPPLY_TYPE"])

    unit = df.get("LOAD_UNIT", "").astype(str).str.upper().str.strip()
    load = pd.to_numeric(df.get("LOAD", 0), errors="coerce").fillna(0.0)
    load_kw = pd.Series(float("nan"), index=df.index, dtype="float64")
    load_kw = load_kw.mask(unit.eq("KW"), load.round(0))
    load_kw = load_kw.mask(unit.eq("KVA"), load.round(0) * 0.9)
    load_kw = load_kw.mask(unit.isin(["HP", "BHP"]), load.round(0) * 0.746)
    df["LOAD_KW"] = load_kw
    df["MONTH"] = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%b_%Y").upper()
    
    # Cast based on schema, else stringify object columns
    for col in df.columns:
        if col in MERCADOS_SCHEMA:
            dtype = str(MERCADOS_SCHEMA[col]).upper()
            if dtype == "NUMBER":
                df[col] = pd.to_numeric(df[col], errors="coerce")
            elif dtype == "VARCHAR2" or dtype == "CHAR":
                df[col] = _normalize_identifier_like_series(df[col])
            elif dtype == "DATE":
                pass
            else:
                df[col] = _normalize_identifier_like_series(df[col])
        else:
            df[col] = _normalize_identifier_like_series(df[col])
            
    rows = len(df)
    if rows == 0:
        return False, 0, "NO_ROWS_AFTER_FILTERING"
        
    df.to_parquet(target_file, compression=compression, index=False)
    return True, rows, ""


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
    target_lower = object_name.strip().lower()
    if target_lower not in {"master", "billed"} or object_type.upper() != "TABLE":
        return

    prev_label = _previous_month_label(month_label or "")
    if not prev_label:
        return

    existing = conn.execute(
        "SELECT table_type FROM information_schema.tables "
        f"WHERE table_schema = current_schema() AND lower(table_name) = '{target_lower}' LIMIT 1"
    ).fetchone()
    if not existing or existing[0] != "BASE TABLE":
        return

    archive_name = f"{target_lower}_{prev_label}"
    _drop_existing_duckdb_object(conn, archive_name)
    conn.execute(f"ALTER TABLE \"{target_lower}\" RENAME TO \"{archive_name}\"")




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
    is_master = lowered == "master" or lowered.startswith("master_")
    is_billed = lowered == "billed" or lowered.startswith("billed_")
    
    if not (is_master or is_billed):
        return cleaned

    label = (month_label or "").strip()

    if is_billed:
        # For billed, allow daily format or whatever label they provide
        if not label and "_" in cleaned:
            return cleaned  # They already named it like Billed_02062026
        if not label:
            raise ValueError("month_label (e.g. 02062026) is required for Billed tables.")
        return f"Billed_{label}"

    # For master, strictly enforce MMYY
    month_code = _month_code_mmyy(label)
    if not month_code:
        raise ValueError("month_label is required for master table/view names and must be like MAR_2026 or 0326.")

    return f"Master_{month_code}"
def _sql_string_literal(value: str) -> str:
    return f"'{value.replace(chr(39), chr(39) * 2)}'"


def _sql_string_list_literal(values: list[str]) -> str:
    return "[" + ", ".join(_sql_string_literal(value) for value in values) + "]"


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
        matches = [item for item in glob.glob(input_path, recursive=True) if _is_readable_input_file(item)]
        if matches:
            return f"read_parquet({_sql_string_list_literal(sorted(matches))}, union_by_name = true)"
        return f"read_parquet({input_path_sql}, union_by_name = true)"
    if ".csv" in lowered or ".tsv" in lowered or lowered.endswith(".gz") or ".gz" in lowered:
        return f"read_csv_auto({input_path_sql}, union_by_name = true, filename = true)"

    matches = [item for item in glob.glob(input_path, recursive=True) if _is_readable_input_file(item)]
    if matches:
        sample = matches[0].lower()
        if sample.endswith(".parquet"):
            return f"read_parquet({_sql_string_list_literal(sorted(matches))}, union_by_name = true)"
        if (
            sample.endswith(".csv")
            or sample.endswith(".csv.gz")
            or sample.endswith(".tsv")
            or sample.endswith(".gz")
        ):
            return f"read_csv_auto({input_path_sql}, union_by_name = true, filename = true)"

    raise ValueError(f"No readable files matched '{input_path}'.")




def _validate_gzip_file(path: Path) -> tuple[bool, str | None]:
    if path.suffix.lower() != ".gz":
        return True, None
    try:
        with path.open("rb") as handle:
            header = handle.read(2)

        if header != b"\x1f\x8b":
            try:
                pd.read_csv(path, compression=None, nrows=5, encoding="utf-8", encoding_errors="replace")
                return True, "PLAIN_TEXT_GZ_FALLBACK"
            except Exception:
                return False, "NOT_GZIP_HEADER"

        with gzip.open(path, "rb") as gz_handle:
            while gz_handle.read(1024 * 1024):
                pass
        return True, None
    except EOFError:
        try:
            test_df = pd.read_csv(path, nrows=5, encoding="utf-8", encoding_errors="replace", on_bad_lines="skip")
            if not test_df.empty and len(test_df.columns) > 0:
                return True, "TRUNCATED_GZ_PARTIAL_RECOVERY"
        except Exception:
            pass
        return False, "TRUNCATED_EOF"
    except OSError as exc:
        return False, f"GZIP_OSERROR:{exc}"


def _partition_valid_csv_sources(files: list[Path]) -> tuple[list[Path], list[dict[str, str]], list[dict[str, str]]]:
    valid_files: list[Path] = []
    invalid_files: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for source_file in files:
        is_valid, reason = _validate_gzip_file(source_file)
        if is_valid:
            valid_files.append(source_file)
            if reason:
                warnings.append({"file": str(source_file), "reason": reason})
            continue
        invalid_files.append({"file": str(source_file), "reason": reason or "INVALID_GZIP"})
    return valid_files, invalid_files, warnings


def _resolve_parquet_only_glob(input_path: str) -> str:
    cleaned = sanitize_local_path_input(input_path.replace("\u00A0", " "), "input_path").strip().strip('"').strip("'")
    normalized = cleaned.replace("\\", "/")
    path_obj = Path(normalized).expanduser()

    if path_obj.is_file():
        if path_obj.suffix.lower() != ".parquet":
            raise ValueError("Build step requires Parquet input. Provide a .parquet file or folder with parquet outputs.")
        return str(path_obj)

    if path_obj.is_dir():
        pattern = str((path_obj / "**/*.parquet").as_posix())
        if any(_is_readable_input_file(item) for item in glob.glob(pattern, recursive=True)):
            return pattern
        raise ValueError(f"No parquet files found under '{path_obj}'.")

    parquet_matches = [item for item in glob.glob(normalized, recursive=True) if item.lower().endswith('.parquet') and _is_readable_input_file(item)]
    if parquet_matches:
        return normalized

    if "*" in normalized and ".parquet" not in normalized.lower():
        base_prefix = normalized.split("*")[0]
        base_dir = Path(base_prefix).expanduser()
        candidate_dir = base_dir if base_dir.is_dir() else base_dir.parent
        candidate = str((candidate_dir / "**/*.parquet").as_posix())
        if any(_is_readable_input_file(item) for item in glob.glob(candidate, recursive=True)):
            return candidate

    raise ValueError("Build step could not find parquet outputs. Run CSV→Parquet first and pass that parquet folder/path.")

def _resolve_csv_parquet_read_sql(input_path: str) -> str:
    input_path_sql = _sql_string_literal(input_path)
    return (
        f"read_csv({input_path_sql}, union_by_name = true, filename = true, auto_detect = true, "
        "all_varchar = true, sample_size = -1)"
    )


def _resolve_existing_input_glob(input_path: str) -> str:
    cleaned = sanitize_local_path_input(input_path.replace("\u00A0", " "), "input_path").strip().strip('"').strip("'")
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
    output_path = Path(sanitize_local_path_input(payload.output_path, "output_path")).expanduser().resolve()
    matched_files = _list_matching_input_files(resolved_input)
    if not matched_files:
        raise ValueError(f"No readable files matched '{resolved_input}'.")

    if len(matched_files) == 1 and output_path.suffix.lower() == ".parquet":
        return matched_files, output_path.parent, matched_files[0].parent, output_path

    output_root = output_path if output_path.suffix.lower() != ".parquet" else output_path.parent
    input_root = _infer_input_root(resolved_input, matched_files)
    return matched_files, output_root, input_root, None


def _update_csv_job(job_id: str, **updates: Any) -> None:
    job_runtime.update_job(job_id, **updates)


def _update_build_job(job_id: str, **updates: Any) -> None:
    job_runtime.update_job(job_id, **updates)


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

    db_path = Path(sanitize_local_path_input(payload.db_path, "db_path")).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    object_sql = f'"{ normalized_object_name.replace(chr(34), chr(34) * 2)}"'
    resolved_input = _resolve_parquet_only_glob(payload.input_path)
    relation_sql = _resolve_relation_sql(resolved_input)

    # Temporarily release the dashboard's singleton connection to avoid
    # DuckDB write-write conflicts (DuckDB allows only one writer at a time).
    svc = get_db_service()
    dashboard_was_connected = False
    if svc.is_connected and svc._db_path is not None:
        try:
            same_db = svc._db_path.resolve() == db_path.resolve()
        except Exception:
            same_db = str(svc._db_path) == str(db_path)
        if same_db:
            dashboard_was_connected = True
            svc.disconnect()

    # Get column names via in-memory connection (reads parquet schema only,
    # avoids write-write transaction conflict on the target database).
    with duckdb.connect() as mem_conn:
        columns_info = mem_conn.execute(f"DESCRIBE SELECT * FROM {relation_sql} LIMIT 0").fetchall()
    col_names = [row[0] for row in columns_info]
    select_sql = _build_select_sql_for_schema(relation_sql, col_names)

    try:
        with duckdb.connect(str(db_path)) as conn:
            thread_count = max(1, os.cpu_count() or 1)
            conn.execute(f"PRAGMA threads={thread_count}")
            conn.execute("PRAGMA preserve_insertion_order=false")
            if payload.replace:
                # Use DROP IF EXISTS instead of querying information_schema
                # (the information_schema SELECT opens a read transaction that
                # conflicts with the subsequent CREATE write transaction).
                conn.execute(f"DROP VIEW IF EXISTS {object_sql}")
                conn.execute(f"DROP TABLE IF EXISTS {object_sql}")
            conn.execute(f"CREATE {payload.object_type} {object_sql} AS {select_sql}")
    finally:
        # Reconnect the dashboard so the user can immediately see the new table.
        if dashboard_was_connected:
            try:
                svc.connect(str(db_path))
            except Exception:
                pass  # Non-fatal: user can manually reconnect from the UI.

    month_text = f" for {payload.month_label}" if payload.month_label else ""
    return str(db_path), f"Created {payload.object_type} {normalized_object_name}{month_text}."


def _run_build_duckdb_job(job_id: str, payload: BuildDuckDbRequest) -> None:
    try:
        job_runtime.raise_if_cancelled(job_id)
        _update_build_job(job_id, progress_percent=25, message="Preparing build...")
        output_path, message = _execute_build_duckdb(payload)
        if job_runtime.is_cancelled(job_id):
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
    except BackgroundJobCancelled:
        _update_build_job(
            job_id,
            status="cancelled",
            message="Build cancelled before execution.",
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
        if job_runtime.is_cancelled(job_id):
            _update_build_job(
                job_id,
                status="cancelled",
                message="Stop requested. Build cancelled.",
                progress_percent=100,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            return
        _update_build_job(job_id, message=str(exc), progress_percent=100)
        raise


def _sql_varchar_normalize_expr(col: str) -> str:
    """DuckDB SQL expression: cast to VARCHAR and strip trailing .0 from integer-like values.

    Turns 9411240068.0 → '9411240068' while leaving normal strings untouched.
    """
    return (
        f"REGEXP_REPLACE(RTRIM(CAST(\"{col}\" AS VARCHAR)), "
        f"'^(-?\\d+)\\.0+$', '\\1')"
    )


def _build_select_sql_for_schema(relation_sql: str, col_names: list[str]) -> str:
    select_exprs = []
    for col in col_names:
        if col == "DISCOM": 
            continue
        expr = f'"{col}"'
        if col in MERCADOS_SCHEMA:
            dtype = str(MERCADOS_SCHEMA[col]).upper()
            if dtype == "NUMBER":
                expr = f'CAST("{col}" AS DOUBLE)'
            elif dtype == "VARCHAR2" or dtype == "CHAR":
                expr = _sql_varchar_normalize_expr(col)
            elif dtype == "DATE":
                pass
            else:
                expr = _sql_varchar_normalize_expr(col)
        else:
            expr = _sql_varchar_normalize_expr(col)
        select_exprs.append(f'{expr} AS "{col}"')

    if "DIV_CODE" in col_names:
        select_exprs.append("""CASE 
            WHEN starts_with("DIV_CODE", 'DIV1') THEN 'PVVNL'
            WHEN starts_with("DIV_CODE", 'DIV2') THEN 'DVVNL'
            WHEN starts_with("DIV_CODE", 'DIV3') THEN 'MVVNL'
            WHEN starts_with("DIV_CODE", 'DIV4') THEN 'PuVNL'
            WHEN starts_with("DIV_CODE", 'DIV5') THEN 'KESCO'
            ELSE NULL
        END AS DISCOM""")

    if "SUPPLY_TYPE" in col_names:
        select_exprs.append(_category_case_sql())

    return f"SELECT {', '.join(select_exprs)} FROM {relation_sql}"


def _run_csv_to_parquet_job(job_id: str, payload: CsvToParquetRequest) -> None:
    try:
        files, output_root, input_root, single_target = _build_csv_to_parquet_targets(payload)
        valid_files, invalid_files, warning_files = _partition_valid_csv_sources(files)
        output_root.mkdir(parents=True, exist_ok=True)
        if not valid_files:
            invalid_summary = "; ".join(f"{item['file']} ({item['reason']})" for item in invalid_files[:5])
            raise ValueError(f"No valid input files after gzip pre-validation. Invalid files: {invalid_summary}")
        compression_sql = _sql_string_literal(payload.compression)
        lookup_mode = bool(payload.hir_file and payload.supp_mapper_file)
        if lookup_mode:
            hir_div, hir_sdo, supp = _load_lookup_tables(payload.hir_file or "", payload.supp_mapper_file or "")
        reported_output_path = str(single_target if single_target is not None else output_root)
        precheck_message = "CSV to Parquet conversion started."
        if invalid_files:
            precheck_message = (
                f"Skipped {len(invalid_files)} invalid gzip file(s) during pre-validation."
                + (f" {len(warning_files)} .gz file(s) treated as plain CSV." if warning_files else "")
            )
        elif warning_files:
            precheck_message = f"{len(warning_files)} .gz file(s) treated as plain CSV."
        _update_csv_job(
            job_id,
            status="running",
            total_files=len(valid_files),
            output_path=reported_output_path,
            skipped_files=len(invalid_files),
            message=precheck_message,
        )
        skipped_files = len(invalid_files)
        parquet_skipped_details = [f"{item['file']} ({item['reason']})" for item in invalid_files]
        total_output_rows = 0

        with duckdb.connect() as conn:
            for index, source_file in enumerate(valid_files, start=1):
                if job_runtime.is_cancelled(job_id):
                    _update_csv_job(
                        job_id,
                        status="cancelled",
                        message="CSV to Parquet conversion stopped by user.",
                        finished_at=datetime.now().isoformat(timespec="seconds"),
                    )
                    return

                target_file = single_target if single_target is not None else _parquet_target_for_input(output_root, input_root, source_file)
                target_file.parent.mkdir(parents=True, exist_ok=True)
                if target_file.exists():
                    if payload.overwrite_parquet:
                        target_file.unlink()
                    else:
                        skipped_files += 1
                        parquet_skipped_details.append(f"{source_file} (ALREADY_EXISTS)")
                        _update_csv_job(
                            job_id,
                            processed_files=index,
                            skipped_files=skipped_files,
                            parquet_skipped_details=parquet_skipped_details,
                            current_file=str(source_file),
                            message=f"Skipping existing parquet file ({index}/{len(valid_files)}).",
                        )
                        continue
                _update_csv_job(
                    job_id,
                    processed_files=index - 1,
                    skipped_files=skipped_files,
                    current_file=str(source_file),
                    message=f"Processing file {index}/{len(valid_files)}...",
                )
                if lookup_mode:
                    success, rows_written, skip_reason = _apply_csv_enrichment(source_file, target_file, payload.compression, hir_div, hir_sdo, supp)
                    if not success:
                        skipped_files += 1
                        parquet_skipped_details.append(f"{source_file} ({skip_reason})")
                        _update_csv_job(
                            job_id, 
                            processed_files=index, 
                            skipped_files=skipped_files, 
                            parquet_skipped_details=parquet_skipped_details,
                            message=f"Skipping file ({index}/{len(valid_files)}) - {skip_reason}."
                        )
                        continue
                    total_output_rows += rows_written
                else:
                    relation_sql = _resolve_csv_parquet_read_sql(str(source_file))
                    target_sql = _sql_string_literal(str(target_file))
                    
                    columns_info = conn.execute(f"DESCRIBE SELECT * FROM {relation_sql} LIMIT 0").fetchall()
                    col_names = [row[0] for row in columns_info]
                    select_sql = _build_select_sql_for_schema(relation_sql, col_names)
                        
                    res = conn.execute(
                        f"COPY ({select_sql}) TO {target_sql} (FORMAT PARQUET, COMPRESSION {compression_sql})"
                    ).fetchone()
                    if res:
                        total_output_rows += int(res[0])
                _update_csv_job(
                    job_id, 
                    processed_files=index, 
                    skipped_files=skipped_files,
                    parquet_skipped_details=parquet_skipped_details,
                    total_output_rows=total_output_rows
                )

        skipped_str = f" Skipped: {skipped_files}" + (f" ({', '.join(parquet_skipped_details)})" if parquet_skipped_details else ".")
        _update_csv_job(
            job_id,
            status="completed",
            current_file=None,
            message=(
                f"Parquet conversion completed successfully for {len(valid_files)} file(s).{skipped_str}"
                + (" Enrichment applied (HIR + suppMapper + LOAD_KW)." if lookup_mode else "")
                + (f" Invalid gzip files: {len(invalid_files)}." if invalid_files else "")
                + (f" Plain-text .gz fallback files: {len(warning_files)}." if warning_files else "")
            ),
            finished_at=datetime.now().isoformat(timespec="seconds"),
            skipped_files=skipped_files,
        )
    except BackgroundJobCancelled:
        _update_csv_job(
            job_id,
            status="cancelled",
            message="CSV to Parquet conversion stopped by user.",
            finished_at=datetime.now().isoformat(timespec="seconds"),
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
        if job_runtime.is_cancelled(job_id):
            _update_csv_job(
                job_id,
                status="cancelled",
                message="CSV to Parquet conversion stopped by user.",
                current_file=None,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            return
        _update_csv_job(job_id, message=str(exc), current_file=None)
        raise


@router.post("/sidebar-tools/build-duckdb", response_model=SidebarToolResponse)
async def build_duckdb(request: Request, payload: BuildDuckDbRequest) -> SidebarToolResponse:
    try:
        enforce_rate_limit(request, "sidebar_build_duckdb")
        output_path, message = _execute_build_duckdb(payload)
        return SidebarToolResponse(message=message, output_path=output_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sidebar-tools/build-duckdb/start", response_model=BuildDuckDbJobStartResponse)
async def build_duckdb_start(request: Request, payload: BuildDuckDbRequest) -> BuildDuckDbJobStartResponse:
    enforce_rate_limit(request, "sidebar_build_duckdb")
    job_id = uuid.uuid4().hex
    job_runtime.start_job(
        job_type=BUILD_DUCKDB_JOB_TYPE,
        job_id=job_id,
        initial_snapshot={
            "job_id": job_id,
            "status": "queued",
            "message": "Build job queued.",
            "output_path": None,
            "progress_percent": 0,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        },
        payload=payload.model_dump(mode="json"),
        policy=BUILD_DUCKDB_POLICY,
        worker=lambda running_job_id: _run_build_duckdb_job(running_job_id, payload),
    )
    return BuildDuckDbJobStartResponse(job_id=job_id, status="queued", message="Build DuckDB job started.")


@router.get("/sidebar-tools/build-duckdb/status/{job_id}", response_model=BuildDuckDbJobResponse)
async def build_duckdb_status(job_id: str) -> BuildDuckDbJobResponse:
    job = job_runtime.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build DuckDB job not found.")
    return BuildDuckDbJobResponse(**job)


@router.post("/sidebar-tools/build-duckdb/stop/{job_id}", response_model=BuildDuckDbJobResponse)
async def build_duckdb_stop(job_id: str) -> BuildDuckDbJobResponse:
    job = job_runtime.stop_job(job_id, "Stop requested. Waiting for operation to finish...")
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build DuckDB job not found.")
    return BuildDuckDbJobResponse(**job)


@router.post("/sidebar-tools/csv-to-parquet", response_model=SidebarToolResponse)
async def csv_to_parquet(request: Request, payload: CsvToParquetRequest) -> SidebarToolResponse:
    try:
        enforce_rate_limit(request, "sidebar_csv_to_parquet")
        resolved_input = _resolve_existing_input_glob(payload.input_path)
        output_path = Path(sanitize_local_path_input(payload.output_path, "output_path")).expanduser().resolve()
        matched_files = _list_matching_input_files(resolved_input)
        if not matched_files:
            raise ValueError(f"No readable files matched '{resolved_input}'.")
        matched_files, invalid_files, warning_files = _partition_valid_csv_sources(matched_files)
        if not matched_files:
            invalid_summary = "; ".join(f"{item['file']} ({item['reason']})" for item in invalid_files[:5])
            raise ValueError(f"No valid input files after gzip pre-validation. Invalid files: {invalid_summary}")

        compression_sql = _sql_string_literal(payload.compression)
        lookup_mode = bool(payload.hir_file and payload.supp_mapper_file)
        if lookup_mode:
            hir_div, hir_sdo, supp = _load_lookup_tables(payload.hir_file or "", payload.supp_mapper_file or "")

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
                if lookup_mode:
                    _apply_csv_enrichment(matched_files[0], output_path, payload.compression, hir_div, hir_sdo, supp)
                else:
                    columns_info = conn.execute(f"DESCRIBE SELECT * FROM {relation_sql} LIMIT 0").fetchall()
                    col_names = [row[0] for row in columns_info]
                    
                    if "DIV_CODE" in col_names:
                        discom_exclude = " EXCLUDE (DISCOM)," if "DISCOM" in col_names else ","
                        category_expr = f", {_category_case_sql()}" if "SUPPLY_TYPE" in col_names else ""
                        select_sql = f"""SELECT *{discom_exclude} 
                            CASE 
                                WHEN starts_with(DIV_CODE, 'DIV1') THEN 'PVVNL'
                                WHEN starts_with(DIV_CODE, 'DIV2') THEN 'DVVNL'
                                WHEN starts_with(DIV_CODE, 'DIV3') THEN 'MVVNL'
                                WHEN starts_with(DIV_CODE, 'DIV4') THEN 'PuVNL'
                                WHEN starts_with(DIV_CODE, 'DIV5') THEN 'KESCO'
                                ELSE NULL
                            END AS DISCOM{category_expr}
                            FROM {relation_sql}"""
                    elif "SUPPLY_TYPE" in col_names:
                        select_sql = f"SELECT *, {_category_case_sql()} FROM {relation_sql}"
                    else:
                        select_sql = f"SELECT * FROM {relation_sql}"
                        
                    conn.execute(
                        f"COPY ({select_sql}) TO {output_path_sql} (FORMAT PARQUET, COMPRESSION {compression_sql})"
                    )
            return SidebarToolResponse(
                message="Parquet conversion completed successfully." + (" Enrichment applied (HIR + suppMapper + LOAD_KW)." if lookup_mode else "")
            + (f" Invalid gzip files: {len(invalid_files)}." if invalid_files else "")
                + (f" Plain-text .gz fallback files: {len(warning_files)}." if warning_files else ""),
                output_path=str(output_path),
            )

        # Multi-file mode writes parquet files preserving input relative folder structure.
        output_root = output_path if output_path.suffix.lower() != ".parquet" else output_path.parent
        output_root.mkdir(parents=True, exist_ok=True)
        input_root = _infer_input_root(resolved_input, matched_files)

        converted_count = 0
        skipped_count = len(invalid_files)
        with duckdb.connect() as conn:
            for source_file in matched_files:
                target_file = _parquet_target_for_input(output_root, input_root, source_file)
                target_file.parent.mkdir(parents=True, exist_ok=True)
                if target_file.exists():
                    skipped_count += 1
                    continue
                if lookup_mode:
                    if not _apply_csv_enrichment(source_file, target_file, payload.compression, hir_div, hir_sdo, supp):
                        skipped_count += 1
                        continue
                else:
                    relation_sql = _resolve_csv_parquet_read_sql(str(source_file))
                    target_sql = _sql_string_literal(str(target_file))
                    
                    columns_info = conn.execute(f"DESCRIBE SELECT * FROM {relation_sql} LIMIT 0").fetchall()
                    col_names = [row[0] for row in columns_info]
                    
                    if "DIV_CODE" in col_names:
                        discom_exclude = " EXCLUDE (DISCOM)," if "DISCOM" in col_names else ","
                        category_expr = f", {_category_case_sql()}" if "SUPPLY_TYPE" in col_names else ""
                        select_sql = f"""SELECT *{discom_exclude} 
                            CASE 
                                WHEN starts_with(DIV_CODE, 'DIV1') THEN 'PVVNL'
                                WHEN starts_with(DIV_CODE, 'DIV2') THEN 'DVVNL'
                                WHEN starts_with(DIV_CODE, 'DIV3') THEN 'MVVNL'
                                WHEN starts_with(DIV_CODE, 'DIV4') THEN 'PuVNL'
                                WHEN starts_with(DIV_CODE, 'DIV5') THEN 'KESCO'
                                ELSE NULL
                            END AS DISCOM{category_expr}
                            FROM {relation_sql}"""
                    elif "SUPPLY_TYPE" in col_names:
                        select_sql = f"SELECT *, {_category_case_sql()} FROM {relation_sql}"
                    else:
                        select_sql = f"SELECT * FROM {relation_sql}"
                        
                    conn.execute(
                        f"COPY ({select_sql}) TO {target_sql} (FORMAT PARQUET, COMPRESSION {compression_sql})"
                    )
                converted_count += 1

        skipped_str = f" Skipped existing/invalid: {skipped_count}" + (f" ({', '.join(parquet_skipped_details)})" if parquet_skipped_details else ".")
        return SidebarToolResponse(
            message=f"Parquet conversion completed successfully for {converted_count} file(s).{skipped_str}"
            + (" Enrichment applied (HIR + suppMapper + LOAD_KW)." if lookup_mode else "")
            + (f" Invalid gzip files: {len(invalid_files)}." if invalid_files else "")
            + (f" Plain-text .gz fallback files: {len(warning_files)}." if warning_files else ""),
            output_path=str(output_root),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sidebar-tools/csv-to-parquet/start", response_model=CsvToParquetJobStartResponse)
async def csv_to_parquet_start(request: Request, payload: CsvToParquetRequest) -> CsvToParquetJobStartResponse:
    enforce_rate_limit(request, "sidebar_csv_to_parquet")
    try:
        files, output_root, _, single_target = _build_csv_to_parquet_targets(payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    job_runtime.start_job(
        job_type=CSV_TO_PARQUET_JOB_TYPE,
        job_id=job_id,
        initial_snapshot={
            "job_id": job_id,
            "status": "queued",
            "message": "CSV to Parquet conversion queued.",
            "processed_files": 0,
            "total_files": len(files),
            "skipped_files": 0,
            "current_file": None,
            "output_path": str(single_target if single_target is not None else output_root),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        },
        payload=payload.model_dump(mode="json"),
        policy=CSV_TO_PARQUET_POLICY,
        worker=lambda running_job_id: _run_csv_to_parquet_job(running_job_id, payload),
    )
    return CsvToParquetJobStartResponse(job_id=job_id, status="queued", message="CSV to Parquet job started.")


@router.get("/sidebar-tools/csv-to-parquet/status/{job_id}", response_model=CsvToParquetJobResponse)
async def csv_to_parquet_status(job_id: str) -> CsvToParquetJobResponse:
    job = job_runtime.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSV to Parquet job not found.")
    return CsvToParquetJobResponse(**job)


@router.post("/sidebar-tools/csv-to-parquet/stop/{job_id}", response_model=CsvToParquetJobResponse)
async def csv_to_parquet_stop(job_id: str) -> CsvToParquetJobResponse:
    job = job_runtime.stop_job(job_id, "Stop requested. Waiting for current file to finish...")
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSV to Parquet job not found.")
    return CsvToParquetJobResponse(**job)


# ──────────────── Full Pipeline (CSV→Parquet + Build DuckDB) ─────────────────


def _run_full_pipeline_job(job_id: str, payload: FullPipelineRequest) -> None:
    """Worker that chains CSV→Parquet then Build DuckDB as a single job."""

    def _update(**updates) -> None:
        job_runtime.update_job(job_id, **updates)

    try:
        # ── Phase 1: CSV → Parquet ──
        _update(
            current_phase="csv_to_parquet",
            message="Phase 1: Preparing CSV to Parquet conversion…",
            overall_progress_percent=2,
        )

        parquet_payload = CsvToParquetRequest(
            input_path=payload.input_path,
            output_path=payload.parquet_output_path,
            compression=payload.compression,
            hir_file=payload.hir_file,
            supp_mapper_file=payload.supp_mapper_file,
            overwrite_parquet=payload.overwrite_parquet,
        )

        files, output_root, input_root, single_target = _build_csv_to_parquet_targets(parquet_payload)
        valid_files, invalid_files, warning_files = _partition_valid_csv_sources(files)
        output_root.mkdir(parents=True, exist_ok=True)

        if not valid_files:
            invalid_summary = "; ".join(f"{item['file']} ({item['reason']})" for item in invalid_files[:5])
            raise ValueError(f"No valid input files after gzip pre-validation. Invalid files: {invalid_summary}")

        compression_sql = _sql_string_literal(payload.compression)
        lookup_mode = bool(payload.hir_file and payload.supp_mapper_file)
        if lookup_mode:
            hir_div, hir_sdo, supp = _load_lookup_tables(payload.hir_file or "", payload.supp_mapper_file or "")

        reported_parquet_output = str(single_target if single_target is not None else output_root)
        total_valid = len(valid_files)
        skipped_files = len(invalid_files)

        _update(
            current_phase="csv_to_parquet",
            parquet_total_files=total_valid,
            parquet_skipped_files=skipped_files,
            parquet_output_path=reported_parquet_output,
            message=f"Phase 1: Converting {total_valid} file(s) to Parquet…",
            overall_progress_percent=5,
        )
        parquet_skipped_details = [f"{item['file']} ({item['reason']})" for item in invalid_files]
        total_output_rows = 0

        with duckdb.connect() as conn:
            for index, source_file in enumerate(valid_files, start=1):
                if job_runtime.is_cancelled(job_id):
                    _update(
                        status="cancelled",
                        current_phase="csv_to_parquet",
                        message="Pipeline stopped by user during Parquet conversion.",
                        finished_at=datetime.now().isoformat(timespec="seconds"),
                    )
                    return

                target_file = single_target if single_target is not None else _parquet_target_for_input(
                    output_root, input_root, source_file
                )
                target_file.parent.mkdir(parents=True, exist_ok=True)

                if target_file.exists():
                    if payload.overwrite_parquet:
                        target_file.unlink()
                    else:
                        skipped_files += 1
                        parquet_skipped_details.append(f"{source_file} (ALREADY_EXISTS)")
                        parquet_pct = int((index / total_valid) * 70)
                        _update(
                            parquet_processed_files=index,
                            parquet_skipped_files=skipped_files,
                            parquet_skipped_details=parquet_skipped_details,
                            parquet_current_file=str(source_file),
                            message=f"Phase 1: Skipping existing file ({index}/{total_valid}).",
                            overall_progress_percent=min(70, parquet_pct),
                        )
                        continue

                parquet_pct = int(((index - 1) / total_valid) * 70)
                _update(
                    parquet_processed_files=index - 1,
                    parquet_skipped_files=skipped_files,
                    parquet_current_file=str(source_file),
                    message=f"Phase 1: Processing file {index}/{total_valid}…",
                    overall_progress_percent=min(70, parquet_pct),
                )

                if lookup_mode:
                    success, rows_written, skip_reason = _apply_csv_enrichment(source_file, target_file, payload.compression, hir_div, hir_sdo, supp)
                    if not success:
                        skipped_files += 1
                        parquet_skipped_details.append(f"{source_file} ({skip_reason})")
                        _update(
                            parquet_processed_files=index,
                            parquet_skipped_files=skipped_files,
                            parquet_skipped_details=parquet_skipped_details,
                            message=f"Phase 1: Skipping file ({index}/{total_valid}) - {skip_reason}.",
                        )
                        continue
                    total_output_rows += rows_written
                else:
                    relation_sql = _resolve_csv_parquet_read_sql(str(source_file))
                    target_sql = _sql_string_literal(str(target_file))

                    columns_info = conn.execute(f"DESCRIBE SELECT * FROM {relation_sql} LIMIT 0").fetchall()
                    col_names = [row[0] for row in columns_info]
                    select_sql = _build_select_sql_for_schema(relation_sql, col_names)

                    res = conn.execute(
                        f"COPY ({select_sql}) TO {target_sql} (FORMAT PARQUET, COMPRESSION {compression_sql})"
                    ).fetchone()
                    if res:
                        total_output_rows += int(res[0])

                parquet_pct = int((index / total_valid) * 70)
                _update(
                    parquet_processed_files=index,
                    parquet_skipped_files=skipped_files,
                    parquet_skipped_details=parquet_skipped_details,
                    total_output_rows=total_output_rows,
                    overall_progress_percent=min(70, parquet_pct),
                )

        skipped_str = f" {skipped_files} skipped" + (f" ({', '.join(parquet_skipped_details)})" if parquet_skipped_details else "")
        parquet_summary = (
            f"Parquet done: {total_valid} file(s),{skipped_str}."
            + (" Enrichment applied." if lookup_mode else "")
        )

        _update(
            current_phase="csv_to_parquet",
            parquet_processed_files=total_valid,
            parquet_current_file=None,
            message=f"Phase 1 complete. {parquet_summary} Starting Phase 2…",
            overall_progress_percent=70,
        )

        # ── Phase 2: Build DuckDB ──
        if job_runtime.is_cancelled(job_id):
            _update(
                status="cancelled",
                message="Pipeline stopped by user after Parquet phase.",
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            return

        # Auto-derive the build input path from the parquet output
        parquet_out_path = Path(payload.parquet_output_path).expanduser().resolve()
        if parquet_out_path.is_dir() or not parquet_out_path.suffix:
            build_input_glob = str((parquet_out_path / "**/*.parquet").as_posix())
        else:
            build_input_glob = str(parquet_out_path)

        build_payload = BuildDuckDbRequest(
            db_path=payload.db_path,
            input_path=build_input_glob,
            object_name=payload.object_name,
            object_type=payload.object_type,
            replace=payload.replace,
            month_label=payload.month_label,
        )

        _update(
            current_phase="build_duckdb",
            build_progress_percent=0,
            message="Phase 2: Building DuckDB table…",
            overall_progress_percent=72,
        )

        try:
            build_output_path, build_message = _execute_build_duckdb(build_payload)
        except Exception as build_exc:
            _update(
                status="failed",
                current_phase="build_duckdb",
                message=f"Phase 2 failed: {build_exc}. {parquet_summary}",
                build_progress_percent=100,
                overall_progress_percent=100,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            raise

        if job_runtime.is_cancelled(job_id):
            _update(
                status="cancelled",
                current_phase="build_duckdb",
                message=f"Pipeline stopped. Build ran but marked cancelled. {parquet_summary}",
                build_output_path=build_output_path,
                build_progress_percent=100,
                overall_progress_percent=100,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            return

        _update(
            status="completed",
            current_phase="completed",
            message=f"Pipeline complete. {parquet_summary} {build_message}",
            build_output_path=build_output_path,
            build_progress_percent=100,
            overall_progress_percent=100,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )

    except BackgroundJobCancelled:
        _update(
            status="cancelled",
            message="Pipeline cancelled.",
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
    except Exception as exc:
        ErrorLogService.append(
            {
                "endpoint": "/api/sidebar-tools/full-pipeline/start",
                "method": "POST",
                "status_code": 500,
                "error": str(exc),
                "exception_type": type(exc).__name__,
                "job_id": job_id,
                "payload": payload.model_dump(),
                "stage": "background_worker",
            }
        )
        if job_runtime.is_cancelled(job_id):
            _update(
                status="cancelled",
                message="Pipeline cancelled.",
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            return
        _update(
            status="failed",
            message=str(exc),
            overall_progress_percent=100,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        raise


@router.post("/sidebar-tools/full-pipeline/start", response_model=FullPipelineStartResponse)
async def full_pipeline_start(request: Request, payload: FullPipelineRequest) -> FullPipelineStartResponse:
    enforce_rate_limit(request, "sidebar_full_pipeline")
    job_id = uuid.uuid4().hex
    job_runtime.start_job(
        job_type=FULL_PIPELINE_JOB_TYPE,
        job_id=job_id,
        initial_snapshot={
            "job_id": job_id,
            "status": "queued",
            "message": "Full pipeline queued.",
            "current_phase": "queued",
            "parquet_processed_files": 0,
            "parquet_total_files": 0,
            "parquet_skipped_files": 0,
            "parquet_current_file": None,
            "parquet_output_path": None,
            "build_progress_percent": 0,
            "build_output_path": None,
            "overall_progress_percent": 0,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        },
        payload=payload.model_dump(mode="json"),
        policy=FULL_PIPELINE_POLICY,
        worker=lambda running_job_id: _run_full_pipeline_job(running_job_id, payload),
    )
    return FullPipelineStartResponse(job_id=job_id, status="queued", message="Full pipeline job started.")


@router.get("/sidebar-tools/full-pipeline/status/{job_id}", response_model=FullPipelineStatusResponse)
async def full_pipeline_status(job_id: str) -> FullPipelineStatusResponse:
    job = job_runtime.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Full pipeline job not found.")
    return FullPipelineStatusResponse(**job)


@router.post("/sidebar-tools/full-pipeline/stop/{job_id}", response_model=FullPipelineStatusResponse)
async def full_pipeline_stop(job_id: str) -> FullPipelineStatusResponse:
    job = job_runtime.stop_job(job_id, "Stop requested. Waiting for current operation to finish…")
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Full pipeline job not found.")
    return FullPipelineStatusResponse(**job)
