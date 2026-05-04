from fastapi import APIRouter, HTTPException, Request
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.models.ftp_download import (
    FTPDownloadRequest,
    FTPDownloadStartResponse,
    FTPDownloadStatusResponse,
)
from backend.services.ftp_download_service import FTPDownloadService
from backend.utils.rate_limits import enforce_rate_limit

router = APIRouter()


@router.post(
    "/ftp-download/start",
    response_model=FTPDownloadStartResponse,
    summary="Start a background FTP download job",
)
def start_ftp_download(request: Request, payload: FTPDownloadRequest) -> FTPDownloadStartResponse:
    try:
        enforce_rate_limit(request, "ftp_download_start")
        result = FTPDownloadService.start_download(
            host=payload.host,
            port=payload.port,
            output_root=payload.output_root,
            file_suffix=payload.file_suffix,
            max_workers=payload.max_workers,
            max_retries=payload.max_retries,
            retry_delay_seconds=payload.retry_delay_seconds,
            timeout_seconds=payload.timeout_seconds,
            passive_mode=payload.passive_mode,
            skip_existing=payload.skip_existing,
            profiles=payload.profiles,
        )
        return FTPDownloadStartResponse(**result)
    except (HTTPException, StarletteHTTPException):
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {exc}") from exc


@router.get(
    "/ftp-download/status/{job_id}",
    response_model=FTPDownloadStatusResponse,
    summary="Get current status for an FTP download job",
)
def get_ftp_download_status(job_id: str) -> FTPDownloadStatusResponse:
    result = FTPDownloadService.get_job_status(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="FTP download job not found.")
    return FTPDownloadStatusResponse(**result)


@router.post(
    "/ftp-download/stop/{job_id}",
    response_model=FTPDownloadStatusResponse,
    summary="Request stop for a running FTP download job",
)
def stop_ftp_download(job_id: str) -> FTPDownloadStatusResponse:
    result = FTPDownloadService.stop_download(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="FTP download job not found.")
    return FTPDownloadStatusResponse(**result)
