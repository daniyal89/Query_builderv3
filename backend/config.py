"""
config.py — Centralized runtime settings for the FastAPI backend.

Resolves the static files directory using sys._MEIPASS when running as a
frozen PyInstaller executable, falling back to the project root in dev mode.
"""

import sys
from pathlib import Path
from typing import Any

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
        extra="allow",  # Allow extra fields so pydantic-settings can read proxy vars
    )

    # Standard proxy vars (not prefixed with DASHBOARD_)
    HTTP_PROXY: str | None = None
    HTTPS_PROXY: str | None = None
    NO_PROXY: str | None = None

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        import os
        
        # Load proxy settings from either DASHBOARD_* or standard env vars and
        # inject them into os.environ so urllib/requests/google-auth can use them.
        http_proxy = self.HTTP_PROXY or os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        https_proxy = self.HTTPS_PROXY or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
        no_proxy = self.NO_PROXY or os.getenv("NO_PROXY") or os.getenv("no_proxy")

        if http_proxy:
            os.environ["HTTP_PROXY"] = http_proxy
            os.environ["http_proxy"] = http_proxy
        if https_proxy:
            os.environ["HTTPS_PROXY"] = https_proxy
            os.environ["https_proxy"] = https_proxy
        if no_proxy:
            os.environ["NO_PROXY"] = no_proxy
            os.environ["no_proxy"] = no_proxy


settings = Settings()
