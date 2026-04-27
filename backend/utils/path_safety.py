"""Utilities for defensive local-path validation."""

from __future__ import annotations

import os
from pathlib import PurePath


def sanitize_local_path_input(value: str, field_name: str) -> str:
    """Normalize user path input and reject empty values."""
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty.")
    if normalized.startswith('"') and normalized.endswith('"'):
        normalized = normalized[1:-1].strip()
    return os.path.expandvars(os.path.expanduser(normalized))


def validate_relative_subpath(value: str, field_name: str) -> str:
    """Allow only safe relative folder segments."""
    normalized = (value or "").strip().replace("\\", "/")
    if not normalized:
        return ""
    pure = PurePath(normalized)
    if pure.is_absolute():
        raise ValueError(f"{field_name} must be a relative subfolder path.")
    if any(part in {"..", ""} for part in pure.parts):
        raise ValueError(f"{field_name} cannot include path traversal segments.")
    return normalized
