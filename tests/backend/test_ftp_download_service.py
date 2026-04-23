from pathlib import Path

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
    existing_dir = root / "MAR_2026" / "KESCO"
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
