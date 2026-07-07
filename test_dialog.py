import os
import ctypes
from ctypes.wintypes import HWND, HINSTANCE, LPCWSTR, DWORD, WORD, LPWSTR

OFN_OVERWRITEPROMPT = 0x00000002
OFN_NOCHANGEDIR = 0x00000008
OFN_PATHMUSTEXIST = 0x00000800

class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", DWORD),
        ("hwndOwner", HWND),
        ("hInstance", HINSTANCE),
        ("lpstrFilter", LPCWSTR),
        ("lpstrCustomFilter", LPWSTR),
        ("nMaxCustFilter", DWORD),
        ("nFilterIndex", DWORD),
        ("lpstrFile", LPWSTR),
        ("nMaxFile", DWORD),
        ("lpstrFileTitle", LPWSTR),
        ("nMaxFileTitle", DWORD),
        ("lpstrInitialDir", LPCWSTR),
        ("lpstrTitle", LPCWSTR),
        ("Flags", DWORD),
        ("nFileOffset", WORD),
        ("nFileExtension", WORD),
        ("lpstrDefExt", LPCWSTR),
        ("lCustData", DWORD),
        ("lpfnHook", ctypes.c_void_p),
        ("lpTemplateName", LPCWSTR)
    ]

def ask_save_as_filename(suggested_name: str = "export.csv") -> str:
    MAX_PATH = 32768
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    
    filter_str = "CSV Files\0*.csv\0All Files\0*.*\0\0"
    ofn.lpstrFilter = filter_str
    ofn.nFilterIndex = 1
    
    file_buffer = ctypes.create_unicode_buffer(MAX_PATH)
    file_buffer.value = suggested_name
    ofn.lpstrFile = ctypes.cast(file_buffer, LPWSTR)
    ofn.nMaxFile = MAX_PATH
    
    ofn.lpstrTitle = "Save Query Results As..."
    ofn.lpstrDefExt = "csv"
    ofn.Flags = OFN_OVERWRITEPROMPT | OFN_NOCHANGEDIR | OFN_PATHMUSTEXIST
    
    comdlg32 = ctypes.windll.comdlg32
    if comdlg32.GetSaveFileNameW(ctypes.byref(ofn)):
        return file_buffer.value
    return None

if __name__ == "__main__":
    print("Calling GetSaveFileNameW...")
    res = ask_save_as_filename("C:\\test\\test.csv")
    print("Result:", res)
