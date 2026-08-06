"""`alter_db` must not offer or attempt to alter a month stored as a view.

Views already appeared in this page's table picker before the storage change, and
`ALTER TABLE <view>` fails at job time with DuckDB's own wording ("Can only modify
view with ALTER VIEW statement") — which tells an operator nothing about what to do
instead. With months stored as views by default, that becomes the common case.
"""

from pathlib import Path
from uuid import uuid4

import duckdb
import pytest

from backend.api.endpoints.alter_db import _run_alter_db_job, get_alter_db_tables
from backend.models.alter_db import AlterDbDerivedRequest, AlterDbDropRequest
from backend.services.job_runtime import job_runtime


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / f"alter_{uuid4().hex[:8]}.duckdb"
    with duckdb.connect(str(path)) as conn:
        conn.execute("CREATE TABLE Master_0526 AS SELECT 1 AS ACCT_ID, '10' AS TOTAL_AMT")
        conn.execute("CREATE VIEW Master_0426 AS SELECT 2 AS ACCT_ID, '20' AS TOTAL_AMT")
        conn.execute("CREATE TABLE HIR AS SELECT 'DIV1' AS DIV_CODE")
    return path


def test_the_table_picker_omits_views(db_path: Path) -> None:
    names = get_alter_db_tables(str(db_path))

    assert "Master_0526" in names
    assert "HIR" in names
    assert "Master_0426" not in names, "a view cannot be altered, so it must not be offered"


def test_the_picker_reuses_the_live_connection_and_still_omits_views(db_path: Path) -> None:
    """The endpoint has two branches; the connected one had the same missing filter."""
    from backend.api.deps import get_db_service

    svc = get_db_service()
    svc.connect(str(db_path))
    try:
        names = get_alter_db_tables(str(db_path))
    finally:
        svc.disconnect()

    assert "Master_0526" in names
    assert "Master_0426" not in names


def _run(job_type_request) -> dict:
    job_id = uuid4().hex
    job_runtime.start_job(
        job_type="alter_db.test",
        job_id=job_id,
        initial_snapshot={"job_id": job_id, "status": "queued", "message": ""},
        payload={},
        worker=lambda running_id: _run_alter_db_job(running_id, job_type_request),
    )
    for _ in range(200):
        job = job_runtime.get_job(job_id)
        if job and job["status"] in {"completed", "failed", "cancelled"}:
            return job
        import time

        time.sleep(0.05)
    raise AssertionError("alter_db job did not finish")


def test_altering_a_view_fails_with_an_actionable_message(db_path: Path) -> None:
    job = _run(
        AlterDbDerivedRequest(
            db_path=str(db_path),
            table_name="Master_0426",
            new_column_name="FLAG",
            column_type="VARCHAR",
            sql_formula="'x'",
        )
    )

    assert job["status"] == "failed"
    message = job["message"]
    assert "is a view over parquet files" in message
    assert "Materialise" in message, "the message must say what to do instead"
    assert "ALTER VIEW" not in message, "DuckDB's raw wording is not actionable"


def test_dropping_a_column_from_a_view_is_refused(db_path: Path) -> None:
    job = _run(
        AlterDbDropRequest(
            db_path=str(db_path),
            table_name="Master_0426",
            column_name="TOTAL_AMT",
        )
    )

    assert job["status"] == "failed"
    assert "is a view over parquet files" in job["message"]


def test_the_view_is_left_completely_untouched(db_path: Path) -> None:
    """Refusing must happen before any DDL, so the month still resolves its rows."""
    _run(
        AlterDbDerivedRequest(
            db_path=str(db_path),
            table_name="Master_0426",
            new_column_name="FLAG",
            column_type="VARCHAR",
            sql_formula="'x'",
        )
    )

    with duckdb.connect(str(db_path)) as conn:
        columns = [
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM duckdb_columns() WHERE table_name = 'Master_0426'"
            ).fetchall()
        ]
        assert conn.execute("SELECT count(*) FROM Master_0426").fetchone()[0] == 1

    assert "FLAG" not in columns


def test_altering_a_real_table_still_works(db_path: Path) -> None:
    """The guard must not block the case the page exists for."""
    job = _run(
        AlterDbDerivedRequest(
            db_path=str(db_path),
            table_name="Master_0526",
            new_column_name="FLAG",
            column_type="VARCHAR",
            sql_formula="'yes'",
        )
    )

    assert job["status"] == "completed", job["message"]
    with duckdb.connect(str(db_path)) as conn:
        assert conn.execute("SELECT FLAG FROM Master_0526").fetchone()[0] == "yes"
