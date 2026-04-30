from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from fastapi import Request

from backend.utils.logger import app_logger


class ErrorLogService:
    """Wrapper over the central structured logger for backward compatibility."""

    _REPO_ROOT = Path(__file__).resolve().parents[2]
    REPO_ROOT = _REPO_ROOT
    ERROR_DIR = _REPO_ROOT / "samples" / "error"
    ERROR_FILE = ERROR_DIR / "errors.log"

    @staticmethod
    def _request_context(request: Request) -> dict[str, Any]:
        return {
            "endpoint": request.url.path,
            "method": request.method,
            "query_params": dict(request.query_params),
            "path_params": dict(request.path_params),
            "client": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent", ""),
            "request_id": getattr(request.state, "request_id", "unknown"),
        }

    @classmethod
    def _write_event(cls, payload: dict[str, Any]) -> None:
        cls.ERROR_DIR.mkdir(parents=True, exist_ok=True)
        with cls.ERROR_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")

    @classmethod
    def append(cls, event: dict[str, Any]) -> None:
        """Legacy generic append method."""
        cls._write_event(event)
        app_logger.error(event.get("error", "Error logged via append"), extra={"extra_info": event})

    @classmethod
    def append_request_error(
        cls,
        request: Request,
        *,
        status_code: int,
        error: str,
        detail: Any,
        exception_type: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            **cls._request_context(request),
            "status_code": status_code,
            "error": error,
            "detail": detail,
            "exception_type": exception_type,
            "event": "request_error",
        }
        if extra:
            payload.update(extra)

        cls._write_event(payload)
        app_logger.error(f"Request Error: {request.method} {request.url.path} - {error}", extra={"extra_info": payload})

    @classmethod
    def append_system_event(cls, *, event: str, detail: str, extra: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "event_type": "system",
            "event": event,
            "detail": detail,
        }
        if extra:
            payload.update(extra)
            
        app_logger.info(f"System Event: {event}", extra={"extra_info": payload})
