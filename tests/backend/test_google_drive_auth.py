from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.services.google_drive_service import GoogleDriveService


class _FakeCredentials:
    def __init__(self, token: str = "access-token", refresh_token: str = "refresh-token") -> None:
        self.token = token
        self.refresh_token = refresh_token
        self.valid = True


def test_drive_logout_clears_cached_token_and_revokes_remote_grant(
    tmp_path: Path,
    monkeypatch,
) -> None:
    token_path = tmp_path / "google_drive_token.json"
    token_path.write_text("{}", encoding="utf-8")
    (tmp_path / "google_oauth_client.json").write_text("{}", encoding="utf-8")

    revoked_tokens: list[str] = []

    monkeypatch.setattr(GoogleDriveService, "_user_config_dir", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        GoogleDriveService,
        "_load_cached_oauth_credentials",
        staticmethod(lambda _token_path: _FakeCredentials()),
    )
    monkeypatch.setattr(
        GoogleDriveService,
        "_revoke_oauth_token",
        staticmethod(lambda token: revoked_tokens.append(token or "") or bool(token)),
    )

    client = TestClient(app)
    response = client.post("/api/drive/auth/logout")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "configured": True,
        "token_exists": False,
        "token_valid": False,
        "message": "Signed out from Google Drive and cleared the cached login token.",
    }
    assert revoked_tokens == ["refresh-token"]
    assert not GoogleDriveService._has_cached_oauth_token(token_path)
    if token_path.exists():
        assert token_path.read_text(encoding="utf-8") == ""


def test_drive_logout_is_idempotent_when_cached_token_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(GoogleDriveService, "_user_config_dir", classmethod(lambda cls: tmp_path))
    (tmp_path / "google_oauth_client.json").write_text("{}", encoding="utf-8")

    client = TestClient(app)
    response = client.post("/api/drive/auth/logout")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "configured": True,
        "token_exists": False,
        "token_valid": False,
        "message": "No cached Google login token was found.",
    }
