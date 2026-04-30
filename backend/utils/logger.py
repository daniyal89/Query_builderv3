import json
import logging
import sys
from datetime import datetime, timezone
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

    formatter = JsonFormatter()

    # File Handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    
    # Stream Handler (Stdout)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    
    # Prevent propagation to the root logger to avoid duplicate standard logs
    logger.propagate = False

    return logger


# Instantiate the global logger
app_logger = setup_logger()
