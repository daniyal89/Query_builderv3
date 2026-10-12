"""Server-side FTP credentials.

The five DISCOM passwords used to live in the frontend source, which compiled
them into the shipped bundle and left them in git history. They now live in
``config/ftp_profiles.json`` beside the exe (gitignored), and are read only
here. A request may name a profile without a password; the password is filled
in from this file and is never written back to the API or the job store.

File shape::

    {
      "host": "ftp.uppclonline.com",
      "port": 21,
      "profiles": {
        "MVVNL": {"username": "mvftpreport", "password": "..."},
        "DVVNL": {"username": "dvftpreport", "password": "..."}
      }
    }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from backend.config import settings
from backend.models.ftp_download import FTPDownloadProfile

FTP_PROFILES_FILENAME = "ftp_profiles.json"


class FtpProfileCredential(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class FtpProfilesFile(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    profiles: dict[str, FtpProfileCredential] = Field(default_factory=dict)

    def find(self, name: str) -> FtpProfileCredential | None:
        wanted = name.strip().upper()
        for key, credential in self.profiles.items():
            if key.strip().upper() == wanted:
                return credential
        return None


def ftp_profiles_path() -> Path:
    return settings.CONFIG_DIR / FTP_PROFILES_FILENAME


def load_ftp_profiles() -> FtpProfilesFile | None:
    """Return the configured profiles, or None when the file is absent.

    A present-but-broken file raises, because silently treating it as absent
    would make every unattended run fail with "password required" and send
    the operator looking in the wrong place.
    """
    path = ftp_profiles_path()
    if not path.is_file():
        return None
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        return FtpProfilesFile.model_validate(raw)
    except (OSError, ValueError, ValidationError) as exc:
        raise ValueError(f"Could not read FTP profiles from {path}: {exc}") from exc


def configured_profile_summary() -> dict[str, Any]:
    """What the UI may know: names and usernames, never passwords."""
    loaded = load_ftp_profiles()
    if loaded is None:
        return {"configured": False, "path": str(ftp_profiles_path()), "host": None, "port": None, "profiles": []}
    return {
        "configured": True,
        "path": str(ftp_profiles_path()),
        "host": loaded.host,
        "port": loaded.port,
        "profiles": [
            {"name": name, "username": credential.username}
            for name, credential in loaded.profiles.items()
        ],
    }


def resolve_profile_passwords(profiles: list[FTPDownloadProfile]) -> list[FTPDownloadProfile]:
    """Fill in any profile whose password was left blank.

    Raises ValueError naming the profile when it is neither supplied nor
    configured, so the message says exactly which DISCOM to add to the file.
    """
    missing = [profile for profile in profiles if not (profile.password or "").strip()]
    if not missing:
        return list(profiles)

    loaded = load_ftp_profiles()
    resolved: list[FTPDownloadProfile] = []
    for profile in profiles:
        if (profile.password or "").strip():
            resolved.append(profile)
            continue
        credential = loaded.find(profile.name) if loaded else None
        if credential is None:
            raise ValueError(
                f"No password given for FTP profile '{profile.name}' and it is not configured in "
                f"{ftp_profiles_path()}. Add it there, or enter the password in the form."
            )
        username = profile.username.strip() or credential.username
        resolved.append(profile.model_copy(update={"username": username, "password": credential.password}))
    return resolved
