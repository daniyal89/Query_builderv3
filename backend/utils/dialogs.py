import subprocess
import sys
import json
from typing import Optional

from backend.utils.logger import app_logger

def ask_save_as_filename(suggested_name: str = "export.csv") -> Optional[str]:
    """
    Opens a native Windows Save As dialog.
    Runs in a subprocess to avoid tkinter thread/asyncio loop conflicts.
    """
    script = f"""
import tkinter as tk
from tkinter import filedialog
import json

try:
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.asksaveasfilename(
        initialfile={repr(suggested_name)},
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
    )
    root.destroy()
    print(json.dumps({{"path": path if path else None}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    try:
        # Prevent showing a black console window when running python.exe on Windows
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            startupinfo=startupinfo
        )
        
        try:
            data = json.loads(result.stdout.strip())
            if "error" in data:
                app_logger.warning(f"Save-as dialog subprocess reported an error: {data['error']}")
                return None
            return data.get("path")
        except json.JSONDecodeError:
            app_logger.warning(f"Could not parse save-as dialog output: {result.stdout!r}")
            return None
            
    except Exception as e:
        app_logger.warning(f"Failed to open save-as dialog subprocess: {e}")
        return None
