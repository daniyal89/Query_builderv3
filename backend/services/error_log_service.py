from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Request


class ErrorLogService:
    """Persist API error events into samples/error for local troubleshooting."""

    ERROR_DIR = Path("samples") / "error"
    ERROR_FILE = ERROR_DIR / "errors.log"
    _lock = threading.Lock()

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
    def append(cls, event: dict[str, Any]) -> None:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        cls.ERROR_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        with cls._lock:
            with cls.ERROR_FILE.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")

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
        }
        if extra:
            payload.update(extra)
        cls.append(payload)
