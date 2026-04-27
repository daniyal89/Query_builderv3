from __future__ import annotations

import ftplib
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from backend.models.ftp_download import FTPDownloadProfile


@dataclass(frozen=True)
class _PreparedProfile:
    name: str
    username: str
    password: str
    remote_dir: str
    local_dir: Path


@dataclass(frozen=True)
class _DownloadTask:
    filename: str
    expected_size: int
    local_path: Path
    profile: _PreparedProfile


class _FTPJobCancelled(Exception):
    pass


class FTPDownloadService:
    _jobs: dict[str, dict[str, Any]] = {}
    _jobs_lock = threading.Lock()
    _cancel_events: dict[str, threading.Event] = {}

    @classmethod
    def start_download(
        cls,
        host: str,
        port: int,
        output_root: str,
        file_suffix: str,
        max_workers: int,
        max_retries: int,
        retry_delay_seconds: int,
        timeout_seconds: int,
        passive_mode: bool,
        skip_existing: bool,
        profiles: list[FTPDownloadProfile],
    ) -> dict[str, str]:
        normalized_host = host.strip()
        if not normalized_host:
            raise ValueError("FTP host is required.")
        if not output_root.strip():
            raise ValueError("Output root folder is required.")
        if not profiles:
            raise ValueError("At least one FTP profile is required.")

        job_id = uuid.uuid4().hex
        job_state = {
            "job_id": job_id,
            "status": "queued",
            "host": normalized_host,
            "output_root": str(Path(output_root).expanduser()),
            "current_profile": None,
            "total_profiles": len(profiles),
            "total_files_found": 0,
            "total_downloaded_files": 0,
            "total_skipped_files": 0,
            "total_failed_files": 0,
            "profile_results": [],
            "error_message": None,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        }
        with cls._jobs_lock:
            cls._cancel_events[job_id] = threading.Event()
            cls._jobs[job_id] = job_state

        worker = threading.Thread(
            target=cls._run_download_job,
            args=(
                job_id,
                normalized_host,
                port,
                output_root,
                file_suffix,
                max_workers,
                max_retries,
                retry_delay_seconds,
                timeout_seconds,
                passive_mode,
                skip_existing,
                profiles,
            ),
            daemon=True,
        )
        worker.start()
        return {"job_id": job_id, "status": "queued"}

    @classmethod
    def download_files(
        cls,
        host: str,
        port: int,
        output_root: str,
        file_suffix: str,
        max_workers: int,
        max_retries: int,
        retry_delay_seconds: int,
        timeout_seconds: int,
        passive_mode: bool,
        skip_existing: bool,
        profiles: list[FTPDownloadProfile],
    ) -> dict[str, Any]:
        """
        Run FTP downloads synchronously and return the final aggregate result.

        This compatibility API is kept for internal callers/tests that expect
        the pre-job-system return shape.
        """
        normalized_host = host.strip()
        if not normalized_host:
            raise ValueError("FTP host is required.")
        if not output_root.strip():
            raise ValueError("Output root folder is required.")
        if not profiles:
            raise ValueError("At least one FTP profile is required.")

        normalized_suffix = file_suffix.strip() or ".gz"
        if not normalized_suffix.startswith("."):
            normalized_suffix = f".{normalized_suffix}"
        normalized_suffix = normalized_suffix.lower()

        output_root_path = cls._expand_tokens(output_root, "ROOT")
        root_dir = Path(output_root_path).expanduser()
        root_dir.mkdir(parents=True, exist_ok=True)

        prepared_profiles = [cls._prepare_profile(profile, root_dir) for profile in profiles]

        total_found = total_downloaded = total_skipped = total_failed = 0
        profile_results: list[dict[str, Any]] = []
        for prepared in prepared_profiles:
            result = cls._download_profile(
                host=normalized_host,
                port=port,
                file_suffix=normalized_suffix,
                max_workers=max_workers,
                max_retries=max_retries,
                retry_delay_seconds=retry_delay_seconds,
                timeout_seconds=timeout_seconds,
                passive_mode=passive_mode,
                skip_existing=skip_existing,
                profile=prepared,
                job_id="sync",
            )
            profile_results.append(result)
            total_found += result["found_files"]
            total_downloaded += result["downloaded_files"]
            total_skipped += result["skipped_files"]
            total_failed += result["failed_files"]

        return {
            "status": "completed",
            "host": normalized_host,
            "output_root": str(root_dir),
            "total_profiles": len(prepared_profiles),
            "total_files_found": total_found,
            "total_downloaded_files": total_downloaded,
            "total_skipped_files": total_skipped,
            "total_failed_files": total_failed,
            "profile_results": profile_results,
            "error_message": None,
        }

    @classmethod
    def get_job_status(cls, job_id: str) -> dict[str, Any] | None:
        with cls._jobs_lock:
            job = cls._jobs.get(job_id)
            return dict(job) if job else None

    @classmethod
    def stop_download(cls, job_id: str) -> dict[str, Any] | None:
        with cls._jobs_lock:
            job = cls._jobs.get(job_id)
            if not job:
                return None
            if job.get("status") in {"completed", "failed", "cancelled"}:
                return dict(job)
            event = cls._cancel_events.get(job_id)
            if event:
                event.set()
            job["status"] = "cancelling"
            job["error_message"] = "Stop requested. Waiting for the current FTP operation to finish..."
            return dict(job)

    @classmethod
    def _is_cancelled(cls, job_id: str) -> bool:
        event = cls._cancel_events.get(job_id)
        return bool(event and event.is_set())

    @classmethod
    def _raise_if_cancelled(cls, job_id: str) -> None:
        if cls._is_cancelled(job_id):
            raise _FTPJobCancelled()

    @classmethod
    def _update_job(cls, job_id: str, **updates: Any) -> None:
        with cls._jobs_lock:
            if job_id not in cls._jobs:
                return
            cls._jobs[job_id].update(updates)

    @classmethod
    def _replace_profile_result(cls, job_id: str, result: dict[str, Any]) -> None:
        with cls._jobs_lock:
            if job_id not in cls._jobs:
                return
            results = list(cls._jobs[job_id].get("profile_results", []))
            existing_index = next(
                (index for index, item in enumerate(results) if item.get("profile_name") == result.get("profile_name")),
                None,
            )
            if existing_index is None:
                results.append(result)
            else:
                results[existing_index] = result
            cls._jobs[job_id]["profile_results"] = results

    @classmethod
    def _run_download_job(
        cls,
        job_id: str,
        host: str,
        port: int,
        output_root: str,
        file_suffix: str,
        max_workers: int,
        max_retries: int,
        retry_delay_seconds: int,
        timeout_seconds: int,
        passive_mode: bool,
        skip_existing: bool,
        profiles: list[FTPDownloadProfile],
    ) -> None:
        try:
            cls._raise_if_cancelled(job_id)
            cls._update_job(job_id, status="running")

            normalized_suffix = file_suffix.strip() or ".gz"
            if not normalized_suffix.startswith("."):
                normalized_suffix = f".{normalized_suffix}"
            normalized_suffix = normalized_suffix.lower()

            output_root_path = cls._expand_tokens(output_root, "ROOT")
            root_dir = Path(output_root_path).expanduser()
            root_dir.mkdir(parents=True, exist_ok=True)
            cls._update_job(job_id, output_root=str(root_dir))

            prepared_profiles = [cls._prepare_profile(profile, root_dir) for profile in profiles]
            cls._update_job(job_id, total_profiles=len(prepared_profiles))

            total_found = total_downloaded = total_skipped = total_failed = 0
            profile_results: list[dict[str, Any]] = []

            for prepared in prepared_profiles:
                cls._raise_if_cancelled(job_id)
                cls._update_job(job_id, current_profile=prepared.name)
                result = cls._download_profile(
                    host=host,
                    port=port,
                    file_suffix=normalized_suffix,
                    max_workers=max_workers,
                    max_retries=max_retries,
                    retry_delay_seconds=retry_delay_seconds,
                    timeout_seconds=timeout_seconds,
                    passive_mode=passive_mode,
                    skip_existing=skip_existing,
                    profile=prepared,
                    job_id=job_id,
                )
                profile_results.append(result)
                total_found += result["found_files"]
                total_downloaded += result["downloaded_files"]
                total_skipped += result["skipped_files"]
                total_failed += result["failed_files"]
                cls._replace_profile_result(job_id, result)
                cls._update_job(
                    job_id,
                    total_files_found=total_found,
                    total_downloaded_files=total_downloaded,
                    total_skipped_files=total_skipped,
                    total_failed_files=total_failed,
                )

            cls._update_job(
                job_id,
                status="cancelled" if cls._is_cancelled(job_id) else "completed",
                current_profile=None,
                profile_results=profile_results,
                total_files_found=total_found,
                total_downloaded_files=total_downloaded,
                total_skipped_files=total_skipped,
                total_failed_files=total_failed,
                error_message="Stopped by user." if cls._is_cancelled(job_id) else None,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        except _FTPJobCancelled:
            cls._update_job(
                job_id,
                status="cancelled",
                current_profile=None,
                error_message="Stopped by user.",
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        except Exception as exc:
            if cls._is_cancelled(job_id):
                cls._update_job(
                    job_id,
                    status="cancelled",
                    current_profile=None,
                    error_message="Stopped by user.",
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )
            else:
                cls._update_job(
                    job_id,
                    status="failed",
                    current_profile=None,
                    error_message=str(exc),
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )

    @staticmethod
    def _prepare_profile(profile: FTPDownloadProfile, root_dir: Path) -> _PreparedProfile:
        profile_name = profile.name.strip()
        if not profile_name:
            raise ValueError("Each FTP profile must have a name.")
        if not profile.username.strip():
            raise ValueError(f"FTP username is required for profile '{profile_name}'.")
        if not profile.password.strip():
            raise ValueError(f"FTP password is required for profile '{profile_name}'.")
        if not profile.remote_dir.strip():
            raise ValueError(f"Remote folder is required for profile '{profile_name}'.")

        remote_dir = FTPDownloadService._expand_tokens(profile.remote_dir, profile_name)
        local_subfolder = profile.local_subfolder or "{PROFILE}"
        resolved_local_subfolder = FTPDownloadService._expand_tokens(local_subfolder, profile_name)
        local_dir = (root_dir / resolved_local_subfolder).expanduser()
        local_dir.mkdir(parents=True, exist_ok=True)

        return _PreparedProfile(
            name=profile_name,
            username=profile.username,
            password=profile.password,
            remote_dir=remote_dir,
            local_dir=local_dir,
        )

    @staticmethod
    def _expand_tokens(template: str, profile_name: str) -> str:
        now = datetime.now()
        date_value = now.strftime("%d%m%Y")
        first_of_this_month = now.replace(day=1)
        last_month = first_of_this_month - timedelta(days=1)
        month_value = last_month.strftime("%b_%Y").upper()
        tokens = {"DATE": date_value, "MONTH": month_value, "PROFILE": profile_name}
        try:
            return template.format(**tokens)
        except KeyError as exc:
            missing = str(exc).strip("'")
            raise ValueError(
                f"Unsupported token '{{{missing}}}'. Use only {{DATE}}, {{MONTH}}, or {{PROFILE}}."
            ) from exc

    @classmethod
    def _download_profile(
        cls,
        host: str,
        port: int,
        file_suffix: str,
        max_workers: int,
        max_retries: int,
        retry_delay_seconds: int,
        timeout_seconds: int,
        passive_mode: bool,
        skip_existing: bool,
        profile: _PreparedProfile,
        job_id: str,
    ) -> dict[str, Any]:
        cls._raise_if_cancelled(job_id)
        errors: list[str] = []
        tasks = cls._scan_profile(
            host=host,
            port=port,
            file_suffix=file_suffix,
            timeout_seconds=timeout_seconds,
            passive_mode=passive_mode,
            profile=profile,
            errors=errors,
        )

        result = {
            "profile_name": profile.name,
            "remote_dir": profile.remote_dir,
            "local_dir": str(profile.local_dir),
            "found_files": len(tasks),
            "downloaded_files": 0,
            "skipped_files": 0,
            "failed_files": 0,
            "errors": errors,
        }
        cls._replace_profile_result(job_id, result)

        downloadable_tasks: list[_DownloadTask] = []
        for task in tasks:
            cls._raise_if_cancelled(job_id)
            if skip_existing and task.local_path.exists() and task.local_path.stat().st_size == task.expected_size:
                result["skipped_files"] += 1
                cls._replace_profile_result(job_id, result)
            else:
                downloadable_tasks.append(task)

        if downloadable_tasks:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        cls._download_single_file,
                        host,
                        port,
                        timeout_seconds,
                        passive_mode,
                        max_retries,
                        retry_delay_seconds,
                        task,
                        job_id,
                    ): task.filename
                    for task in downloadable_tasks
                }
                for future in as_completed(futures):
                    if cls._is_cancelled(job_id):
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    try:
                        success, message = future.result()
                    except _FTPJobCancelled:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    if success:
                        result["downloaded_files"] += 1
                    else:
                        result["failed_files"] += 1
                        result["errors"].append(message)
                    cls._replace_profile_result(job_id, result)
                    current_status = cls.get_job_status(job_id) or {}
                    partial_results = current_status.get("profile_results", [])
                    cls._update_job(
                        job_id,
                        total_files_found=sum(item.get("found_files", 0) for item in partial_results),
                        total_downloaded_files=sum(item.get("downloaded_files", 0) for item in partial_results),
                        total_skipped_files=sum(item.get("skipped_files", 0) for item in partial_results),
                        total_failed_files=sum(item.get("failed_files", 0) for item in partial_results),
                    )

        return result

    @staticmethod
    def _scan_profile(
        host: str,
        port: int,
        file_suffix: str,
        timeout_seconds: int,
        passive_mode: bool,
        profile: _PreparedProfile,
        errors: list[str],
    ) -> list[_DownloadTask]:
        ftp = None
        tasks: list[_DownloadTask] = []
        try:
            ftp = FTPDownloadService._connect(
                host=host,
                port=port,
                timeout_seconds=timeout_seconds,
                passive_mode=passive_mode,
                profile=profile,
            )
            names = FTPDownloadService._list_names(ftp)
            for name in names:
                if not name.lower().endswith(file_suffix):
                    continue
                try:
                    size = ftp.size(name)
                except Exception:
                    continue
                if size is None:
                    continue
                local_path = profile.local_dir / name
                tasks.append(_DownloadTask(filename=name, expected_size=int(size), local_path=local_path, profile=profile))
        except Exception as exc:
            errors.append(f"{profile.name}: {exc}")
        finally:
            FTPDownloadService._safe_quit(ftp)
        return tasks

    @staticmethod
    def _download_single_file(
        host: str,
        port: int,
        timeout_seconds: int,
        passive_mode: bool,
        max_retries: int,
        retry_delay_seconds: int,
        task: _DownloadTask,
        job_id: str,
    ) -> tuple[bool, str]:
        ftp = None
        for attempt in range(1, max_retries + 1):
            FTPDownloadService._raise_if_cancelled(job_id)
            try:
                ftp = FTPDownloadService._connect(
                    host=host,
                    port=port,
                    timeout_seconds=timeout_seconds,
                    passive_mode=passive_mode,
                    profile=task.profile,
                )
                with task.local_path.open("wb") as file_handle:
                    def write_chunk(chunk: bytes) -> None:
                        FTPDownloadService._raise_if_cancelled(job_id)
                        file_handle.write(chunk)
                    ftp.retrbinary(f"RETR {task.filename}", write_chunk)
                actual_size = task.local_path.stat().st_size
                if actual_size == task.expected_size:
                    return True, task.filename
                FTPDownloadService._safe_quit(ftp)
                ftp = None
                if attempt < max_retries:
                    time.sleep(retry_delay_seconds)
            except _FTPJobCancelled:
                FTPDownloadService._safe_quit(ftp)
                raise
            except Exception as exc:
                FTPDownloadService._safe_quit(ftp)
                ftp = None
                if attempt < max_retries:
                    time.sleep(retry_delay_seconds)
                else:
                    return False, f"{task.profile.name}: failed to download {task.filename} ({exc})"
            finally:
                FTPDownloadService._safe_quit(ftp)
                ftp = None
        return False, f"{task.profile.name}: failed to download {task.filename}"

    @staticmethod
    def _connect(
        host: str,
        port: int,
        timeout_seconds: int,
        passive_mode: bool,
        profile: _PreparedProfile,
    ) -> ftplib.FTP:
        ftp = ftplib.FTP()
        ftp.connect(host, port, timeout=timeout_seconds)
        ftp.login(profile.username, profile.password)
        ftp.set_pasv(passive_mode)
        ftp.cwd(profile.remote_dir)
        return ftp

    @staticmethod
    def _list_names(ftp: ftplib.FTP) -> list[str]:
        try:
            return ftp.nlst()
        except ftplib.error_perm:
            names: list[str] = []
            ftp.retrlines("NLST", callback=names.append)
            return names

    @staticmethod
    def _safe_quit(ftp: ftplib.FTP | None) -> None:
        if ftp is None:
            return
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass
