"""The service-wide lock must not serialise whole statements.

``DuckDBService.execute`` and ``export_to_csv`` used to hold ``_lock`` for the
entire query/COPY, so a Home page load queued behind a 10-minute export and the
app looked hung. They now run on a borrowed cursor — an independent DuckDB
connection onto the same database — with the lock held only long enough to take
it. These tests pin both halves of that: the lock really is free mid-statement,
and disconnect still cannot close the parent connection under a live cursor.
"""

import threading
from pathlib import Path

import pytest

from backend.services.duckdb_service import DuckDBService

# ~0.8s locally — long enough that a lock held for its duration is unmistakable.
SLOW_SQL = "SELECT sum(hash(i)) FROM range(30000000) t(i)"


@pytest.fixture
def db(tmp_path: Path):
    service = DuckDBService()
    service.connect(str(tmp_path / "concurrency.duckdb"))
    service.execute("CREATE TABLE t AS SELECT * FROM range(10) r(i)")
    try:
        yield service
    finally:
        service.disconnect()


def test_lock_is_free_while_a_statement_is_in_flight(db: DuckDBService) -> None:
    """The invariant, stated without timing: mid-statement, _lock is available."""
    with db._borrowed_cursor() as cursor:
        cursor.execute("SELECT 1")
        acquired = db._lock.acquire(blocking=False)
        if acquired:
            db._lock.release()

    assert acquired, "the service-wide lock was held for the whole statement"


def test_list_tables_does_not_queue_behind_a_long_query(db: DuckDBService) -> None:
    """A metadata read must complete *before* a slow query finishes, not after."""
    finished: list[str] = []
    started = threading.Event()

    def slow() -> None:
        started.set()
        db.execute(SLOW_SQL)
        finished.append("slow_query")

    def light() -> None:
        started.wait(timeout=5)
        db.list_tables()
        finished.append("list_tables")

    slow_thread = threading.Thread(target=slow)
    light_thread = threading.Thread(target=light)
    slow_thread.start()
    light_thread.start()
    slow_thread.join(timeout=60)
    light_thread.join(timeout=60)

    assert finished == ["list_tables", "slow_query"], (
        f"list_tables was serialised behind the slow query: {finished}"
    )


def test_concurrent_queries_all_return_their_own_results(db: DuckDBService) -> None:
    """Cursors are independent — results must not bleed between threads."""
    results: dict[int, int] = {}
    lock = threading.Lock()

    def run(n: int) -> None:
        _, rows, _ = db.execute(f"SELECT {n} * 2 AS doubled")
        with lock:
            results[n] = rows[0][0]

    threads = [threading.Thread(target=run, args=(n,)) for n in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert results == {n: n * 2 for n in range(12)}


def test_disconnect_waits_for_an_in_flight_cursor(db: DuckDBService) -> None:
    """Narrowing the lock must not let disconnect close the parent mid-query.

    Without the drain, this is a use-after-close crash rather than a clean wait.
    """
    holding = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def hold_a_cursor() -> None:
        try:
            with db._borrowed_cursor() as cursor:
                holding.set()
                release.wait(timeout=10)
                # Must still be usable: the parent cannot have been closed.
                cursor.execute("SELECT count(*) FROM t").fetchone()
        except BaseException as exc:  # noqa: BLE001 - reported to the main thread
            errors.append(exc)

    worker = threading.Thread(target=hold_a_cursor)
    worker.start()
    assert holding.wait(timeout=5)

    disconnected = threading.Event()

    def disconnect() -> None:
        db.disconnect()
        disconnected.set()

    closer = threading.Thread(target=disconnect)
    closer.start()

    # disconnect must still be blocked, because a cursor is outstanding.
    assert not disconnected.wait(timeout=0.5), "disconnect closed the DB under a live cursor"

    release.set()
    worker.join(timeout=10)
    closer.join(timeout=10)

    assert not errors, f"the in-flight cursor was invalidated: {errors!r}"
    assert disconnected.is_set(), "disconnect never completed after the cursor was returned"
    assert not db.is_connected


def test_export_to_csv_streams_without_holding_the_lock(db: DuckDBService, tmp_path: Path) -> None:
    """The COPY path takes the same borrowed cursor, and still counts rows."""
    out = tmp_path / "out.csv"

    rows_written = db.export_to_csv("SELECT * FROM t ORDER BY i", str(out))

    assert rows_written == 10
    assert out.exists()
    assert len(out.read_text(encoding="utf-8").strip().splitlines()) == 11  # header + 10


def test_export_to_csv_still_accepts_parameters(db: DuckDBService, tmp_path: Path) -> None:
    out = tmp_path / "filtered.csv"

    rows_written = db.export_to_csv("SELECT * FROM t WHERE i >= ?", str(out), params=[7])

    assert rows_written == 3
