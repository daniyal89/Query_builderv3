"""The session preamble has to reach the connection queries actually run on.

`DuckDBService.execute` and `export_to_csv` run on a cursor borrowed from the
service connection, and a DuckDB cursor is an independent connection with its own
session config. A plain `SET` does not reach it. That makes `SET GLOBAL` load-bearing
in a way nothing else in the code signals — the single most likely regression here is
someone "simplifying" it back to `SET`, after which the parquet metadata cache
silently stops applying to every real query.
"""

from pathlib import Path

import duckdb
import pytest

from backend.config import settings
from backend.services.duckdb_service import DuckDBService
from backend.services.duckdb_session import apply_session_settings, resolve_temp_directory


@pytest.fixture
def service(tmp_path: Path):
    svc = DuckDBService()
    svc.connect(str(tmp_path / "session.duckdb"))
    try:
        yield svc
    finally:
        svc.disconnect()


def _setting(conn: duckdb.DuckDBPyConnection, name: str):
    return conn.execute(f"SELECT current_setting('{name}')").fetchone()[0]


def test_the_preamble_reaches_a_borrowed_cursor(service: DuckDBService) -> None:
    """The regression guard for SET vs SET GLOBAL."""
    with service._borrowed_cursor() as cursor:
        assert _setting(cursor, "parquet_metadata_cache") is True


def test_connect_enables_the_parquet_metadata_cache(service: DuckDBService) -> None:
    """DuckDB's default is false, so this only holds because we set it."""
    assert _setting(service._conn, "parquet_metadata_cache") is True


def test_connect_enables_the_external_file_cache(service: DuckDBService) -> None:
    assert _setting(service._conn, "enable_external_file_cache") is True


def test_temp_directory_is_pinned_off_the_working_directory(service: DuckDBService) -> None:
    """The default '.tmp' is CWD-relative and wrong in a frozen exe."""
    configured = str(_setting(service._conn, "temp_directory"))

    assert Path(configured).is_absolute()
    assert configured != ".tmp"
    assert "duckdb_tmp" in configured.replace("\\", "/")


def test_the_temp_directory_exists(service: DuckDBService) -> None:
    """DuckDB will not create it, and a missing path only fails mid-spill."""
    assert Path(str(_setting(service._conn, "temp_directory"))).is_dir()


def test_resolve_temp_directory_lives_under_the_runtime_dir() -> None:
    resolved = resolve_temp_directory()

    assert resolved is not None
    assert settings.RUNTIME_DIR.resolve() in resolved.resolve().parents


def test_an_unwritable_runtime_dir_falls_back_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bad path must leave DuckDB's default in place, not break connecting."""

    def boom(*_args, **_kwargs):
        raise OSError("read-only volume")

    monkeypatch.setattr(Path, "mkdir", boom)

    assert resolve_temp_directory() is None


def test_an_unrecognised_option_does_not_stop_the_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One bad SET must not cost the app its database."""
    real_execute = duckdb.DuckDBPyConnection.execute

    def selective(self, sql, *args, **kwargs):  # type: ignore[no-untyped-def]
        if "parquet_metadata_cache" in str(sql):
            raise duckdb.CatalogException("unrecognised option")
        return real_execute(self, sql, *args, **kwargs)

    monkeypatch.setattr(duckdb.DuckDBPyConnection, "execute", selective)

    svc = DuckDBService()
    try:
        svc.connect(str(tmp_path / "resilient.duckdb"))
        assert svc.is_connected
    finally:
        monkeypatch.undo()
        svc.disconnect()


def test_failed_statements_are_reported_not_swallowed() -> None:
    """The caller can see what did not apply, rather than guessing later."""
    with duckdb.connect() as conn:
        failed = apply_session_settings(conn)

    assert failed == [], f"unexpected preamble failures: {failed}"


def test_the_build_preamble_sets_threads_and_insertion_order() -> None:
    with duckdb.connect() as conn:
        apply_session_settings(conn, threads=3, preserve_insertion_order=False)

        assert _setting(conn, "threads") == 3
        assert _setting(conn, "preserve_insertion_order") is False


def test_settings_do_not_leak_between_databases(tmp_path: Path) -> None:
    """SET GLOBAL is scoped to one DuckDB instance, so tests cannot poison each other.

    Asserted on preserve_insertion_order because its default (true) is fixed, unlike
    `threads`, whose default is the core count and could coincide with any value here.
    """
    with duckdb.connect(str(tmp_path / "a.duckdb")) as first:
        apply_session_settings(first, preserve_insertion_order=False)
        assert _setting(first, "preserve_insertion_order") is False

    with duckdb.connect(str(tmp_path / "b.duckdb")) as second:
        assert _setting(second, "preserve_insertion_order") is True, (
            "session config leaked across DuckDB instances"
        )
