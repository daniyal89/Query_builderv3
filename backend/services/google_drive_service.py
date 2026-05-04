import html
import logging
import mimetypes
import os
import re
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Optional
from urllib import error, parse, request
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google_auth_httplib2 import AuthorizedHttp
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import httplib2
import socks

from backend.config import settings
from backend.services.job_runtime import (
    BackgroundJobCancelled,
    BackgroundJobPolicy,
    job_runtime,
)
from backend.models.google_drive import DriveAuthConfig


SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_MIME_PREFIX = "application/vnd.google-apps."

EXPORT_TYPES = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
}

PUBLIC_EXPORT_HINTS = [
    ("docs.google.com/document", "docx", ".docx"),
    ("docs.google.com/spreadsheets", "xlsx", ".xlsx"),
    ("docs.google.com/presentation", "pptx", ".pptx"),
]


class _DriveJobCancelled(Exception):
    pass


class GoogleDriveService:
    _logger = logging.getLogger("duckdb_dashboard")
    UPLOAD_JOB_TYPE = "google_drive.upload"
    DOWNLOAD_JOB_TYPE = "google_drive.download"
    UPLOAD_JOB_POLICY = BackgroundJobPolicy(max_attempts=1, retry_backoff_seconds=0)
    DOWNLOAD_JOB_POLICY = BackgroundJobPolicy(max_attempts=1, retry_backoff_seconds=0)

    @classmethod
    def start_upload(
        cls,
        auth: DriveAuthConfig,
        local_folder: str,
        parent_folder_id: str,
        root_folder_name: Optional[str],
        skip_existing: bool,
        max_workers: int,
    ) -> dict[str, str]:
        source = Path(local_folder).expanduser()
        if not source.is_dir():
            raise ValueError(f"Local folder not found: {source}")
        if not parent_folder_id.strip():
            raise ValueError("Google Drive parent folder ID is required.")

        if auth.mode == "auto":
            auth = auth.model_copy(update={"mode": "oauth"})

        job_id = str(uuid.uuid4())
        job_runtime.start_job(
            job_type=cls.UPLOAD_JOB_TYPE,
            job_id=job_id,
            initial_snapshot=cls._create_job(
                job_id,
                "upload",
                f"Queued upload from {source}",
            ),
            payload={
                "auth": auth.model_dump(mode="json"),
                "local_folder": str(source),
                "parent_folder_id": parent_folder_id.strip(),
                "root_folder_name": root_folder_name,
                "skip_existing": skip_existing,
                "max_workers": max_workers,
            },
            policy=cls.UPLOAD_JOB_POLICY,
            worker=lambda running_job_id: cls._run_upload_job(
                running_job_id,
                auth,
                source,
                parent_folder_id.strip(),
                root_folder_name,
                skip_existing,
                max_workers,
            ),
        )
        return {"job_id": job_id, "status": "queued"}

    @classmethod
    def start_download(
        cls,
        auth: DriveAuthConfig,
        drive_link_or_id: str,
        output_folder: str,
        overwrite_existing: bool,
        export_google_files: bool,
    ) -> dict[str, str]:
        original_link = drive_link_or_id.strip()
        target_id = cls.extract_drive_id(original_link)
        if not target_id:
            raise ValueError("Enter a valid Google Drive file/folder link or ID.")

        output_path = Path(output_folder).expanduser()
        output_path.mkdir(parents=True, exist_ok=True)

        job_id = str(uuid.uuid4())
        job_runtime.start_job(
            job_type=cls.DOWNLOAD_JOB_TYPE,
            job_id=job_id,
            initial_snapshot=cls._create_job(
                job_id,
                "download",
                f"Queued download to {output_path}",
                output_path=str(output_path),
            ),
            payload={
                "auth": auth.model_dump(mode="json"),
                "drive_link_or_id": original_link,
                "resolved_drive_id": target_id,
                "output_folder": str(output_path),
                "overwrite_existing": overwrite_existing,
                "export_google_files": export_google_files,
            },
            policy=cls.DOWNLOAD_JOB_POLICY,
            worker=lambda running_job_id: cls._run_download_job(
                running_job_id,
                auth,
                original_link,
                target_id,
                output_path,
                overwrite_existing,
                export_google_files,
            ),
        )
        return {"job_id": job_id, "status": "queued"}

    @classmethod
    def get_job_status(cls, job_id: str) -> Optional[dict[str, Any]]:
        return job_runtime.get_job(job_id)

    @classmethod
    def stop_job(cls, job_id: str) -> Optional[dict[str, Any]]:
        return job_runtime.stop_job(
            job_id,
            "Stop requested. Waiting for the current file operation to finish...",
        )

    @classmethod
    def _is_cancelled(cls, job_id: str) -> bool:
        return job_runtime.is_cancelled(job_id)

    @classmethod
    def _raise_if_cancelled(cls, job_id: str) -> None:
        try:
            job_runtime.raise_if_cancelled(job_id)
        except BackgroundJobCancelled:
            raise _DriveJobCancelled()

    @classmethod
    def get_auth_status(cls, message_override: Optional[str] = None) -> dict[str, Any]:
        client_path = cls._resolve_oauth_client_path(None, raise_if_missing=False)
        token_path = cls._resolve_token_path(None)
        token_exists = cls._has_cached_oauth_token(token_path)
        creds = cls._load_cached_oauth_credentials(token_path) if token_exists else None
        token_valid = bool(creds and creds.valid)
        return cls._build_auth_status(
            client_path=client_path,
            token_exists=token_exists,
            token_valid=token_valid,
            message_override=message_override,
        )

    @classmethod
    def login_google(cls) -> dict[str, Any]:
        cls._get_drive_service(DriveAuthConfig(mode="oauth"))
        return cls.get_auth_status("Google login is ready.")

    @classmethod
    def logout_google(cls, token_override: Optional[str] = None) -> dict[str, Any]:
        token_path = cls._resolve_token_path(token_override)
        if not cls._has_cached_oauth_token(token_path):
            return cls.get_auth_status("No cached Google login token was found.")

        creds = cls._load_cached_oauth_credentials(token_path)
        remote_revoked = cls._revoke_cached_oauth_tokens(creds)

        cls._clear_cached_oauth_token(token_path)
        if cls._has_cached_oauth_token(token_path):
            raise ValueError(f"Could not remove cached Google login token: {token_path}")

        if remote_revoked:
            message = "Signed out from Google Drive and cleared the cached login token."
        elif creds:
            message = "Cleared the cached Google login token. Remote revoke could not be confirmed."
        else:
            message = "Cleared the cached Google login token."
        return cls.get_auth_status(message)

    @staticmethod
    def extract_drive_id(value: str) -> str:
        text = value.strip()
        if not text:
            return ""
        patterns = [
            r"/folders/([a-zA-Z0-9_-]+)",
            r"/file/d/([a-zA-Z0-9_-]+)",
            r"[?&]id=([a-zA-Z0-9_-]+)",
            r"/d/([a-zA-Z0-9_-]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        if re.fullmatch(r"[a-zA-Z0-9_-]{10,}", text):
            return text
        return ""

    @classmethod
    def _create_job(cls, job_id: str, job_type: str, message: str, output_path: Optional[str] = None) -> dict[str, Any]:
        return {
            "job_id": job_id,
            "status": "queued",
            "job_type": job_type,
            "message": message,
            "total_items": 0,
            "processed_items": 0,
            "uploaded_items": 0,
            "downloaded_items": 0,
            "skipped_items": 0,
            "failed_items": 0,
            "output_path": output_path,
            "errors": [],
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        }

    @classmethod
    def _update_job(cls, job_id: str, **updates: Any) -> None:
        job_runtime.update_job(job_id, **updates)

    @classmethod
    def _increment_job(cls, job_id: str, **increments: int) -> None:
        job_runtime.increment_job(job_id, **increments)

    @classmethod
    def _add_error(cls, job_id: str, message: str) -> None:
        def mutate(snapshot: dict[str, Any]) -> None:
            errors = list(snapshot.get("errors", []))
            errors.append(message)
            snapshot["errors"] = errors[-100:]
            snapshot["failed_items"] = int(snapshot.get("failed_items", 0)) + 1

        job_runtime.mutate_job(job_id, mutate, last_error=message)

    @classmethod
    def _finish_job(cls, job_id: str, failed: bool = False, message: Optional[str] = None) -> None:
        current = cls.get_job_status(job_id) or {}
        if cls._is_cancelled(job_id):
            cls._update_job(
                job_id,
                status="cancelled",
                message=message or "Stopped by user.",
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            return
        failed = failed or int(current.get("failed_items", 0)) > 0
        cls._update_job(
            job_id,
            status="failed" if failed else "completed",
            message=message or ("Completed with errors." if failed else "Completed successfully."),
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )

    @staticmethod
    def _user_config_dir() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent / "config"
        return settings.BASE_DIR / "config"

    @classmethod
    def _default_oauth_client_path(cls) -> Path:
        return cls._user_config_dir() / "google_oauth_client.json"

    @classmethod
    def _build_auth_status(
        cls,
        client_path: Optional[Path],
        token_exists: bool,
        token_valid: bool,
        message_override: Optional[str] = None,
    ) -> dict[str, Any]:
        configured = bool(client_path)
        if message_override is not None:
            message = message_override
        elif configured:
            if token_valid:
                message = "Google login is ready."
            elif token_exists:
                message = "Google login token exists but may need refresh."
            else:
                message = "Google OAuth client is configured. Click Sign in with Google when needed."
        else:
            message = (
                "Public file links can still be tried. For private links, put your OAuth desktop client JSON at "
                f"{cls._default_oauth_client_path()} or set QUERY_BUILDER_GOOGLE_OAUTH_CLIENT_JSON."
            )
        return {
            "configured": configured,
            "token_exists": token_exists,
            "token_valid": token_valid,
            "message": message,
        }

    @classmethod
    def _resolve_token_path(cls, token_override: Optional[str]) -> Path:
        if token_override and token_override.strip():
            return Path(token_override).expanduser()
        return cls._user_config_dir() / "google_drive_token.json"

    @classmethod
    def _resolve_oauth_client_path(cls, override: Optional[str], raise_if_missing: bool = True) -> Optional[Path]:
        candidates: list[Path] = []
        if override and override.strip():
            candidates.append(Path(override).expanduser())
        env_path = os.environ.get("QUERY_BUILDER_GOOGLE_OAUTH_CLIENT_JSON")
        if env_path:
            candidates.append(Path(env_path).expanduser())
        candidates.append(cls._default_oauth_client_path())
        candidates.append(settings.BASE_DIR / "config" / "google_oauth_client.json")

        for candidate in candidates:
            if candidate.is_file():
                return candidate

        if raise_if_missing:
            raise ValueError(
                "Google login is not configured. Put the OAuth Desktop client JSON at "
                f"{cls._default_oauth_client_path()} or set QUERY_BUILDER_GOOGLE_OAUTH_CLIENT_JSON."
            )
        return None

    @staticmethod
    def _has_cached_oauth_token(token_path: Path) -> bool:
        try:
            return token_path.is_file() and token_path.stat().st_size > 0
        except OSError:
            return token_path.is_file()

    @staticmethod
    def _clear_cached_oauth_token(token_path: Path) -> None:
        try:
            token_path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            pass
        except OSError:
            pass

        try:
            token_path.write_text("", encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Could not remove cached Google login token: {exc}") from exc

    @staticmethod
    def _load_cached_oauth_credentials(token_path: Path) -> Optional[Credentials]:
        try:
            return Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            return None

    @classmethod
    def _revoke_cached_oauth_tokens(cls, creds: Optional[Credentials]) -> bool:
        if creds is None:
            return False
        for token in (getattr(creds, "refresh_token", None), getattr(creds, "token", None)):
            if cls._revoke_oauth_token(token):
                return True
        return False

    @staticmethod
    def _revoke_oauth_token(token: Optional[str]) -> bool:
        clean_token = (token or "").strip()
        if not clean_token:
            return False
        revoke_request = request.Request(
            "https://oauth2.googleapis.com/revoke",
            data=parse.urlencode({"token": clean_token}).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with request.urlopen(revoke_request, timeout=15) as response:
                status_code = getattr(response, "status", 200)
            return 200 <= status_code < 300
        except error.HTTPError as exc:
            if exc.code == 400:
                return False
            return False
        except Exception:
            return False

    @classmethod
    def _build_google_http(cls, creds: Credentials | service_account.Credentials):
        explicit_proxy_host = (settings.PROXY_HOST or "").strip() or None
        explicit_proxy_port = settings.PROXY_PORT
        explicit_proxy_user = (settings.PROXY_USER or "").strip() or None
        explicit_proxy_pass = (settings.PROXY_PASS or "").strip() or None
        proxy_url = (
            settings.HTTPS_PROXY
            or settings.HTTP_PROXY
            or os.getenv("HTTPS_PROXY")
            or os.getenv("https_proxy")
            or os.getenv("HTTP_PROXY")
            or os.getenv("http_proxy")
        )
        if explicit_proxy_host:
            proxy_port = explicit_proxy_port or 80
            cls._logger.info(
                "Google Drive HTTP transport configured with explicit proxy host=%s port=%s.",
                explicit_proxy_host,
                proxy_port,
            )
            proxy_info = httplib2.ProxyInfo(
                proxy_type=socks.PROXY_TYPE_HTTP,
                proxy_host=explicit_proxy_host,
                proxy_port=int(proxy_port),
                proxy_user=explicit_proxy_user,
                proxy_pass=explicit_proxy_pass,
            )
            return AuthorizedHttp(creds, http=httplib2.Http(proxy_info=proxy_info, timeout=60))

        if proxy_url:
            if "://" not in proxy_url:
                proxy_url = f"http://{proxy_url}"
            parsed = urlparse(proxy_url)
            proxy_host = parsed.hostname
            proxy_port = parsed.port or 80
            cls._logger.info(
                "Google Drive HTTP transport configured with outbound proxy host=%s port=%s.",
                proxy_host,
                proxy_port,
            )
        else:
            cls._logger.warning("Google Drive HTTP transport has no proxy configured; using direct internet route.")
        if proxy_url:
            parsed = urlparse(proxy_url)
            proxy_info = None
            if parsed.hostname:
                proxy_info = httplib2.ProxyInfo(
                    proxy_type=socks.PROXY_TYPE_HTTP,
                    proxy_host=parsed.hostname,
                    proxy_port=parsed.port or 80,
                    proxy_user=parsed.username,
                    proxy_pass=parsed.password,
                )
            if proxy_info is None:
                proxy_info = httplib2.proxy_info_from_url(proxy_url, method="https")
            if proxy_info:
                return AuthorizedHttp(creds, http=httplib2.Http(proxy_info=proxy_info, timeout=60))
        return AuthorizedHttp(creds, http=httplib2.Http(timeout=60))

    @staticmethod
    def _exception_details(exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}"

    @classmethod
    def _get_drive_service(cls, auth: DriveAuthConfig):
        if auth.mode == "service_account":
            path = Path(auth.service_account_json_path or "").expanduser()
            if not path.is_file():
                raise ValueError("Service-account JSON path is required for service-account mode.")
            creds = service_account.Credentials.from_service_account_file(str(path), scopes=SCOPES)
            return build("drive", "v3", http=cls._build_google_http(creds), cache_discovery=False)

        client_path = cls._resolve_oauth_client_path(auth.oauth_client_json_path)
        assert client_path is not None
        token_path = cls._resolve_token_path(auth.token_json_path)
        creds = cls._load_cached_oauth_credentials(token_path) if token_path.is_file() else None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
                creds = flow.run_local_server(port=0, prompt="consent")
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")

        return build("drive", "v3", http=cls._build_google_http(creds), cache_discovery=False)

    @staticmethod
    def _escape_drive_query(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    def _safe_name(name: str) -> str:
        return re.sub(r'[<>:"/\\|?*]+', "_", name).strip().strip(".") or "untitled"

    @classmethod
    def _create_or_get_folder(cls, service, name: str, parent_id: str) -> str:
        clean_name = cls._safe_name(name)
        query = (
            f"'{parent_id}' in parents and trashed = false and "
            f"mimeType = '{FOLDER_MIME}' and name = '{cls._escape_drive_query(clean_name)}'"
        )
        result = service.files().list(
            q=query,
            fields="files(id, name)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = result.get("files", [])
        if files:
            return files[0]["id"]
        folder = service.files().create(
            body={"name": clean_name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
            fields="id",
            supportsAllDrives=True,
        ).execute()
        return folder["id"]

    @classmethod
    def _existing_file_names(cls, service, parent_id: str) -> set[str]:
        names: set[str] = set()
        page_token = None
        query = f"'{parent_id}' in parents and trashed = false and mimeType != '{FOLDER_MIME}'"
        while True:
            result = service.files().list(
                q=query,
                fields="nextPageToken, files(name)",
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            names.update(item["name"] for item in result.get("files", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break
        return names

    @classmethod
    def _run_upload_job(
        cls,
        job_id: str,
        auth: DriveAuthConfig,
        source: Path,
        parent_folder_id: str,
        root_folder_name: Optional[str],
        skip_existing: bool,
        max_workers: int,
    ) -> None:
        try:
            cls._raise_if_cancelled(job_id)
            cls._update_job(job_id, status="running", message="Opening Google login if needed...")
            service = cls._get_drive_service(auth)
            cls._raise_if_cancelled(job_id)
            root_name = root_folder_name.strip() if root_folder_name and root_folder_name.strip() else source.name
            root_drive_id = cls._create_or_get_folder(service, root_name, parent_folder_id)
            all_files = [path for path in source.rglob("*") if path.is_file()]
            cls._update_job(job_id, total_items=len(all_files), message=f"Uploading {len(all_files)} file(s)...")
            cls._raise_if_cancelled(job_id)

            folder_cache: dict[Path, str] = {Path("."): root_drive_id}

            def drive_folder_for(local_parent: Path) -> str:
                rel = local_parent.relative_to(source) if local_parent != source else Path(".")
                if rel in folder_cache:
                    return folder_cache[rel]
                current = Path(".")
                current_id = root_drive_id
                for part in rel.parts:
                    current = current / part
                    if current not in folder_cache:
                        current_id = cls._create_or_get_folder(service, part, current_id)
                        folder_cache[current] = current_id
                    else:
                        current_id = folder_cache[current]
                return current_id

            folder_existing: dict[str, set[str]] = {}
            upload_tasks: list[tuple[Path, str]] = []
            for local_file in all_files:
                cls._raise_if_cancelled(job_id)
                parent_id = drive_folder_for(local_file.parent)
                if skip_existing:
                    if parent_id not in folder_existing:
                        folder_existing[parent_id] = cls._existing_file_names(service, parent_id)
                    if local_file.name in folder_existing[parent_id]:
                        cls._increment_job(job_id, processed_items=1, skipped_items=1)
                        continue
                upload_tasks.append((local_file, parent_id))

            def upload_one(item: tuple[Path, str]) -> None:
                if cls._is_cancelled(job_id):
                    raise _DriveJobCancelled()
                local_file, parent_id = item
                worker_service = cls._get_drive_service(auth)
                if cls._is_cancelled(job_id):
                    raise _DriveJobCancelled()
                mime_type, _ = mimetypes.guess_type(str(local_file))
                media = MediaFileUpload(str(local_file), mimetype=mime_type, resumable=True, chunksize=5 * 1024 * 1024)
                worker_service.files().create(
                    body={"name": local_file.name, "parents": [parent_id]},
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                ).execute()

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {executor.submit(upload_one, task): task[0] for task in upload_tasks}
                for future in as_completed(future_map):
                    if cls._is_cancelled(job_id):
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    local_file = future_map[future]
                    try:
                        future.result()
                        cls._increment_job(job_id, processed_items=1, uploaded_items=1)
                    except _DriveJobCancelled:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    except Exception as exc:
                        cls._increment_job(job_id, processed_items=1)
                        cls._add_error(job_id, f"{local_file}: {exc}")

            cls._finish_job(job_id, message=f"Upload finished. Drive folder: {root_name}")
        except _DriveJobCancelled:
            cls._finish_job(job_id, message="Upload stopped by user.")
        except Exception as exc:
            if cls._is_cancelled(job_id):
                cls._finish_job(job_id, message="Upload stopped by user.")
            else:
                detail = cls._exception_details(exc)
                cls._logger.exception("Google Drive upload job failed (job_id=%s): %s", job_id, detail)
                cls._add_error(job_id, detail)
                cls._finish_job(job_id, failed=True, message=detail)

    @classmethod
    def _run_download_job(
        cls,
        job_id: str,
        auth: DriveAuthConfig,
        original_link: str,
        target_id: str,
        output_path: Path,
        overwrite_existing: bool,
        export_google_files: bool,
    ) -> None:
        try:
            cls._raise_if_cancelled(job_id)
            if auth.mode == "auto":
                cls._update_job(job_id, status="running", total_items=1, message="Trying public link without Google login...")
                public_result = cls._try_public_download(original_link, target_id, output_path, overwrite_existing, export_google_files, job_id)
                cls._raise_if_cancelled(job_id)
                if public_result[0]:
                    cls._finish_job(job_id, message=f"Public download finished: {output_path}")
                    return
                cls._update_job(job_id, message="Public download needs Google login. Opening Google sign-in if needed...")
                cls._clear_errors(job_id)
                auth = auth.model_copy(update={"mode": "oauth"})
            elif auth.mode == "oauth":
                cls._update_job(job_id, status="running", message="Opening Google sign-in if needed...")
            else:
                cls._update_job(job_id, status="running", message="Connecting with service account...")

            service = cls._get_drive_service(auth)
            cls._raise_if_cancelled(job_id)
            root_meta = cls._get_metadata(service, target_id)
            cls._raise_if_cancelled(job_id)
            total = cls._count_items(service, target_id, root_meta, job_id)
            cls._update_job(job_id, total_items=total, processed_items=0, downloaded_items=0, skipped_items=0, failed_items=0, message=f"Downloading {total} item(s)...")
            cls._download_item(service, target_id, root_meta, output_path, overwrite_existing, export_google_files, job_id)
            cls._finish_job(job_id, message=f"Download finished: {output_path}")
        except _DriveJobCancelled:
            cls._finish_job(job_id, message="Download stopped by user.")
        except Exception as exc:
            if cls._is_cancelled(job_id):
                cls._finish_job(job_id, message="Download stopped by user.")
            else:
                if type(exc).__name__ == "ServerNotFoundError":
                    cls._logger.warning(
                        "Drive API host could not be resolved; attempting public-link fallback (job_id=%s, target_id=%s).",
                        job_id,
                        target_id,
                    )
                    fallback_link = original_link if original_link.strip() else f"https://drive.google.com/file/d/{target_id}/view"
                    try:
                        ok, fallback_msg = cls._try_public_download(
                            fallback_link,
                            target_id,
                            output_path,
                            overwrite_existing,
                            export_google_files,
                            job_id,
                        )
                        if ok:
                            cls._finish_job(job_id, message=f"Fallback public download finished: {output_path}")
                            return
                        cls._add_error(job_id, f"Fallback public download failed: {fallback_msg}")
                    except Exception as fallback_exc:
                        cls._add_error(job_id, f"Fallback public download failed: {cls._exception_details(fallback_exc)}")
                detail = cls._exception_details(exc)
                cls._logger.exception(
                    "Google Drive download job failed (job_id=%s, mode=%s, target_id=%s): %s",
                    job_id,
                    auth.mode,
                    target_id,
                    detail,
                )
                cls._add_error(job_id, detail)
                cls._finish_job(job_id, failed=True, message=detail)

    @classmethod
    def _clear_errors(cls, job_id: str) -> None:
        job_runtime.update_job(job_id, errors=[], failed_items=0, processed_items=0)

    @staticmethod
    def _get_metadata(service, file_id: str) -> dict[str, Any]:
        return service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size",
            supportsAllDrives=True,
        ).execute()

    @classmethod
    def _count_items(cls, service, file_id: str, metadata: dict[str, Any], job_id: Optional[str] = None) -> int:
        if job_id:
            cls._raise_if_cancelled(job_id)
        if metadata.get("mimeType") != FOLDER_MIME:
            return 1
        total = 0
        for child in cls._list_children(service, file_id):
            if job_id:
                cls._raise_if_cancelled(job_id)
            total += cls._count_items(service, child["id"], child, job_id)
        return total

    @classmethod
    def _list_children(cls, service, folder_id: str) -> list[dict[str, Any]]:
        children: list[dict[str, Any]] = []
        page_token = None
        query = f"'{folder_id}' in parents and trashed = false"
        while True:
            result = service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=page_token,
                orderBy="folder,name",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            children.extend(result.get("files", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break
        return children

    @classmethod
    def _download_item(
        cls,
        service,
        file_id: str,
        metadata: dict[str, Any],
        output_path: Path,
        overwrite_existing: bool,
        export_google_files: bool,
        job_id: str,
    ) -> None:
        cls._raise_if_cancelled(job_id)
        name = cls._safe_name(metadata.get("name") or file_id)
        mime_type = metadata.get("mimeType") or ""
        if mime_type == FOLDER_MIME:
            folder_path = output_path / name
            folder_path.mkdir(parents=True, exist_ok=True)
            for child in cls._list_children(service, file_id):
                cls._raise_if_cancelled(job_id)
                cls._download_item(service, child["id"], child, folder_path, overwrite_existing, export_google_files, job_id)
            return

        try:
            target_path = output_path / name
            if mime_type.startswith(GOOGLE_MIME_PREFIX):
                if not export_google_files:
                    cls._increment_job(job_id, processed_items=1, skipped_items=1)
                    return
                export_mime, extension = EXPORT_TYPES.get(mime_type, ("application/pdf", ".pdf"))
                target_path = target_path.with_suffix(extension)
                if target_path.exists() and not overwrite_existing:
                    cls._increment_job(job_id, processed_items=1, skipped_items=1)
                    return
                request_obj = service.files().export_media(fileId=file_id, mimeType=export_mime)
            else:
                if target_path.exists() and not overwrite_existing:
                    cls._increment_job(job_id, processed_items=1, skipped_items=1)
                    return
                request_obj = service.files().get_media(fileId=file_id, supportsAllDrives=True)

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with target_path.open("wb") as fh:
                downloader = MediaIoBaseDownload(fh, request_obj, chunksize=5 * 1024 * 1024)
                done = False
                while not done:
                    cls._raise_if_cancelled(job_id)
                    _, done = downloader.next_chunk()
            cls._increment_job(job_id, processed_items=1, downloaded_items=1)
        except _DriveJobCancelled:
            raise
        except HttpError as exc:
            cls._increment_job(job_id, processed_items=1)
            detail = cls._exception_details(exc)
            cls._logger.exception("Drive file download HttpError (job_id=%s, file_id=%s, name=%s): %s", job_id, file_id, name, detail)
            cls._add_error(job_id, f"{name}: {detail}")
        except Exception as exc:
            cls._increment_job(job_id, processed_items=1)
            detail = cls._exception_details(exc)
            cls._logger.exception("Drive file download error (job_id=%s, file_id=%s, name=%s): %s", job_id, file_id, name, detail)
            cls._add_error(job_id, f"{name}: {detail}")

    @classmethod
    def _try_public_download(
        cls,
        original_link: str,
        file_id: str,
        output_path: Path,
        overwrite_existing: bool,
        export_google_files: bool,
        job_id: str,
    ) -> tuple[bool, str]:
        if "/folders/" in original_link or "drive.google.com/drive/folders" in original_link:
            return False, "Public folder listing needs Google Drive API login."

        public_url, fallback_name = cls._public_download_url(original_link, file_id, export_google_files)
        if not public_url:
            return False, "No public download URL could be created."

        try:
            cls._raise_if_cancelled(job_id)
            opener = request.build_opener(request.HTTPCookieProcessor(CookieJar()))
            response = opener.open(public_url, timeout=60)
            cls._raise_if_cancelled(job_id)
            data, headers, final_url = cls._read_google_public_response(opener, response, file_id)
            content_type = headers.get("Content-Type", "")
            disposition = headers.get("Content-Disposition", "")
            if "text/html" in content_type.lower() and "attachment" not in disposition.lower():
                return False, "The public link returned a Google web page instead of a downloadable file."

            file_name = cls._filename_from_headers(headers) or fallback_name
            target_path = output_path / cls._safe_name(file_name)
            if target_path.exists() and not overwrite_existing:
                cls._increment_job(job_id, processed_items=1, skipped_items=1)
                return True, "Skipped existing public file."

            cls._raise_if_cancelled(job_id)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(data)
            cls._increment_job(job_id, processed_items=1, downloaded_items=1)
            return True, f"Downloaded public file from {final_url}"
        except _DriveJobCancelled:
            raise
        except Exception as exc:
            detail = cls._exception_details(exc)
            cls._logger.exception("Public Drive download failed (job_id=%s, file_id=%s, url=%s): %s", job_id, file_id, public_url, detail)
            return False, detail

    @classmethod
    def _public_download_url(cls, original_link: str, file_id: str, export_google_files: bool) -> tuple[Optional[str], str]:
        lower = original_link.lower()
        if export_google_files:
            for marker, fmt, extension in PUBLIC_EXPORT_HINTS:
                if marker in lower:
                    if "presentation" in marker:
                        return f"https://docs.google.com/presentation/d/{file_id}/export/{fmt}", f"{file_id}{extension}"
                    return f"https://{marker}/d/{file_id}/export?format={fmt}", f"{file_id}{extension}"
        return f"https://drive.google.com/uc?export=download&id={parse.quote(file_id)}", f"{file_id}.download"

    @classmethod
    def _read_google_public_response(cls, opener, response, file_id: str) -> tuple[bytes, Any, str]:
        data = response.read()
        headers = response.headers
        final_url = response.geturl()
        content_type = headers.get("Content-Type", "")
        disposition = headers.get("Content-Disposition", "")
        if "text/html" not in content_type.lower() or "attachment" in disposition.lower():
            return data, headers, final_url

        text = data.decode("utf-8", errors="ignore")
        confirm_match = re.search(r"confirm=([0-9A-Za-z_\-]+)", text)
        if not confirm_match:
            href_match = re.search(r'href="([^"]*uc\?export=download[^"]*)"', text)
            if href_match:
                href = html.unescape(href_match.group(1))
                url = parse.urljoin("https://drive.google.com", href)
            else:
                return data, headers, final_url
        else:
            token = confirm_match.group(1)
            url = f"https://drive.google.com/uc?export=download&confirm={parse.quote(token)}&id={parse.quote(file_id)}"
        response2 = opener.open(url, timeout=60)
        return response2.read(), response2.headers, response2.geturl()

    @staticmethod
    def _filename_from_headers(headers: Any) -> Optional[str]:
        disposition = headers.get("Content-Disposition", "")
        if not disposition:
            return None
        utf_match = re.search(r"filename\*=UTF-8''([^;]+)", disposition, flags=re.IGNORECASE)
        if utf_match:
            return parse.unquote(utf_match.group(1).strip().strip('"'))
        match = re.search(r'filename="?([^";]+)"?', disposition, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None
