from fastapi import APIRouter, HTTPException, Request

from backend.models.google_drive import (
    DriveAuthStatusResponse,
    DriveDownloadRequest,
    DriveJobStartResponse,
    DriveJobStatusResponse,
    DriveUploadRequest,
)
from backend.services.google_drive_service import GoogleDriveService
from backend.utils.rate_limits import enforce_rate_limit

router = APIRouter()


@router.get(
    "/drive/auth/status",
    response_model=DriveAuthStatusResponse,
    summary="Get Google Drive login configuration status",
)
def get_drive_auth_status() -> DriveAuthStatusResponse:
    return DriveAuthStatusResponse(**GoogleDriveService.get_auth_status())


@router.post(
    "/drive/auth/login",
    response_model=DriveAuthStatusResponse,
    summary="Open Google OAuth login and cache the user token",
)
def login_drive_user(request: Request) -> DriveAuthStatusResponse:
    try:
        enforce_rate_limit(request, "drive_auth_login")
        return DriveAuthStatusResponse(**GoogleDriveService.login_google())
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {exc}") from exc


@router.post(
    "/drive/auth/logout",
    response_model=DriveAuthStatusResponse,
    summary="Revoke the cached Google OAuth token and sign out the user",
)
def logout_drive_user() -> DriveAuthStatusResponse:
    try:
        return DriveAuthStatusResponse(**GoogleDriveService.logout_google())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {exc}") from exc


@router.post(
    "/drive/upload/start",
    response_model=DriveJobStartResponse,
    summary="Start a background Google Drive folder upload job",
)
def start_drive_upload(request: Request, payload: DriveUploadRequest) -> DriveJobStartResponse:
    try:
        enforce_rate_limit(request, "drive_upload_start")
        result = GoogleDriveService.start_upload(
            auth=payload.auth,
            local_folder=payload.local_folder,
            parent_folder_id=payload.parent_folder_id,
            root_folder_name=payload.root_folder_name,
            skip_existing=payload.skip_existing,
            max_workers=payload.max_workers,
        )
        return DriveJobStartResponse(**result)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {exc}") from exc


@router.post(
    "/drive/download/start",
    response_model=DriveJobStartResponse,
    summary="Start a background Google Drive file/folder download job",
)
def start_drive_download(request: Request, payload: DriveDownloadRequest) -> DriveJobStartResponse:
    try:
        enforce_rate_limit(request, "drive_download_start")
        result = GoogleDriveService.start_download(
            auth=payload.auth,
            drive_link_or_id=payload.drive_link_or_id,
            output_folder=payload.output_folder,
            overwrite_existing=payload.overwrite_existing,
            export_google_files=payload.export_google_files,
        )
        return DriveJobStartResponse(**result)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {exc}") from exc


@router.get(
    "/drive/status/{job_id}",
    response_model=DriveJobStatusResponse,
    summary="Get current status for a Google Drive job",
)
def get_drive_job_status(job_id: str) -> DriveJobStatusResponse:
    result = GoogleDriveService.get_job_status(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Google Drive job not found.")
    return DriveJobStatusResponse(**result)


@router.post(
    "/drive/stop/{job_id}",
    response_model=DriveJobStatusResponse,
    summary="Request stop for a running Google Drive job",
)
def stop_drive_job(job_id: str) -> DriveJobStatusResponse:
    result = GoogleDriveService.stop_job(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Google Drive job not found.")
    return DriveJobStatusResponse(**result)
