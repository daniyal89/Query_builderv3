"""The FTP output root is a per-computer setting, remembered from the last run."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import settings
from backend.services import ftp_download_settings


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "config"
    path.mkdir()
    monkeypatch.setattr(settings, "CONFIG_DIR", path)
    return path


def test_nothing_saved_falls_back_to_the_monthly_csv_root(config_dir: Path) -> None:
    (config_dir / "monthly_automation.json").write_text(json.dumps({"csv_root": "E:/DATA/MASTER"}), encoding="utf-8")

    roots = ftp_download_settings.effective_output_roots()

    assert roots["master"] == {"saved": None, "effective": "E:/DATA/MASTER"}
    assert roots["billed"]["saved"] is None
    assert roots["billed"]["effective"] == str(Path("E:/DATA") / "BILLED")


def test_saving_one_kind_keeps_the_other(config_dir: Path) -> None:
    ftp_download_settings.save_output_roots({"master": "E:/one", "billed": "E:/two"})
    ftp_download_settings.save_output_roots({"master": "E:/three"})

    saved = ftp_download_settings.load_settings().output_roots
    assert saved == {"master": "E:/three", "billed": "E:/two"}
    assert not (config_dir / "ftp_download_settings.json.tmp").exists(), "written atomically"


def test_saved_root_wins_over_the_fallback(config_dir: Path) -> None:
    (config_dir / "monthly_automation.json").write_text(json.dumps({"csv_root": "E:/DATA/MASTER"}), encoding="utf-8")
    ftp_download_settings.save_output_roots({"master": "F:/elsewhere"})

    roots = ftp_download_settings.effective_output_roots()
    assert roots["master"] == {"saved": "F:/elsewhere", "effective": "F:/elsewhere"}
    assert roots["billed"]["effective"] == str(Path("E:/DATA") / "BILLED"), "unsaved kind still falls back"


def test_unknown_kind_and_traversal_are_rejected(config_dir: Path) -> None:
    with pytest.raises(ValueError, match="Unknown preset kind"):
        ftp_download_settings.save_output_roots({"weekly": "E:/x"})
    with pytest.raises(ValueError, match="traversal"):
        ftp_download_settings.save_output_roots({"master": "E:/x/../y"})
    assert not ftp_download_settings.ftp_download_settings_path().exists(), "a rejected save writes nothing"


def test_broken_file_raises_rather_than_offering_a_stale_default(config_dir: Path) -> None:
    ftp_download_settings.ftp_download_settings_path().write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        ftp_download_settings.load_settings()


def test_settings_endpoints_round_trip(config_dir: Path) -> None:
    client = TestClient(app)

    response = client.put("/api/ftp-download/settings", json={"output_roots": {"master": "E:/DATA/MASTER"}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["path"].endswith("ftp_download_settings.json")
    assert body["output_roots"]["master"] == {"saved": "E:/DATA/MASTER", "effective": "E:/DATA/MASTER"}

    assert client.get("/api/ftp-download/settings").json() == body

    bad = client.put("/api/ftp-download/settings", json={"output_roots": {"master": "  "}})
    assert bad.status_code == 400
    assert "empty" in bad.json()["detail"]
