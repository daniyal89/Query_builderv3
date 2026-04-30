from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.endpoints.sidebar_tools import _resolve_existing_input_glob
from backend.app import app
from backend.utils.rate_limits import DEFAULT_RATE_LIMIT_POLICIES, RateLimitPolicy, rate_limiter


TEST_DB_PATH = Path(__file__).resolve().parents[2] / "test_data.duckdb"


@pytest.fixture(autouse=True)
def reset_rate_limits() -> None:
    rate_limiter.reset()
    for name, policy in DEFAULT_RATE_LIMIT_POLICIES.items():
        rate_limiter.set_policy(name, policy)
    yield
    rate_limiter.reset()
    for name, policy in DEFAULT_RATE_LIMIT_POLICIES.items():
        rate_limiter.set_policy(name, policy)


def _connect_duckdb(client: TestClient) -> None:
    response = client.post("/api/duckdb/connect", json={"db_path": str(TEST_DB_PATH)})
    assert response.status_code == 200, response.text


def test_query_execution_returns_429_after_rate_limit_is_exceeded() -> None:
    rate_limiter.set_policy(
        "query_execute",
        RateLimitPolicy(max_requests=1, window_seconds=60, label="query execution"),
    )

    client = TestClient(app)
    _connect_duckdb(client)

    payload = {
        "execution_mode": "builder",
        "engine": "duckdb",
        "table": "employees",
        "select": ["id"],
        "filters": [],
        "sort": [],
        "limit_rows": 5,
        "offset": 0,
        "mode": "LIST",
        "group_by": [],
        "aggregates": [],
    }

    first = client.post("/api/query", json=payload)
    second = client.post("/api/query", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 429, second.text
    assert second.headers["Retry-After"] == "60"
    assert "Too many query execution requests" in second.json()["detail"]


def test_ftp_download_start_returns_429_after_rate_limit_is_exceeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.api.endpoints import ftp_download

    rate_limiter.set_policy(
        "ftp_download_start",
        RateLimitPolicy(max_requests=1, window_seconds=60, label="FTP download start"),
    )

    monkeypatch.setattr(
        ftp_download.FTPDownloadService,
        "start_download",
        lambda **_kwargs: {"job_id": "job-1", "status": "queued"},
    )

    client = TestClient(app)
    payload = {
        "host": "ftp.example.com",
        "output_root": str(tmp_path / "ftp-out"),
        "profiles": [
            {
                "name": "DVVNL",
                "username": "reader",
                "password": "secret",
                "remote_dir": "/exports",
            }
        ],
    }

    first = client.post("/api/ftp-download/start", json=payload)
    second = client.post("/api/ftp-download/start", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 429, second.text
    assert second.headers["Retry-After"] == "60"
    assert "Too many FTP download start requests" in second.json()["detail"]


def test_duckdb_connect_rejects_path_traversal_before_service_execution() -> None:
    client = TestClient(app)

    response = client.post("/api/duckdb/connect", json={"db_path": "../secrets.duckdb"})

    assert response.status_code == 422
    assert "path traversal" in response.text.lower()


def test_sidebar_tool_glob_helper_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="path traversal"):
        _resolve_existing_input_glob("../*.csv")
