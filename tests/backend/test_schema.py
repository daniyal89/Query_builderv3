"""
test_schema.py — Tests for schema introspection endpoints.

Verifies:
- GET /api/tables returns correct list of TableMetadata.
- GET /api/tables/{name}/columns returns correct ColumnDetail list.
- GET /api/tables/{name}/row-count returns an exact count.
- 503 when no database is connected.
- 404 when requesting columns for a non-existent table.

``list_tables`` reads the catalog rather than counting each table, so these also
pin that it stays correct for views, for column order, and for a table that has
had rows appended.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.deps import get_connected_db, get_db_service
from backend.app import app
from backend.services import duckdb_handoff
from backend.services.duckdb_service import DuckDBService


@pytest.fixture
def connected_db(tmp_path: Path):
    """A real DuckDBService over a temp file, injected into the app."""
    db = DuckDBService()
    db.connect(str(tmp_path / "schema.duckdb"))
    app.dependency_overrides[get_connected_db] = lambda: db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_connected_db, None)
        db.disconnect()


def _seed(db: DuckDBService) -> None:
    db.execute("CREATE TABLE consumers (acct_id VARCHAR, amount DECIMAL(18,2), discom VARCHAR)")
    db.execute("INSERT INTO consumers VALUES ('0000000001', 10.50, 'PVVNL'), ('0000000002', 20.00, 'DVVNL')")
    db.execute("CREATE VIEW pvvnl AS SELECT * FROM consumers WHERE discom = 'PVVNL'")


def test_list_tables_returns_tables_and_views(connected_db: DuckDBService) -> None:
    _seed(connected_db)

    tables = connected_db.list_tables()
    by_name = {t.table_name: t for t in tables}

    assert set(by_name) == {"consumers", "pvvnl"}
    assert by_name["consumers"].row_count == 2
    # A view's count is not run — it has always reported 0 here.
    assert by_name["pvvnl"].row_count == 0


def test_list_tables_reports_columns_in_ordinal_order(connected_db: DuckDBService) -> None:
    _seed(connected_db)

    by_name = {t.table_name: t for t in connected_db.list_tables()}

    assert [c.name for c in by_name["consumers"].columns] == ["acct_id", "amount", "discom"]
    assert [c.dtype for c in by_name["consumers"].columns] == ["VARCHAR", "DECIMAL(18,2)", "VARCHAR"]
    # Views must carry their columns too — the column picker depends on it.
    assert [c.name for c in by_name["pvvnl"].columns] == ["acct_id", "amount", "discom"]


def test_estimated_count_tracks_appended_rows(connected_db: DuckDBService) -> None:
    """The catalog estimate must follow a bulk append, which is how months load."""
    _seed(connected_db)

    connected_db.execute("INSERT INTO consumers SELECT '0000000003', 1.00, 'PVVNL' FROM range(500)")

    by_name = {t.table_name: t for t in connected_db.list_tables()}
    assert by_name["consumers"].row_count == 502


def test_list_tables_is_empty_for_a_fresh_database(connected_db: DuckDBService) -> None:
    assert connected_db.list_tables() == []


def test_count_rows_is_exact(connected_db: DuckDBService) -> None:
    _seed(connected_db)

    assert connected_db.count_rows("consumers") == 2


def test_count_rows_rejects_an_unknown_table(connected_db: DuckDBService) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        connected_db.count_rows("nope")


def test_list_tables_reports_object_type(connected_db: DuckDBService) -> None:
    """A view's row_count of 0 is only intelligible alongside its type."""
    _seed(connected_db)

    by_name = {t.table_name: t for t in connected_db.list_tables()}

    assert by_name["consumers"].object_type == "TABLE"
    assert by_name["pvvnl"].object_type == "VIEW"


def test_count_rows_is_exact_for_a_view(connected_db: DuckDBService) -> None:
    """list_tables reports 0 for a view; this is how the real number is obtained."""
    _seed(connected_db)

    assert connected_db.count_rows("pvvnl") == 1


def test_counting_a_view_does_not_hold_the_service_lock(connected_db: DuckDBService) -> None:
    """For a parquet-backed view this binds a whole month's glob.

    Holding _lock across that would block every other endpoint for its duration,
    which is the problem _borrowed_cursor was introduced to solve.
    """
    _seed(connected_db)
    observed: list[bool] = []

    real_cursor = DuckDBService._borrowed_cursor

    def spy(self):  # type: ignore[no-untyped-def]
        ctx = real_cursor(self)
        observed.append(self._lock.acquire(blocking=False))
        if observed[-1]:
            self._lock.release()
        return ctx

    try:
        DuckDBService._borrowed_cursor = spy  # type: ignore[method-assign]
        connected_db.count_rows("consumers")
    finally:
        DuckDBService._borrowed_cursor = real_cursor  # type: ignore[method-assign]

    assert observed and all(observed), "count_rows held the service-wide lock"


def test_row_count_endpoint_424s_when_a_views_sources_are_unreachable(
    tmp_path: Path, connected_db: DuckDBService
) -> None:
    """A month whose parquet moved must not take the Home page down with it."""
    parquet = tmp_path / "gone.parquet"
    import duckdb as _duckdb

    _duckdb.connect().execute(
        "COPY (SELECT 1 AS ACCT_ID) TO ? (FORMAT PARQUET)", [str(parquet)]
    )
    connected_db.execute(
        f"CREATE VIEW orphan AS SELECT * FROM read_parquet('{parquet.as_posix()}')"
    )
    parquet.unlink()

    client = TestClient(app)

    # The catalog still answers, so the object is still listed with its columns...
    listing = client.get("/api/tables")
    assert listing.status_code == 200, listing.text
    assert "orphan" in {row["table_name"] for row in listing.json()}

    # ...and only reading through it fails, with an actionable status.
    response = client.get("/api/tables/orphan/row-count")
    assert response.status_code == 424, response.text
    assert "parquet" in response.json()["detail"].lower()


# ── HTTP surface ──────────────────────────────────────────────────────────────


def test_tables_endpoint_returns_metadata(connected_db: DuckDBService) -> None:
    _seed(connected_db)
    client = TestClient(app)

    response = client.get("/api/tables")

    assert response.status_code == 200, response.text
    names = {row["table_name"] for row in response.json()}
    assert names == {"consumers", "pvvnl"}


def test_columns_endpoint_returns_column_details(connected_db: DuckDBService) -> None:
    _seed(connected_db)
    client = TestClient(app)

    response = client.get("/api/tables/consumers/columns")

    assert response.status_code == 200, response.text
    assert [row["name"] for row in response.json()] == ["acct_id", "amount", "discom"]


def test_columns_endpoint_404s_for_an_unknown_table(connected_db: DuckDBService) -> None:
    client = TestClient(app)

    response = client.get("/api/tables/does_not_exist/columns")

    assert response.status_code == 404


def test_row_count_endpoint_returns_the_exact_count(connected_db: DuckDBService) -> None:
    _seed(connected_db)
    client = TestClient(app)

    response = client.get("/api/tables/consumers/row-count")

    assert response.status_code == 200, response.text
    assert response.json() == {"table_name": "consumers", "row_count": 2}


def test_row_count_endpoint_404s_for_an_unknown_table(connected_db: DuckDBService) -> None:
    client = TestClient(app)

    response = client.get("/api/tables/does_not_exist/row-count")

    assert response.status_code == 404


def test_endpoints_503_when_no_database_is_connected() -> None:
    """No dependency override here — the real singleton answers.

    It is a module-level singleton other tests may have connected, so disconnect
    explicitly rather than depending on test order.
    """
    get_db_service().disconnect()
    client = TestClient(app)

    assert client.get("/api/tables").status_code == 503
    assert client.get("/api/tables/consumers/columns").status_code == 503
    assert client.get("/api/tables/consumers/row-count").status_code == 503


def test_endpoints_409_while_a_build_holds_the_database() -> None:
    """A build disconnects the dashboard; that is "busy", not "no database".

    503 here was indistinguishable from the app having lost its database, which
    is what an operator saw for the whole 41-minute build.
    """
    get_db_service().disconnect()
    client = TestClient(app)
    duckdb_handoff.begin()
    try:
        response = client.get("/api/tables")

        assert response.status_code == 409
        assert "build is running" in response.json()["detail"]
    finally:
        duckdb_handoff.end()

    # ...and back to 503 once the build has handed the connection back.
    assert client.get("/api/tables").status_code == 503


def test_handoff_depth_survives_two_overlapping_builds() -> None:
    """The first build to finish must not clear the second one's handoff."""
    duckdb_handoff.begin()
    duckdb_handoff.begin()
    duckdb_handoff.end()

    assert duckdb_handoff.is_handed_off(), "a concurrent build's handoff was cleared early"

    duckdb_handoff.end()
    assert not duckdb_handoff.is_handed_off()
