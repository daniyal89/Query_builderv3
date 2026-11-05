"""Per-computer defaults for the FTP Download page.

The project runs on several machines whose data drives differ, so the output
root must not be baked into the bundle. It lives in
``config/ftp_download_settings.json`` beside the exe (gitignored), one entry
per preset kind. Starting a download records the root that was used, so the
next visit on that machine offers it back as the default.

File shape::

    {
      "output_roots": {
        "master": "D:/DATA/MASTER",
        "billed": "D:/DATA/BILLED"
      }
    }

When nothing has been saved yet, the master root falls back to the monthly
automation ``csv_root`` (the same folder the one-click run downloads into), and
the billed root to a ``BILLED`` folder beside it.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path, PurePath
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from backend.config import settings
from backend.utils.path_safety import sanitize_local_path_input

FTP_DOWNLOAD_SETTINGS_FILENAME = "ftp_download_settings.json"

PresetKind = Literal["master", "billed"]
PRESET_KINDS: tuple[PresetKind, ...] = ("master", "billed")

_write_lock = threading.Lock()


class FtpDownloadSettingsFile(BaseModel):
    output_roots: dict[str, str] = Field(default_factory=dict)


def ftp_download_settings_path() -> Path:
    return settings.CONFIG_DIR / FTP_DOWNLOAD_SETTINGS_FILENAME


def load_settings() -> FtpDownloadSettingsFile:
    """Return the saved settings, or empty ones when the file is absent.

    A present-but-broken file raises: silently ignoring it would make the page
    keep offering a default the operator believed they had changed.
    """
    path = ftp_download_settings_path()
    if not path.is_file():
        return FtpDownloadSettingsFile()
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        return FtpDownloadSettingsFile.model_validate(raw)
    except (OSError, ValueError, ValidationError) as exc:
        raise ValueError(f"Could not read FTP download settings from {path}: {exc}") from exc


def _fallback_output_roots() -> dict[str, str]:
    # Imported here: monthly_run_service pulls in the whole pipeline, and this
    # module must stay cheap to import from the endpoint.
    from backend.services.monthly_run_service import load_config

    try:
        csv_root = load_config().csv_root
    except ValueError:
        return {}
    return {"master": csv_root, "billed": str(PurePath(csv_root).parent / "BILLED")}


def effective_output_roots() -> dict[str, dict[str, str | None]]:
    """Per preset kind: the saved root, and the value the page should offer."""
    saved = load_settings().output_roots
    fallback = _fallback_output_roots()
    result: dict[str, dict[str, str | None]] = {}
    for kind in PRESET_KINDS:
        saved_value = (saved.get(kind) or "").strip() or None
        result[kind] = {"saved": saved_value, "effective": saved_value or fallback.get(kind)}
    return result


def save_output_roots(output_roots: dict[str, str]) -> Path:
    """Merge the given roots into the file; kinds not mentioned keep their value."""
    cleaned: dict[str, str] = {}
    for kind, value in output_roots.items():
        if kind not in PRESET_KINDS:
            raise ValueError(f"Unknown preset kind '{kind}'. Expected one of: {', '.join(PRESET_KINDS)}.")
        cleaned[kind] = sanitize_local_path_input(value, f"output_roots.{kind}")

    with _write_lock:
        current = load_settings()
        current.output_roots.update(cleaned)
        path = ftp_download_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(current.model_dump(mode="json"), indent=2), encoding="utf-8")
        tmp.replace(path)
    return path
