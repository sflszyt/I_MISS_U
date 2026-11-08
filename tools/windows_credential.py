"""Read exactly one explicitly selected Generic credential, never enumerate."""
import ctypes
from ctypes import wintypes

TARGET = "I_MISS_U/father/openai"

class CREDENTIALW(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR)]


def _api():
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    return api


def read_openai_credential(target=""):
    if not target:
        return ""
    if target != TARGET:
        raise ValueError("unsupported OpenAI credential target")
    credential = ctypes.POINTER(CREDENTIALW)()
    try:
        api = _api()
        if not api.CredReadW(TARGET, 1, 0, ctypes.byref(credential)):
            raise ValueError()
        try:
            item = credential.contents
            if item.Type != 1 or not item.CredentialBlob or not 2 <= item.CredentialBlobSize <= 4096 or item.CredentialBlobSize % 2:
                raise ValueError()
            value = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize).decode("utf-16-le")
            # Generic credentials provisioned through Windows UI use UTF-16LE.
            if not value or any(ord(c) < 33 or ord(c) > 126 for c in value):
                raise ValueError()
            return value
        finally:
            api.CredFree(credential)
    except Exception:
        raise ValueError("OpenAI credential unavailable or invalid") from None
