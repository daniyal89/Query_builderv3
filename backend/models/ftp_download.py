from typing import Literal, Optional

from pydantic import BaseModel, Field


class FTPDownloadProfile(BaseModel):
    name: str = Field(..., description="Friendly label for the FTP profile, for example KESCO.")
    username: str = Field(..., description="FTP username.")
    password: str = Field(..., description="FTP password.")
    remote_dir: str = Field(..., description="Remote FTP folder. Supports {DATE}, {MONTH}, {PROFILE}.")
    local_subfolder: Optional[str] = Field(
        default=None,
        description="Optional subfolder under the output root. Supports {DATE}, {MONTH}, {PROFILE}.",
    )


class FTPDownloadRequest(BaseModel):
    host: str = Field(..., description="FTP host name or IP address.")
    port: int = Field(default=21, ge=1, le=65535, description="FTP port.")
    output_root: str = Field(..., description="Root folder where downloaded files will be saved.")
    file_suffix: str = Field(default=".gz", description="Only files ending with this suffix will be downloaded.")
    max_workers: int = Field(default=3, ge=1, le=16, description="Parallel downloads per profile.")
    max_retries: int = Field(default=3, ge=1, le=10, description="Retry count per file.")
    retry_delay_seconds: int = Field(default=5, ge=0, le=120, description="Delay between retries.")
    timeout_seconds: int = Field(default=30, ge=5, le=600, description="FTP socket timeout.")
    passive_mode: bool = Field(default=True, description="Use FTP passive mode.")
    skip_existing: bool = Field(
        default=True,
        description="Skip local files when file size already matches the FTP file size.",
    )
    profiles: list[FTPDownloadProfile] = Field(..., min_length=1, description="One or more FTP login profiles.")


class FTPProfileResult(BaseModel):
    profile_name: str
    remote_dir: str
    local_dir: str
    found_files: int = Field(..., ge=0)
    downloaded_files: int = Field(..., ge=0)
    skipped_files: int = Field(..., ge=0)
    failed_files: int = Field(..., ge=0)
    errors: list[str] = Field(default_factory=list)


class FTPDownloadStartResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "cancelling", "completed", "failed", "cancelled"]


class FTPDownloadStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "cancelling", "completed", "failed", "cancelled"]
    host: str = ""
    output_root: str = ""
    current_profile: Optional[str] = None
    total_profiles: int = Field(default=0, ge=0)
    total_files_found: int = Field(default=0, ge=0)
    total_downloaded_files: int = Field(default=0, ge=0)
    total_skipped_files: int = Field(default=0, ge=0)
    total_failed_files: int = Field(default=0, ge=0)
    profile_results: list[FTPProfileResult] = Field(default_factory=list)
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
