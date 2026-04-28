from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.utils.exceptions import (
    CSVParseError,
    DatabaseNotConnectedError,
    InvalidPathError,
    QueryBuildError,
    register_exception_handlers,
)


def _client_for_exception(exc: Exception) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise exc

    return TestClient(app)


def test_database_not_connected_handler() -> None:
    client = _client_for_exception(DatabaseNotConnectedError("Connect first"))
    response = client.get("/boom")
    assert response.status_code == 409
    assert response.json()["error"] == "DatabaseNotConnectedError"
    assert response.json()["request_id"] == "unknown"


def test_invalid_path_handler() -> None:
    client = _client_for_exception(InvalidPathError("Bad path"))
    response = client.get("/boom")
    assert response.status_code == 400
    assert response.json()["error"] == "InvalidPathError"
    assert response.json()["request_id"] == "unknown"


def test_query_build_handler() -> None:
    client = _client_for_exception(QueryBuildError("Invalid filter"))
    response = client.get("/boom")
    assert response.status_code == 422
    assert response.json()["error"] == "QueryBuildError"
    assert response.json()["request_id"] == "unknown"


def test_csv_parse_handler() -> None:
    client = _client_for_exception(CSVParseError("Cannot parse csv"))
    response = client.get("/boom")
    assert response.status_code == 400
    assert response.json()["error"] == "CSVParseError"
    assert response.json()["request_id"] == "unknown"
