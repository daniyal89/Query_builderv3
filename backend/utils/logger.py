import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp_utc": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger_name": record.name,
            "message": record.getMessage(),
        }

        # Add any extra arguments passed via logging extra kwargs
        if hasattr(record, "extra_info") and isinstance(record.extra_info, dict):
            log_entry.update(record.extra_info)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def _is_important_log_entry(log_entry: Dict[str, Any]) -> bool:
    level = str(log_entry.get("level", "")).upper()
    if level in {"WARNING", "ERROR", "CRITICAL"}:
        return True

    status_code = log_entry.get("status_code")
    if isinstance(status_code, int) and status_code >= 400:
        return True

    event_type = str(log_entry.get("event_type", "")).lower()
    event = str(log_entry.get("event", "")).lower()
    if event_type == "system" or event in {"application_startup", "application_shutdown"}:
        return True

    return False


def _prune_log_file(log_file: Path, keep_hours: int = 12, errors_only: bool = False) -> None:
    if not log_file.exists():
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=keep_hours)
    kept_lines: list[str] = []
    for raw_line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
            timestamp_raw = payload.get("timestamp_utc")
            timestamp = datetime.fromisoformat(timestamp_raw) if isinstance(timestamp_raw, str) else None
            if timestamp is None or timestamp.tzinfo is None:
                continue
            if timestamp < cutoff:
                continue
            if errors_only:
                level = str(payload.get("level", "")).upper()
                if level in {"ERROR", "CRITICAL"}:
                    kept_lines.append(raw_line)
                continue
            if _is_important_log_entry(payload):
                kept_lines.append(raw_line)
        except Exception:
            # Drop malformed/non-JSON lines while pruning.
            continue

    log_file.write_text(("\n".join(kept_lines) + ("\n" if kept_lines else "")), encoding="utf-8")


class ImportantLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True

        status_code = getattr(record, "status_code", None)
        if isinstance(status_code, int) and status_code >= 400:
            return True

        event_type = str(getattr(record, "event_type", "")).lower()
        event = str(getattr(record, "event", "")).lower()
        if event_type == "system" or event in {"application_startup", "application_shutdown"}:
            return True

        return False


class ErrorOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.ERROR


def setup_logger() -> logging.Logger:
    """Initialize and configure the centralized application logger."""
    logger = logging.getLogger("duckdb_dashboard")
    
    # Avoid attaching handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Resolve paths relative to this file
    repo_root = Path(__file__).resolve().parents[2]
    logs_dir = repo_root / "samples" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"
    error_log_file = logs_dir / "error.log"
    _prune_log_file(log_file, keep_hours=12)
    _prune_log_file(error_log_file, keep_hours=12, errors_only=True)

    formatter = JsonFormatter()

    # File Handler
    file_handler = TimedRotatingFileHandler(log_file, when="h", interval=12, backupCount=2, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(ImportantLogFilter())

    error_file_handler = TimedRotatingFileHandler(
        error_log_file,
        when="h",
        interval=12,
        backupCount=2,
        encoding="utf-8",
    )
    error_file_handler.setFormatter(formatter)
    error_file_handler.addFilter(ErrorOnlyFilter())
    
    # Stream Handler (Stdout)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(error_file_handler)
    logger.addHandler(stream_handler)
    
    # Prevent propagation to the root logger to avoid duplicate standard logs
    logger.propagate = False

    return logger


# Instantiate the global logger
app_logger = setup_logger()
