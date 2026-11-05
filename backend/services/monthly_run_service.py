"""The monthly master run: FTP download, then Drive upload and parquet/view build.

The month can also come *from* Google Drive instead: on a computer where
someone else has already run the month, the operator picks the Drive source,
the DISCOM folders are downloaded from the month's Drive folder into the same
CSV layout the FTP step produces, and the upload step is skipped because the
files are already there.

One job that drives three existing ones. Each step is already a persistent
background job of its own (FTP download, Drive upload, full pipeline); this
module starts them with the right month-derived arguments, waits for them, and
refuses to feed a partial month forward.

Why a supervisor over existing jobs rather than one big worker:

- each step stays visible on its own page with its own progress;
- stopping the run stops whichever child is running through the same
  cancellation the pages already use;
- the step workers are untouched, so nothing about *how* a month is
  downloaded, uploaded or built changes here.

Progress is remembered per month in ``RUNTIME_DIR/monthly_runs/<MON>_<YYYY>.json``
rather than in the job row: ``recover_interrupted_jobs`` marks any job running
at shutdown as failed, so the job row cannot be the memory of what is done. A
re-run reads the marker and skips completed steps.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.config import settings
from backend.models.ftp_download import FTPDownloadProfile
from backend.models.google_drive import DriveAuthConfig
from backend.models.monthly_run import MasterSource, MonthlyAutomationConfig, MonthlyRunStartRequest
from backend.models.sidebar_tools import FullPipelineRequest
from backend.services import ftp_profiles
from backend.services.ftp_download_service import FTPDownloadService
from backend.services.google_drive_service import GoogleDriveService
from backend.services.job_runtime import (
    FINAL_JOB_STATUSES,
    BackgroundJobCancelled,
    BackgroundJobPolicy,
    job_runtime,
)
from backend.services.sidebar_tools_service import (
    FULL_PIPELINE_JOB_TYPE,
    FULL_PIPELINE_POLICY,
    _run_full_pipeline_job,
)

logger = logging.getLogger("duckdb_dashboard")

MONTHLY_RUN_JOB_TYPE = "automation.monthly_master_run"
#: Never retried as a whole: each child job has its own policy, and re-running
#: the supervisor would re-queue children that may already be running.
MONTHLY_RUN_POLICY = BackgroundJobPolicy(max_attempts=1, retry_backoff_seconds=0)

MONTH_ABBR = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
STEP_ORDER: tuple[str, ...] = ("download", "upload", "build")
CONFIG_FILENAME = "monthly_automation.json"


class MonthlyRunAlreadyActive(RuntimeError):
    def __init__(self, job_id: str, month: str) -> None:
        super().__init__(f"A monthly run is already in progress (job {job_id}, {month}).")
        self.job_id = job_id
        self.month = month


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── Month derivation ────────────────────────────────────────────────────────────


def default_month() -> str:
    """The previous calendar month as YYYY-MM: what the 3rd-of-the-month drop holds."""
    today = datetime.now(timezone.utc).date()
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"{year:04d}-{month:02d}"


@dataclass(frozen=True)
class MonthPlan:
    year: int
    month: int
    token: str            # JUL_2026 — the FTP, CSV and parquet folder name
    object_name: str      # Master_0726
    month_label: str      # what the build's naming rule accepts (JUL_2026)
    remote_dir: str
    csv_dir: Path
    csv_glob: str
    parquet_dir: Path
    drive_root_name: str

    @property
    def month_input(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def as_dict(self) -> dict[str, str]:
        return {
            "month": self.month_input,
            "token": self.token,
            "object_name": self.object_name,
            "remote_dir": self.remote_dir,
            "csv_dir": self.csv_dir.as_posix(),
            "csv_glob": self.csv_glob,
            "parquet_dir": self.parquet_dir.as_posix(),
            "drive_root_name": self.drive_root_name,
        }


def _fill_tokens(template: str, *, mon: str, yyyy: str, mm: str, yy: str) -> str:
    # str.replace, not str.format: the FTP service has its own {DATE}/{PROFILE}
    # tokens that must survive untouched.
    return (
        template.replace("{MON}", mon)
        .replace("{YYYY}", yyyy)
        .replace("{MM}", mm)
        .replace("{YY}", yy)
    )


def derive_plan(month_input: str | None, config: MonthlyAutomationConfig) -> MonthPlan:
    text = (month_input or default_month()).strip()
    year_text, month_text = text.split("-", 1)
    year, month = int(year_text), int(month_text)
    if not 1 <= month <= 12:
        raise ValueError("month must look like 2026-07.")

    mon = MONTH_ABBR[month - 1]
    yyyy, mm, yy = f"{year:04d}", f"{month:02d}", f"{year:04d}"[2:]
    token = f"{mon}_{yyyy}"
    csv_dir = Path(config.csv_root).expanduser() / token
    parquet_dir = Path(config.parquet_root).expanduser() / token
    return MonthPlan(
        year=year,
        month=month,
        token=token,
        object_name=f"Master_{mm}{yy}",
        month_label=token,
        remote_dir=_fill_tokens(config.ftp_remote_template, mon=mon, yyyy=yyyy, mm=mm, yy=yy),
        csv_dir=csv_dir,
        csv_glob=f"{csv_dir.as_posix()}/**/*.gz",
        parquet_dir=parquet_dir,
        drive_root_name=_fill_tokens(config.drive_root_name_template, mon=mon, yyyy=yyyy, mm=mm, yy=yy),
    )


# ── Config and per-month markers ────────────────────────────────────────────────


def config_path() -> Path:
    return settings.CONFIG_DIR / CONFIG_FILENAME


def load_config() -> MonthlyAutomationConfig:
    path = config_path()
    if not path.is_file():
        return MonthlyAutomationConfig()
    try:
        return MonthlyAutomationConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not read monthly automation settings from {path}: {exc}") from exc


def save_config(config: MonthlyAutomationConfig) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.model_dump(mode="json"), indent=2), encoding="utf-8")
    return path


def marker_path(token: str) -> Path:
    return settings.MONTHLY_RUNS_DIR / f"{token}.json"


def read_marker(token: str) -> dict[str, Any] | None:
    path = marker_path(token)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Ignoring unreadable monthly-run marker %s", path)
        return None
    return data if isinstance(data, dict) else None


_marker_lock = threading.Lock()


def record_step(token: str, step: str, state: dict[str, Any], job_id: str) -> None:
    with _marker_lock:
        current = read_marker(token) or {"month": token, "steps": {}}
        steps = dict(current.get("steps") or {})
        steps[step] = dict(state)
        current.update({"month": token, "steps": steps, "last_job_id": job_id, "updated_at": _now_iso()})
        path = marker_path(token)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(current, indent=2), encoding="utf-8")
        tmp.replace(path)


def completed_steps(marker: dict[str, Any] | None) -> set[str]:
    if not marker:
        return set()
    steps = marker.get("steps") or {}
    return {name for name, state in steps.items() if isinstance(state, dict) and state.get("status") == "completed"}


# ── Starting the children ───────────────────────────────────────────────────────


def start_full_pipeline_job(payload: FullPipelineRequest) -> str:
    """The same job the Data Tools page starts, without going through HTTP."""
    job_id = uuid.uuid4().hex
    job_runtime.start_job(
        job_type=FULL_PIPELINE_JOB_TYPE,
        job_id=job_id,
        initial_snapshot={
            "job_id": job_id,
            "status": "queued",
            "message": "Full pipeline queued.",
            "current_phase": "queued",
            "parquet_processed_files": 0,
            "parquet_total_files": 0,
            "parquet_skipped_files": 0,
            "parquet_current_file": None,
            "parquet_output_path": None,
            "build_progress_percent": 0,
            "build_output_path": None,
            "overall_progress_percent": 0,
            "started_at": _now_iso(),
            "finished_at": None,
        },
        payload=payload.model_dump(mode="json"),
        policy=FULL_PIPELINE_POLICY,
        worker=lambda running_job_id: _run_full_pipeline_job(running_job_id, payload),
    )
    return job_id


# ── Download classification ─────────────────────────────────────────────────────


def classify_download(profile_results: list[dict[str, Any]], discoms: list[str]) -> tuple[str, list[str], str]:
    """Decide what an FTP result means for the month.

    The FTP service reports a missing month folder as a profile error with
    ``found_files == 0`` and still completes the job, so "not there yet" has to
    be read out of the per-profile results rather than the job status.

    Returns (verdict, missing_discoms, message) where verdict is one of
    ``ok``, ``not_available_yet``, ``partial`` or ``failed``.
    """
    by_name = {str(item.get("profile_name", "")).strip().upper(): item for item in profile_results}
    missing: list[str] = []
    failures: list[str] = []
    for discom in discoms:
        result = by_name.get(discom.strip().upper())
        if result is None or int(result.get("found_files", 0)) == 0:
            missing.append(discom)
            continue
        failed = int(result.get("failed_files", 0))
        errors = [str(err) for err in (result.get("errors") or [])]
        if failed or errors:
            failures.append(f"{discom}: {failed} failed file(s)" + (f"; {errors[0]}" if errors else ""))

    if failures:
        return "failed", missing, "Download finished with failures — " + "; ".join(failures)
    if len(missing) == len(discoms):
        return "not_available_yet", missing, "The month is not on the FTP server yet for any DISCOM."
    if missing:
        return "partial", missing, "Not every DISCOM has uploaded yet: missing " + ", ".join(missing) + "."
    total = sum(int(item.get("found_files", 0)) for item in profile_results)
    return "ok", [], f"Downloaded {total:,} file(s) across {len(discoms)} DISCOM(s)."


# ── The supervisor ──────────────────────────────────────────────────────────────


class MonthlyRunService:
    POLL_SECONDS = 2.0
    _sleep: Callable[[float], None] = staticmethod(time.sleep)

    # — public —

    @classmethod
    def start(cls, request: MonthlyRunStartRequest) -> dict[str, Any]:
        config = request.config_override or load_config()
        plan = derive_plan(request.month, config)
        source: MasterSource = request.source or config.master_source

        active = job_runtime.active_jobs(MONTHLY_RUN_JOB_TYPE)
        if active:
            raise MonthlyRunAlreadyActive(active[0]["job_id"], str(active[0].get("month") or "?"))

        cls.preflight(config, plan, source)

        marker = None if request.from_scratch else read_marker(plan.token)
        resumed = sorted(completed_steps(marker) & set(STEP_ORDER), key=STEP_ORDER.index)

        steps: dict[str, dict[str, Any]] = {}
        for step in STEP_ORDER:
            if step in resumed:
                prior = dict((marker or {}).get("steps", {}).get(step, {}))
                steps[step] = {
                    "status": "skipped",
                    "message": f"Already completed on {prior.get('finished_at') or prior.get('at') or 'an earlier run'} — skipped.",
                    "job_id": prior.get("job_id"),
                    "detail": dict(prior.get("detail") or {}),
                    "started_at": prior.get("started_at"),
                    "finished_at": prior.get("finished_at"),
                }
            elif step == "upload" and source == "drive":
                steps[step] = {
                    "status": "skipped",
                    "message": "The month is taken from Google Drive, so there is nothing to upload.",
                    "job_id": None,
                    "detail": {},
                    "started_at": None,
                    "finished_at": None,
                }
            else:
                steps[step] = {"status": "pending", "message": "", "job_id": None, "detail": {}, "started_at": None, "finished_at": None}

        job_id = uuid.uuid4().hex
        snapshot = {
            "job_id": job_id,
            "status": "queued",
            "message": f"Monthly run for {plan.token} queued.",
            "month": plan.token,
            "object_name": plan.object_name,
            "outcome": None,
            "source": source,
            "current_step": None,
            "steps": steps,
            "resumed_steps": resumed,
            "missing_discoms": [],
            "paths": plan.as_dict(),
            "started_at": _now_iso(),
            "finished_at": None,
        }
        job_runtime.start_job(
            job_type=MONTHLY_RUN_JOB_TYPE,
            job_id=job_id,
            initial_snapshot=snapshot,
            payload={"month": plan.month_input, "from_scratch": request.from_scratch, "source": source, "config": config.model_dump(mode="json")},
            policy=MONTHLY_RUN_POLICY,
            worker=lambda running_job_id: cls._run(running_job_id, plan, config, set(resumed), source),
        )
        return {
            "job_id": job_id,
            "status": "queued",
            "message": snapshot["message"],
            "month": plan.token,
            "object_name": plan.object_name,
        }

    @staticmethod
    def status(job_id: str) -> dict[str, Any] | None:
        return job_runtime.get_job(job_id)

    @staticmethod
    def stop(job_id: str) -> dict[str, Any] | None:
        return job_runtime.stop_job(job_id, "Stop requested. Stopping the current step...")

    @staticmethod
    def active() -> dict[str, Any] | None:
        active = job_runtime.active_jobs(MONTHLY_RUN_JOB_TYPE)
        return active[0] if active else None

    @classmethod
    def preflight(cls, config: MonthlyAutomationConfig, plan: MonthPlan, source: MasterSource = "ftp") -> None:
        """Everything that would fail an hour in, checked before anything starts.

        Google is needed either way: the FTP source uploads to Drive, the Drive
        source downloads from it. FTP passwords matter only for the FTP source.
        """
        problems: list[str] = []

        if source == "ftp":
            loaded = ftp_profiles.load_ftp_profiles()
            if loaded is None:
                problems.append(f"FTP passwords are not configured: create {ftp_profiles.ftp_profiles_path()}.")
            else:
                missing = [name for name in config.discoms if loaded.find(name) is None]
                if missing:
                    problems.append(
                        f"FTP passwords missing for {', '.join(missing)} in {ftp_profiles.ftp_profiles_path()}."
                    )

        drive_purpose = "to download the month from Drive" if source == "drive" else "to upload the month to Drive"
        if not config.drive_parent_folder_id.strip():
            problems.append(f"Google Drive parent folder ID is not set in the monthly run settings (needed {drive_purpose}).")
        auth = GoogleDriveService.get_auth_status()
        if not auth.get("configured"):
            problems.append("Google OAuth client JSON is not configured (see Upload master in Drive).")
        elif not auth.get("token_exists"):
            problems.append("Nobody has signed in to Google on this machine yet — open Upload master in Drive and sign in once.")

        if not Path(config.db_path).expanduser().parent.is_dir():
            problems.append(f"The folder for the DuckDB file does not exist: {Path(config.db_path).parent}")

        if problems:
            raise ValueError("Cannot start the monthly run: " + " ".join(problems))

    # — worker —

    @classmethod
    def _run(cls, job_id: str, plan: MonthPlan, config: MonthlyAutomationConfig, resumed: set[str], source: MasterSource = "ftp") -> None:
        children: dict[str, str | None] = {}
        where = "on the FTP server" if source == "ftp" else "in Google Drive"
        try:
            job_runtime.update_job(job_id, status="running", message=f"Monthly run for {plan.token} started.")

            if "download" not in resumed:
                if source == "drive":
                    verdict, missing = cls._step_drive_download(job_id, plan, config)
                else:
                    verdict, missing = cls._step_download(job_id, plan, config)
                if verdict in {"not_available_yet", "partial"}:
                    cls._finish(
                        job_id,
                        status="completed",
                        outcome=verdict,
                        message=(
                            f"{plan.token} is not {where} yet. Try again later."
                            if verdict == "not_available_yet"
                            else f"{plan.token} is only partly {where} (missing {', '.join(missing)}). Try again later."
                        ),
                        missing_discoms=missing,
                    )
                    return
                if verdict == "failed":
                    cls._finish(job_id, status="failed", outcome="failed", message=f"Download step failed for {plan.token}.")
                    return

            # Upload and build only read the downloaded files, so they run together:
            # upload is network-bound, conversion is CPU-bound. A month taken from
            # Drive is already there, so it has nothing to upload.
            if "upload" not in resumed and source == "ftp":
                children["upload"] = cls._start_upload(job_id, plan, config)
            if "build" not in resumed:
                children["build"] = cls._start_build(job_id, plan, config)

            job_runtime.update_job(
                job_id,
                current_step="upload+build" if len(children) == 2 else next(iter(children), None),
                message="Uploading to Drive and building the month..." if len(children) == 2 else "Running the remaining step...",
            )
            results = cls._wait_all(job_id, children)

            failures: list[str] = []
            if "upload" in results:
                ok, note = cls._gate_upload(results["upload"])
                cls._record(job_id, plan, "upload", ok, note, results["upload"])
                if not ok:
                    failures.append(note)
            if "build" in results:
                ok, note = cls._gate_build(results["build"])
                cls._record(job_id, plan, "build", ok, note, results["build"])
                if not ok:
                    failures.append(note)

            if failures:
                cls._finish(job_id, status="failed", outcome="failed", message=" ".join(failures))
                return

            cls._finish(
                job_id,
                status="completed",
                outcome="completed",
                message=(
                    f"{plan.token} is downloaded from Drive and available as {plan.object_name}."
                    if source == "drive"
                    else f"{plan.token} is downloaded, uploaded to Drive and available as {plan.object_name}."
                ),
            )
        except BackgroundJobCancelled:
            for child_id in children.values():
                if child_id:
                    job_runtime.stop_job(child_id, "Monthly run stopped.")
            cls._close_unfinished_steps(job_id, "cancelled", "Stopped with the run.")
            cls._finish(job_id, status="cancelled", outcome="cancelled", message="Monthly run stopped.")
        except Exception as exc:
            logger.exception("Monthly run %s failed", job_id)
            cls._close_unfinished_steps(job_id, "failed", str(exc))
            cls._finish(job_id, status="failed", outcome="failed", message=f"Monthly run failed: {exc}")

    # — steps —

    @classmethod
    def _step_download(cls, job_id: str, plan: MonthPlan, config: MonthlyAutomationConfig) -> tuple[str, list[str]]:
        profiles = ftp_profiles.resolve_profile_passwords(
            [
                FTPDownloadProfile(
                    name=discom,
                    username="",
                    password=None,
                    remote_dir=plan.remote_dir,
                    local_subfolder=f"{plan.token}/{discom}",
                )
                for discom in config.discoms
            ]
        )
        cls._set_step(job_id, "download", status="running", message="Checking the FTP server...", started_at=_now_iso())
        job_runtime.update_job(job_id, current_step="download")

        # The credentials file may name the server too (an internal IP rather
        # than the public hostname). When it does, it wins: whoever maintains
        # the passwords knows which server they are for.
        loaded = ftp_profiles.load_ftp_profiles()
        host = loaded.host if loaded and loaded.host else config.ftp_host
        port = loaded.port if loaded and loaded.port else config.ftp_port

        started = FTPDownloadService.start_download(
            host=host,
            port=port,
            output_root=config.csv_root,
            file_suffix=".gz",
            max_workers=config.ftp_max_workers,
            max_retries=3,
            retry_delay_seconds=5,
            timeout_seconds=30,
            passive_mode=True,
            skip_existing=True,
            profiles=profiles,
        )
        child_id = started["job_id"]
        cls._set_step(job_id, "download", job_id=child_id)
        result = cls._wait_all(job_id, {"download": child_id})["download"]

        if result.get("status") != "completed":
            note = result.get("error_message") or result.get("message") or f"FTP download {result.get('status')}."
            cls._set_step(job_id, "download", status="failed", message=str(note), finished_at=_now_iso(), detail=cls._download_detail(result))
            return "failed", []

        verdict, missing, message = classify_download(list(result.get("profile_results") or []), config.discoms)
        detail = cls._download_detail(result)
        if verdict == "ok":
            state = {"status": "completed", "message": message, "finished_at": _now_iso(), "detail": detail}
            cls._set_step(job_id, "download", **state)
            record_step(plan.token, "download", {**state, "job_id": child_id}, job_id)
        elif verdict == "failed":
            cls._set_step(job_id, "download", status="failed", message=message, finished_at=_now_iso(), detail=detail)
        else:
            cls._set_step(job_id, "download", status="pending", message=message, finished_at=_now_iso(), detail=detail)
        return verdict, missing

    @classmethod
    def _step_drive_download(cls, job_id: str, plan: MonthPlan, config: MonthlyAutomationConfig) -> tuple[str, list[str]]:
        """Pull the month's DISCOM folders out of Google Drive, one Drive job per DISCOM.

        The upload step stores ``<csv_dir>`` as ``<drive_root_name>/<DISCOM>/…``,
        and a Drive download recreates a folder under its own name, so
        downloading each DISCOM folder into ``csv_dir`` lands the files exactly
        where the FTP step would have put them. Files already present are
        skipped, so an interrupted step picks up where it stopped.
        """
        auth = DriveAuthConfig(mode="oauth")
        cls._set_step(job_id, "download", status="running", message=f"Looking for {plan.drive_root_name} in Google Drive...", started_at=_now_iso())
        job_runtime.update_job(job_id, current_step="download")

        month_folder = GoogleDriveService.find_child_folder(auth, config.drive_parent_folder_id, plan.drive_root_name)
        if month_folder is None:
            message = f"{plan.drive_root_name} is not in Google Drive yet (nobody has uploaded this month)."
            cls._set_step(job_id, "download", status="pending", message=message, finished_at=_now_iso(), detail={"source": "drive"})
            return "not_available_yet", list(config.discoms)

        by_name = {item["name"].strip().upper(): item for item in GoogleDriveService.list_child_folders(auth, month_folder["id"])}
        present = [discom for discom in config.discoms if discom.strip().upper() in by_name]
        missing = [discom for discom in config.discoms if discom.strip().upper() not in by_name]
        if not present:
            message = f"{plan.drive_root_name} is in Google Drive but holds no DISCOM folder yet."
            cls._set_step(job_id, "download", status="pending", message=message, finished_at=_now_iso(), detail={"source": "drive"})
            return "not_available_yet", missing

        totals = {"total_files_found": 0, "total_downloaded_files": 0, "total_skipped_files": 0, "total_failed_files": 0}
        failures: list[str] = []
        last_child_id: str | None = None
        for index, discom in enumerate(present, start=1):
            cls._set_step(job_id, "download", message=f"Downloading {discom} from Drive ({index}/{len(present)})...")
            started = GoogleDriveService.start_download(
                auth=auth,
                drive_link_or_id=by_name[discom.strip().upper()]["id"],
                output_folder=str(plan.csv_dir),
                overwrite_existing=False,
                export_google_files=False,
            )
            last_child_id = started["job_id"]
            cls._set_step(job_id, "download", job_id=last_child_id)
            result = cls._wait_all(job_id, {"download": last_child_id})["download"]

            found = int(result.get("total_items", 0) or 0)
            failed = int(result.get("failed_items", 0) or 0)
            totals["total_files_found"] += found
            totals["total_downloaded_files"] += int(result.get("downloaded_items", 0) or 0)
            totals["total_skipped_files"] += int(result.get("skipped_items", 0) or 0)
            totals["total_failed_files"] += failed
            if result.get("status") != "completed":
                failures.append(f"{discom}: Drive download {result.get('status')} — {result.get('message') or 'no detail'}")
            elif failed:
                errors = [str(err) for err in (result.get("errors") or [])]
                failures.append(f"{discom}: {failed} failed file(s)" + (f"; {errors[0]}" if errors else ""))
            elif found == 0:
                missing.append(discom)

        detail: dict[str, Any] = {"source": "drive", "current_profile": None, **totals}
        if failures:
            message = "Download finished with failures — " + "; ".join(failures)
            cls._set_step(job_id, "download", status="failed", message=message, finished_at=_now_iso(), detail=detail)
            return "failed", missing
        if len(missing) == len(config.discoms):
            message = f"{plan.drive_root_name} is in Google Drive but every DISCOM folder is empty."
            cls._set_step(job_id, "download", status="pending", message=message, finished_at=_now_iso(), detail=detail)
            return "not_available_yet", missing
        if missing:
            ordered = [discom for discom in config.discoms if discom in missing]
            message = "Not every DISCOM is in Drive yet: missing " + ", ".join(ordered) + "."
            cls._set_step(job_id, "download", status="pending", message=message, finished_at=_now_iso(), detail=detail)
            return "partial", ordered

        message = f"Downloaded {totals['total_files_found']:,} file(s) from Drive across {len(present)} DISCOM(s)."
        state = {"status": "completed", "message": message, "finished_at": _now_iso(), "detail": detail}
        cls._set_step(job_id, "download", **state)
        record_step(plan.token, "download", {**state, "job_id": last_child_id}, job_id)
        return "ok", []

    @classmethod
    def _start_upload(cls, job_id: str, plan: MonthPlan, config: MonthlyAutomationConfig) -> str:
        cls._set_step(job_id, "upload", status="running", message="Starting Drive upload...", started_at=_now_iso())
        started = GoogleDriveService.start_upload(
            auth=DriveAuthConfig(mode="oauth"),
            local_folder=str(plan.csv_dir),
            parent_folder_id=config.drive_parent_folder_id,
            root_folder_name=plan.drive_root_name,
            skip_existing=True,
            max_workers=config.drive_max_workers,
            interactive=False,
        )
        cls._set_step(job_id, "upload", job_id=started["job_id"])
        return started["job_id"]

    @classmethod
    def _start_build(cls, job_id: str, plan: MonthPlan, config: MonthlyAutomationConfig) -> str:
        cls._set_step(job_id, "build", status="running", message="Starting CSV → parquet → view...", started_at=_now_iso())
        payload = FullPipelineRequest(
            input_path=plan.csv_glob,
            parquet_output_path=plan.parquet_dir.as_posix(),
            compression=config.compression,
            overwrite_parquet=False,
            db_path=config.db_path,
            object_name=plan.object_name,
            object_type=config.object_type,
            replace=True,
            month_label=plan.month_label,
        )
        child_id = start_full_pipeline_job(payload)
        cls._set_step(job_id, "build", job_id=child_id)
        return child_id

    # — gates —

    @staticmethod
    def _gate_upload(result: dict[str, Any]) -> tuple[bool, str]:
        status = result.get("status")
        failed = int(result.get("failed_items", 0))
        if status != "completed":
            return False, f"Drive upload {status}: {result.get('message') or 'no detail'}"
        if failed:
            return False, f"Drive upload finished with {failed} failed file(s)."
        return True, f"Uploaded {int(result.get('uploaded_items', 0)):,} file(s), skipped {int(result.get('skipped_items', 0)):,} already present."

    @staticmethod
    def _gate_build(result: dict[str, Any]) -> tuple[bool, str]:
        status = result.get("status")
        if status != "completed":
            return False, f"Build {status}: {result.get('message') or 'no detail'}"
        reconciliation = result.get("reconciliation") or {}
        unaccounted = int(reconciliation.get("unaccounted_rows", 0) or 0)
        if result.get("data_quality") == "loss" or unaccounted:
            return False, f"Build reported row loss ({unaccounted:,} rows unaccounted for) — the month was not accepted."
        rows = result.get("table_rows")
        return True, f"{result.get('build_output_path') or 'DuckDB'}: {rows:,} rows" if isinstance(rows, int) else "Build completed."

    # — waiting and bookkeeping —

    @classmethod
    def _wait_all(cls, job_id: str, children: dict[str, str | None]) -> dict[str, dict[str, Any]]:
        pending = {step: child for step, child in children.items() if child}
        results: dict[str, dict[str, Any]] = {}
        while pending:
            if job_runtime.is_cancelled(job_id):
                for child_id in pending.values():
                    job_runtime.stop_job(child_id, "Monthly run stopped.")
                raise BackgroundJobCancelled()
            for step, child_id in list(pending.items()):
                child = job_runtime.get_job(child_id)
                if child is None:
                    results[step] = {"status": "failed", "message": "Child job disappeared from the job store."}
                    pending.pop(step)
                    continue
                cls._set_step(job_id, step, message=str(child.get("message") or ""), detail=cls._progress_detail(step, child))
                if child.get("status") in FINAL_JOB_STATUSES:
                    # Reflect the child's own ending straight away. The gate may
                    # refine this later, but a run that is stopped while another
                    # step is still going must not leave this one shown as
                    # "running" with a failure message underneath it.
                    child_status = str(child.get("status"))
                    cls._set_step(
                        job_id,
                        step,
                        status=child_status if child_status in {"completed", "failed", "cancelled"} else "failed",
                        message=str(child.get("message") or child.get("error_message") or ""),
                        finished_at=_now_iso(),
                        detail=cls._progress_detail(step, child),
                    )
                    results[step] = child
                    pending.pop(step)
            if pending:
                cls._sleep(cls.POLL_SECONDS)
        return results

    @classmethod
    def _record(cls, job_id: str, plan: MonthPlan, step: str, ok: bool, note: str, result: dict[str, Any]) -> None:
        state = {
            "status": "completed" if ok else "failed",
            "message": note,
            "finished_at": _now_iso(),
            "detail": cls._progress_detail(step, result),
        }
        cls._set_step(job_id, step, **state)
        if ok:
            record_step(plan.token, step, {**state, "job_id": result.get("job_id")}, job_id)

    @staticmethod
    def _progress_detail(step: str, child: dict[str, Any]) -> dict[str, Any]:
        if step == "download":
            return MonthlyRunService._download_detail(child)
        if step == "upload":
            return {
                key: child.get(key)
                for key in ("total_items", "processed_items", "uploaded_items", "skipped_items", "failed_items")
            }
        return {
            key: child.get(key)
            for key in (
                "current_phase",
                "overall_progress_percent",
                "parquet_processed_files",
                "parquet_total_files",
                "table_rows",
                "data_quality",
                "build_output_path",
            )
        }

    @staticmethod
    def _download_detail(child: dict[str, Any]) -> dict[str, Any]:
        if "total_items" in child:
            # A Drive download job: same shape as the FTP numbers so the card
            # shows one kind of progress line for either source.
            return {
                "source": "drive",
                "current_profile": None,
                "total_files_found": child.get("total_items"),
                "total_downloaded_files": child.get("downloaded_items"),
                "total_skipped_files": child.get("skipped_items"),
                "total_failed_files": child.get("failed_items"),
            }
        return {
            key: child.get(key)
            for key in (
                "current_profile",
                "total_files_found",
                "total_downloaded_files",
                "total_skipped_files",
                "total_failed_files",
            )
        }

    @staticmethod
    def _set_step(run_id: str, step: str, **fields: Any) -> None:
        # First parameter is deliberately not called job_id: callers record the
        # child's id as a field named job_id, which would otherwise collide.
        def mutate(snapshot: dict[str, Any]) -> None:
            steps = dict(snapshot.get("steps") or {})
            current = dict(steps.get(step) or {})
            current.update(fields)
            steps[step] = current
            snapshot["steps"] = steps

        job_runtime.mutate_job(run_id, mutate)

    @staticmethod
    def _close_unfinished_steps(run_id: str, status: str, message: str) -> None:
        """Any step still 'running' when the run ends takes the run's ending."""

        def mutate(snapshot: dict[str, Any]) -> None:
            steps = dict(snapshot.get("steps") or {})
            for name, state in steps.items():
                if isinstance(state, dict) and state.get("status") == "running":
                    closed = dict(state)
                    closed.update(status=status, message=message, finished_at=_now_iso())
                    steps[name] = closed
            snapshot["steps"] = steps

        job_runtime.mutate_job(run_id, mutate)

    @staticmethod
    def _finish(job_id: str, *, status: str, outcome: str, message: str, missing_discoms: list[str] | None = None) -> None:
        job_runtime.update_job(
            job_id,
            status=status,
            outcome=outcome,
            message=message,
            current_step=None,
            missing_discoms=list(missing_discoms or []),
            finished_at=_now_iso(),
        )
