from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import app
from backend.api.endpoints import importer
from backend.models.importer import CSVMappingPayload
from backend.services.csv_import_service import CSVImportService


def test_parse_csv_returns_headers_and_preview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CSVImportService, "TEMP_DIR", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/api/parse-csv",
        files={"file": ("sample.csv", b"id,name\n1,Alice\n2,Bob\n", "text/csv")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["headers"] == ["id", "name"]
    assert payload["preview"] == [["1", "Alice"], ["2", "Bob"]]
    assert (tmp_path / payload["file_id"]).exists()


def test_parse_csv_enforces_upload_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importer, "MAX_PARSE_CSV_BYTES", 8)

    client = TestClient(app)
    response = client.post(
        "/api/parse-csv",
        files={"file": ("too-large.csv", b"123456789", "text/csv")},
    )

    assert response.status_code == 413
    assert "maximum allowed size" in response.json()["detail"]


def test_csv_mapping_payload_rejects_path_traversal_file_id() -> None:
    with pytest.raises(ValidationError, match="file_id is invalid"):
        CSVMappingPayload(
            file_id="../escape.csv",
            target_table="safe_table",
            column_map=[],
        )


def test_csv_mapping_payload_rejects_invalid_target_table() -> None:
    with pytest.raises(ValidationError, match="target_table must start with a letter or underscore"):
        CSVMappingPayload(
            file_id="safe_file.csv",
            target_table="users; DROP TABLE master;",
            column_map=[],
        )
