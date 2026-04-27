from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ErrorLogService:
    """Persist API error events into samples/error for local troubleshooting."""

    ERROR_DIR = Path("samples") / "error"
    ERROR_FILE = ERROR_DIR / "errors.log"
    _lock = threading.Lock()

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
