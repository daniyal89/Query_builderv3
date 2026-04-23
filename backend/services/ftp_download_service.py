from __future__ import annotations

import ftplib
import time
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


class FTPDownloadService:
    @staticmethod
    def download_files(
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
        normalized_host = host.strip()
        if not normalized_host:
            raise ValueError("FTP host is required.")

        normalized_suffix = file_suffix.strip() or ".gz"
        if not normalized_suffix.startswith("."):
            normalized_suffix = f".{normalized_suffix}"
        normalized_suffix = normalized_suffix.lower()

        output_root_path = FTPDownloadService._expand_tokens(output_root, "ROOT")
        root_dir = Path(output_root_path).expanduser()
        root_dir.mkdir(parents=True, exist_ok=True)

        prepared_profiles = [
            FTPDownloadService._prepare_profile(profile, root_dir) for profile in profiles
        ]

        profile_results: list[dict[str, Any]] = []
        total_found = total_downloaded = total_skipped = total_failed = 0

        for prepared in prepared_profiles:
            result = FTPDownloadService._download_profile(
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
            )
            profile_results.append(result)
            total_found += result["found_files"]
            total_downloaded += result["downloaded_files"]
            total_skipped += result["skipped_files"]
            total_failed += result["failed_files"]

        return {
            "host": normalized_host,
            "output_root": str(root_dir),
            "total_profiles": len(prepared_profiles),
            "total_files_found": total_found,
            "total_downloaded_files": total_downloaded,
            "total_skipped_files": total_skipped,
            "total_failed_files": total_failed,
            "profile_results": profile_results,
        }

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
        tokens = {
            "DATE": date_value,
            "MONTH": month_value,
            "PROFILE": profile_name,
        }
        try:
            return template.format(**tokens)
        except KeyError as exc:
            missing = str(exc).strip("'")
            raise ValueError(
                f"Unsupported token '{{{missing}}}'. Use only {{DATE}}, {{MONTH}}, or {{PROFILE}}."
            ) from exc

    @staticmethod
    def _download_profile(
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
    ) -> dict[str, Any]:
        errors: list[str] = []
        tasks = FTPDownloadService._scan_profile(
            host=host,
            port=port,
            file_suffix=file_suffix,
            timeout_seconds=timeout_seconds,
            passive_mode=passive_mode,
            profile=profile,
            errors=errors,
        )

        found_files = len(tasks)
        skipped_files = 0
        if found_files == 0 and errors:
            return {
                "profile_name": profile.name,
                "remote_dir": profile.remote_dir,
                "local_dir": str(profile.local_dir),
                "found_files": 0,
                "downloaded_files": 0,
                "skipped_files": 0,
                "failed_files": 0,
                "errors": errors,
            }

        if found_files == 0:
            return {
                "profile_name": profile.name,
                "remote_dir": profile.remote_dir,
                "local_dir": str(profile.local_dir),
                "found_files": 0,
                "downloaded_files": 0,
                "skipped_files": 0,
                "failed_files": 0,
                "errors": [],
            }

        downloadable_tasks: list[_DownloadTask] = []
        for task in tasks:
            if skip_existing and task.local_path.exists() and task.local_path.stat().st_size == task.expected_size:
                skipped_files += 1
            else:
                downloadable_tasks.append(task)

        downloaded_files = 0
        failed_files = 0
        if downloadable_tasks:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        FTPDownloadService._download_single_file,
                        host,
                        port,
                        timeout_seconds,
                        passive_mode,
                        max_retries,
                        retry_delay_seconds,
                        task,
                    ): task.filename
                    for task in downloadable_tasks
                }

                for future in as_completed(futures):
                    success, message = future.result()
                    if success:
                        downloaded_files += 1
                    else:
                        failed_files += 1
                        errors.append(message)

        return {
            "profile_name": profile.name,
            "remote_dir": profile.remote_dir,
            "local_dir": str(profile.local_dir),
            "found_files": found_files,
            "downloaded_files": downloaded_files,
            "skipped_files": skipped_files,
            "failed_files": failed_files,
            "errors": errors,
        }

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
                filename = Path(name).name
                if not filename.lower().endswith(file_suffix):
                    continue
                try:
                    expected_size = int(ftp.size(name) or 0)
                except Exception:
                    expected_size = 0
                local_path = profile.local_dir / filename
                tasks.append(
                    _DownloadTask(
                        filename=name,
                        expected_size=expected_size,
                        local_path=local_path,
                        profile=profile,
                    )
                )
            return tasks
        except Exception as exc:
            errors.append(f"{profile.name}: {exc}")
            return []
        finally:
            FTPDownloadService._close_quietly(ftp)

    @staticmethod
    def _download_single_file(
        host: str,
        port: int,
        timeout_seconds: int,
        passive_mode: bool,
        max_retries: int,
        retry_delay_seconds: int,
        task: _DownloadTask,
    ) -> tuple[bool, str]:
        ftp = None
        task.local_path.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, max_retries + 1):
            try:
                ftp = FTPDownloadService._connect(
                    host=host,
                    port=port,
                    timeout_seconds=timeout_seconds,
                    passive_mode=passive_mode,
                    profile=task.profile,
                )
                with task.local_path.open("wb") as output_handle:
                    ftp.retrbinary(f"RETR {task.filename}", output_handle.write)

                if task.expected_size > 0 and task.local_path.stat().st_size != task.expected_size:
                    raise IOError(
                        f"size mismatch for {task.filename} (expected {task.expected_size}, got {task.local_path.stat().st_size})"
                    )
                return True, task.filename
            except Exception as exc:
                FTPDownloadService._close_quietly(ftp)
                ftp = None
                if attempt == max_retries:
                    return False, f"{task.profile.name}: failed to download {task.filename}: {exc}"
                time.sleep(retry_delay_seconds)
            finally:
                FTPDownloadService._close_quietly(ftp)
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
            names = ftp.nlst()
            return [name for name in names if name not in {".", ".."}]
        except ftplib.error_perm:
            names: list[str] = []
            ftp.retrlines("NLST", callback=names.append)
            return [name for name in names if name not in {".", ".."}]

    @staticmethod
    def _close_quietly(ftp: ftplib.FTP | None) -> None:
        if ftp is None:
            return
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass
