import subprocess
import sys
import json
from typing import Optional

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
                print(f"Tkinter subprocess error: {data['error']}")
                return None
            return data.get("path")
        except json.JSONDecodeError:
            print(f"Failed to parse subprocess output: {result.stdout}")
            return None
            
    except Exception as e:
        print(f"Error opening dialog via subprocess: {e}")
        return None
