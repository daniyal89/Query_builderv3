import asyncio
import tkinter as tk
from tkinter import filedialog
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class PickPathResponse(BaseModel):
    path: Optional[str] = None


def _build_root() -> tk.Tk:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def _pick_file_dialog(file_types: Optional[str] = None) -> Optional[str]:
    root = _build_root()

    if file_types == "duckdb":
        filetypes = [("DuckDB Files", "*.duckdb"), ("All Files", "*.*")]
    elif file_types == "data":
        filetypes = [
            ("Data Files", "*.csv;*.tsv;*.xlsx;*.xls;*.xlsb;*.gz;*.zip"),
            ("All Files", "*.*"),
        ]
    else:
        filetypes = [("All Files", "*.*")]

    path = filedialog.askopenfilename(filetypes=filetypes)
    root.destroy()
    return path if path else None


def _pick_folder_dialog() -> Optional[str]:
    root = _build_root()
    path = filedialog.askdirectory()
    root.destroy()
    return path if path else None


def _pick_save_path_dialog(
    suggested_name: str = "merged_output.csv",
    default_extension: str = ".csv",
) -> Optional[str]:
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


@router.get("/system/pick-file", response_model=PickPathResponse, summary="Open a native file picker dialog")
async def pick_file(file_types: Optional[str] = None) -> PickPathResponse:
    path = await asyncio.to_thread(_pick_file_dialog, file_types)
    return PickPathResponse(path=path)


@router.get("/system/pick-folder", response_model=PickPathResponse, summary="Open a native folder picker dialog")
async def pick_folder() -> PickPathResponse:
    path = await asyncio.to_thread(_pick_folder_dialog)
    return PickPathResponse(path=path)


@router.get("/system/pick-save-path", response_model=PickPathResponse, summary="Open a native save dialog")
async def pick_save_path(
    suggested_name: str = "merged_output.csv",
    default_extension: str = ".csv",
) -> PickPathResponse:
    path = await asyncio.to_thread(
        _pick_save_path_dialog,
        suggested_name,
        default_extension,
    )
    return PickPathResponse(path=path)
