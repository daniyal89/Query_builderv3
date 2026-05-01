from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.deps import get_connected_db
from backend.api.endpoints import merge
from backend.app import app
from backend.models.merge import FolderMergeRequest


def test_upload_sheets_accepts_csv_without_connected_db() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/upload-sheets",
        files=[("files", ("sample.csv", b"ACCT_ID,NAME\n1,Alice\n", "text/csv"))],
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["conflicts"] == []
    assert [column["name"] for column in payload["detected_columns"]] == ["ACCT_ID", "NAME"]


def test_upload_sheets_enforces_total_upload_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(merge, "MAX_UPLOAD_SHEETS_FILE_BYTES", 32)
    monkeypatch.setattr(merge, "MAX_UPLOAD_SHEETS_TOTAL_BYTES", 10)

    client = TestClient(app)
    response = client.post(
        "/api/upload-sheets",
        files=[("files", ("sample.csv", b"01234567890", "text/csv"))],
    )

    assert response.status_code == 413
    assert "maximum allowed size" in response.json()["detail"]


def test_enrich_data_enforces_upload_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyDb:
        _conn = object()

    monkeypatch.setattr(merge, "MAX_ENRICH_UPLOAD_BYTES", 8)
    app.dependency_overrides[get_connected_db] = lambda: DummyDb()

    try:
        client = TestClient(app)
        response = client.post(
            "/api/enrich-data",
            data={
                "db_path": str(Path("D:/data/master.duckdb")),
                "master_table": "master",
                "fetch_columns": '["NAME"]',
                "join_keys": '[{"fileColumn":"ACCT_ID","tableColumn":"ACCT_ID"}]',
            },
            files={"file": ("sample.csv", b"0123456789", "text/csv")},
        )
    finally:
        app.dependency_overrides.pop(get_connected_db, None)

    assert response.status_code == 413
    assert "maximum allowed size" in response.json()["detail"]


def test_folder_merge_request_rejects_parent_traversal() -> None:
    with pytest.raises(ValidationError, match="path traversal segments"):
        FolderMergeRequest(
            source_folder="..\\secret",
            output_path="D:\\Output\\merged.csv",
        )
