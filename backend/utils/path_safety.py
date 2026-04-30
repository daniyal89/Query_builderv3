"""Utilities for defensive local-path validation."""

from __future__ import annotations

import os
import re
from pathlib import PurePath


def sanitize_local_path_input(value: str, field_name: str) -> str:
    """Normalize user path input and reject empty values."""
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty.")
    if normalized.startswith('"') and normalized.endswith('"'):
        normalized = normalized[1:-1].strip()
    expanded = os.path.expandvars(os.path.expanduser(normalized))
    pure = PurePath(expanded)
    if any(part == ".." for part in pure.parts):
        raise ValueError(f"{field_name} cannot include path traversal segments.")
    return expanded


def sanitize_dialog_filename(value: str | None, default_name: str) -> str:
    """Reduce save-dialog suggestions to a safe leaf filename."""
    normalized = (value or "").strip()
    if not normalized:
        normalized = default_name
    basename = normalized.replace("\\", "/").split("/")[-1].strip()
    if not basename or basename in {".", ".."}:
        return default_name
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", basename).strip().strip(".")
    return cleaned or default_name


def sanitize_file_extension(
    value: str | None,
    default_extension: str,
    allowed_extensions: set[str] | None = None,
) -> str:
    """Normalize user-provided save extensions to a conservative allowlist."""
    normalized = (value or "").strip()
    if not normalized:
        return default_extension
    basename = normalized.replace("\\", "/").split("/")[-1].strip()
    if not basename:
        return default_extension
    if not basename.startswith("."):
        basename = f".{basename.lstrip('.')}"
    if not re.fullmatch(r"\.[A-Za-z0-9]{1,10}", basename):
        return default_extension
    if allowed_extensions and basename.lower() not in {item.lower() for item in allowed_extensions}:
        return default_extension
    return basename


def validate_relative_subpath(value: str, field_name: str) -> str:
    """Allow only safe relative folder segments."""
    normalized = (value or "").strip().replace("\\", "/")
    if not normalized:
        return ""
    pure = PurePath(normalized)
    if pure.is_absolute() or getattr(pure, "drive", "") or getattr(pure, "root", ""):
        raise ValueError(f"{field_name} must be a relative subfolder path.")
    if any(part in {"..", ""} for part in pure.parts):
        raise ValueError(f"{field_name} cannot include path traversal segments.")
    return normalized
