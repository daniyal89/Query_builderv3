"""Differential test: the SQL enrichment must match the pandas one it replaces.

The pandas implementation (`_apply_csv_enrichment_pandas`) is kept solely as the
oracle for this test. Both are run over the same fixtures and their parquet
output compared column-by-column; the SQL version is what the pipeline uses.

Known, deliberate differences are asserted explicitly at the bottom rather than
being papered over.
"""

from pathlib import Path

import duckdb
import pytest

from backend.services.sidebar_tools_service import (
    _apply_csv_enrichment_pandas,
    _enrich_csv_to_parquet_sql,
    _load_lookup_tables,
)


HIR = (
    "DIV_CODE,DISCOM,CIR_SP_ID,ZON_SP_ID,DIV_NAME,CIRCLE_NAME,ZONE_NAME,SDO_SP_ID,SDO_NAME\n"
    "DIV100,DVVNL,C1,Z1,Div A,Circle A,Zone A,SDO100,Sub Div A\n"
    "DIV205,PVVNL,C2,Z2,Div B,Circle B,Zone B,SDO205,Sub Div B\n"
)
SUPP = "SUPPLY_TYPE,SUPPLY_TYPE_NAME\n49,LMV\n100,LMV-10\n11A,LMV-11\nH2,HV\n"


@pytest.fixture
def lookups(tmp_path: Path):
    hir = tmp_path / "hir.csv"
    hir.write_text(HIR, encoding="utf-8")
    supp = tmp_path / "supp.csv"
    supp.write_text(SUPP, encoding="utf-8")
    return _load_lookup_tables(str(hir), str(supp))


def _read(path: Path) -> tuple[list[str], list[tuple]]:
    con = duckdb.connect()
    result = con.execute(f"SELECT * FROM read_parquet('{path.as_posix()}')")
    columns = [desc[0] for desc in result.description]
    rows = result.fetchall()
    return columns, rows


def _run_both(tmp_path: Path, csv_text: str, lookups) -> tuple[tuple, tuple]:
    hir_div, hir_sdo, supp = lookups
    source = tmp_path / "input.csv"
    source.write_text(csv_text, encoding="utf-8")

    pandas_target = tmp_path / "pandas.parquet"
    sql_target = tmp_path / "sql.parquet"

    pandas_audit = _apply_csv_enrichment_pandas(source, pandas_target, "zstd", hir_div, hir_sdo, supp)
    sql_audit = _enrich_csv_to_parquet_sql(source, sql_target, "zstd", hir_div, hir_sdo, supp)

    assert pandas_audit.outcome == sql_audit.outcome, (pandas_audit, sql_audit)
    assert pandas_audit.source_rows == sql_audit.source_rows
    assert pandas_audit.written_rows == sql_audit.written_rows
    assert pandas_audit.quarantined_rows == sql_audit.quarantined_rows
    assert pandas_audit.quarantine_reasons == sql_audit.quarantine_reasons

    if pandas_audit.outcome != "written":
        return ((), ()), ((), ())
    return _read(pandas_target), _read(sql_target)


# `filename` is provenance that the DuckDB (non-enrichment) branch has always
# emitted. Unifying the two branches means the enriched output carries it too.
DELIBERATE_SQL_ONLY_COLUMNS = {"filename"}


def _assert_same(pandas_out, sql_out) -> None:
    (pandas_cols, pandas_rows), (sql_cols, sql_rows) = pandas_out, sql_out
    if not pandas_cols and not sql_cols:
        return  # both paths failed identically; the audit assertions already checked that

    sql_only = set(sql_cols) - set(pandas_cols)
    assert sql_only <= DELIBERATE_SQL_ONLY_COLUMNS, f"unexpected new columns: {sorted(sql_only)}"
    assert not set(pandas_cols) - set(sql_cols), (
        f"columns lost in the SQL port: {sorted(set(pandas_cols) - set(sql_cols))}"
    )

    # Row order is not meaningful here and the SQL path runs with
    # preserve_insertion_order=false, so compare as sorted sets of rows.
    def _sorted(rows: list[tuple]) -> list[tuple]:
        return sorted(rows, key=lambda row: tuple("" if v is None else str(v) for v in row))

    pandas_rows = _sorted(pandas_rows)
    sql_rows = _sorted(sql_rows)

    # Compare values column-by-column so a mismatch names the column.
    pandas_by_col = {name: [row[i] for row in pandas_rows] for i, name in enumerate(pandas_cols)}
    sql_by_col = {name: [row[i] for row in sql_rows] for i, name in enumerate(sql_cols)}
    for name in pandas_cols:
        assert pandas_by_col[name] == sql_by_col[name], (
            f"column {name!r} differs\n  pandas: {pandas_by_col[name]}\n  sql:    {sql_by_col[name]}"
        )


def test_differential_full_row(tmp_path: Path, lookups) -> None:
    csv_text = (
        "ACCT_ID,DIV_CODE,SDO_CODE,SUPPLY_TYPE,LOAD,LOAD_UNIT,BILLED_AMOUNT\n"
        "1001,DIV100,SDO100,49,5,KW,1234.50\n"
        "0000002002,DIV205,SDO205,100,10,KVA,99\n"
        "3003,DIV100,SDO100,11A,7,HP,0\n"
        "4004,DIV205,SDO205,H2,3,BHP,55.5\n"
    )
    _assert_same(*_run_both(tmp_path, csv_text, lookups))


def test_differential_dirty_acct_ids(tmp_path: Path, lookups) -> None:
    csv_text = (
        "ACCT_ID,DIV_CODE,SUPPLY_TYPE\n"
        "123456,DIV100,49\n"
        " 987 ,DIV100,49\n"
        '"1,234",DIV100,49\n'
        "1234.0,DIV100,49\n"
        ",DIV100,49\n"
        "A1234,DIV100,49\n"
        "12345678901,DIV100,49\n"
    )
    _assert_same(*_run_both(tmp_path, csv_text, lookups))


def test_differential_no_lookup_matches(tmp_path: Path, lookups) -> None:
    csv_text = (
        "ACCT_ID,DIV_CODE,SDO_CODE,SUPPLY_TYPE,LOAD,LOAD_UNIT\n"
        "1001,DIV999,SDO999,ZZZ,5,KW\n"
    )
    _assert_same(*_run_both(tmp_path, csv_text, lookups))


def test_differential_minimal_columns(tmp_path: Path, lookups) -> None:
    _assert_same(*_run_both(tmp_path, "ACCT_ID\n1001\n2002\n", lookups))


def test_differential_missing_load_unit(tmp_path: Path, lookups) -> None:
    csv_text = "ACCT_ID,DIV_CODE,LOAD\n1001,DIV100,5\n"
    _assert_same(*_run_both(tmp_path, csv_text, lookups))


def test_differential_supply_type_variants(tmp_path: Path, lookups) -> None:
    csv_text = (
        "ACCT_ID,SUPPLY_TYPE\n"
        "1,49\n2,100\n3,107\n4,11\n5,11A\n6,H2\n7,H9X\n8,ZZZ\n9,\n10,1\n"
    )
    _assert_same(*_run_both(tmp_path, csv_text, lookups))


# ── Deliberate improvements over the pandas implementation ────────────────────
#
# These are the only value-level differences on real data, and in every case the
# SQL path preserves what the source file actually said while pandas reformatted
# it through float64 or its own NA handling.


def test_sql_preserves_source_text_that_pandas_mangled(tmp_path: Path, lookups) -> None:
    hir_div, hir_sdo, supp = lookups
    source = tmp_path / "input.csv"
    source.write_text(
        "ACCT_ID,PRESYS_CODE,LATITUDE,CA\n"
        "1001,NA,26.415439999999997,-.2\n"
        "1002,DV02,26.41567,-0.21\n",
        encoding="utf-8",
    )

    pandas_target = tmp_path / "pandas.parquet"
    sql_target = tmp_path / "sql.parquet"
    _apply_csv_enrichment_pandas(source, pandas_target, "zstd", hir_div, hir_sdo, supp)
    _enrich_csv_to_parquet_sql(source, sql_target, "zstd", hir_div, hir_sdo, supp)

    def values(path: Path, col: str) -> list:
        return [
            row[0]
            for row in duckdb.connect()
            .execute(f'SELECT "{col}" FROM read_parquet(\'{path.as_posix()}\') ORDER BY ACCT_ID')
            .fetchall()
        ]

    # pandas reads the literal code "NA" as a missing value and blanks it out.
    assert values(pandas_target, "PRESYS_CODE") == ["", "DV02"]
    assert values(sql_target, "PRESYS_CODE") == ["NA", "DV02"]

    # pandas round-trips numerics through float64 and re-formats them.
    assert values(pandas_target, "LATITUDE") == ["26.41544", "26.41567"]
    assert values(sql_target, "LATITUDE") == ["26.415439999999997", "26.41567"]

    assert values(pandas_target, "CA") == ["-0.2", "-0.21"]
    assert values(sql_target, "CA") == ["-.2", "-0.21"]


def test_differential_all_rows_rejected(tmp_path: Path, lookups) -> None:
    _run_both(tmp_path, "ACCT_ID,DIV_CODE\nA1,DIV100\nB2,DIV100\n", lookups)


def test_differential_missing_acct_id_column(tmp_path: Path, lookups) -> None:
    _run_both(tmp_path, "DIV_CODE,LOAD\nDIV100,5\n", lookups)
