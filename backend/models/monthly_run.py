"""Request and response models for the monthly master run."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from backend.utils.path_safety import sanitize_local_path_input

MONTH_INPUT_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")

StepName = Literal["download", "upload", "build"]
StepStatus = Literal["pending", "skipped", "running", "completed", "failed", "cancelled"]
RunOutcome = Literal["completed", "not_available_yet", "partial", "failed", "cancelled"]
#: Where the month's CSVs come from. ``drive`` is for a computer where someone
#: else has already uploaded the month: it downloads from Google Drive and has
#: nothing to upload back.
MasterSource = Literal["ftp", "drive"]


class MonthlyAutomationConfig(BaseModel):
    """Everything a monthly run needs that is not the month itself.

    Stored in ``config/monthly_automation.json`` beside the exe. Credentials are
    deliberately not here: FTP passwords live in ``ftp_profiles.json`` and the
    Google token in its own file.
    """

    ftp_host: str = Field(
        default="ftp.uppclonline.com",
        description="Used unless config/ftp_profiles.json names a host, which then wins.",
    )
    ftp_port: int = Field(default=21, ge=1, le=65535)
    ftp_remote_template: str = Field(
        default="/01-MASTER_DATA/{MON}_{YYYY}/",
        description="Remote folder per month. {MON}=JUL, {YYYY}=2026, {MM}=07, {YY}=26.",
    )
    discoms: list[str] = Field(default_factory=lambda: ["MVVNL", "DVVNL", "PVVNL", "PuVNL", "KESCO"])
    csv_root: str = Field(default="D:/DATA/MASTER", description="Each month downloads into <csv_root>/<MON>_<YYYY>.")
    parquet_root: str = Field(default="D:/DATA/MASTER_PARQUET", description="Each month converts into <parquet_root>/<MON>_<YYYY>.")
    db_path: str = Field(default="D:/uppcl_duckdb/uppcl_latest.duckdb")
    object_type: Literal["TABLE", "VIEW"] = Field(default="VIEW")
    compression: str = Field(default="snappy")
    drive_parent_folder_id: str = Field(default="")
    drive_root_name_template: str = Field(default="MASTER_DATA_{YYYY}_{MM}")
    drive_max_workers: int = Field(default=3, ge=1, le=8)
    ftp_max_workers: int = Field(default=3, ge=1, le=16)
    master_source: MasterSource = Field(
        default="ftp",
        description="Default source for this computer: 'ftp' downloads and uploads to Drive; 'drive' downloads an already-uploaded month from Drive.",
    )
    # The Drive pages carry the browser's emergency-proxy choice with every
    # job. An unattended run has no browser, so the choice lives here, per
    # computer, and is used for both the Drive download and the Drive upload.
    drive_enable_emergency_proxy: bool = Field(
        default=False,
        description="Route Google Drive traffic through the emergency proxy, as the Drive pages do when their checkbox is on.",
    )
    drive_emergency_proxy_host: Optional[str] = Field(default=None, description="Emergency proxy host; blank uses the built-in default.")
    drive_emergency_proxy_port: Optional[int] = Field(default=None, ge=1, le=65535, description="Emergency proxy port; blank uses the built-in default.")

    @field_validator("csv_root", "parquet_root", "db_path")
    @classmethod
    def validate_paths(cls, value: str) -> str:
        return sanitize_local_path_input(value, "path")

    @field_validator("discoms")
    @classmethod
    def validate_discoms(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("At least one DISCOM is required.")
        return cleaned


class MonthlyRunStartRequest(BaseModel):
    month: Optional[str] = Field(
        default=None,
        description="YYYY-MM. Defaults to the previous calendar month, which is what the 3rd-of-month drop holds.",
    )
    from_scratch: bool = Field(
        default=False,
        description="Ignore the month's progress marker and run every step again.",
    )
    source: Optional[MasterSource] = Field(
        default=None,
        description="Where to get the month from for this run. Defaults to the saved master_source.",
    )
    config_override: Optional[MonthlyAutomationConfig] = Field(
        default=None,
        description="Use these settings for this run instead of the saved config.",
    )

    @field_validator("month")
    @classmethod
    def validate_month(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        match = MONTH_INPUT_PATTERN.match(text)
        if not match or not 1 <= int(match.group(2)) <= 12:
            raise ValueError("month must look like 2026-07.")
        return text


class MonthlyRunStepState(BaseModel):
    status: StepStatus = "pending"
    message: str = ""
    job_id: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class MonthlyRunStartResponse(BaseModel):
    job_id: str
    status: str
    message: str
    month: str
    object_name: str


class MonthlyRunStatusResponse(BaseModel):
    job_id: str
    status: str
    message: str = ""
    month: str = ""
    object_name: str = ""
    outcome: Optional[RunOutcome] = None
    source: MasterSource = "ftp"
    current_step: Optional[str] = None
    steps: dict[str, MonthlyRunStepState] = Field(default_factory=dict)
    resumed_steps: list[str] = Field(default_factory=list)
    missing_discoms: list[str] = Field(default_factory=list)
    paths: dict[str, str] = Field(default_factory=dict)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class MonthlyRunMarkerResponse(BaseModel):
    """What a past run recorded for a month, if anything."""

    month: str
    exists: bool
    steps: dict[str, MonthlyRunStepState] = Field(default_factory=dict)
    last_job_id: Optional[str] = None
    updated_at: Optional[str] = None
