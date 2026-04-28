import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.services.error_log_service import ErrorLogService
from backend.utils.exceptions import InvalidPathError, register_exception_handlers


def test_append_request_error_includes_rich_request_context(tmp_path: Path) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    original_dir = ErrorLogService.ERROR_DIR
    original_file = ErrorLogService.ERROR_FILE
    ErrorLogService.ERROR_DIR = tmp_path
    ErrorLogService.ERROR_FILE = tmp_path / "errors.log"

    @app.middleware("http")
    async def add_request_id(request, call_next):
        request.state.request_id = "req-test-123"
        return await call_next(request)

    @app.get("/boom")
    def boom() -> None:
        raise InvalidPathError("Bad path provided")

    @app.get("/http")
    def http_error() -> None:
        raise HTTPException(status_code=404, detail="missing")

    @app.exception_handler(HTTPException)
    async def log_http_exception(request, exc: HTTPException):
        ErrorLogService.append_request_error(
            request,
            status_code=exc.status_code,
            error=str(exc.detail),
            detail=exc.detail,
            exception_type=type(exc).__name__,
        )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    try:
        client = TestClient(app)
        invalid_resp = client.get("/boom?source=unit")
        assert invalid_resp.status_code == 400

        http_resp = client.get("/http?source=unit")
        assert http_resp.status_code == 404

        lines = ErrorLogService.ERROR_FILE.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

        first = json.loads(lines[0])
        second = json.loads(lines[1])

        assert first["endpoint"] == "/boom"
        assert first["method"] == "GET"
        assert first["query_params"]["source"] == "unit"
        assert first["request_id"] == "req-test-123"
        assert first["status_code"] == 400
        assert first["exception_type"] == "InvalidPathError"

        assert second["endpoint"] == "/http"
        assert second["status_code"] == 404
        assert second["exception_type"] == "HTTPException"
    finally:
        ErrorLogService.ERROR_DIR = original_dir
        ErrorLogService.ERROR_FILE = original_file
