import duckdb
from datetime import datetime
from pathlib import Path

from backend.models.local_object import FileObjectRequest, FilePreviewResponse
from backend.services.duckdb_service import DuckDBService


def test_create_table_from_csv_file(tmp_path: Path) -> None:
    db_path = tmp_path / "local.duckdb"
    csv_path = tmp_path / "source.csv"
    csv_path.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")

    db = DuckDBService()
    db.connect(str(db_path))

    metadata = db.create_object_from_file(
        FileObjectRequest(
            file_path=str(csv_path),
            object_name="source_table",
            object_type="TABLE",
        )
    )

    assert metadata.table_name == "source_table"
    assert metadata.row_count == 2
    assert [column.name for column in metadata.columns] == ["id", "name"]
    columns, rows, total = db.execute('SELECT * FROM "source_table" ORDER BY id')
    assert columns == ["id", "name"]
    assert rows == [[1, "Alice"], [2, "Bob"]]
    assert total == 2


def test_create_view_from_csv_file_is_listed(tmp_path: Path) -> None:
    db_path = tmp_path / "local.duckdb"
    csv_path = tmp_path / "source.csv"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")

    db = DuckDBService()
    db.connect(str(db_path))
    db.create_object_from_file(
        FileObjectRequest(
            file_path=str(csv_path),
            object_name="source_view",
            object_type="VIEW",
        )
    )

    tables = db.list_tables()

    assert "source_view" in {table.table_name for table in tables}
    columns, rows, _ = db.execute('SELECT * FROM "source_view"')
    assert columns == ["id", "name"]
    assert rows == [[1, "Alice"]]


def test_file_preview_response_accepts_datetime_cells() -> None:
    payload = FilePreviewResponse(
        columns=["dt"],
        rows=[[datetime(2026, 3, 1, 4, 57)]],
    )

    assert payload.columns == ["dt"]
    assert len(payload.rows) == 1


def test_create_object_replace_can_switch_table_to_view(tmp_path: Path) -> None:
    db_path = tmp_path / "switch_type_local.duckdb"
    csv_path = tmp_path / "source.csv"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")

    db = DuckDBService()
    db.connect(str(db_path))

    db.create_object_from_file(
        FileObjectRequest(
            file_path=str(csv_path),
            object_name="MASTER",
            object_type="TABLE",
            replace=True,
        )
    )
    db.create_object_from_file(
        FileObjectRequest(
            file_path=str(csv_path),
            object_name="master",
            object_type="VIEW",
            replace=True,
        )
    )

    with duckdb.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = 'master'"
        ).fetchone()

    assert row is not None
    assert row[0] == "VIEW"


def test_drop_object_removes_local_table(tmp_path: Path) -> None:
    db_path = tmp_path / "drop_test.duckdb"
    csv_path = tmp_path / "source.csv"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")

    db = DuckDBService()
    db.connect(str(db_path))
    db.create_object_from_file(
        FileObjectRequest(
            file_path=str(csv_path),
            object_name="drop_me",
            object_type="TABLE",
            replace=True,
        )
    )

    dropped_type = db.drop_object("drop_me")
    assert dropped_type == "BASE TABLE"

    with duckdb.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND lower(table_name) = 'drop_me'"
        ).fetchone()
    assert row is None
