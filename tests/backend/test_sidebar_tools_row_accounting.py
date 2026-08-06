"""Regression tests for the silent row-loss defects in the CSV→Parquet pipeline.

Each test here pins one way rows used to disappear without a trace. The
conservation law they all serve is: every source row is either written or
explicitly accounted for, and no job reports success while data went missing.
"""

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.models.sidebar_tools import BuildDuckDbRequest, FileRowAudit
from backend.services.sidebar_tools_service import (
    ConversionLedger,
    _apply_csv_enrichment,
    _atomic_parquet_target,
    _classify_existing_target,
    _classify_input_file,
    _column_as_series,
    _execute_build_duckdb,
    _load_lookup_tables,
    _parquet_row_count,
)


HIR_HEADER = (
    "DIV_CODE,DISCOM,CIR_SP_ID,ZON_SP_ID,DIV_NAME,CIRCLE_NAME,ZONE_NAME,SDO_SP_ID,SDO_NAME\n"
    "DIV100,DVVNL,C1,Z1,Div A,Circle A,Zone A,SDO100,Sub Div A\n"
)
SUPP_HEADER = "SUPPLY_TYPE,SUPPLY_TYPE_NAME\n49,LMV\n"


def _write_lookups(tmp_path: Path) -> tuple[Path, Path]:
    hir = tmp_path / "hir.csv"
    hir.write_text(HIR_HEADER, encoding="utf-8")
    supp = tmp_path / "supp.csv"
    supp.write_text(SUPP_HEADER, encoding="utf-8")
    return hir, supp


def _lookup_frames(tmp_path: Path):
    hir, supp = _write_lookups(tmp_path)
    return _load_lookup_tables(str(hir), str(supp))


# ── The scalar-default bug: a missing column used to nuke every row ────────────


def test_column_as_series_is_full_length_when_column_is_absent() -> None:
    import pandas as pd

    frame = pd.DataFrame({"A": [1, 2, 3]})

    # The old `frame.get("ACCT_ID", "")` produced a length-1 Series, so assigning
    # it back left rows 1..n as NaN and every subsequent filter dropped them.
    series = _column_as_series(frame, "ACCT_ID")

    assert len(series) == len(frame)
    assert series.notna().all()
    assert list(series) == ["", "", ""]


def test_missing_acct_id_column_fails_loudly_instead_of_dropping_every_row(tmp_path: Path) -> None:
    hir_div, hir_sdo, supp = _lookup_frames(tmp_path)
    source = tmp_path / "no_acct.csv"
    source.write_text("DIV_CODE,LOAD,LOAD_UNIT\nDIV100,5,KW\nDIV100,6,KW\n", encoding="utf-8")
    target = tmp_path / "out.parquet"

    audit = _apply_csv_enrichment(source, target, "zstd", hir_div, hir_sdo, supp)

    assert audit.outcome == "failed"
    assert audit.reason == "MISSING_ACCT_ID_COLUMN"
    assert audit.written_rows == 0
    assert not target.exists()


def test_missing_load_columns_do_not_drop_rows(tmp_path: Path) -> None:
    hir_div, hir_sdo, supp = _lookup_frames(tmp_path)
    source = tmp_path / "no_load.csv"
    source.write_text("ACCT_ID,DIV_CODE\n1001,DIV100\n1002,DIV100\n", encoding="utf-8")
    target = tmp_path / "out.parquet"

    audit = _apply_csv_enrichment(source, target, "zstd", hir_div, hir_sdo, supp)

    assert audit.outcome == "written", audit.reason
    assert audit.source_rows == 2
    assert audit.written_rows == 2
    assert _parquet_row_count(target) == 2


# ── The ACCT_ID rule: recover what's recoverable, quarantine the rest ─────────


def test_dirty_acct_ids_are_recovered_or_quarantined_never_lost(tmp_path: Path) -> None:
    """The conservation law: source == written + quarantined, always.

    The old code silently dropped 6 of these 10 rows, including three that are
    perfectly valid accounts once normalized.
    """
    hir_div, hir_sdo, supp = _lookup_frames(tmp_path)
    source = tmp_path / "dirty.csv"
    source.write_text(
        "ACCT_ID,DIV_CODE\n"
        "123456,DIV100\n"       # plain
        "0012,DIV100\n"         # already padded, short
        ",DIV100\n"             # blank        -> quarantine
        "A1234,DIV100\n"        # alphanumeric -> quarantine
        "12 34,DIV100\n"        # embedded space  -> recoverable
        "1234.0,DIV100\n"       # float round-trip -> recoverable
        '"1,234",DIV100\n'      # thousands separator -> recoverable
        " 987 ,DIV100\n"        # padded with spaces  -> recoverable
        "1.23457E+11,DIV100\n"  # precision already lost -> quarantine
        "12345678901,DIV100\n"  # 11 digits -> quarantine
        ,
        encoding="utf-8",
    )
    target = tmp_path / "out.parquet"

    audit = _apply_csv_enrichment(source, target, "zstd", hir_div, hir_sdo, supp)

    assert audit.source_rows == 10
    assert audit.written_rows + audit.quarantined_rows == 10, "no row may vanish"
    assert _parquet_row_count(target) == audit.written_rows
    assert sum(audit.quarantine_reasons.values()) == audit.quarantined_rows

    written = [
        row[0]
        for row in duckdb.connect()
        .execute("SELECT ACCT_ID FROM read_parquet(?) ORDER BY ACCT_ID", [str(target)])
        .fetchall()
    ]
    # Every surviving id is a 10-digit, zero-padded string.
    assert all(len(value) == 10 and value.isdigit() for value in written), written
    # The recoverable ones were repaired rather than thrown away.
    assert "0000000987" in written  # ' 987 '
    assert "0000001234" in written  # '1,234' and '1234.0'
    assert "0000001234" in written
    assert "0000123456" in written

    assert audit.quarantine_file is not None
    assert _parquet_row_count(Path(audit.quarantine_file)) == audit.quarantined_rows


def test_all_rows_rejected_is_a_named_failure_with_evidence(tmp_path: Path) -> None:
    hir_div, hir_sdo, supp = _lookup_frames(tmp_path)
    source = tmp_path / "all_bad.csv"
    source.write_text("ACCT_ID,DIV_CODE\nA1,DIV100\nB2,DIV100\n", encoding="utf-8")
    target = tmp_path / "out.parquet"

    audit = _apply_csv_enrichment(source, target, "zstd", hir_div, hir_sdo, supp)

    assert audit.outcome == "failed"
    assert audit.reason == "ALL_ROWS_REJECTED_ACCT_ID"
    assert audit.quarantined_rows == 2
    # The rows still exist on disk — they were not simply discarded.
    assert _parquet_row_count(Path(audit.quarantine_file)) == 2


def test_lookup_file_without_join_key_raises(tmp_path: Path) -> None:
    hir = tmp_path / "hir_bad.csv"
    hir.write_text("DISCOM,DIV_NAME\nDVVNL,Div A\n", encoding="utf-8")
    supp = tmp_path / "supp.csv"
    supp.write_text(SUPP_HEADER, encoding="utf-8")

    with pytest.raises(ValueError, match="DIV_CODE"):
        _load_lookup_tables(str(hir), str(supp))


# ── The tuple-truthiness bug: failures counted as successes ───────────────────


def test_sync_endpoint_reports_enrichment_failure(tmp_path: Path) -> None:
    """`if not <3-tuple>` is always False, so every failure read as success."""
    hir, supp = _write_lookups(tmp_path)
    source = tmp_path / "no_acct.csv"
    source.write_text("DIV_CODE,LOAD\nDIV100,5\n", encoding="utf-8")
    output_path = tmp_path / "out.parquet"

    response = TestClient(app).post(
        "/api/sidebar-tools/csv-to-parquet",
        json={
            "input_path": str(source),
            "output_path": str(output_path),
            "compression": "zstd",
            "hir_file": str(hir),
            "supp_mapper_file": str(supp),
        },
    )

    assert response.status_code == 400, response.text
    assert "MISSING_ACCT_ID_COLUMN" in response.text
    assert not output_path.exists()


# ── Partial writes: a crashed conversion must not look "already converted" ────


def test_atomic_target_leaves_nothing_behind_when_the_write_fails(tmp_path: Path) -> None:
    """A crashed write must not leave a file at the final path.

    That is precisely how a zero-byte parquet became permanent: it existed, so
    every later run skipped it as "already converted".
    """
    target = tmp_path / "out.parquet"

    with pytest.raises(OSError):
        with _atomic_parquet_target(target) as tmp:
            tmp.write_bytes(b"")  # a truncated write
            raise OSError("disk full")

    assert not target.exists(), "the final path must stay clean"
    assert not list(tmp_path.glob(".*")), "the temp file must be cleaned up"


def test_atomic_target_publishes_only_on_success(tmp_path: Path) -> None:
    target = tmp_path / "out.parquet"

    with _atomic_parquet_target(target) as tmp:
        assert tmp != target
        duckdb.connect().execute("COPY (SELECT 1 AS id) TO ? (FORMAT PARQUET)", [str(tmp)])
        assert not target.exists(), "nothing is published until the write completes"

    assert _parquet_row_count(target) == 1


def test_enrichment_failure_leaves_no_target_file(tmp_path: Path) -> None:
    hir_div, hir_sdo, supp = _lookup_frames(tmp_path)
    source = tmp_path / "all_bad.csv"
    source.write_text("ACCT_ID,DIV_CODE\nA1,DIV100\n", encoding="utf-8")
    target = tmp_path / "out.parquet"

    audit = _apply_csv_enrichment(source, target, "zstd", hir_div, hir_sdo, supp)

    assert audit.outcome == "failed"
    assert not target.exists()


    assert not target.exists(), "a failed write must not leave a file at the final path"
    assert not list(tmp_path.glob(".*tmp")), "temp files must be cleaned up"


def test_zero_byte_parquet_is_repaired_not_reused(tmp_path: Path) -> None:
    target = tmp_path / "crashed.parquet"
    target.write_bytes(b"")

    action, rows = _classify_existing_target(target, overwrite=False)

    assert action == "repair"
    assert rows == 0


def test_valid_parquet_is_reused_with_its_row_count(tmp_path: Path) -> None:
    target = tmp_path / "good.parquet"
    duckdb.connect().execute(
        "COPY (SELECT * FROM range(7) t(id)) TO ? (FORMAT PARQUET)", [str(target)]
    )

    action, rows = _classify_existing_target(target, overwrite=False)

    assert action == "reuse"
    assert rows == 7


def test_overwrite_always_reconverts(tmp_path: Path) -> None:
    target = tmp_path / "good.parquet"
    duckdb.connect().execute(
        "COPY (SELECT * FROM range(3) t(id)) TO ? (FORMAT PARQUET)", [str(target)]
    )

    assert _classify_existing_target(target, overwrite=True) == ("convert", 0)


def test_zero_byte_parquet_is_rebuilt_by_the_job(tmp_path: Path) -> None:
    """End-to-end: the 0-byte-parquet-skipped-forever case."""
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    (csv_dir / "part.csv").write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "part.parquet").write_bytes(b"")  # crashed previous run

    response = TestClient(app).post(
        "/api/sidebar-tools/csv-to-parquet",
        json={
            "input_path": str(csv_dir),
            "output_path": str(out_dir),
            "compression": "zstd",
        },
    )

    assert response.status_code == 200, response.text
    assert _parquet_row_count(out_dir / "part.parquet") == 2


# ── Plain-text file wearing a .gz extension ───────────────────────────────────


def _parquet_with_rows(path: Path, rows: int) -> None:
    duckdb.connect().execute(
        f"COPY (SELECT * FROM range({rows}) t(id)) TO ? (FORMAT PARQUET)", [str(path)]
    )


def _build(tmp_path: Path, input_glob: str, db_path: Path, name: str = "part_table"):
    return _execute_build_duckdb(
        BuildDuckDbRequest(
            db_path=str(db_path),
            input_path=input_glob,
            object_name=name,
            object_type="TABLE",
            replace=True,
        )
    )


# ── The build must never replace a good table with a partial one ──────────────


def test_build_reports_row_balance(tmp_path: Path) -> None:
    src = tmp_path / "in"
    src.mkdir()
    _parquet_with_rows(src / "a.parquet", 5)
    _parquet_with_rows(src / "b.parquet", 7)
    db_path = tmp_path / "out.duckdb"

    outcome = _build(tmp_path, str(src / "*.parquet"), db_path)

    assert outcome.parquet_input_rows == 12
    assert outcome.table_rows == 12
    assert outcome.row_delta == 0
    assert outcome.data_quality == "ok"


def test_build_refuses_corrupt_parquet_instead_of_silently_shrinking(tmp_path: Path) -> None:
    """The BILLED_DVVNL 0-byte case: it must block the build, not vanish."""
    src = tmp_path / "in"
    src.mkdir()
    _parquet_with_rows(src / "good.parquet", 4)
    (src / "crashed.parquet").write_bytes(b"")
    db_path = tmp_path / "out.duckdb"

    with pytest.raises(ValueError, match="Corrupt or empty parquet"):
        _build(tmp_path, str(src / "*.parquet"), db_path)


def test_failed_build_leaves_the_previous_table_intact(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "in"
    src.mkdir()
    _parquet_with_rows(src / "a.parquet", 6)
    db_path = tmp_path / "out.duckdb"

    first = _build(tmp_path, str(src / "*.parquet"), db_path)
    assert first.table_rows == 6

    # Force the staged build to come out short, which must abort the swap.
    import backend.services.sidebar_tools_service as svc

    monkeypatch.setattr(
        svc,
        "_build_select_sql_for_schema",
        lambda relation, cols, **kwargs: f"SELECT * FROM {relation} WHERE false",
    )

    with pytest.raises(ValueError, match="Row count mismatch"):
        _build(tmp_path, str(src / "*.parquet"), db_path)

    rows = duckdb.connect(str(db_path)).execute("SELECT count(*) FROM part_table").fetchone()
    assert rows[0] == 6, "the previous good table must survive a failed build"


def test_build_ignores_quarantine_directory(tmp_path: Path) -> None:
    src = tmp_path / "in"
    quarantine = src / "_quarantine"
    quarantine.mkdir(parents=True)
    _parquet_with_rows(src / "good.parquet", 3)
    _parquet_with_rows(quarantine / "rejects.parquet", 99)
    db_path = tmp_path / "out.duckdb"

    outcome = _build(tmp_path, str(src / "**/*.parquet"), db_path)

    assert outcome.table_rows == 3, "quarantined rows must never reach the master table"


def test_classify_input_file_reasons(tmp_path: Path) -> None:
    good = tmp_path / "good.parquet"
    _parquet_with_rows(good, 1)
    tiny = tmp_path / "tiny.parquet"
    tiny.write_bytes(b"")
    in_flight = tmp_path / "tmp_writing.parquet"
    in_flight.write_bytes(b"")

    assert _classify_input_file(str(good)) == (True, "")
    assert _classify_input_file(str(tiny)) == (False, "PARQUET_TOO_SMALL")
    assert _classify_input_file(str(in_flight)) == (False, "TEMP_PARQUET")


def test_build_survives_unparseable_number_column(tmp_path: Path) -> None:
    """Plain CAST aborted the build after the DROP had already committed."""
    src = tmp_path / "in"
    src.mkdir()
    duckdb.connect().execute(
        "COPY (SELECT '1001' AS ACCT_ID, 'not-a-number' AS BILLED_AMOUNT) TO ? (FORMAT PARQUET)",
        [str(src / "a.parquet")],
    )
    db_path = tmp_path / "out.duckdb"

    outcome = _build(tmp_path, str(src / "*.parquet"), db_path)

    assert outcome.table_rows == 1
    value = duckdb.connect(str(db_path)).execute("SELECT BILLED_AMOUNT FROM part_table").fetchone()
    assert value[0] is None, "an unparseable NUMBER becomes NULL rather than killing the build"


def test_plain_text_gz_is_converted_not_silently_skipped(tmp_path: Path) -> None:
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    # Not actually gzipped, despite the name.
    (csv_dir / "part.csv.gz").write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    response = TestClient(app).post(
        "/api/sidebar-tools/csv-to-parquet",
        json={
            "input_path": str(csv_dir),
            "output_path": str(out_dir),
            "compression": "zstd",
        },
    )

    assert response.status_code == 200, response.text
    assert _parquet_row_count(out_dir / "part.parquet") == 2


def test_empty_source_reports_empty_file_not_missing_column(tmp_path: Path) -> None:
    """A zero-row .gz must not be reported as a schema problem.

    DuckDB gives an empty gz a dummy `column0`, which used to read as
    MISSING_ACCT_ID_COLUMN and sent operators hunting for a header fault that
    was not there. 93 files in one real month hit this.
    """
    import gzip

    hir_div, hir_sdo, supp = _lookup_frames(tmp_path)
    source = tmp_path / "empty.csv.gz"
    with gzip.open(source, "wb"):
        pass  # a valid gzip stream with no payload
    target = tmp_path / "out.parquet"

    audit = _apply_csv_enrichment(source, target, "zstd", hir_div, hir_sdo, supp)

    assert audit.outcome == "failed"
    assert audit.reason == "EMPTY_FILE"
    assert audit.source_rows == 0
    assert not target.exists()


def test_missing_acct_id_is_still_reported_when_the_file_has_rows(tmp_path: Path) -> None:
    hir_div, hir_sdo, supp = _lookup_frames(tmp_path)
    source = tmp_path / "no_acct.csv"
    source.write_text("DIV_CODE,LOAD\nDIV100,5\nDIV100,6\n", encoding="utf-8")

    audit = _apply_csv_enrichment(source, tmp_path / "o.parquet", "zstd", hir_div, hir_sdo, supp)

    assert audit.reason == "MISSING_ACCT_ID_COLUMN"
    assert audit.source_rows == 2, "report how many rows the failed file held"


# ── The quality verdict must distinguish "no rows existed" from "rows were lost" ──


def _ledger(*entries: FileRowAudit) -> ConversionLedger:
    ledger = ConversionLedger()
    for entry in entries:
        ledger.record(entry)
    return ledger


def _empty(name: str, reason: str = "EMPTY_FILE") -> FileRowAudit:
    return FileRowAudit(source_file=name, outcome="failed", reason=reason, source_rows=0)


def test_empty_sources_are_a_warning_not_row_loss() -> None:
    """A month with empty divisions must not paint the run red.

    "loss" sits next to "every source row is accounted for" in the same card, so
    spending it on files that never held a row teaches operators to ignore it.
    """
    ledger = _ledger(
        FileRowAudit(source_file="a.csv.gz", outcome="written", source_rows=10, written_rows=10),
        *[_empty(f"empty{i}.csv.gz") for i in range(93)],
    )

    assert ledger.data_quality() == "warning"
    assert ledger.totals().unaccounted_rows == 0
    assert ledger.totals().balanced


@pytest.mark.parametrize("reason", ["EMPTY_FILE", "EMPTY_DATAFRAME", "EMPTY_DATA_ERROR"])
def test_every_empty_reason_is_treated_alike(reason: str) -> None:
    assert _ledger(_empty("e.csv.gz", reason)).data_quality() == "warning"


@pytest.mark.parametrize("reason", ["MISSING_ACCT_ID_COLUMN", "TRUNCATED_EOF", "READ_ERROR:boom", ""])
def test_real_failures_are_still_row_loss(reason: str) -> None:
    """Including a blank reason — an unrecognised failure must not be excused."""
    entry = FileRowAudit(source_file="bad.csv.gz", outcome="failed", reason=reason, source_rows=5)

    assert _ledger(entry).data_quality() == "loss"


def test_one_real_failure_outweighs_many_empty_files() -> None:
    ledger = _ledger(
        *[_empty(f"empty{i}.csv.gz") for i in range(50)],
        FileRowAudit(
            source_file="bad.csv.gz", outcome="failed", reason="TRUNCATED_EOF", source_rows=7
        ),
    )

    assert ledger.data_quality() == "loss"


def test_a_clean_run_is_still_ok() -> None:
    ledger = _ledger(
        FileRowAudit(source_file="a.csv.gz", outcome="written", source_rows=10, written_rows=10)
    )

    assert ledger.data_quality() == "ok"
