from typing import Literal, Optional

from pydantic import BaseModel, Field


DriveAuthMode = Literal["auto", "oauth", "service_account"]
DriveJobStatus = Literal["queued", "running", "cancelling", "completed", "failed", "cancelled"]


class DriveAuthConfig(BaseModel):
    mode: DriveAuthMode = Field(
        default="auto",
        description="Auto tries public link first, then Google login. Service account remains optional.",
    )
    oauth_client_json_path: Optional[str] = Field(
        default=None,
        description="Optional override. Normal users should leave blank; the app uses config/google_oauth_client.json.",
    )
    token_json_path: Optional[str] = Field(
        default=None,
        description="Optional local token cache path for OAuth mode.",
    )
    service_account_json_path: Optional[str] = Field(
        default=None,
        description="Optional service-account JSON path. Required only for service_account mode.",
    )


class DriveUploadRequest(BaseModel):
    auth: DriveAuthConfig = Field(default_factory=DriveAuthConfig)
    local_folder: str = Field(..., description="Local folder to upload recursively.")
    parent_folder_id: str = Field(..., description="Google Drive parent folder ID.")
    root_folder_name: Optional[str] = Field(
        default=None,
        description="Optional Drive folder name. Defaults to local folder name.",
    )
    skip_existing: bool = Field(default=True, description="Skip files that already exist by name in the target folder.")
    max_workers: int = Field(default=3, ge=1, le=8, description="Parallel upload workers.")


class DriveDownloadRequest(BaseModel):
    auth: DriveAuthConfig = Field(default_factory=DriveAuthConfig)
    drive_link_or_id: str = Field(..., description="Google Drive file/folder link or raw ID.")
    output_folder: str = Field(..., description="Local folder where files will be downloaded.")
    overwrite_existing: bool = Field(default=False, description="Overwrite local files when they already exist.")
    export_google_files: bool = Field(default=True, description="Export Google Docs/Sheets/Slides while downloading.")


class DriveJobStartResponse(BaseModel):
    job_id: str
    status: DriveJobStatus


class DriveJobStatusResponse(BaseModel):
    job_id: str
    status: DriveJobStatus
    job_type: Literal["upload", "download"]
    message: str = ""
    total_items: int = Field(default=0, ge=0)
    processed_items: int = Field(default=0, ge=0)
    uploaded_items: int = Field(default=0, ge=0)
    downloaded_items: int = Field(default=0, ge=0)
    skipped_items: int = Field(default=0, ge=0)
    failed_items: int = Field(default=0, ge=0)
    output_path: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class DriveAuthStatusResponse(BaseModel):
    configured: bool = Field(default=False, description="True when the default OAuth client JSON is available.")
    token_exists: bool = Field(default=False, description="True when a cached user token exists.")
    token_valid: bool = Field(default=False, description="True when the cached token is currently valid.")
    message: str = Field(default="", description="Human-readable Google login status.")
