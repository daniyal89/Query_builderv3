from pathlib import Path

import pytest

from backend.models.ftp_download import FTPDownloadProfile
from backend.services.ftp_download_service import FTPDownloadService


class FakeFTP:
    def __init__(self, files: dict[str, bytes]):
        self.files = files

    def nlst(self):
        return list(self.files.keys())

    def size(self, name: str):
        return len(self.files[name])

    def retrbinary(self, command: str, callback):
        name = command.split(" ", 1)[1]
        callback(self.files[name])

    def quit(self):
        return None

    def close(self):
        return None


def test_expand_tokens_replaces_supported_placeholders() -> None:
    value = FTPDownloadService._expand_tokens("/01-MASTER_DATA/{MONTH}/{PROFILE}/{DATE}/", "KESCO")

    assert "KESCO" in value
    assert value.startswith("/01-MASTER_DATA/")
    assert value.endswith("/")


def test_download_files_skips_existing_and_downloads_missing(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "output"
    # {MONTH} resolves to the previous calendar month, so derive it the same way
    # the service does instead of hardcoding a label that expires.
    current_month = FTPDownloadService._expand_tokens("{MONTH}", "KESCO")
    existing_dir = root / current_month / "KESCO"
    existing_dir.mkdir(parents=True, exist_ok=True)
    existing_file = existing_dir / "already.gz"
    existing_file.write_bytes(b"1234")

    files = {
        "already.gz": b"1234",
        "new.gz": b"56789",
        "ignore.txt": b"x",
    }

    def fake_connect(**kwargs):
        return FakeFTP(files)

    monkeypatch.setattr(FTPDownloadService, "_connect", staticmethod(fake_connect))

    result = FTPDownloadService.download_files(
        host="ftp.example.com",
        port=21,
        output_root=str(root),
        file_suffix=".gz",
        max_workers=2,
        max_retries=2,
        retry_delay_seconds=0,
        timeout_seconds=30,
        passive_mode=True,
        skip_existing=True,
        profiles=[
            FTPDownloadProfile(
                name="KESCO",
                username="user",
                password="pass",
                remote_dir="/01-MASTER_DATA/{MONTH}/",
                local_subfolder="{MONTH}/KESCO",
            )
        ],
    )

    assert result["total_profiles"] == 1
    assert result["total_files_found"] == 2
    assert result["total_downloaded_files"] == 1
    assert result["total_skipped_files"] == 1
    assert result["total_failed_files"] == 0
    assert (existing_dir / "new.gz").read_bytes() == b"56789"


# ── Output-root failures must name the actual problem ─────────────────────────
#
# mkdir reports a bare WinError 2 for several unrelated conditions, and the job
# used to surface only "Download failed" with no reason at all.


def test_output_root_is_created_when_writable(tmp_path: Path) -> None:
    target = tmp_path / "MASTER" / "nested"

    FTPDownloadService._ensure_output_root(target)

    assert target.is_dir()


def test_unavailable_drive_is_named(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "MASTER"

    def _boom(*_args, **_kwargs):
        raise FileNotFoundError(2, "The system cannot find the file specified")

    monkeypatch.setattr(Path, "mkdir", _boom)
    monkeypatch.setattr(Path, "exists", lambda self: False)

    with pytest.raises(ValueError, match="is not available"):
        FTPDownloadService._ensure_output_root(target)


def test_cloud_drive_root_suggests_my_drive(monkeypatch, tmp_path: Path) -> None:
    """Folders cannot be created at a Google Drive virtual root."""
    drive = tmp_path / "gdrive"
    (drive / "My Drive").mkdir(parents=True)
    (drive / "Shared drives").mkdir()
    target = drive / "MASTER"

    real_mkdir = Path.mkdir

    def _fail_at_root(self, *args, **kwargs):
        if self == target:
            raise FileNotFoundError(2, "The system cannot find the file specified")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", _fail_at_root)
    # Treat the fixture folder as the drive anchor.
    monkeypatch.setattr(Path, "anchor", property(lambda self: str(drive)))

    with pytest.raises(ValueError, match="cloud-synced drive") as excinfo:
        FTPDownloadService._ensure_output_root(target)

    assert "My Drive" in str(excinfo.value)
