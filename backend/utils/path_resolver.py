"""
path_resolver.py — Resolves filesystem paths for PyInstaller compatibility.

When running as a frozen PyInstaller executable, bundled data files are
extracted to a temporary directory accessed via sys._MEIPASS. This module
abstracts that logic so the rest of the codebase never touches sys._MEIPASS
directly.
"""

import sys
from pathlib import Path


def get_base_dir() -> Path:
    """Return the application root directory.

    In a frozen PyInstaller build, this is the temporary extraction folder.
    In development, this is the project root (parent of backend/).
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent.parent


def get_static_dir() -> Path:
    """Return the absolute path to the frontend_dist/ directory.

    This is where the compiled React static files (index.html, assets/)
    are located, whether running from source or from a bundled exe.
    """
    return get_base_dir() / "frontend_dist"


def get_resource_path(relative_path: str) -> Path:
    """Resolve a relative resource path to its absolute location.

    Args:
        relative_path: Path relative to the application root.

    Returns:
        Absolute Path to the resource.

    Raises:
        FileNotFoundError: If the resolved path does not exist.
    """
    resolved = get_base_dir() / relative_path
    if not resolved.exists():
        raise FileNotFoundError(f"Resource not found: {resolved}")
    return resolved
