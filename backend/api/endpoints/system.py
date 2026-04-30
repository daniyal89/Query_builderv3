import threading
import tkinter as tk
from tkinter import filedialog
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from backend.utils.path_safety import sanitize_dialog_filename, sanitize_file_extension

router = APIRouter()
DIALOG_LOCK = threading.Lock()


class PickPathResponse(BaseModel):
    path: Optional[str] = None


class PickFileRequest(BaseModel):
    file_type: Optional[str] = None
    file_types: Optional[str] = None


class PickSavePathRequest(BaseModel):
    default_file_name: Optional[str] = None
    suggested_name: Optional[str] = None
    extension: Optional[str] = None
    default_extension: Optional[str] = None


def _build_root() -> tk.Tk:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def _pick_file_dialog(file_types: Optional[str] = None) -> Optional[str]:
    root = _build_root()

    if file_types == "duckdb":
        dialog_types = [("DuckDB Files", "*.duckdb"), ("All Files", "*.*")]
    elif file_types == "data":
        dialog_types = [
            ("Data Files", "*.csv;*.tsv;*.xlsx;*.xls;*.xlsb;*.gz;*.zip"),
            ("All Files", "*.*"),
        ]
    elif file_types == "json":
        dialog_types = [("JSON Files", "*.json"), ("All Files", "*.*")]
    else:
        dialog_types = [("All Files", "*.*")]

    path = filedialog.askopenfilename(filetypes=dialog_types)
    root.destroy()
    return path if path else None


def _pick_folder_dialog() -> Optional[str]:
    root = _build_root()
    path = filedialog.askdirectory()
    root.destroy()
    return path if path else None


def _pick_save_path_dialog(suggested_name: str = "merged_output.csv", default_extension: str = ".csv") -> Optional[str]:
    root = _build_root()
    path = filedialog.asksaveasfilename(
        initialfile=suggested_name,
        defaultextension=default_extension,
        filetypes=[
            ("CSV File", "*.csv"),
            ("Excel Workbook", "*.xlsx"),
            ("All Files", "*.*"),
        ],
    )
    root.destroy()
    return path if path else None


async def _run_pick_file(file_types: Optional[str] = None) -> PickPathResponse:
    try:
        with DIALOG_LOCK:
            path = _pick_file_dialog(file_types)
        return PickPathResponse(path=path)
    except (RuntimeError, tk.TclError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Native file picker is unavailable. Ensure GUI calls run on the main thread.",
        ) from exc


async def _run_pick_folder() -> PickPathResponse:
    try:
        with DIALOG_LOCK:
            path = _pick_folder_dialog()
        return PickPathResponse(path=path)
    except (RuntimeError, tk.TclError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Native folder picker is unavailable. Ensure GUI calls run on the main thread.",
        ) from exc


async def _run_pick_save_path(suggested_name: str, default_extension: str) -> PickPathResponse:
    try:
        with DIALOG_LOCK:
            path = _pick_save_path_dialog(suggested_name, default_extension)
        return PickPathResponse(path=path)
    except (RuntimeError, tk.TclError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Native save dialog is unavailable. Ensure GUI calls run on the main thread.",
        ) from exc


@router.get("/system/pick-file", response_model=PickPathResponse, summary="Open a native file picker dialog")
async def pick_file_get(file_types: Optional[str] = None) -> PickPathResponse:
    return await _run_pick_file(file_types)


@router.post("/system/pick-file", response_model=PickPathResponse, summary="Open a native file picker dialog")
async def pick_file_post(payload: PickFileRequest) -> PickPathResponse:
    requested_type = (payload.file_types or payload.file_type or "").strip().lower()
    file_types = requested_type if requested_type in {"duckdb", "data", "json"} else None
    return await _run_pick_file(file_types)


@router.get("/system/pick-folder", response_model=PickPathResponse, summary="Open a native folder picker dialog")
async def pick_folder_get() -> PickPathResponse:
    return await _run_pick_folder()


@router.post("/system/pick-folder", response_model=PickPathResponse, summary="Open a native folder picker dialog")
async def pick_folder_post() -> PickPathResponse:
    return await _run_pick_folder()


@router.get("/system/pick-save-path", response_model=PickPathResponse, summary="Open a native save dialog")
async def pick_save_path_get(
    suggested_name: str = "merged_output.csv",
    default_extension: str = ".csv",
) -> PickPathResponse:
    return await _run_pick_save_path(
        sanitize_dialog_filename(suggested_name, "merged_output.csv"),
        sanitize_file_extension(default_extension, ".csv", allowed_extensions={".csv", ".xlsx"}),
    )


@router.post("/system/pick-save-path", response_model=PickPathResponse, summary="Open a native save dialog")
async def pick_save_path_post(payload: PickSavePathRequest) -> PickPathResponse:
    suggested_name = sanitize_dialog_filename(
        payload.default_file_name or payload.suggested_name,
        "merged_output.csv",
    )
    default_extension = sanitize_file_extension(
        payload.extension or payload.default_extension,
        ".csv",
        allowed_extensions={".csv", ".xlsx"},
    )
    return await _run_pick_save_path(suggested_name, default_extension)
