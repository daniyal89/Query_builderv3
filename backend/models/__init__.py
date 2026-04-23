"""models — Pydantic request/response schemas for all API endpoints."""

from backend.models.connection import ConnectionRequest, ConnectionResponse
from backend.models.schema import TableMetadata, ColumnDetail, MasterTable
from backend.models.query import QueryPayload, QueryResult, FilterCondition
from backend.models.importer import CSVMappingPayload, ImportResult

from backend.models.ftp_download import (
    FTPDownloadProfile,
    FTPDownloadRequest,
    FTPDownloadResponse,
    FTPProfileResult,
)

from backend.models.merge import (
    ConflictResolutionMap,
    ColumnResolution,
    DetectedColumn,
    EnrichmentRequest,
    EnrichmentResponse,
    MergeSheetsResponse,
    UploadSheetsResponse,
)

__all__ = [
    "ConnectionRequest",
    "ConnectionResponse",
    "TableMetadata",
    "ColumnDetail",
    "MasterTable",
    "QueryPayload",
    "QueryResult",
    "FilterCondition",
    "CSVMappingPayload",
    "ImportResult",
    "FTPDownloadProfile",
    "FTPDownloadRequest",
    "FTPDownloadResponse",
    "FTPProfileResult",
    "ConflictResolutionMap",
    "ColumnResolution",
    "DetectedColumn",
    "EnrichmentRequest",
    "EnrichmentResponse",
    "MergeSheetsResponse",
    "UploadSheetsResponse",
]
