"""The read-only row audit must spot the losses the pipeline used to hide."""

import gzip
from pathlib import Path

import duckdb

from backend.tools.audit_rows import audit


def _write_source(path: Path, rows: int) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("ACCT_ID,VAL\n")
        for index in range(rows):
            handle.write(f"{index},{index}\n")


def _write_parquet(path: Path, rows: int) -> None:
    duckdb.connect().execute(
        f"COPY (SELECT * FROM range({rows}) t(id)) TO ? (FORMAT PARQUET)", [str(path)]
    )


def test_audit_reports_balanced_month(tmp_path: Path, capsys) -> None:
    src, pq = tmp_path / "src", tmp_path / "pq"
    src.mkdir()
    pq.mkdir()
    _write_source(src / "DIV1.csv.gz", 10)
    _write_parquet(pq / "DIV1.parquet", 10)

    exit_code = audit(src, pq, None, None)

    assert exit_code == 0
    assert "balances" in capsys.readouterr().out


def test_audit_flags_zero_byte_and_short_parquet(tmp_path: Path, capsys) -> None:
    src, pq = tmp_path / "src", tmp_path / "pq"
    src.mkdir()
    pq.mkdir()
    _write_source(src / "DIV1.csv.gz", 120)
    _write_source(src / "DIV2.csv.gz", 45)
    (pq / "DIV1.parquet").write_bytes(b"")  # the crashed-write case
    _write_parquet(pq / "DIV2.parquet", 40)  # a short conversion

    exit_code = audit(src, pq, None, None)
    out = capsys.readouterr().out

    assert exit_code == 1, "an unbalanced month must exit non-zero"
    assert "(-125)" in out
    assert "MISSING" in out
    assert "DIV1.csv.gz" in out and "DIV2.csv.gz" in out


def test_audit_compares_table_against_parquet(tmp_path: Path, capsys) -> None:
    pq = tmp_path / "pq"
    pq.mkdir()
    _write_parquet(pq / "DIV1.parquet", 30)
    db_path = tmp_path / "monthly.duckdb"
    with duckdb.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE Master AS SELECT * FROM range(25) t(id)")

    exit_code = audit(None, pq, db_path, "Master")
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "(-5)" in out


def test_audit_ignores_quarantine_directory(tmp_path: Path, capsys) -> None:
    src, pq = tmp_path / "src", tmp_path / "pq"
    src.mkdir()
    (pq / "_quarantine").mkdir(parents=True)
    _write_source(src / "DIV1.csv.gz", 10)
    _write_parquet(pq / "DIV1.parquet", 8)
    _write_parquet(pq / "_quarantine" / "DIV1.ACCT_ID_INVALID.parquet", 2)

    exit_code = audit(src, pq, None, None)
    out = capsys.readouterr().out

    # Quarantined rows are reported separately, never counted as delivered.
    assert "quarantined elsewhere: 2" in out
    assert exit_code == 1
