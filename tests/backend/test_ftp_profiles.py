"""FTP passwords live on the server, and never travel back out."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import settings
from backend.models.ftp_download import FTPDownloadProfile
from backend.services import ftp_profiles
from backend.services.ftp_download_service import FTPDownloadService
from backend.services.job_runtime import job_runtime


@pytest.fixture
def profiles_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path / "config")
    path = ftp_profiles.ftp_profiles_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "host": "ftp.example.com",
                "profiles": {
                    "KESCO": {"username": "ksftpreport", "password": "secret-k"},
                    "mvvnl": {"username": "mvftpreport", "password": "secret-m"},
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _profile(name: str, password: str | None = None, username: str = "") -> FTPDownloadProfile:
    return FTPDownloadProfile(name=name, username=username, password=password, remote_dir="/x/")


def test_blank_password_is_filled_from_the_file_case_insensitively(profiles_file: Path) -> None:
    resolved = ftp_profiles.resolve_profile_passwords([_profile("kesco"), _profile("MVVNL", username="custom")])

    assert resolved[0].password == "secret-k"
    assert resolved[0].username == "ksftpreport", "username also comes from the file when blank"
    assert resolved[1].password == "secret-m"
    assert resolved[1].username == "custom", "a supplied username wins"


def test_supplied_password_is_left_alone(profiles_file: Path) -> None:
    resolved = ftp_profiles.resolve_profile_passwords([_profile("KESCO", password="typed")])
    assert resolved[0].password == "typed"


def test_unknown_profile_without_password_names_itself_and_the_file(profiles_file: Path) -> None:
    with pytest.raises(ValueError) as excinfo:
        ftp_profiles.resolve_profile_passwords([_profile("PVVNL")])
    assert "PVVNL" in str(excinfo.value)
    assert str(profiles_file) in str(excinfo.value)


def test_missing_file_is_reported_as_absent_not_as_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path / "nowhere")
    assert ftp_profiles.load_ftp_profiles() is None
    assert ftp_profiles.configured_profile_summary()["configured"] is False


def test_broken_file_raises_rather_than_pretending_to_be_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    ftp_profiles.ftp_profiles_path().write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        ftp_profiles.load_ftp_profiles()


def test_profiles_endpoint_never_returns_a_password(profiles_file: Path) -> None:
    response = TestClient(app).get("/api/ftp-download/profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert {item["name"] for item in body["profiles"]} == {"KESCO", "mvvnl"}
    assert "secret" not in response.text


def test_start_with_blank_password_resolves_it_and_persists_none(profiles_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(job_id: str, host, port, output_root, file_suffix, max_workers, max_retries, retry_delay_seconds, timeout_seconds, passive_mode, skip_existing, profiles) -> None:
        seen["passwords"] = [p.password for p in profiles]
        job_runtime.update_job(job_id, status="completed")

    monkeypatch.setattr(FTPDownloadService, "_run_download_job", classmethod(lambda cls, *args: fake_run(*args)))

    response = TestClient(app).post(
        "/api/ftp-download/start",
        json={
            "host": "ftp.example.com",
            "output_root": "./downloads",
            "profiles": [{"name": "KESCO", "username": "", "password": "", "remote_dir": "/x/"}],
        },
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]

    deadline = 50
    while deadline and (job_runtime.get_job(job_id) or {}).get("status") != "completed":
        deadline -= 1
        import time

        time.sleep(0.02)

    assert seen["passwords"] == ["secret-k"], "the worker received the real password"
    record = job_runtime.list_jobs(job_type=FTPDownloadService.JOB_TYPE)[0]
    assert "password" not in record["payload"]["profiles"][0], "the job store must not keep it"
