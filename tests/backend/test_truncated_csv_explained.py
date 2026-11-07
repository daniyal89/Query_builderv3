"""A cut-off .gz must be named as such, not reported as a column-count fault.

A build failed on "Expected Number of Columns: 154 Found: 88" at the last line
of a DVVNL file. The reader stays strict (null_padding / ignore_errors would
silently drop that row and break the source == written row ledger); the error
now says which file is incomplete and whether downloading it again can help.
"""
from __future__ import annotations

import gzip
from pathlib import Path

import duckdb
import pytest

from backend.services import sidebar_tools_service as svc

COLUMNS = 10
HEADER = ",".join(f"C{i}" for i in range(COLUMNS))


def _csv_text(rows: int) -> str:
    # Varied rows, like real data: a repeated row compresses so well that any
    # cut leaves almost nothing to read.
    lines = [HEADER] + [",".join(f"{(r * 7919 + c * 104729) % 1000003}" for c in range(COLUMNS)) for r in range(rows)]
    return "\n".join(lines) + "\n"


def _write_gz(path: Path, text: str) -> bytes:
    with gzip.open(path, "wb") as handle:
        handle.write(text.encode())
    return path.read_bytes()


def _duckdb_error(path: Path) -> Exception:
    with duckdb.connect() as conn:
        with pytest.raises(Exception) as excinfo:
            conn.execute(f"SELECT count(*) FROM {svc._resolve_csv_parquet_read_sql(str(path))}").fetchall()
    return excinfo.value


def test_the_reader_stays_strict() -> None:
    sql = svc._resolve_csv_parquet_read_sql("x.csv.gz")
    assert "ignore_errors" not in sql and "null_padding" not in sql


def test_a_cut_off_download_says_download_it_again(tmp_path: Path) -> None:
    whole = _write_gz(tmp_path / "full.csv.gz", _csv_text(20000))
    cut = tmp_path / "DVVNL_DIV211242_SEP_2026.csv.gz"
    cut.write_bytes(whole[: int(len(whole) * 0.6)])

    assert svc._gzip_damage(cut) == "download"
    # The job's current file is the fallback: DuckDB shortens long paths in this error.
    message = svc._explain_read_failure(_duckdb_error(cut), str(cut))

    assert str(cut) in message
    assert "download was cut off" in message and "download it again" in message


def test_a_file_cut_off_before_it_was_gzipped_says_downloading_will_not_help(tmp_path: Path) -> None:
    # The real failure: a whole gzip whose CSV stops part-way through its last
    # row, past DuckDB's sniffing sample so the error is the column count.
    cut = tmp_path / "DVVNL_DIV211242_SEP_2026.csv.gz"
    _write_gz(cut, _csv_text(30000) + ",".join(["9"] * (COLUMNS - 4)))

    assert svc._gzip_damage(cut) == "export"
    error = _duckdb_error(cut)
    assert "Expected Number of Columns" in str(error), "same error the build reported"

    message = svc._explain_read_failure(error)
    assert str(cut) in message
    assert "will not help" in message and "exported again" in message


def test_a_complete_file_keeps_the_original_error(tmp_path: Path) -> None:
    good = tmp_path / "ok.csv.gz"
    _write_gz(good, _csv_text(10))
    exc = RuntimeError(f"CSV Error on Line: 3\nExpected Number of Columns: 10 Found: 9\n  file = {good}\n")

    assert svc._gzip_damage(good) is None
    assert svc._explain_read_failure(exc) == str(exc), "a real bad row is not blamed on the file"


def test_unrelated_errors_pass_through_untouched() -> None:
    assert svc._explain_read_failure(RuntimeError("disk full"), "whatever.csv.gz") == "disk full"
