import threading
import time
from pathlib import Path

from backend.services.job_runtime import (
    BackgroundJobPolicy,
    PersistentJobStore,
    job_runtime,
)


def _wait_for_status(job_id: str, expected: set[str], timeout_seconds: float = 3.0) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        job = job_runtime.get_job(job_id)
        if job and job.get("status") in expected:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Job {job_id} did not reach one of {expected!r} in time.")


def test_job_runtime_retries_and_dead_letters_failed_jobs() -> None:
    attempts: list[int] = []

    def worker(job_id: str) -> None:
        attempts.append(len(attempts) + 1)
        job_runtime.update_job(job_id, message=f"attempt-{len(attempts)}")
        raise RuntimeError("boom")

    job = job_runtime.start_job(
        job_type="test.retry.failure",
        initial_snapshot={"message": "queued"},
        payload={"kind": "test"},
        policy=BackgroundJobPolicy(max_attempts=2, retry_backoff_seconds=0),
        worker=worker,
    )

    failed_job = _wait_for_status(job["job_id"], {"failed"})

    assert attempts == [1, 2]
    assert failed_job["attempt_count"] == 2
    assert failed_job["dead_letter_reason"] == "max_attempts_exhausted"
    assert failed_job["last_error"] == "boom"
    dead_letters = job_runtime.list_dead_letters()
    assert len(dead_letters) == 1
    assert dead_letters[0]["job_id"] == job["job_id"]
    assert dead_letters[0]["attempt_count"] == 2
    assert dead_letters[0]["reason"] == "max_attempts_exhausted"
    assert dead_letters[0]["last_error"] == "boom"


def test_job_runtime_recovers_interrupted_jobs_on_initialize(tmp_path: Path) -> None:
    store_path = tmp_path / "recovery.sqlite3"
    job_runtime.reset_for_tests(store_path)

    store = PersistentJobStore(store_path)
    store.create_job(
        job_id="recover-me",
        job_type="test.recovery",
        snapshot={
            "job_id": "recover-me",
            "status": "running",
            "message": "still working",
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": None,
        },
        payload={"kind": "test"},
    )

    job_runtime.initialize()
    recovered = job_runtime.get_job("recover-me")

    assert recovered is not None
    assert recovered["status"] == "failed"
    assert "Application restarted before the background job finished" in str(recovered["message"])
    assert recovered["last_error"] == recovered["message"]
    assert recovered["finished_at"] is not None


def test_job_runtime_persists_completed_snapshots(tmp_path: Path) -> None:
    finished = threading.Event()

    def worker(job_id: str) -> None:
        job_runtime.update_job(job_id, message="done", output_path=str(tmp_path / "artifact.txt"))
        finished.set()

    job = job_runtime.start_job(
        job_type="test.persistence",
        initial_snapshot={"message": "queued"},
        payload={"kind": "test"},
        worker=worker,
    )

    assert finished.wait(2.0)
    completed = _wait_for_status(job["job_id"], {"completed"})

    store = PersistentJobStore(tmp_path / "job_store.sqlite3")
    reloaded = store.get_job(job["job_id"])

    assert completed["status"] == "completed"
    assert reloaded is not None
    assert reloaded["status"] == "completed"
    assert reloaded["message"] == "done"
    assert reloaded["output_path"] == str(tmp_path / "artifact.txt")
