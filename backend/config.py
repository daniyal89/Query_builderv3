"""
config.py — Centralized runtime settings for the FastAPI backend.

Resolves the static files directory using sys._MEIPASS when running as a
frozen PyInstaller executable, falling back to the project root in dev mode.
"""

import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import AliasChoices, Field
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


def _candidate_env_paths() -> list[Path]:
    base = _resolve_base_dir()
    return [base / ".env", base / "backend" / ".env", Path.cwd() / ".env"]


def _read_env_value(env_path: Path, key: str) -> str | None:
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() != key:
                continue
            return value.strip().strip("\"\'")
    except OSError:
        return None
    return None


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
        env_file=str(_resolve_base_dir() / ".env"),
        env_file_encoding="utf-8",
        extra="allow",  # Allow extra fields so pydantic-settings can read proxy vars
    )

    # Standard proxy vars (not prefixed with DASHBOARD_)
    HTTP_PROXY: str | None = Field(default=None, validation_alias=AliasChoices("DASHBOARD_HTTP_PROXY", "HTTP_PROXY", "http_proxy", "QUERY_BUILDER_HTTP_PROXY"))
    HTTPS_PROXY: str | None = Field(default=None, validation_alias=AliasChoices("DASHBOARD_HTTPS_PROXY", "HTTPS_PROXY", "https_proxy", "QUERY_BUILDER_HTTPS_PROXY"))
    NO_PROXY: str | None = Field(default=None, validation_alias=AliasChoices("DASHBOARD_NO_PROXY", "NO_PROXY", "no_proxy", "QUERY_BUILDER_NO_PROXY"))
    PROXY_HOST: str | None = Field(default=None, validation_alias=AliasChoices("DASHBOARD_PROXY_HOST", "PROXY_HOST", "QUERY_BUILDER_PROXY_HOST"))
    PROXY_PORT: int | None = Field(default=None, validation_alias=AliasChoices("DASHBOARD_PROXY_PORT", "PROXY_PORT", "QUERY_BUILDER_PROXY_PORT"))
    PROXY_USER: str | None = Field(default=None, validation_alias=AliasChoices("DASHBOARD_PROXY_USER", "PROXY_USER", "QUERY_BUILDER_PROXY_USER"))
    PROXY_PASS: str | None = Field(default=None, validation_alias=AliasChoices("DASHBOARD_PROXY_PASS", "PROXY_PASS", "QUERY_BUILDER_PROXY_PASS"))
    GOOGLE_API_BASE_URL: str = "https://www.googleapis.com/"

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        import os

        def _normalize_proxy(value: str | None) -> str | None:
            if not value:
                return None
            cleaned = value.strip()
            if not cleaned:
                return None
            if "://" not in cleaned:
                cleaned = f"http://{cleaned}"
            parsed = urlparse(cleaned)
            if not parsed.hostname:
                return None
            return cleaned
        
        env_paths = _candidate_env_paths()

        def _from_env_files(*keys: str) -> str | None:
            for env_path in env_paths:
                for key in keys:
                    value = _read_env_value(env_path, key)
                    if value:
                        return value
            return None

        # Load proxy settings from settings, process env, or .env file fallback and
        # inject them into os.environ so urllib/requests/google-auth can use them.
        http_proxy = _normalize_proxy(
            self.HTTP_PROXY
            or os.getenv("DASHBOARD_HTTP_PROXY")
            or os.getenv("QUERY_BUILDER_HTTP_PROXY")
            or os.getenv("HTTP_PROXY")
            or os.getenv("http_proxy")
            or _from_env_files("DASHBOARD_HTTP_PROXY", "QUERY_BUILDER_HTTP_PROXY", "HTTP_PROXY")
        )
        https_proxy = _normalize_proxy(
            self.HTTPS_PROXY
            or os.getenv("DASHBOARD_HTTPS_PROXY")
            or os.getenv("QUERY_BUILDER_HTTPS_PROXY")
            or os.getenv("HTTPS_PROXY")
            or os.getenv("https_proxy")
            or _from_env_files("DASHBOARD_HTTPS_PROXY", "QUERY_BUILDER_HTTPS_PROXY", "HTTPS_PROXY")
        )
        no_proxy = (
            self.NO_PROXY
            or os.getenv("DASHBOARD_NO_PROXY")
            or os.getenv("QUERY_BUILDER_NO_PROXY")
            or os.getenv("NO_PROXY")
            or os.getenv("no_proxy")
            or _from_env_files("DASHBOARD_NO_PROXY", "QUERY_BUILDER_NO_PROXY", "NO_PROXY")
        )

        # If only one proxy is configured, reuse it for both protocols because
        # Google APIs are HTTPS and many enterprise proxies expose one endpoint.
        if http_proxy and not https_proxy:
            https_proxy = http_proxy
        if https_proxy and not http_proxy:
            http_proxy = https_proxy

        if http_proxy:
            os.environ["HTTP_PROXY"] = http_proxy
            os.environ["http_proxy"] = http_proxy
        if https_proxy:
            os.environ["HTTPS_PROXY"] = https_proxy
            os.environ["https_proxy"] = https_proxy
            os.environ["ALL_PROXY"] = https_proxy
            os.environ["all_proxy"] = https_proxy
        if no_proxy:
            os.environ["NO_PROXY"] = no_proxy
            os.environ["no_proxy"] = no_proxy

        if not os.getenv("DASHBOARD_PROXY_HOST") and not os.getenv("QUERY_BUILDER_PROXY_HOST"):
            proxy_host_file = _from_env_files("DASHBOARD_PROXY_HOST", "QUERY_BUILDER_PROXY_HOST", "PROXY_HOST")
            if proxy_host_file:
                os.environ.setdefault("DASHBOARD_PROXY_HOST", proxy_host_file)
        if not os.getenv("DASHBOARD_PROXY_PORT") and not os.getenv("QUERY_BUILDER_PROXY_PORT"):
            proxy_port_file = _from_env_files("DASHBOARD_PROXY_PORT", "QUERY_BUILDER_PROXY_PORT", "PROXY_PORT")
            if proxy_port_file:
                os.environ.setdefault("DASHBOARD_PROXY_PORT", proxy_port_file)


settings = Settings()
