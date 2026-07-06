import threading
import tkinter as tk
from tkinter import filedialog
from typing import Optional

def _pick_save_file(suggested_name: str, default_ext: str, file_types: list[tuple[str, str]], result: dict[str, Optional[str]]) -> None:
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.asksaveasfilename(
            initialfile=suggested_name,
            defaultextension=default_ext,
            filetypes=file_types
        )
        result["path"] = path if path else None
    except Exception as e:
        print(f"Error in tkinter dialog: {e}")
        result["path"] = None
    finally:
        try:
            root.destroy()
        except:
            pass

def ask_save_as_filename(suggested_name: str = "export.csv") -> Optional[str]:
    """
    Opens a native Windows Save As dialog.
    Must be run in a separate thread if called from an async event loop
    to avoid freezing the loop or encountering threading issues.
    """
    result: dict[str, Optional[str]] = {"path": None}
    
    # Run in a separate thread to ensure it has its own main loop
    t = threading.Thread(
        target=_pick_save_file,
        args=(suggested_name, ".csv", [("CSV files", "*.csv"), ("All files", "*.*")], result)
    )
    t.start()
    t.join()
    
    return result["path"]
