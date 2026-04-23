from fastapi import APIRouter, HTTPException

from backend.models.ftp_download import FTPDownloadRequest, FTPDownloadResponse
from backend.services.ftp_download_service import FTPDownloadService

router = APIRouter()


@router.post(
    "/ftp-download",
    response_model=FTPDownloadResponse,
    summary="Download files from one or more FTP folders",
)
def ftp_download(payload: FTPDownloadRequest) -> FTPDownloadResponse:
    try:
        result = FTPDownloadService.download_files(
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
        return FTPDownloadResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {exc}") from exc
