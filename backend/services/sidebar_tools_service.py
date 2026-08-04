"""Sidebar-6 tooling services.

Holds the file-discovery, conversion, enrichment and DuckDB-build logic behind
the ``/api/sidebar-tools/*`` endpoints, plus the background-job workers that
drive the long-running variants. The endpoint module is a thin HTTP wrapper
over the functions defined here.
"""

from __future__ import annotations

import re
import glob
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Iterator

import duckdb
import pandas as pd

from backend.api.endpoints.mercados_schema import MERCADOS_SCHEMA
from backend.models.sidebar_tools import (
    BuildDuckDbRequest,
    CsvToParquetRequest,
    FileRowAudit,
    FullPipelineRequest,
    RowReconciliation,
    SidebarToolResponse,
)
from backend.services import pipeline_sql
from backend.services.error_log_service import ErrorLogService
from backend.services.job_runtime import (
    BackgroundJobCancelled,
    BackgroundJobPolicy,
    job_runtime,
)
from backend.utils.path_safety import sanitize_local_path_input

VALID_OBJECT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MIN_PARQUET_FILE_BYTES = 16
# Rejected rows are written here, under the parquet output root. Excluded from
# every build glob so quarantined records can never reach the master table.
QUARANTINE_DIR_NAME = "_quarantine"
CSV_TO_PARQUET_JOB_TYPE = "sidebar.csv_to_parquet"
BUILD_DUCKDB_JOB_TYPE = "sidebar.build_duckdb"
CSV_TO_PARQUET_POLICY = BackgroundJobPolicy(max_attempts=2, retry_backoff_seconds=1)
BUILD_DUCKDB_POLICY = BackgroundJobPolicy(max_attempts=2, retry_backoff_seconds=1)
FULL_PIPELINE_JOB_TYPE = "sidebar.full_pipeline"
FULL_PIPELINE_POLICY = BackgroundJobPolicy(max_attempts=2, retry_backoff_seconds=1)


MAX_CLEAN_AUDIT_ENTRIES = 200


@dataclass(frozen=True)
class BuildOutcome:
    """Result of a Parquet→DuckDB build, including the row balance."""

    output_path: str
    message: str
    parquet_input_rows: int | None = None
    table_rows: int | None = None
    excluded_input_files: tuple[str, ...] = ()

    @property
    def row_delta(self) -> int:
        if self.parquet_input_rows is None or self.table_rows is None:
            return 0
        return self.table_rows - self.parquet_input_rows

    @property
    def data_quality(self) -> str:
        if self.row_delta:
            return "loss"
        return "warning" if self.excluded_input_files else "ok"


class ConversionLedger:
    """Row-level accounting for one CSV→Parquet run.

    Before this existed, three separate workers each kept their own loose
    ``skipped_files`` / ``parquet_skipped_details`` / ``total_output_rows``
    locals — which is how the synchronous path silently drifted into counting
    failures as successes. One accumulator, one set of totals.
    """

    def __init__(self) -> None:
        self._entries: list[FileRowAudit] = []
        self._clean_dropped = 0

    def record(self, entry: FileRowAudit) -> None:
        # Keep every problem entry; cap the boring ones so a 5000-file run
        # doesn't bloat the persisted job snapshot.
        interesting = entry.outcome not in {"written", "reused"} or entry.quarantined_rows > 0
        if interesting or len(self._entries) < MAX_CLEAN_AUDIT_ENTRIES:
            self._entries.append(entry)
        else:
            self._clean_dropped += 1

    @property
    def entries(self) -> list[FileRowAudit]:
        return self._entries

    @property
    def truncated(self) -> bool:
        return self._clean_dropped > 0

    def totals(self) -> RowReconciliation:
        totals = RowReconciliation()
        discrepancies: list[str] = []
        for entry in self._entries:
            totals.source_rows += entry.source_rows
            totals.quarantined_rows += entry.quarantined_rows
            if entry.outcome == "reused":
                totals.reused_rows += entry.written_rows
            else:
                totals.written_rows += entry.written_rows

            accounted = entry.written_rows + entry.quarantined_rows
            if entry.source_rows and accounted != entry.source_rows:
                gap = entry.source_rows - accounted
                totals.unaccounted_rows += gap
                discrepancies.append(
                    f"{entry.source_file}: source {entry.source_rows:,}, "
                    f"written {entry.written_rows:,}, quarantined {entry.quarantined_rows:,} "
                    f"-> {gap:,} unaccounted"
                )
        totals.discrepancies = discrepancies
        totals.balanced = totals.unaccounted_rows == 0
        return totals

    def data_quality(self) -> str:
        totals = self.totals()
        if totals.unaccounted_rows or any(e.outcome == "failed" for e in self._entries):
            return "loss"
        if totals.quarantined_rows or any(e.outcome == "repaired" for e in self._entries):
            return "warning"
        return "ok"

    def as_snapshot(self) -> dict[str, Any]:
        """Job-snapshot fields, including the legacy keys the current UI reads."""
        totals = self.totals()
        return {
            "row_audit": [entry.model_dump(mode="json") for entry in self._entries],
            "row_audit_truncated": self.truncated,
            "reconciliation": totals.model_dump(mode="json"),
            "data_quality": self.data_quality(),
        }


def _discom_case_sql(div_code_sql: str = "DIV_CODE") -> str:
    """CASE expression mapping a DIV_CODE prefix to its owning DISCOM."""
    return (
        "CASE "
        f"WHEN starts_with({div_code_sql}, 'DIV1') THEN 'PVVNL' "
        f"WHEN starts_with({div_code_sql}, 'DIV2') THEN 'DVVNL' "
        f"WHEN starts_with({div_code_sql}, 'DIV3') THEN 'MVVNL' "
        f"WHEN starts_with({div_code_sql}, 'DIV4') THEN 'PuVNL' "
        f"WHEN starts_with({div_code_sql}, 'DIV5') THEN 'KESCO' "
        "ELSE NULL END AS DISCOM"
    )


def _csv_to_parquet_select_sql(relation_sql: str, col_names: list[str]) -> str:
    """SELECT used by the CSV→Parquet conversion, deriving DISCOM/CATEGORY when possible."""
    if "DIV_CODE" in col_names:
        discom_exclude = " EXCLUDE (DISCOM)," if "DISCOM" in col_names else ","
        category_expr = f", {_category_case_sql()}" if "SUPPLY_TYPE" in col_names else ""
        return f"SELECT *{discom_exclude} {_discom_case_sql()}{category_expr} FROM {relation_sql}"
    if "SUPPLY_TYPE" in col_names:
        return f"SELECT *, {_category_case_sql()} FROM {relation_sql}"
    return f"SELECT * FROM {relation_sql}"


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


def _column_as_series(frame: pd.DataFrame, column: str, default: Any = "") -> pd.Series:
    """Return *column* from *frame*, or a full-length column of *default*.

    ``frame.get(column, "")`` returns the bare scalar when the column is missing,
    and assigning that back index-aligns a length-1 Series onto an N-row frame —
    row 0 gets the value and every other row gets NaN. That silently destroyed
    whole files, so never use ``.get()`` for this.
    """
    if column in frame.columns:
        return frame[column]
    return pd.Series([default] * len(frame), index=frame.index, dtype=object)


def _normalize_identifier_like_series(series: pd.Series | Any) -> pd.Series:
    """Vectorized: strip whitespace, blank out NAs, truncate '.0' floats."""
    s = pd.Series(series)
    na_mask = s.isna()
    s = s.astype(str).str.strip()
    # Restore original NAs as empty string
    s = s.mask(na_mask, "")
    # Fix float-like integers: "123.0", "-45.000" -> "123", "-45"
    float_mask = s.str.fullmatch(r"-?\d+\.0+", na=False)
    if float_mask.any():
        s = s.where(~float_mask, s.str.split(".", n=1).str[0])
    return s


def _load_lookup_tables(hir_file: str, supp_mapper_file: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    hir_raw = _read_lookup_file(hir_file)
    if "DIV_CODE" not in hir_raw.columns:
        raise ValueError(f"HIR lookup file has no DIV_CODE column: {hir_file}")
    hir_raw["DIV_CODE"] = _normalize_identifier_like_series(hir_raw["DIV_CODE"])
    if "CIR_SP_ID" in hir_raw.columns:
        hir_raw["CIR_SP_ID"] = _normalize_identifier_like_series(hir_raw["CIR_SP_ID"])
    if "ZON_SP_ID" in hir_raw.columns:
        hir_raw["ZON_SP_ID"] = _normalize_identifier_like_series(hir_raw["ZON_SP_ID"])
    if "SDO_SP_ID" in hir_raw.columns:
        hir_raw["SDO_SP_ID"] = _normalize_identifier_like_series(hir_raw["SDO_SP_ID"])
    hir_div = hir_raw[["DIV_CODE", "DISCOM", "CIR_SP_ID", "ZON_SP_ID", "DIV_NAME", "CIRCLE_NAME", "ZONE_NAME"]].drop_duplicates("DIV_CODE")
    hir_sdo = hir_raw[["SDO_SP_ID", "SDO_NAME"]].rename(columns={"SDO_SP_ID": "SUB_DIV_CODE"}).drop_duplicates("SUB_DIV_CODE")

    supp = _read_lookup_file(supp_mapper_file)
    if "SUPPLY_TYPE" not in supp.columns:
        raise ValueError(f"suppMapper lookup file has no SUPPLY_TYPE column: {supp_mapper_file}")
    supp["SUPPLY_TYPE"] = _normalize_identifier_like_series(supp["SUPPLY_TYPE"])
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


ACCT_ID_WIDTH = 10


def _normalize_acct_id_series(series: pd.Series) -> pd.Series:
    """Normalize ACCT_ID to a bare digit string, ready for zero-padding.

    An account id is a 10-digit string, not a number — treating it numerically is
    how `1.23457E+11` and `1234567890.0` get into source files in the first place.
    Strips whitespace and thousands separators, then drops a trailing `.0` left by
    a float round-trip.
    """
    s = pd.Series(series)
    na_mask = s.isna()
    s = s.astype(str).str.strip().str.replace(r"[,\s]", "", regex=True)
    s = s.mask(na_mask, "")
    float_like = s.str.fullmatch(r"\d+\.0+", na=False)
    if float_like.any():
        s = s.where(~float_like, s.str.split(".", n=1).str[0])
    return s


def _classify_acct_id_series(normalized: pd.Series) -> pd.Series:
    """Per-row validity of a normalized ACCT_ID: 'OK' or a rejection reason."""
    status = pd.Series("OK", index=normalized.index, dtype=object)
    status = status.mask(normalized.str.len() > ACCT_ID_WIDTH, "ACCT_ID_TOO_LONG")
    status = status.mask(~normalized.str.fullmatch(r"\d+", na=False), "ACCT_ID_NON_NUMERIC")
    status = status.mask(normalized.eq(""), "ACCT_ID_BLANK")
    return status


def _write_quarantine(frame: pd.DataFrame, target_file: Path, tag: str) -> str | None:
    """Persist rejected rows next to the output so they can be inspected.

    Everything is stringified: these rows are already malformed, and a mixed-dtype
    column would otherwise fail the parquet write and lose the evidence.
    """
    try:
        out_dir = target_file.parent / QUARANTINE_DIR_NAME
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{target_file.stem}.{tag}.parquet"
        with _atomic_parquet_target(dest) as tmp:
            frame.astype(str).to_parquet(tmp, compression="zstd", index=False)
        return str(dest)
    except Exception:
        # Never let a quarantine write failure abort a conversion that otherwise
        # succeeded — the rows are still counted either way.
        return None


def _register_lookups(
    conn: duckdb.DuckDBPyConnection,
    hir_div: pd.DataFrame,
    hir_sdo: pd.DataFrame,
    supp: pd.DataFrame,
) -> None:
    """Expose the lookup frames to SQL as relations for the enrichment joins."""
    conn.register("__hir_div_df", hir_div)
    conn.register("__hir_sdo_df", hir_sdo)
    conn.register("__supp_df", supp)
    conn.execute(f"CREATE OR REPLACE TEMP VIEW {pipeline_sql.HIR_DIV_RELATION} AS SELECT * FROM __hir_div_df")
    conn.execute(f"CREATE OR REPLACE TEMP VIEW {pipeline_sql.HIR_SDO_RELATION} AS SELECT * FROM __hir_sdo_df")
    conn.execute(f"CREATE OR REPLACE TEMP VIEW {pipeline_sql.SUPP_RELATION} AS SELECT * FROM __supp_df")


def _current_month_label() -> str:
    """The reporting month: the calendar month that just closed."""
    return (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%b_%Y").upper()


def _enrich_csv_to_parquet_sql(
    source_file: Path,
    target_file: Path,
    compression: str,
    hir_div: pd.DataFrame,
    hir_sdo: pd.DataFrame,
    supp: pd.DataFrame,
) -> FileRowAudit:
    """Enrich a CSV into parquet entirely in DuckDB, accounting for every row.

    Streams instead of loading the file into memory, and shares its derivations
    with the non-enrichment path so both produce the same parquet shape.
    """
    audit = FileRowAudit(source_file=str(source_file), target_file=str(target_file))

    def _fail(reason: str) -> FileRowAudit:
        audit.outcome = "failed"
        audit.reason = reason
        return audit

    relation_sql = _resolve_csv_parquet_read_sql(str(source_file))
    try:
        with duckdb.connect() as conn:
            conn.execute("PRAGMA preserve_insertion_order=false")
            try:
                columns_info = conn.execute(
                    f"DESCRIBE SELECT * FROM {relation_sql} LIMIT 0"
                ).fetchall()
            except Exception as exc:
                return _fail(f"READ_ERROR:{exc}")

            col_names = [row[0] for row in columns_info]
            if not col_names:
                return _fail("EMPTY_DATAFRAME")

            if "ACCT_ID" not in col_names:
                # A consumer cannot exist without an account id. Still report how
                # many rows the file held, so the size of the gap is visible.
                count_row = conn.execute(f"SELECT count(*) FROM {relation_sql}").fetchone()
                audit.source_rows = int(count_row[0]) if count_row else 0
                return _fail("MISSING_ACCT_ID_COLUMN")

            status_rows = conn.execute(
                pipeline_sql.build_row_status_count_sql(relation_sql, col_names)
            ).fetchall()
            counts = {str(row[0]): int(row[1]) for row in status_rows}
            audit.source_rows = sum(counts.values())
            if audit.source_rows == 0:
                return _fail("EMPTY_DATAFRAME")

            rejected = {reason: n for reason, n in counts.items() if reason != "OK"}
            if rejected:
                audit.quarantined_rows = sum(rejected.values())
                audit.quarantine_reasons = rejected
                audit.quarantine_file = _write_quarantine_sql(
                    conn, relation_sql, col_names, target_file
                )

            if counts.get("OK", 0) == 0:
                return _fail("ALL_ROWS_REJECTED_ACCT_ID")

            _register_lookups(conn, hir_div, hir_sdo, supp)
            select_sql = pipeline_sql.build_enrichment_sql(
                relation_sql,
                col_names,
                month_label=_current_month_label(),
                enriched=True,
                hir_div_columns=tuple(hir_div.columns),
                hir_sdo_columns=tuple(hir_sdo.columns),
                supp_columns=tuple(supp.columns),
            )
            with _atomic_parquet_target(target_file) as tmp_target:
                res = conn.execute(
                    f"COPY ({select_sql}) TO {_sql_string_literal(str(tmp_target))} "
                    f"(FORMAT PARQUET, COMPRESSION {compression})"
                ).fetchone()
            audit.written_rows = int(res[0]) if res else 0
    except Exception as exc:
        return _fail(f"READ_ERROR:{exc}")

    audit.outcome = "written"
    return audit


def _write_quarantine_sql(
    conn: duckdb.DuckDBPyConnection,
    relation_sql: str,
    col_names: list[str],
    target_file: Path,
) -> str | None:
    """Persist rejected rows beside the output so the evidence survives."""
    try:
        out_dir = target_file.parent / QUARANTINE_DIR_NAME
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{target_file.stem}.ACCT_ID_INVALID.parquet"
        rejects_sql = pipeline_sql.build_rejects_sql(relation_sql, col_names)
        with _atomic_parquet_target(dest) as tmp:
            conn.execute(
                f"COPY ({rejects_sql}) TO {_sql_string_literal(str(tmp))} "
                "(FORMAT PARQUET, COMPRESSION zstd)"
            )
        return str(dest)
    except Exception:
        # Losing the quarantine copy must never fail a conversion that worked.
        return None


def _apply_csv_enrichment_pandas(
    source_file: Path,
    target_file: Path,
    compression: str,
    hir_div: pd.DataFrame,
    hir_sdo: pd.DataFrame,
    supp: pd.DataFrame,
) -> FileRowAudit:
    """RETIRED reference implementation — not used by the pipeline.

    Superseded by :func:`_enrich_csv_to_parquet_sql`, which is ~8x faster and
    streams instead of holding the whole file in memory. Kept only as the oracle
    for ``tests/backend/test_enrichment_differential.py``, which pins the SQL
    port against it. Safe to delete (along with that test,
    ``_derive_category_from_supply_type`` and ``_write_quarantine``) once one
    production month has run clean on the SQL path.
    """
    audit = FileRowAudit(source_file=str(source_file), target_file=str(target_file))

    def _fail(reason: str) -> FileRowAudit:
        audit.outcome = "failed"
        audit.reason = reason
        return audit

    # pandas spells "no compression" as None; DuckDB spells it 'none'.
    read_compression = "gzip" if _source_compression(source_file) == "gzip" else None
    try:
        df = pd.read_csv(
            source_file, encoding="utf-8", encoding_errors="replace", compression=read_compression
        )
    except pd.errors.EmptyDataError:
        try:
            df = pd.read_csv(source_file, encoding="latin-1", compression=read_compression)
        except Exception:
            return _fail("EMPTY_DATA_ERROR")
    except Exception as exc:
        return _fail(f"READ_ERROR:{exc}")

    if df.empty or len(df.columns) == 0:
        return _fail("EMPTY_DATAFRAME")

    audit.source_rows = len(df)
    # Batch-add derived columns to avoid fragmented inserts
    _pre = {}
    if "BILLED_AMOUNT" in df.columns and "TOTAL_AMT" not in df.columns:
        _pre["TOTAL_AMT"] = pd.to_numeric(df["BILLED_AMOUNT"], errors="coerce")
    if "SDO_CODE" in df.columns and "SUB_DIV_CODE" not in df.columns:
        _pre["SUB_DIV_CODE"] = _normalize_identifier_like_series(df["SDO_CODE"])
    if _pre:
        df = pd.concat([df, pd.DataFrame(_pre, index=df.index)], axis=1)
    if "ACCT_ID" not in df.columns:
        # A consumer cannot exist without an account id, and silently dropping the
        # whole file (which is what the old .get() default did) hid entire divisions.
        return _fail("MISSING_ACCT_ID_COLUMN")

    normalized_acct = _normalize_acct_id_series(df["ACCT_ID"])
    acct_status = _classify_acct_id_series(normalized_acct)
    valid_mask = acct_status.eq("OK")

    rejected = df.loc[~valid_mask]
    if not rejected.empty:
        audit.quarantined_rows = int(len(rejected))
        audit.quarantine_reasons = {
            reason: int(count) for reason, count in acct_status[~valid_mask].value_counts().items()
        }
        audit.quarantine_file = _write_quarantine(rejected, target_file, "ACCT_ID_INVALID")

    df = df.loc[valid_mask].copy()
    # Zero-pad to the canonical 10-digit width so joins line up with the master
    # table (merge_service does the same with zfill/LPAD).
    df["ACCT_ID"] = normalized_acct.loc[valid_mask].str.zfill(ACCT_ID_WIDTH)
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

    unit = _column_as_series(df, "LOAD_UNIT").astype(str).str.upper().str.strip()
    load = pd.to_numeric(_column_as_series(df, "LOAD", 0), errors="coerce").fillna(0.0)
    load_kw = pd.Series(float("nan"), index=df.index, dtype="float64")
    load_kw = load_kw.mask(unit.eq("KW"), load.round(0))
    load_kw = load_kw.mask(unit.eq("KVA"), load.round(0) * 0.9)
    load_kw = load_kw.mask(unit.isin(["HP", "BHP"]), load.round(0) * 0.746)
    # --- Bulk schema cast: build all columns into a dict, then reconstruct ---
    # Include computed columns that were not yet added to df
    month_val = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%b_%Y").upper()
    _extra = {"LOAD_KW": load_kw, "MONTH": pd.Series(month_val, index=df.index)}
    all_col_names = list(df.columns) + [c for c in _extra if c not in df.columns]

    casted = {}
    for col in all_col_names:
        src = _extra[col] if col in _extra else df[col]
        if col in MERCADOS_SCHEMA:
            dtype = str(MERCADOS_SCHEMA[col]).upper()
            if dtype == "NUMBER":
                casted[col] = pd.to_numeric(src, errors="coerce")
            elif dtype in ("VARCHAR2", "CHAR"):
                casted[col] = _normalize_identifier_like_series(src)
            elif dtype == "DATE":
                casted[col] = src
            else:
                casted[col] = _normalize_identifier_like_series(src)
        else:
            casted[col] = _normalize_identifier_like_series(src)

    # Single DataFrame construction — no fragmentation, no per-column inserts
    df = pd.DataFrame(casted, index=df.index)

    rows = len(df)
    if rows == 0:
        # Every row was quarantined. Still a file-level failure, but the rows are
        # on disk under _quarantine/ rather than gone.
        return _fail("ALL_ROWS_REJECTED_ACCT_ID")

    with _atomic_parquet_target(target_file) as tmp_target:
        df.to_parquet(tmp_target, compression=compression, index=False)

    audit.outcome = "written"
    audit.written_rows = rows
    return audit


# The SQL implementation is the one the pipeline uses; the pandas version above
# is retained only as the differential-test oracle.
_apply_csv_enrichment = _enrich_csv_to_parquet_sql


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


@contextmanager
def _atomic_parquet_target(target: Path) -> Iterator[Path]:
    """Yield a temp path, then atomically move it onto *target* on success.

    Writing straight to the final name means a crash or cancellation mid-write
    leaves a truncated or zero-byte parquet at the path everything else treats
    as "already converted". The leading dot also keeps the temp file out of
    ``**/*.parquet`` globs while it is being written.
    """
    tmp = target.parent / f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        yield tmp
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _parquet_row_count(path: Path) -> int | None:
    """Row count read from the parquet footer, or None when unreadable.

    None means the file is corrupt, zero-byte, or not parquet at all — which is
    exactly the state a crashed write leaves behind. Footer-only, so this costs
    nothing even on multi-GB files.
    """
    try:
        with duckdb.connect() as conn:
            row = conn.execute(
                "SELECT sum(num_rows) FROM parquet_file_metadata(?)", [str(path)]
            ).fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


def _classify_existing_target(target: Path, overwrite: bool) -> tuple[str, int]:
    """Decide what to do with an existing parquet target.

    Returns one of ``("convert", 0)``, ``("reuse", rows)`` or ``("repair", 0)``.
    Testing existence alone is what made a zero-byte parquet permanent: it was
    skipped forever by this stage and filtered out of the build by the size gate.
    """
    if not target.exists():
        return "convert", 0
    if overwrite:
        return "convert", 0
    rows = _parquet_row_count(target)
    if rows is None or rows == 0:
        return "repair", 0
    return "reuse", rows


def _classify_input_file(path_str: str) -> tuple[bool, str]:
    """Whether *path_str* can be read, and why not when it can't.

    Reasons: ``NOT_A_FILE``, ``QUARANTINED``, ``TEMP_PARQUET`` (a write in
    flight — benign), ``PARQUET_TOO_SMALL`` and ``STAT_ERROR`` (corrupt — the
    caller should refuse to build rather than quietly drop the rows).
    """
    path = Path(path_str)
    if not path.is_file():
        return False, "NOT_A_FILE"
    if QUARANTINE_DIR_NAME in path.parts:
        return False, "QUARANTINED"
    if path.suffix.lower() != ".parquet":
        return True, ""
    name = path.name.lower()
    if name.startswith("tmp_") or name.startswith("."):
        return False, "TEMP_PARQUET"
    try:
        if path.stat().st_size < MIN_PARQUET_FILE_BYTES:
            return False, "PARQUET_TOO_SMALL"
    except OSError:
        return False, "STAT_ERROR"
    return True, ""


def _is_readable_input_file(path_str: str) -> bool:
    usable, _reason = _classify_input_file(path_str)
    return usable


def _resolve_relation_sql(input_path: str, *, _cached_files: list[str] | None = None) -> str:
    """Build a DuckDB relation SQL from an input path.

    If *_cached_files* is given it is used directly, skipping a redundant
    ``glob.glob`` (the caller already resolved the file list).
    """
    lowered = input_path.lower()
    input_path_sql = _sql_string_literal(input_path)

    if ".parquet" in lowered:
        matches = _cached_files or [
            item for item in glob.glob(input_path, recursive=True)
            if _is_readable_input_file(item)
        ]
        if matches:
            return f"read_parquet({_sql_string_list_literal(sorted(matches))}, union_by_name = true, hive_partitioning = false)"
        return f"read_parquet({input_path_sql}, union_by_name = true, hive_partitioning = false)"
    if ".csv" in lowered or ".tsv" in lowered or lowered.endswith(".gz") or ".gz" in lowered:
        return f"read_csv_auto({input_path_sql}, union_by_name = true, filename = true)"

    matches = _cached_files or [
        item for item in glob.glob(input_path, recursive=True)
        if _is_readable_input_file(item)
    ]
    if matches:
        sample = matches[0].lower()
        if sample.endswith(".parquet"):
            return f"read_parquet({_sql_string_list_literal(sorted(matches))}, union_by_name = true, hive_partitioning = false)"
        if (
            sample.endswith(".csv")
            or sample.endswith(".csv.gz")
            or sample.endswith(".tsv")
            or sample.endswith(".gz")
        ):
            return f"read_csv_auto({input_path_sql}, union_by_name = true, filename = true)"

    raise ValueError(f"No readable files matched '{input_path}'.")




def _is_gzip_file(path: Path) -> bool:
    """True when the file really starts with the gzip magic bytes."""
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"\x1f\x8b"
    except OSError:
        return False


def _source_compression(path: Path) -> str:
    """Compression to read *path* with: 'gzip' or 'none'.

    A ``.gz`` name is not proof of gzip content — operators do produce plain-text
    files with a ``.gz`` extension. Reading those with gzip inference fails, and
    that failure used to be swallowed into a silent file skip, so detect it from
    the magic bytes instead of the filename.
    """
    if path.suffix.lower() != ".gz":
        return "none"
    return "gzip" if _is_gzip_file(path) else "none"


def _validate_gzip_file(path: Path) -> tuple[bool, str | None]:
    """Cheap pre-validation of a ``.gz`` source.

    Only the 2-byte magic is checked. Fully decompressing every file here cost
    ~0.29s/file and still let truncated archives through as "valid" on the
    strength of their first five rows — a truncation now surfaces as a real,
    counted error during conversion instead of a silent partial parquet.
    """
    if path.suffix.lower() != ".gz":
        return True, None
    try:
        if _is_gzip_file(path):
            return True, None
        # Plain text wearing a .gz extension — readable, but say so.
        with path.open("rb") as handle:
            sample = handle.read(4096)
        if not sample.strip():
            return False, "EMPTY_FILE"
        return True, "PLAIN_TEXT_GZ_FALLBACK"
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
    # No sample_size override: with all_varchar = true the sniffer only needs the
    # dialect and header, so a full-file sample buys nothing and measurably hurts
    # (1.09s vs 0.66s on a 103k-row file, and it collapses cross-file parallelism).
    input_path_sql = _sql_string_literal(input_path)
    # DuckDB infers compression from the extension, which is wrong for plain-text
    # files named .gz; pin it from the magic bytes instead.
    compression = _source_compression(Path(input_path))
    return (
        f"read_csv({input_path_sql}, union_by_name = true, filename = true, auto_detect = true, "
        f"all_varchar = true, compression = {_sql_string_literal(compression)})"
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

def _execute_build_duckdb(payload: BuildDuckDbRequest) -> BuildOutcome:
    normalized_object_name = _normalize_master_object_name(payload.object_name, payload.object_type, payload.month_label)
    if not VALID_OBJECT_NAME.fullmatch(normalized_object_name):
        raise ValueError("object_name must start with letter/_ and use only letters, numbers, underscore.")

    db_path = Path(sanitize_local_path_input(payload.db_path, "db_path")).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    object_sql = f'"{ normalized_object_name.replace(chr(34), chr(34) * 2)}"'
    resolved_input = _resolve_parquet_only_glob(payload.input_path)

    # Cache the file list once so _resolve_relation_sql doesn't re-glob.
    # A corrupt parquet here must stop the build: silently excluding it is how a
    # whole division disappeared from the master table without any error.
    cached_files: list[str] = []
    excluded_files: list[str] = []
    for item in glob.glob(resolved_input, recursive=True):
        usable, reason = _classify_input_file(item)
        if usable:
            cached_files.append(item)
            continue
        excluded_files.append(f"{item} ({reason})")
        if reason in {"PARQUET_TOO_SMALL", "STAT_ERROR"}:
            raise ValueError(
                f"Corrupt or empty parquet in the build input: {item} ({reason}). "
                "Delete it and re-run CSV→Parquet for that source, or the table would "
                "silently be built without those rows."
            )
    relation_sql = _resolve_relation_sql(resolved_input, _cached_files=cached_files)

    # Expected row count straight from the parquet footers — no data scan.
    parquet_input_rows: int | None = None
    if cached_files:
        try:
            with duckdb.connect() as meta_conn:
                row = meta_conn.execute(
                    "SELECT sum(num_rows) FROM parquet_file_metadata("
                    f"{_sql_string_list_literal(sorted(cached_files))})"
                ).fetchone()
            parquet_input_rows = int(row[0]) if row and row[0] is not None else None
        except Exception:
            parquet_input_rows = None

    # Temporarily release the dashboard's singleton connection to avoid
    # DuckDB write-write conflicts (DuckDB allows only one writer at a time).
    from backend.api.deps import get_db_service  # local import: avoids an api↔services cycle

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

    table_rows: int | None = None
    try:
        with duckdb.connect(str(db_path)) as conn:
            thread_count = max(1, os.cpu_count() or 1)
            conn.execute(f"PRAGMA threads={thread_count}")
            conn.execute("PRAGMA preserve_insertion_order=false")

            if payload.object_type == "VIEW":
                # A view holds no rows, so there is nothing to stage or lose.
                if payload.replace:
                    conn.execute(f"DROP VIEW IF EXISTS {object_sql}")
                    conn.execute(f"DROP TABLE IF EXISTS {object_sql}")
                conn.execute(f"CREATE VIEW {object_sql} AS {select_sql}")
            else:
                # Build into a staging table and swap only once the row count is
                # verified. Dropping first meant a failed or short build destroyed
                # the previous good table with nothing to fall back on.
                staging_name = f"{normalized_object_name}__staging_{uuid.uuid4().hex[:8]}"
                staging_sql = f'"{staging_name}"'
                try:
                    conn.execute(f"CREATE TABLE {staging_sql} AS {select_sql}")
                    count_row = conn.execute(f"SELECT count(*) FROM {staging_sql}").fetchone()
                    table_rows = int(count_row[0]) if count_row else 0

                    if parquet_input_rows is not None and table_rows != parquet_input_rows:
                        raise ValueError(
                            f"Row count mismatch: parquet inputs hold {parquet_input_rows:,} rows "
                            f"but the built table has {table_rows:,}. "
                            f"{normalized_object_name} was left untouched."
                        )

                    conn.execute("BEGIN")
                    try:
                        if payload.replace:
                            conn.execute(f"DROP VIEW IF EXISTS {object_sql}")
                            conn.execute(f"DROP TABLE IF EXISTS {object_sql}")
                        conn.execute(f"ALTER TABLE {staging_sql} RENAME TO {object_sql}")
                        conn.execute("COMMIT")
                    except Exception:
                        conn.execute("ROLLBACK")
                        raise
                finally:
                    conn.execute(f"DROP TABLE IF EXISTS {staging_sql}")
    finally:
        # Reconnect the dashboard so the user can immediately see the new table.
        if dashboard_was_connected:
            try:
                svc.connect(str(db_path))
            except Exception:
                pass  # Non-fatal: user can manually reconnect from the UI.

    period_suffix = f" for {(payload.month_label or '').strip()}" if (payload.month_label or "").strip() else ""
    message = f"Created {payload.object_type} {normalized_object_name}{period_suffix}."
    if table_rows is not None:
        message += f" {table_rows:,} rows."
    if excluded_files:
        message += f" Excluded inputs: {len(excluded_files)}."
    return BuildOutcome(
        output_path=str(db_path),
        message=message,
        parquet_input_rows=parquet_input_rows,
        table_rows=table_rows,
        excluded_input_files=tuple(excluded_files),
    )


def _run_build_duckdb_job(job_id: str, payload: BuildDuckDbRequest) -> None:
    try:
        job_runtime.raise_if_cancelled(job_id)
        _update_build_job(job_id, progress_percent=25, message="Preparing build...")
        outcome = _execute_build_duckdb(payload)
        row_fields = {
            "parquet_input_rows": outcome.parquet_input_rows,
            "table_rows": outcome.table_rows,
            "row_delta": outcome.row_delta,
            "excluded_input_files": list(outcome.excluded_input_files),
            "data_quality": outcome.data_quality,
        }
        if job_runtime.is_cancelled(job_id):
            _update_build_job(
                job_id,
                status="cancelled",
                message="Stop requested. Build finished but marked cancelled.",
                output_path=outcome.output_path,
                progress_percent=100,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                **row_fields,
            )
            return
        _update_build_job(
            job_id,
            status="completed",
            message=outcome.message,
            output_path=outcome.output_path,
            progress_percent=100,
            finished_at=datetime.now().isoformat(timespec="seconds"),
            **row_fields,
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
    """Build a SELECT with per-column casts.

    When the source is Parquet the CSV→Parquet step already stripped '.0'
    suffixes and normalised strings, so we use a cheap CAST instead of
    REGEXP_REPLACE (which runs a regex per-cell and is the main bottleneck).
    """
    from_parquet = "read_parquet" in relation_sql
    select_exprs = []
    for col in col_names:
        if col == "DISCOM": 
            continue
        expr = f'"{ col}"'
        if col in MERCADOS_SCHEMA:
            dtype = str(MERCADOS_SCHEMA[col]).upper()
            if dtype == "NUMBER":
                # TRY_CAST, not CAST: one unparseable value used to abort the whole
                # CREATE — after the old code had already dropped the good table.
                # This also matches pd.to_numeric(errors="coerce") in the pandas path.
                expr = f'TRY_CAST("{col}" AS DOUBLE)'
            elif dtype in ("VARCHAR2", "CHAR"):
                # Parquet data is already normalised; skip expensive regex
                expr = f'CAST("{col}" AS VARCHAR)' if from_parquet else _sql_varchar_normalize_expr(col)
            elif dtype == "DATE":
                pass
            else:
                expr = f'CAST("{col}" AS VARCHAR)' if from_parquet else _sql_varchar_normalize_expr(col)
        else:
            expr = f'CAST("{col}" AS VARCHAR)' if from_parquet else _sql_varchar_normalize_expr(col)
        select_exprs.append(f'{expr} AS "{col}"')

    if "DIV_CODE" in col_names:
        select_exprs.append(_discom_case_sql('"DIV_CODE"'))

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
        reused_rows = 0
        ledger = ConversionLedger()
        for item in invalid_files:
            ledger.record(
                FileRowAudit(source_file=item["file"], outcome="failed", reason=item["reason"])
            )

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
                action, existing_rows = _classify_existing_target(target_file, payload.overwrite_parquet)
                if action == "reuse":
                    skipped_files += 1
                    reused_rows += existing_rows
                    parquet_skipped_details.append(f"{source_file} (ALREADY_EXISTS)")
                    ledger.record(
                        FileRowAudit(
                            source_file=str(source_file),
                            target_file=str(target_file),
                            outcome="reused",
                            reason="ALREADY_EXISTS",
                            source_rows=existing_rows,
                            written_rows=existing_rows,
                        )
                    )
                    _update_csv_job(
                        job_id,
                        processed_files=index,
                        skipped_files=skipped_files,
                        parquet_skipped_details=parquet_skipped_details,
                        current_file=str(source_file),
                        message=f"Skipping existing parquet file ({index}/{len(valid_files)}).",
                        **ledger.as_snapshot(),
                    )
                    continue
                if action == "repair":
                    # Zero-byte or unreadable target from a crashed/cancelled write.
                    # Rebuilding is the whole point — never skip it as "already done".
                    target_file.unlink(missing_ok=True)
                    parquet_skipped_details.append(f"{source_file} (CORRUPT_PARQUET_REBUILT)")
                elif target_file.exists():
                    target_file.unlink()
                _update_csv_job(
                    job_id,
                    processed_files=index - 1,
                    skipped_files=skipped_files,
                    current_file=str(source_file),
                    message=f"Processing file {index}/{len(valid_files)}...",
                )
                if lookup_mode:
                    audit = _apply_csv_enrichment(source_file, target_file, payload.compression, hir_div, hir_sdo, supp)
                    ledger.record(audit)
                    if audit.outcome == "failed":
                        skipped_files += 1
                        parquet_skipped_details.append(f"{source_file} ({audit.reason})")
                        _update_csv_job(
                            job_id,
                            processed_files=index,
                            skipped_files=skipped_files,
                            parquet_skipped_details=parquet_skipped_details,
                            message=f"Skipping file ({index}/{len(valid_files)}) - {audit.reason}.",
                            **ledger.as_snapshot(),
                        )
                        continue
                    total_output_rows += audit.written_rows
                else:
                    relation_sql = _resolve_csv_parquet_read_sql(str(source_file))

                    columns_info = conn.execute(f"DESCRIBE SELECT * FROM {relation_sql} LIMIT 0").fetchall()
                    col_names = [row[0] for row in columns_info]
                    select_sql = _build_select_sql_for_schema(relation_sql, col_names)

                    with _atomic_parquet_target(target_file) as tmp_target:
                        res = conn.execute(
                            f"COPY ({select_sql}) TO {_sql_string_literal(str(tmp_target))} "
                            f"(FORMAT PARQUET, COMPRESSION {compression_sql})"
                        ).fetchone()
                    written = int(res[0]) if res else 0
                    total_output_rows += written
                    # One scan reads and writes, and read_csv raises rather than
                    # dropping malformed rows, so source == written here.
                    ledger.record(
                        FileRowAudit(
                            source_file=str(source_file),
                            target_file=str(target_file),
                            outcome="written",
                            source_rows=written,
                            written_rows=written,
                        )
                    )
                _update_csv_job(
                    job_id,
                    processed_files=index,
                    skipped_files=skipped_files,
                    parquet_skipped_details=parquet_skipped_details,
                    total_output_rows=total_output_rows,
                    **ledger.as_snapshot(),
                )

        skipped_str = f" Skipped: {skipped_files}." if skipped_files > 0 else "."
        totals = ledger.totals()
        _update_csv_job(
            job_id,
            status="completed",
            current_file=None,
            message=(
                f"Parquet conversion completed successfully for {len(valid_files)} file(s).{skipped_str}"
                + (" Enrichment applied (HIR + suppMapper + LOAD_KW)." if lookup_mode else "")
                + (f" Invalid gzip files: {len(invalid_files)}." if invalid_files else "")
                + (f" Plain-text .gz fallback files: {len(warning_files)}." if warning_files else "")
                + (f" Quarantined rows: {totals.quarantined_rows:,}." if totals.quarantined_rows else "")
                + (f" ROW LOSS: {totals.unaccounted_rows:,} rows unaccounted for." if totals.unaccounted_rows else "")
            ),
            finished_at=datetime.now().isoformat(timespec="seconds"),
            skipped_files=skipped_files,
            **ledger.as_snapshot(),
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


def execute_csv_to_parquet(payload: CsvToParquetRequest) -> SidebarToolResponse:
    """Convert matched CSV/gz sources to Parquet synchronously.

    The response carries the row accounting (written, quarantined, and a
    ``data_quality`` verdict) so a caller can tell a clean run from one that
    silently shed rows.
    """
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

    def _suffixes() -> str:
        return (
            (" Enrichment applied (HIR + suppMapper + LOAD_KW)." if lookup_mode else "")
            + (f" Invalid gzip files: {len(invalid_files)}." if invalid_files else "")
            + (f" Plain-text .gz fallback files: {len(warning_files)}." if warning_files else "")
        )

    ledger = ConversionLedger()
    for item in invalid_files:
        ledger.record(FileRowAudit(source_file=item["file"], outcome="failed", reason=item["reason"]))

    def _respond(message: str, path: str) -> SidebarToolResponse:
        totals = ledger.totals()
        return SidebarToolResponse(
            message=(
                message
                + (f" Quarantined rows: {totals.quarantined_rows:,}." if totals.quarantined_rows else "")
                + (
                    f" ROW LOSS: {totals.unaccounted_rows:,} rows unaccounted for."
                    if totals.unaccounted_rows
                    else ""
                )
            ),
            output_path=path,
            rows_written=totals.written_rows + totals.reused_rows,
            rows_quarantined=totals.quarantined_rows,
            data_quality=ledger.data_quality(),
        )

    # Single-file mode keeps backward compatibility when output is an explicit parquet file.
    if len(matched_files) == 1 and output_path.suffix.lower() == ".parquet":
        action, existing_rows = _classify_existing_target(output_path, payload.overwrite_parquet)
        if action == "reuse":
            ledger.record(
                FileRowAudit(
                    source_file=str(matched_files[0]),
                    target_file=str(output_path),
                    outcome="reused",
                    reason="ALREADY_EXISTS",
                    source_rows=existing_rows,
                    written_rows=existing_rows,
                )
            )
            return _respond("Skipped conversion because output parquet already exists.", str(output_path))
        if action == "repair":
            output_path.unlink(missing_ok=True)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        relation_sql = _resolve_csv_parquet_read_sql(str(matched_files[0]))
        with duckdb.connect() as conn:
            if lookup_mode:
                audit = _apply_csv_enrichment(
                    matched_files[0], output_path, payload.compression, hir_div, hir_sdo, supp
                )
                ledger.record(audit)
                if audit.outcome == "failed":
                    raise ValueError(f"Enrichment failed for {matched_files[0]}: {audit.reason}")
            else:
                columns_info = conn.execute(f"DESCRIBE SELECT * FROM {relation_sql} LIMIT 0").fetchall()
                select_sql = _csv_to_parquet_select_sql(relation_sql, [row[0] for row in columns_info])
                with _atomic_parquet_target(output_path) as tmp_target:
                    res = conn.execute(
                        f"COPY ({select_sql}) TO {_sql_string_literal(str(tmp_target))} "
                        f"(FORMAT PARQUET, COMPRESSION {compression_sql})"
                    ).fetchone()
                written = int(res[0]) if res else 0
                ledger.record(
                    FileRowAudit(
                        source_file=str(matched_files[0]),
                        target_file=str(output_path),
                        outcome="written",
                        source_rows=written,
                        written_rows=written,
                    )
                )
        return _respond("Parquet conversion completed successfully." + _suffixes(), str(output_path))

    # Multi-file mode writes parquet files preserving input relative folder structure.
    output_root = output_path if output_path.suffix.lower() != ".parquet" else output_path.parent
    output_root.mkdir(parents=True, exist_ok=True)
    input_root = _infer_input_root(resolved_input, matched_files)

    converted_count = 0
    skipped_count = len(invalid_files)
    reused_rows = 0
    skipped_details: list[str] = [f"{item['file']} ({item['reason']})" for item in invalid_files]
    with duckdb.connect() as conn:
        for source_file in matched_files:
            target_file = _parquet_target_for_input(output_root, input_root, source_file)
            target_file.parent.mkdir(parents=True, exist_ok=True)
            action, existing_rows = _classify_existing_target(target_file, payload.overwrite_parquet)
            if action == "reuse":
                skipped_count += 1
                reused_rows += existing_rows
                skipped_details.append(f"{source_file} (ALREADY_EXISTS)")
                ledger.record(
                    FileRowAudit(
                        source_file=str(source_file),
                        target_file=str(target_file),
                        outcome="reused",
                        reason="ALREADY_EXISTS",
                        source_rows=existing_rows,
                        written_rows=existing_rows,
                    )
                )
                continue
            if action == "repair":
                target_file.unlink(missing_ok=True)
                skipped_details.append(f"{source_file} (CORRUPT_PARQUET_REBUILT)")
            if lookup_mode:
                audit = _apply_csv_enrichment(
                    source_file, target_file, payload.compression, hir_div, hir_sdo, supp
                )
                ledger.record(audit)
                if audit.outcome == "failed":
                    skipped_count += 1
                    skipped_details.append(f"{source_file} ({audit.reason})")
                    continue
            else:
                relation_sql = _resolve_csv_parquet_read_sql(str(source_file))
                columns_info = conn.execute(f"DESCRIBE SELECT * FROM {relation_sql} LIMIT 0").fetchall()
                select_sql = _csv_to_parquet_select_sql(relation_sql, [row[0] for row in columns_info])
                with _atomic_parquet_target(target_file) as tmp_target:
                    res = conn.execute(
                        f"COPY ({select_sql}) TO {_sql_string_literal(str(tmp_target))} "
                        f"(FORMAT PARQUET, COMPRESSION {compression_sql})"
                    ).fetchone()
                written = int(res[0]) if res else 0
                ledger.record(
                    FileRowAudit(
                        source_file=str(source_file),
                        target_file=str(target_file),
                        outcome="written",
                        source_rows=written,
                        written_rows=written,
                    )
                )
            converted_count += 1

    skipped_str = f" Skipped existing/invalid: {skipped_count}." if skipped_count > 0 else "."
    message = f"Parquet conversion completed successfully for {converted_count} file(s).{skipped_str}" + _suffixes()
    return _respond(message, str(output_root))


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
        reused_rows = 0
        ledger = ConversionLedger()
        for item in invalid_files:
            ledger.record(
                FileRowAudit(source_file=item["file"], outcome="failed", reason=item["reason"])
            )

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

                action, existing_rows = _classify_existing_target(target_file, payload.overwrite_parquet)
                if action == "reuse":
                    skipped_files += 1
                    reused_rows += existing_rows
                    parquet_skipped_details.append(f"{source_file} (ALREADY_EXISTS)")
                    ledger.record(
                        FileRowAudit(
                            source_file=str(source_file),
                            target_file=str(target_file),
                            outcome="reused",
                            reason="ALREADY_EXISTS",
                            source_rows=existing_rows,
                            written_rows=existing_rows,
                        )
                    )
                    parquet_pct = int((index / total_valid) * 70)
                    _update(
                        parquet_processed_files=index,
                        parquet_skipped_files=skipped_files,
                        parquet_skipped_details=parquet_skipped_details,
                        parquet_current_file=str(source_file),
                        message=f"Phase 1: Skipping existing file ({index}/{total_valid}).",
                        overall_progress_percent=min(70, parquet_pct),
                        **ledger.as_snapshot(),
                    )
                    continue
                if action == "repair":
                    target_file.unlink(missing_ok=True)
                    parquet_skipped_details.append(f"{source_file} (CORRUPT_PARQUET_REBUILT)")
                elif target_file.exists():
                    target_file.unlink()

                parquet_pct = int(((index - 1) / total_valid) * 70)
                _update(
                    parquet_processed_files=index - 1,
                    parquet_skipped_files=skipped_files,
                    parquet_current_file=str(source_file),
                    message=f"Phase 1: Processing file {index}/{total_valid}…",
                    overall_progress_percent=min(70, parquet_pct),
                )

                if lookup_mode:
                    audit = _apply_csv_enrichment(source_file, target_file, payload.compression, hir_div, hir_sdo, supp)
                    ledger.record(audit)
                    if audit.outcome == "failed":
                        skipped_files += 1
                        parquet_skipped_details.append(f"{source_file} ({audit.reason})")
                        _update(
                            parquet_processed_files=index,
                            parquet_skipped_files=skipped_files,
                            parquet_skipped_details=parquet_skipped_details,
                            message=f"Phase 1: Skipping file ({index}/{total_valid}) - {audit.reason}.",
                            **ledger.as_snapshot(),
                        )
                        continue
                    total_output_rows += audit.written_rows
                else:
                    relation_sql = _resolve_csv_parquet_read_sql(str(source_file))

                    columns_info = conn.execute(f"DESCRIBE SELECT * FROM {relation_sql} LIMIT 0").fetchall()
                    col_names = [row[0] for row in columns_info]
                    select_sql = _build_select_sql_for_schema(relation_sql, col_names)

                    with _atomic_parquet_target(target_file) as tmp_target:
                        res = conn.execute(
                            f"COPY ({select_sql}) TO {_sql_string_literal(str(tmp_target))} "
                            f"(FORMAT PARQUET, COMPRESSION {compression_sql})"
                        ).fetchone()
                    written = int(res[0]) if res else 0
                    total_output_rows += written
                    ledger.record(
                        FileRowAudit(
                            source_file=str(source_file),
                            target_file=str(target_file),
                            outcome="written",
                            source_rows=written,
                            written_rows=written,
                        )
                    )

                parquet_pct = int((index / total_valid) * 70)
                _update(
                    parquet_processed_files=index,
                    parquet_skipped_files=skipped_files,
                    parquet_skipped_details=parquet_skipped_details,
                    total_output_rows=total_output_rows,
                    overall_progress_percent=min(70, parquet_pct),
                    **ledger.as_snapshot(),
                )

        skipped_str = f" {skipped_files} skipped." if skipped_files > 0 else ""
        phase1_totals = ledger.totals()
        parquet_summary = (
            f"Parquet done: {total_valid} file(s).{skipped_str}"
            + (" Enrichment applied." if lookup_mode else "")
            + (f" Quarantined rows: {phase1_totals.quarantined_rows:,}." if phase1_totals.quarantined_rows else "")
        )

        _update(
            current_phase="csv_to_parquet",
            parquet_processed_files=total_valid,
            parquet_current_file=None,
            message=f"Phase 1 complete. {parquet_summary} Starting Phase 2…",
            overall_progress_percent=70,
            **ledger.as_snapshot(),
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
            build_outcome = _execute_build_duckdb(build_payload)
        except Exception as build_exc:
            _update(
                status="failed",
                current_phase="build_duckdb",
                message=f"Phase 2 failed: {build_exc}. {parquet_summary}",
                build_progress_percent=100,
                overall_progress_percent=100,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                **ledger.as_snapshot(),
            )
            raise

        if job_runtime.is_cancelled(job_id):
            _update(
                status="cancelled",
                current_phase="build_duckdb",
                message=f"Pipeline stopped. Build ran but marked cancelled. {parquet_summary}",
                build_output_path=build_outcome.output_path,
                build_progress_percent=100,
                overall_progress_percent=100,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            return

        snapshot = ledger.as_snapshot()
        if build_outcome.data_quality != "ok" and snapshot["data_quality"] == "ok":
            snapshot["data_quality"] = build_outcome.data_quality
        _update(
            status="completed",
            current_phase="completed",
            message=(
                f"Pipeline complete. {parquet_summary} {build_outcome.message}"
                + (
                    f" ROW LOSS: {phase1_totals.unaccounted_rows:,} rows unaccounted for."
                    if phase1_totals.unaccounted_rows
                    else ""
                )
            ),
            build_output_path=build_outcome.output_path,
            build_progress_percent=100,
            overall_progress_percent=100,
            parquet_input_rows=build_outcome.parquet_input_rows,
            table_rows=build_outcome.table_rows,
            finished_at=datetime.now().isoformat(timespec="seconds"),
            **snapshot,
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
