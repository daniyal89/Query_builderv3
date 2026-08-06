"""The materialised slot moves between months, and demotion must never lose rows.

Steady state is one month stored as a real TABLE (fast for daily analysis) and every
older month as a VIEW over its parquet. Promoting month N therefore has to hand the
slot back from month N-1 — and that demotion drops a table which may be the only
copy of those rows. Every uncertainty must resolve to "leave it materialised".
"""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import duckdb
import pytest

from backend.models.sidebar_tools import BuildDuckDbRequest, MaterialiseMonthRequest
from backend.services import sidebar_tools_service as svc
from backend.services.job_runtime import BackgroundJobCancelled
from backend.services.sidebar_tools_service import (
    QUARANTINE_DIR_NAME,
    _execute_build_duckdb,
    _find_materialised_masters,
    _materialise_month,
    _plan_demotion,
    _read_object_provenance,
)


def _write_parquet(path: Path, rows: int, start: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The path must be the only bound parameter — DuckDB will not take the COPY
    # target positionally alongside others.
    duckdb.connect().execute(
        f"COPY (SELECT i AS ACCT_ID, 'x' AS NAME FROM range({start}, {start + rows}) t(i)) "
        "TO ? (FORMAT PARQUET)",
        [str(path)],
    )


def _build(db_path: Path, glob_root: Path, month: str, object_type: str, rows: int = 4) -> None:
    _write_parquet(glob_root / "part.parquet", rows)
    _execute_build_duckdb(
        BuildDuckDbRequest(
            db_path=str(db_path),
            input_path=str(glob_root),
            object_name="MASTER",
            object_type=object_type,
            replace=True,
            month_label=month,
        )
    )


def _object_type(db_path: Path, name: str) -> str | None:
    with duckdb.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = 'main' AND lower(table_name) = lower(?)",
            [name],
        ).fetchone()
    return row[0] if row else None


def _row_count(db_path: Path, name: str) -> int:
    with duckdb.connect(str(db_path)) as conn:
        return conn.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / uuid4().hex[:8]


# ── Provenance is what makes demotion possible at all ─────────────────────────


def test_a_build_records_where_its_rows_came_from(workspace: Path) -> None:
    db_path = workspace / "db.duckdb"
    _build(db_path, workspace / "may", "MAY_2026", "TABLE", rows=4)

    with duckdb.connect(str(db_path)) as conn:
        provenance = _read_object_provenance(conn, "Master_0526")

    assert provenance is not None
    assert provenance["verified_rows"] == 4
    assert provenance["materialised_at"] is not None, "a TABLE build is a materialisation"
    assert "may" in provenance["source_glob"].replace("\\", "/")


def test_a_view_build_records_provenance_too(workspace: Path) -> None:
    db_path = workspace / "db.duckdb"
    _build(db_path, workspace / "may", "MAY_2026", "VIEW", rows=4)

    with duckdb.connect(str(db_path)) as conn:
        provenance = _read_object_provenance(conn, "Master_0526")

    assert provenance is not None
    assert provenance["materialised_at"] is None


def test_only_materialised_months_are_candidates(workspace: Path) -> None:
    db_path = workspace / "db.duckdb"
    _build(db_path, workspace / "apr", "APR_2026", "TABLE")
    _build(db_path, workspace / "may", "MAY_2026", "VIEW")

    with duckdb.connect(str(db_path)) as conn:
        found = _find_materialised_masters(conn, exclude="Master_0626")

    assert found == ["Master_0426"], "the view must not be offered for demotion"


def test_the_month_being_promoted_is_excluded(workspace: Path) -> None:
    db_path = workspace / "db.duckdb"
    _build(db_path, workspace / "apr", "APR_2026", "TABLE")

    with duckdb.connect(str(db_path)) as conn:
        assert _find_materialised_masters(conn, exclude="Master_0426") == []


# ── The demotion guard: every uncertainty means "leave it alone" ──────────────


def test_demotion_is_planned_when_the_parquet_still_agrees(workspace: Path) -> None:
    db_path = workspace / "db.duckdb"
    _build(db_path, workspace / "apr", "APR_2026", "TABLE", rows=4)

    with duckdb.connect(str(db_path)) as conn:
        source_glob, reason = _plan_demotion(conn, "Master_0426")

    assert reason is None
    assert source_glob is not None


def test_demotion_refused_when_the_parquet_is_gone(workspace: Path) -> None:
    """The operator deleted the parquet after materialising. The table is the only copy."""
    db_path = workspace / "db.duckdb"
    parquet_root = workspace / "apr"
    _build(db_path, parquet_root, "APR_2026", "TABLE", rows=4)
    (parquet_root / "part.parquet").unlink()

    with duckdb.connect(str(db_path)) as conn:
        source_glob, reason = _plan_demotion(conn, "Master_0426")

    assert source_glob is None
    assert reason is not None and "no readable parquet" in reason.lower()


def test_demotion_refused_when_the_parquet_no_longer_matches(workspace: Path) -> None:
    """A re-conversion changed the row count, so a view there is a different month."""
    db_path = workspace / "db.duckdb"
    parquet_root = workspace / "apr"
    _build(db_path, parquet_root, "APR_2026", "TABLE", rows=4)
    _write_parquet(parquet_root / "part.parquet", 9)  # re-converted, now 9 rows

    with duckdb.connect(str(db_path)) as conn:
        source_glob, reason = _plan_demotion(conn, "Master_0426")

    assert source_glob is None
    assert reason is not None
    assert "9" in reason and "4" in reason, "the reason must state both counts"


def test_demotion_refused_when_provenance_is_unknown(workspace: Path) -> None:
    """A table built before provenance existed must not be guessed at."""
    db_path = workspace / "db.duckdb"
    _build(db_path, workspace / "apr", "APR_2026", "TABLE", rows=4)
    with duckdb.connect(str(db_path)) as conn:
        conn.execute('COMMENT ON TABLE "Master_0426" IS NULL')

        source_glob, reason = _plan_demotion(conn, "Master_0426")

    assert source_glob is None
    assert reason is not None and "did not record" in reason


# ── The full cycle ────────────────────────────────────────────────────────────


def test_promoting_a_month_demotes_the_previous_one(workspace: Path) -> None:
    db_path = workspace / "db.duckdb"
    apr_root = workspace / "apr"
    may_root = workspace / "may"
    _build(db_path, apr_root, "APR_2026", "TABLE", rows=4)
    _write_parquet(may_root / "part.parquet", 7)

    outcome = _materialise_month(
        MaterialiseMonthRequest(
            db_path=str(db_path),
            input_path=str(may_root),
            object_name="MASTER",
            month_label="MAY_2026",
        )
    )

    assert outcome.promoted == "Master_0526"
    assert outcome.promoted_rows == 7
    assert outcome.demoted == ("Master_0426",)
    assert outcome.demote_warnings == ()
    assert _object_type(db_path, "Master_0526") == "BASE TABLE"
    assert _object_type(db_path, "Master_0426") == "VIEW"
    # The demoted month must still return exactly its rows.
    assert _row_count(db_path, "Master_0426") == 4
    assert _row_count(db_path, "Master_0526") == 7


def test_an_undemotable_month_stays_a_table_and_is_reported(workspace: Path) -> None:
    """The promote must still succeed, and the cost must be stated, not hidden."""
    db_path = workspace / "db.duckdb"
    apr_root = workspace / "apr"
    may_root = workspace / "may"
    _build(db_path, apr_root, "APR_2026", "TABLE", rows=4)
    (apr_root / "part.parquet").unlink()  # April's parquet is gone
    _write_parquet(may_root / "part.parquet", 7)

    outcome = _materialise_month(
        MaterialiseMonthRequest(
            db_path=str(db_path),
            input_path=str(may_root),
            object_name="MASTER",
            month_label="MAY_2026",
        )
    )

    assert outcome.promoted == "Master_0526"
    assert outcome.demoted == ()
    assert len(outcome.demote_warnings) == 1
    assert outcome.data_quality == "warning"
    assert _object_type(db_path, "Master_0426") == "BASE TABLE", "April keeps its only copy"
    assert _row_count(db_path, "Master_0426") == 4


def test_demote_previous_can_be_turned_off(workspace: Path) -> None:
    db_path = workspace / "db.duckdb"
    _build(db_path, workspace / "apr", "APR_2026", "TABLE", rows=4)
    _write_parquet(workspace / "may" / "part.parquet", 7)

    outcome = _materialise_month(
        MaterialiseMonthRequest(
            db_path=str(db_path),
            input_path=str(workspace / "may"),
            object_name="MASTER",
            month_label="MAY_2026",
            demote_previous=False,
        )
    )

    assert outcome.demoted == ()
    assert outcome.demote_warnings == ()
    assert _object_type(db_path, "Master_0426") == "BASE TABLE"


def test_several_stale_materialised_months_are_all_demoted(workspace: Path) -> None:
    """The migration case: the real file has four materialised months at once."""
    db_path = workspace / "db.duckdb"
    for month, rows in (("FEB_2026", 2), ("MAR_2026", 3), ("APR_2026", 4)):
        _build(db_path, workspace / month, month, "TABLE", rows=rows)
    _write_parquet(workspace / "may" / "part.parquet", 7)

    outcome = _materialise_month(
        MaterialiseMonthRequest(
            db_path=str(db_path),
            input_path=str(workspace / "may"),
            object_name="MASTER",
            month_label="MAY_2026",
        )
    )

    assert set(outcome.demoted) == {"Master_0226", "Master_0326", "Master_0426"}
    for name, expected in (("Master_0226", 2), ("Master_0326", 3), ("Master_0426", 4)):
        assert _object_type(db_path, name) == "VIEW"
        assert _row_count(db_path, name) == expected


def test_a_crashed_builds_staging_table_is_swept_on_the_next_run(workspace: Path) -> None:
    """`CREATE TABLE ... AS` autocommits, so a killed process leaves ~11.7 GB behind.

    Each attempt mints a fresh random suffix, so without a sweep they accumulate in
    the file forever — invisible on the Home page, since the name is not a month.
    """
    db_path = workspace / "db.duckdb"
    _build(db_path, workspace / "apr", "APR_2026", "TABLE", rows=4)

    # Exactly what a crash between the CREATE and the finally-drop leaves behind.
    with duckdb.connect(str(db_path)) as conn:
        conn.execute('CREATE TABLE "Master_0426__staging_deadbeef" AS SELECT 1 AS x')
        conn.execute('CREATE TABLE "Master_0426__staging_cafebabe" AS SELECT 1 AS x')

    _build(db_path, workspace / "apr", "APR_2026", "TABLE", rows=4)

    with duckdb.connect(str(db_path)) as conn:
        leftovers = conn.execute(
            "SELECT table_name FROM duckdb_tables() WHERE table_name LIKE '%__staging_%'"
        ).fetchall()
        assert leftovers == []
        # The real month is untouched.
        assert conn.execute('SELECT count(*) FROM "Master_0426"').fetchone()[0] == 4


def test_a_failed_reconnect_during_a_demote_is_reported(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A demote reconnect failure leaves the app unreachable for the whole promote.

    Only the promote's own outcome was inspected, so the job reported plain success
    while every endpoint was still answering 503.
    """
    db_path = workspace / "db.duckdb"
    _build(db_path, workspace / "apr", "APR_2026", "TABLE", rows=4)
    _write_parquet(workspace / "may" / "part.parquet", 7)

    real_build = svc._execute_build_duckdb

    def failing_reconnect(payload):  # type: ignore[no-untyped-def]
        result = real_build(payload)
        if payload.object_type == "VIEW":
            return replace(result, reconnect_error="DatabaseLockedError: held by another process")
        return result

    monkeypatch.setattr(svc, "_execute_build_duckdb", failing_reconnect)

    outcome = _materialise_month(
        MaterialiseMonthRequest(
            db_path=str(db_path),
            input_path=str(workspace / "may"),
            object_name="MASTER",
            month_label="MAY_2026",
        )
    )

    assert outcome.demoted == ("Master_0426",)
    assert outcome.reconnect_error is not None
    assert "reconnect" in outcome.message.lower()
    assert outcome.data_quality == "warning", "an unreachable app is not a clean run"


def test_a_cancel_after_a_demote_says_what_already_changed(workspace: Path) -> None:
    """Demotions are committed one at a time, so "changed nothing" can be a lie."""
    db_path = workspace / "db.duckdb"
    _build(db_path, workspace / "apr", "APR_2026", "TABLE", rows=4)
    _write_parquet(workspace / "may" / "part.parquet", 7)

    recorded: list[str] = []
    with pytest.raises(BackgroundJobCancelled):
        _materialise_month(
            MaterialiseMonthRequest(
                db_path=str(db_path),
                input_path=str(workspace / "may"),
                object_name="MASTER",
                month_label="MAY_2026",
            ),
            # Cancel lands only once the demote has already been committed.
            progress=lambda message, _pct: (_ for _ in ()).throw(BackgroundJobCancelled())
            if recorded
            else None,
            on_demoted=recorded.append,
        )

    assert recorded == ["Master_0426"], "the demote is reported as it happens"
    assert _object_type(db_path, "Master_0426") == "VIEW"
    assert _row_count(db_path, "Master_0426") == 4, "still fully queryable"


def test_pointing_the_build_at_a_quarantine_file_is_refused(workspace: Path) -> None:
    """Rejected rows are not a data source, and building from them was unverified.

    With every matched file rejected, the footer count came back None (verification
    silently off) and the relation fell back to reading the raw input — so the master
    would have been built out of exactly the rows the pipeline threw away.
    """
    quarantine = workspace / "apr" / QUARANTINE_DIR_NAME
    quarantine.mkdir(parents=True)
    _write_parquet(quarantine / "div_A.ACCT_ID_INVALID.parquet", 3)

    with pytest.raises(ValueError, match="No usable parquet"):
        _execute_build_duckdb(
            BuildDuckDbRequest(
                db_path=str(workspace / "db.duckdb"),
                input_path=str(quarantine / "div_A.ACCT_ID_INVALID.parquet"),
                object_name="part_table",
                object_type="VIEW",
                replace=True,
            )
        )


def test_a_failed_promote_leaves_the_demoted_month_queryable(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Demotion runs first, so a promote failure must not leave a hole.

    A demoted month is a view over parquet that is still there — slower, but every
    row still reachable. That is why demote-first is the safe order even though it
    means the fast slot is briefly empty.
    """
    db_path = workspace / "db.duckdb"
    _build(db_path, workspace / "apr", "APR_2026", "TABLE", rows=4)
    _write_parquet(workspace / "may" / "part.parquet", 7)

    real_build = svc._execute_build_duckdb

    def fail_on_table(payload):  # type: ignore[no-untyped-def]
        if payload.object_type == "TABLE":
            raise RuntimeError("disk full")
        return real_build(payload)

    monkeypatch.setattr(svc, "_execute_build_duckdb", fail_on_table)

    with pytest.raises(RuntimeError, match="disk full"):
        _materialise_month(
            MaterialiseMonthRequest(
                db_path=str(db_path),
                input_path=str(workspace / "may"),
                object_name="MASTER",
                month_label="MAY_2026",
            )
        )

    assert _object_type(db_path, "Master_0426") == "VIEW"
    assert _row_count(db_path, "Master_0426") == 4, "every April row is still reachable"
