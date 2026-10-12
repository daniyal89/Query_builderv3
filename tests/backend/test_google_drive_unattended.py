"""An unattended Drive job must fail fast instead of waiting for a browser nobody will open."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.models.google_drive import DriveAuthConfig
from backend.services import google_drive_service as mod
from backend.services.google_drive_service import DriveLoginRequiredError, GoogleDriveService


class _Expired:
    valid = False
    expired = True

    def __init__(self, refresh_token: str | None, fail: bool = False) -> None:
        self.refresh_token = refresh_token
        self._fail = fail
        self.refreshed = False

    def refresh(self, _request) -> None:
        if self._fail:
            raise RuntimeError("invalid_grant: Token has been expired or revoked.")
        self.refreshed = True
        self.valid = True

    def to_json(self) -> str:
        return "{}"


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "google_oauth_client.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(GoogleDriveService, "_user_config_dir", staticmethod(lambda: tmp_path))

    def never(*_a, **_k):
        raise AssertionError("InstalledAppFlow must not be used when interactive=False")

    monkeypatch.setattr(mod.InstalledAppFlow, "from_client_secrets_file", never)
    monkeypatch.setattr(mod, "build", lambda *a, **k: object())
    monkeypatch.setattr(GoogleDriveService, "_build_google_http", classmethod(lambda cls, creds, auth=None: None))
    monkeypatch.setattr(GoogleDriveService, "_apply_google_api_base_url", classmethod(lambda cls, service: service))
    return tmp_path


def test_no_token_raises_login_required_instead_of_opening_a_browser(config_dir: Path) -> None:
    with pytest.raises(DriveLoginRequiredError) as excinfo:
        GoogleDriveService._get_drive_service(DriveAuthConfig(mode="oauth"), interactive=False)
    assert "Upload master in Drive" in str(excinfo.value)


def test_expired_token_that_can_refresh_is_refreshed_silently(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (config_dir / "google_drive_token.json").write_text("{}", encoding="utf-8")
    creds = _Expired(refresh_token="r")
    monkeypatch.setattr(GoogleDriveService, "_load_cached_oauth_credentials", staticmethod(lambda _p: creds))

    GoogleDriveService._get_drive_service(DriveAuthConfig(mode="oauth"), interactive=False)

    assert creds.refreshed is True


def test_refresh_failure_unattended_becomes_login_required(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The 7-day expiry of a Testing-mode OAuth app lands here: refresh is refused.
    (config_dir / "google_drive_token.json").write_text("{}", encoding="utf-8")
    creds = _Expired(refresh_token="r", fail=True)
    monkeypatch.setattr(GoogleDriveService, "_load_cached_oauth_credentials", staticmethod(lambda _p: creds))

    with pytest.raises(DriveLoginRequiredError) as excinfo:
        GoogleDriveService._get_drive_service(DriveAuthConfig(mode="oauth"), interactive=False)
    assert "invalid_grant" in str(excinfo.value)
