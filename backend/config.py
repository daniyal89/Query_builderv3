"""
config.py — Centralized runtime settings for the FastAPI backend.

Resolves the static files directory using sys._MEIPASS when running as a
frozen PyInstaller executable, falling back to the project root in dev mode.
"""

import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_base_dir() -> Path:
    """Return the base directory, accounting for PyInstaller's temp extraction path."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def _resolve_runtime_dir() -> Path:
    """Return a writable runtime directory for persistent local state."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "runtime"
    return _resolve_base_dir() / "runtime"


class Settings(BaseSettings):
    """Application-wide configuration constants."""

    APP_TITLE: str = "DuckDB Data Dashboard"
    HOST: str = "127.0.0.1"
    PORT: int = 8741
    DEBUG: bool = False
    ENV_PROFILE: str = "dev"

    BASE_DIR: Path = _resolve_base_dir()
    STATIC_DIR: Path = BASE_DIR / "frontend_dist"
    RUNTIME_DIR: Path = _resolve_runtime_dir()
    JOB_STORE_PATH: Path = RUNTIME_DIR / "job_store.sqlite3"
    JOB_RECOVER_INTERRUPTED: bool = True

    model_config = SettingsConfigDict(
        env_prefix="DASHBOARD_",
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
