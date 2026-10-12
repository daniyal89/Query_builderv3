"""A flaky link must not fail an upload that would succeed a moment later.

The first real monthly run lost its Drive step to one 60-second read timeout
while listing a folder -- before a single file was sent. Repeating the tree is
cheap (files already in Drive are skipped by name), so transient network
errors get another attempt; wrong input and an expired login do not.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httplib2
import pytest
from googleapiclient.errors import HttpError

from backend.models.google_drive import DriveAuthConfig
from backend.services.google_drive_service import DriveLoginRequiredError, GoogleDriveService as G
from backend.services.job_runtime import job_runtime


def _wait_final(job_id: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = job_runtime.get_job(job_id)
        if job and job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish: {job_runtime.get_job(job_id)}")


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(G, "_sleep", staticmethod(lambda _seconds: None))
    monkeypatch.setattr(G, "_get_drive_service", classmethod(lambda cls, auth, **_kw: object()))
    monkeypatch.setattr(G, "_existing_file_names", classmethod(lambda cls, service, parent_id: set()))
    # Empty: nothing to upload, so the job is exactly the pre-scan that failed in production.
    folder = tmp_path / "SEP_2026"
    folder.mkdir()
    return folder


def _run(source: Path) -> dict[str, Any]:
    created = job_runtime.start_job(
        job_type=G.UPLOAD_JOB_TYPE,
        initial_snapshot=G._create_job("pending", "upload", "queued"),
        worker=lambda job_id: G._run_upload_job(
            job_id, DriveAuthConfig(mode="oauth"), source, "parent-id", "ROOT", True, 1, False
        ),
    )
    return _wait_final(created["job_id"])


def test_a_timeout_in_the_prescan_is_retried_and_the_job_completes(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def flaky(cls, service, name, parent_id):
        calls.append(name)
        if len(calls) == 1:
            raise TimeoutError("The read operation timed out")
        return "folder-id"

    monkeypatch.setattr(G, "_create_or_get_folder", classmethod(flaky))

    final = _run(source)

    assert final["status"] == "completed", final
    assert calls == ["ROOT", "ROOT"], "one retry, then success"
    assert final["failed_items"] == 0
    assert final["errors"] == [], "a recovered hiccup is not an error the operator has to act on"


def test_an_expired_login_is_not_retried(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def dead(cls, service, name, parent_id):
        calls.append(name)
        raise DriveLoginRequiredError("sign in once")

    monkeypatch.setattr(G, "_create_or_get_folder", classmethod(dead))

    final = _run(source)

    assert final["status"] == "failed"
    assert calls == ["ROOT"], "retrying cannot fix a login that needs a person"
    assert "sign in once" in final["message"]


def test_gives_up_after_the_last_attempt_with_the_real_error(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def always(cls, service, name, parent_id):
        calls.append(name)
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr(G, "_create_or_get_folder", classmethod(always))

    final = _run(source)

    assert final["status"] == "failed"
    assert len(calls) == G.UPLOAD_NETWORK_ATTEMPTS
    assert "timed out" in final["message"]
    assert final["failed_items"] == 1


def test_stop_during_the_retry_pause_ends_the_job_as_cancelled(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    job_box: dict[str, str] = {}

    def always(cls, service, name, parent_id):
        calls.append(name)
        raise TimeoutError("The read operation timed out")

    def stop_while_pausing(_seconds: float) -> None:
        job_runtime.stop_job(job_box["id"], "stop")

    monkeypatch.setattr(G, "_create_or_get_folder", classmethod(always))
    monkeypatch.setattr(G, "_sleep", staticmethod(stop_while_pausing))

    created = job_runtime.start_job(
        job_type=G.UPLOAD_JOB_TYPE,
        initial_snapshot=G._create_job("pending", "upload", "queued"),
        worker=lambda job_id: G._run_upload_job(
            job_id, DriveAuthConfig(mode="oauth"), source, "parent-id", "ROOT", True, 1, False
        ),
    )
    job_box["id"] = created["job_id"]
    final = _wait_final(created["job_id"])

    assert final["status"] == "cancelled"
    assert calls == ["ROOT"], "no second attempt after Stop"


@pytest.mark.parametrize(
    "exc, expected",
    [
        (TimeoutError("The read operation timed out"), True),
        (ConnectionResetError(10054, "An existing connection was forcibly closed"), True),
        (HttpError(httplib2.Response({"status": 503}), b"backend error"), True),
        (HttpError(httplib2.Response({"status": 429}), b"rate limited"), True),
        (HttpError(httplib2.Response({"status": 404}), b"not found"), False),
        (HttpError(httplib2.Response({"status": 403}), b"forbidden"), False),
        (DriveLoginRequiredError("sign in"), False),
        (ValueError("Google Drive parent folder ID is required."), False),
    ],
)
def test_transient_classification(exc: BaseException, expected: bool) -> None:
    assert G._is_transient_network_error(exc) is expected
