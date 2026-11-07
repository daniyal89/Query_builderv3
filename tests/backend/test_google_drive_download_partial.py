"""A Drive download must never leave, or keep, a cut-off file under its real name.

A month's build died on "Expected 154 columns, found 88" at the last line of a
DVVNL file: a download had been interrupted, the half-written file stayed under
its final name, and every later run skipped it as "already present". Files are
now written under a temporary name and renamed once complete, and an existing
file is only skipped when its size matches what Drive reports.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from backend.services import google_drive_service as module
from backend.services.google_drive_service import GoogleDriveService as G
from backend.services.job_runtime import job_runtime

PAYLOAD = b"x" * 2000


class _FakeFiles:
    def get_media(self, fileId: str, supportsAllDrives: bool) -> str:
        return f"media:{fileId}"


class _FakeService:
    def files(self) -> _FakeFiles:
        return _FakeFiles()


class _FakeDownloader:
    """Stands in for MediaIoBaseDownload: writes PAYLOAD in two chunks, or dies mid-way."""

    fail_after_first_chunk = False

    def __init__(self, fh: Any, request_obj: str, chunksize: int) -> None:
        self.fh = fh
        self.sent = 0

    def next_chunk(self, num_retries: int) -> tuple[None, bool]:
        if self.sent == 1 and self.fail_after_first_chunk:
            raise RuntimeError("connection dropped")
        half = len(PAYLOAD) // 2
        self.fh.write(PAYLOAD[self.sent * half : (self.sent + 1) * half])
        self.sent += 1
        return None, self.sent == 2


@pytest.fixture(autouse=True)
def fake_downloader(monkeypatch: pytest.MonkeyPatch) -> type[_FakeDownloader]:
    _FakeDownloader.fail_after_first_chunk = False
    monkeypatch.setattr(module, "MediaIoBaseDownload", _FakeDownloader)
    return _FakeDownloader


def _download(tmp_path: Path, metadata: dict[str, Any], overwrite: bool = False) -> dict[str, Any]:
    """Run _download_item for one file inside a real job so the counters are recorded."""

    def worker(job_id: str) -> None:
        G._download_item(_FakeService(), "file-1", metadata, tmp_path, overwrite, False, job_id)
        job_runtime.update_job(job_id, status="completed")

    created = job_runtime.start_job(
        job_type=G.DOWNLOAD_JOB_TYPE,
        initial_snapshot=G._create_job("pending", "download", "queued"),
        worker=worker,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        job = job_runtime.get_job(created["job_id"])
        if job and job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("download job did not finish")


META = {"id": "file-1", "name": "DVVNL_DIV211242_SEP_2026.csv.gz", "mimeType": "application/gzip", "size": str(len(PAYLOAD))}


def test_a_fresh_download_lands_complete_under_its_real_name(tmp_path: Path) -> None:
    job = _download(tmp_path, META)

    target = tmp_path / META["name"]
    assert target.read_bytes() == PAYLOAD
    assert not (tmp_path / (META["name"] + ".part")).exists()
    assert job["downloaded_items"] == 1 and job["skipped_items"] == 0


def test_a_cut_off_file_is_downloaded_again_instead_of_skipped(tmp_path: Path) -> None:
    target = tmp_path / META["name"]
    target.write_bytes(PAYLOAD[:1000])  # what an interrupted download used to leave behind

    job = _download(tmp_path, META)

    assert target.read_bytes() == PAYLOAD, "the short file was replaced by the whole one"
    assert job["downloaded_items"] == 1 and job["skipped_items"] == 0


def test_a_complete_file_is_still_skipped(tmp_path: Path) -> None:
    target = tmp_path / META["name"]
    target.write_bytes(PAYLOAD)

    job = _download(tmp_path, META)

    assert job["skipped_items"] == 1 and job["downloaded_items"] == 0


def test_without_a_size_from_drive_an_existing_file_is_trusted(tmp_path: Path) -> None:
    target = tmp_path / META["name"]
    target.write_bytes(PAYLOAD[:1000])

    job = _download(tmp_path, {**META, "size": None})

    assert target.read_bytes() == PAYLOAD[:1000]
    assert job["skipped_items"] == 1


def test_a_failed_download_leaves_no_file_under_the_real_name(tmp_path: Path, fake_downloader: type[_FakeDownloader]) -> None:
    fake_downloader.fail_after_first_chunk = True

    job = _download(tmp_path, META)

    assert not (tmp_path / META["name"]).exists(), "nothing half-written for the next run to trust"
    assert not (tmp_path / (META["name"] + ".part")).exists()
    assert job["errors"] and "connection dropped" in job["errors"][0]
    assert job["downloaded_items"] == 0
