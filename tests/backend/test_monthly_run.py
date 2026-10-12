"""The monthly master run supervises three existing jobs and never feeds a partial month forward."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from backend.config import settings
from backend.models.monthly_run import MonthlyAutomationConfig, MonthlyRunStartRequest
from backend.services import ftp_profiles, monthly_run_service as svc
from backend.services.ftp_download_service import FTPDownloadService
from backend.services.ftp_profiles import FtpProfileCredential, FtpProfilesFile
from backend.services.google_drive_service import GoogleDriveService
from backend.services.job_runtime import job_runtime

DISCOMS = ["MVVNL", "DVVNL", "PVVNL", "PuVNL", "KESCO"]


def _profile_results(found: dict[str, int], failed: dict[str, int] | None = None, errors: dict[str, str] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "profile_name": name,
            "found_files": found.get(name, 0),
            "downloaded_files": found.get(name, 0),
            "skipped_files": 0,
            "failed_files": (failed or {}).get(name, 0),
            "errors": [errors[name]] if errors and name in errors else [],
        }
        for name in DISCOMS
    ]


def _fake_child(job_type: str, final: dict[str, Any], *, hold: threading.Event | None = None) -> dict[str, str]:
    """A child job that finishes with *final* once *hold* (if any) is released."""

    def worker(job_id: str) -> None:
        if hold is not None:
            while not hold.wait(0.01):
                job_runtime.raise_if_cancelled(job_id)
        job_runtime.update_job(job_id, **final)

    created = job_runtime.start_job(job_type=job_type, initial_snapshot={"status": "queued", "message": ""}, worker=worker)
    return {"job_id": created["job_id"], "status": "queued"}


def _wait_final(job_id: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = job_runtime.get_job(job_id)
        if job and job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish: {job_runtime.get_job(job_id)}")


@pytest.fixture
def config(tmp_path: Path) -> MonthlyAutomationConfig:
    (tmp_path / "db").mkdir()
    return MonthlyAutomationConfig(
        csv_root=str(tmp_path / "csv"),
        parquet_root=str(tmp_path / "parquet"),
        db_path=str(tmp_path / "db" / "uppcl.duckdb"),
        drive_parent_folder_id="drive-parent",
    )


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: MonthlyAutomationConfig) -> dict[str, Any]:
    """Fake the three children and the two external pre-flight checks."""
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(settings, "MONTHLY_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(svc.MonthlyRunService, "POLL_SECONDS", 0.01)
    svc.save_config(config)

    profiles = FtpProfilesFile(profiles={name: FtpProfileCredential(username=name.lower(), password="pw") for name in DISCOMS})
    monkeypatch.setattr(ftp_profiles, "load_ftp_profiles", lambda: profiles)
    monkeypatch.setattr(GoogleDriveService, "get_auth_status", classmethod(lambda cls, *a, **k: {"configured": True, "token_exists": True, "token_valid": True}))

    calls: dict[str, list[dict[str, Any]]] = {"ftp": [], "drive": [], "build": []}
    state: dict[str, Any] = {
        "ftp_final": {"status": "completed", "profile_results": _profile_results({d: 10 for d in DISCOMS}), "total_files_found": 50},
        "drive_final": {"status": "completed", "uploaded_items": 50, "skipped_items": 0, "failed_items": 0, "message": "done"},
        "build_final": {"status": "completed", "table_rows": 1234, "data_quality": "ok", "reconciliation": {"unaccounted_rows": 0}, "build_output_path": "x.duckdb"},
        "hold": None,
    }

    def fake_ftp(**kwargs: Any) -> dict[str, str]:
        calls["ftp"].append(kwargs)
        return _fake_child(FTPDownloadService.JOB_TYPE, state["ftp_final"], hold=state["hold"])

    def fake_drive(**kwargs: Any) -> dict[str, str]:
        calls["drive"].append(kwargs)
        return _fake_child(GoogleDriveService.UPLOAD_JOB_TYPE, state["drive_final"], hold=state["hold"])

    def fake_build(payload: Any) -> str:
        calls["build"].append(payload.model_dump())
        return _fake_child(svc.FULL_PIPELINE_JOB_TYPE, state["build_final"], hold=state["hold"])["job_id"]

    monkeypatch.setattr(FTPDownloadService, "start_download", staticmethod(fake_ftp))
    monkeypatch.setattr(GoogleDriveService, "start_upload", staticmethod(fake_drive))
    monkeypatch.setattr(svc, "start_full_pipeline_job", fake_build)
    return {"calls": calls, "state": state, "config": config}


# ── derivation ─────────────────────────────────────────────────────────────────


def test_plan_derives_every_name_from_the_month(config: MonthlyAutomationConfig) -> None:
    plan = svc.derive_plan("2026-07", config)

    assert plan.token == "JUL_2026"
    assert plan.object_name == "Master_0726"
    assert plan.month_label == "JUL_2026"
    assert plan.remote_dir == "/01-MASTER_DATA/JUL_2026/"
    assert plan.csv_dir == Path(config.csv_root) / "JUL_2026"
    assert plan.csv_glob.endswith("/JUL_2026/**/*.gz")
    assert plan.parquet_dir == Path(config.parquet_root) / "JUL_2026"
    assert plan.drive_root_name == "MASTER_DATA_2026_07"


def test_default_month_is_the_previous_calendar_month() -> None:
    month = svc.default_month()
    assert len(month) == 7 and month[4] == "-"


def test_start_request_rejects_a_malformed_month() -> None:
    with pytest.raises(ValueError):
        MonthlyRunStartRequest(month="July 2026")


# ── download classification ────────────────────────────────────────────────────


def test_month_absent_everywhere_is_not_available_yet() -> None:
    results = _profile_results({}, errors={d: f"{d}: 550 Failed to change directory." for d in DISCOMS})
    verdict, missing, _ = svc.classify_download(results, DISCOMS)
    assert verdict == "not_available_yet"
    assert missing == DISCOMS


def test_some_discoms_missing_is_partial() -> None:
    results = _profile_results({"MVVNL": 10, "DVVNL": 10, "PVVNL": 10})
    verdict, missing, message = svc.classify_download(results, DISCOMS)
    assert verdict == "partial"
    assert missing == ["PuVNL", "KESCO"]
    assert "PuVNL" in message and "KESCO" in message


def test_zero_files_with_no_error_is_still_not_success() -> None:
    # An empty folder must not be mistaken for a downloaded month.
    verdict, _, _ = svc.classify_download(_profile_results({}), DISCOMS)
    assert verdict == "not_available_yet"


def test_failed_files_fail_the_download_gate() -> None:
    results = _profile_results({d: 10 for d in DISCOMS}, failed={"KESCO": 2})
    verdict, _, message = svc.classify_download(results, DISCOMS)
    assert verdict == "failed"
    assert "KESCO" in message


def test_complete_download_is_ok() -> None:
    verdict, missing, _ = svc.classify_download(_profile_results({d: 123 for d in DISCOMS}), DISCOMS)
    assert verdict == "ok" and missing == []


# ── orchestration ──────────────────────────────────────────────────────────────


def test_happy_path_runs_download_then_upload_and_build_together(harness: dict[str, Any]) -> None:
    started = svc.MonthlyRunService.start(MonthlyRunStartRequest(month="2026-07"))
    final = _wait_final(started["job_id"])

    assert final["status"] == "completed"
    assert final["outcome"] == "completed"
    assert {s: final["steps"][s]["status"] for s in ("download", "upload", "build")} == {
        "download": "completed", "upload": "completed", "build": "completed",
    }
    calls = harness["calls"]
    assert len(calls["ftp"]) == 1 and len(calls["drive"]) == 1 and len(calls["build"]) == 1

    ftp = calls["ftp"][0]
    assert ftp["output_root"] == harness["config"].csv_root
    assert [p.name for p in ftp["profiles"]] == DISCOMS
    assert all(p.password == "pw" for p in ftp["profiles"]), "passwords come from the server-side file"
    assert ftp["profiles"][0].remote_dir == "/01-MASTER_DATA/JUL_2026/"
    assert ftp["profiles"][0].local_subfolder == "JUL_2026/MVVNL"

    drive = calls["drive"][0]
    assert drive["interactive"] is False, "an unattended run must never open a browser"
    assert drive["root_folder_name"] == "MASTER_DATA_2026_07"
    assert drive["local_folder"].endswith("JUL_2026")

    build = calls["build"][0]
    assert build["object_name"] == "Master_0726"
    assert build["object_type"] == "VIEW"
    assert build["month_label"] == "JUL_2026"
    assert build["input_path"].endswith("/JUL_2026/**/*.gz")

    marker = svc.read_marker("JUL_2026")
    assert set(svc.completed_steps(marker)) == {"download", "upload", "build"}


def test_month_not_on_ftp_stops_before_upload_or_build(harness: dict[str, Any]) -> None:
    harness["state"]["ftp_final"] = {
        "status": "completed",
        "profile_results": _profile_results({}, errors={d: "550" for d in DISCOMS}),
    }
    started = svc.MonthlyRunService.start(MonthlyRunStartRequest(month="2026-07"))
    final = _wait_final(started["job_id"])

    assert final["status"] == "completed"
    assert final["outcome"] == "not_available_yet"
    assert final["missing_discoms"] == DISCOMS
    assert harness["calls"]["drive"] == [] and harness["calls"]["build"] == []
    assert svc.read_marker("JUL_2026") is None, "nothing is recorded as done"


def test_partial_month_names_the_missing_discoms_and_stops(harness: dict[str, Any]) -> None:
    harness["state"]["ftp_final"] = {
        "status": "completed",
        "profile_results": _profile_results({"MVVNL": 5, "DVVNL": 5, "PVVNL": 5, "PuVNL": 5}),
    }
    started = svc.MonthlyRunService.start(MonthlyRunStartRequest(month="2026-07"))
    final = _wait_final(started["job_id"])

    assert final["outcome"] == "partial"
    assert final["missing_discoms"] == ["KESCO"]
    assert "KESCO" in final["message"]
    assert harness["calls"]["build"] == []


def test_row_loss_in_the_build_fails_the_run_but_upload_still_completes(harness: dict[str, Any]) -> None:
    harness["state"]["build_final"] = {
        "status": "completed",
        "data_quality": "loss",
        "reconciliation": {"unaccounted_rows": 42},
        "table_rows": 1000,
    }
    started = svc.MonthlyRunService.start(MonthlyRunStartRequest(month="2026-07"))
    final = _wait_final(started["job_id"])

    assert final["status"] == "failed"
    assert final["outcome"] == "failed"
    assert "42" in final["message"]
    assert final["steps"]["build"]["status"] == "failed"
    assert final["steps"]["upload"]["status"] == "completed"
    assert set(svc.completed_steps(svc.read_marker("JUL_2026"))) == {"download", "upload"}


def test_resume_skips_steps_the_marker_says_are_done(harness: dict[str, Any]) -> None:
    svc.record_step("JUL_2026", "download", {"status": "completed", "finished_at": "2026-08-03T19:00:00"}, "old-job")
    svc.record_step("JUL_2026", "upload", {"status": "completed", "finished_at": "2026-08-03T21:00:00"}, "old-job")

    started = svc.MonthlyRunService.start(MonthlyRunStartRequest(month="2026-07"))
    final = _wait_final(started["job_id"])

    assert final["status"] == "completed"
    assert final["resumed_steps"] == ["download", "upload"]
    assert final["steps"]["download"]["status"] == "skipped"
    assert final["steps"]["upload"]["status"] == "skipped"
    assert final["steps"]["build"]["status"] == "completed"
    assert harness["calls"]["ftp"] == [] and harness["calls"]["drive"] == []
    assert len(harness["calls"]["build"]) == 1


def test_from_scratch_ignores_the_marker(harness: dict[str, Any]) -> None:
    svc.record_step("JUL_2026", "download", {"status": "completed"}, "old-job")

    started = svc.MonthlyRunService.start(MonthlyRunStartRequest(month="2026-07", from_scratch=True))
    final = _wait_final(started["job_id"])

    assert final["resumed_steps"] == []
    assert len(harness["calls"]["ftp"]) == 1


def test_second_start_while_one_is_running_is_refused(harness: dict[str, Any]) -> None:
    hold = threading.Event()
    harness["state"]["hold"] = hold
    first = svc.MonthlyRunService.start(MonthlyRunStartRequest(month="2026-07"))
    try:
        time.sleep(0.05)
        with pytest.raises(svc.MonthlyRunAlreadyActive) as excinfo:
            svc.MonthlyRunService.start(MonthlyRunStartRequest(month="2026-07"))
        assert excinfo.value.job_id == first["job_id"]
    finally:
        hold.set()
        _wait_final(first["job_id"])


def test_stop_cancels_the_run_and_its_children(harness: dict[str, Any]) -> None:
    hold = threading.Event()
    harness["state"]["hold"] = hold
    started = svc.MonthlyRunService.start(MonthlyRunStartRequest(month="2026-07"))
    time.sleep(0.05)

    svc.MonthlyRunService.stop(started["job_id"])
    final = _wait_final(started["job_id"])

    assert final["status"] == "cancelled"
    child_id = final["steps"]["download"]["job_id"]
    assert child_id
    child = _wait_final(child_id)
    assert child["status"] == "cancelled"
    hold.set()


def test_preflight_names_every_missing_prerequisite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: MonthlyAutomationConfig) -> None:
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(ftp_profiles, "load_ftp_profiles", lambda: FtpProfilesFile(profiles={"MVVNL": FtpProfileCredential(username="u", password="p")}))
    monkeypatch.setattr(GoogleDriveService, "get_auth_status", classmethod(lambda cls, *a, **k: {"configured": True, "token_exists": False}))
    bad = config.model_copy(update={"drive_parent_folder_id": ""})

    with pytest.raises(ValueError) as excinfo:
        svc.MonthlyRunService.preflight(bad, svc.derive_plan("2026-07", bad))

    text = str(excinfo.value)
    assert "DVVNL" in text and "KESCO" in text
    assert "parent folder" in text
    assert "sign in" in text.lower()


# ── job runtime support ────────────────────────────────────────────────────────


def test_active_jobs_sees_only_unfinished_jobs_of_that_type() -> None:
    hold = threading.Event()
    created = _fake_child("probe.type", {"status": "completed"}, hold=hold)
    _fake_child("other.type", {"status": "completed"})
    try:
        time.sleep(0.02)
        active = job_runtime.active_jobs("probe.type")
        assert [job["job_id"] for job in active] == [created["job_id"]]
        assert job_runtime.active_jobs("other.type") == []
    finally:
        hold.set()
        _wait_final(created["job_id"])
    assert job_runtime.active_jobs("probe.type") == []


# ── HTTP ───────────────────────────────────────────────────────────────────────


def test_endpoints_round_trip_config_plan_and_start(harness: dict[str, Any]) -> None:
    from fastapi.testclient import TestClient

    from backend.app import app

    client = TestClient(app)

    assert client.get("/api/automation/config").json()["drive_parent_folder_id"] == "drive-parent"

    plan = client.get("/api/automation/monthly-run/plan", params={"month": "2026-07"}).json()
    assert plan["object_name"] == "Master_0726"

    started = client.post("/api/automation/monthly-run/start", json={"month": "2026-07"})
    assert started.status_code == 200, started.text
    job_id = started.json()["job_id"]
    _wait_final(job_id)

    status = client.get(f"/api/automation/monthly-run/status/{job_id}").json()
    assert status["outcome"] == "completed"

    marker = client.get("/api/automation/monthly-run/marker", params={"month": "2026-07"}).json()
    assert marker["exists"] is True and marker["steps"]["build"]["status"] == "completed"


def test_start_returns_409_when_a_run_is_active(harness: dict[str, Any]) -> None:
    from fastapi.testclient import TestClient

    from backend.app import app

    hold = threading.Event()
    harness["state"]["hold"] = hold
    client = TestClient(app)
    first = client.post("/api/automation/monthly-run/start", json={"month": "2026-07"}).json()
    try:
        time.sleep(0.05)
        second = client.post("/api/automation/monthly-run/start", json={"month": "2026-07"})
        assert second.status_code == 409
        assert second.json()["detail"]["job_id"] == first["job_id"]
    finally:
        hold.set()
        _wait_final(first["job_id"])
