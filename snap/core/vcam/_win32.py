"""Minimal kernel32 bindings for named shared memory, mutexes and events."""
import ctypes
from ctypes import wintypes

import numpy as np

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
PAGE_READWRITE = 0x04
FILE_MAP_WRITE = 0x0002
FILE_MAP_READ = 0x0004
FILE_MAP_ALL_ACCESS = 0x000F001F
SYNCHRONIZE = 0x00100000
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0x0
WAIT_ABANDONED = 0x80

_fn = kernel32.CreateFileMappingW
_fn.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                wintypes.LPCWSTR]
_fn.restype = wintypes.HANDLE
_fn = kernel32.OpenFileMappingW
_fn.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_fn.restype = wintypes.HANDLE
_fn = kernel32.MapViewOfFile
_fn.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
_fn.restype = wintypes.LPVOID
_fn = kernel32.UnmapViewOfFile
_fn.argtypes = [wintypes.LPCVOID]
_fn.restype = wintypes.BOOL
_fn = kernel32.CloseHandle
_fn.argtypes = [wintypes.HANDLE]
_fn.restype = wintypes.BOOL
_fn = kernel32.OpenMutexW
_fn.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_fn.restype = wintypes.HANDLE
_fn = kernel32.CreateEventW
_fn.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_fn.restype = wintypes.HANDLE
_fn = kernel32.OpenEventW
_fn.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_fn.restype = wintypes.HANDLE
_fn = kernel32.WaitForSingleObject
_fn.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_fn.restype = wintypes.DWORD
_fn = kernel32.ReleaseMutex
_fn.argtypes = [wintypes.HANDLE]
_fn.restype = wintypes.BOOL
_fn = kernel32.SetEvent
_fn.argtypes = [wintypes.HANDLE]
_fn.restype = wintypes.BOOL

_MBI_FIELDS = [("BaseAddress", wintypes.LPVOID), ("AllocationBase", wintypes.LPVOID),
               ("AllocationProtect", wintypes.DWORD), ("PartitionId", wintypes.WORD),
               ("RegionSize", ctypes.c_size_t), ("State", wintypes.DWORD),
               ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD)]


class _MBI(ctypes.Structure):
    _fields_ = _MBI_FIELDS


kernel32.VirtualQuery.argtypes = [wintypes.LPCVOID, ctypes.POINTER(_MBI), ctypes.c_size_t]
kernel32.VirtualQuery.restype = ctypes.c_size_t


def close(handle) -> None:
    if handle:
        kernel32.CloseHandle(handle)


def last_error() -> int:
    return ctypes.get_last_error()


def mapping_exists(name: str) -> bool:
    h = kernel32.OpenFileMappingW(FILE_MAP_READ, False, name)
    if h:
        kernel32.CloseHandle(h)
        return True
    return False


class SharedMemory:
    """A mapped view of a named file mapping, exposed as a numpy uint8 array."""

    def __init__(self, handle, access: int, size: int | None = None):
        self.handle = handle
        self.ptr = kernel32.MapViewOfFile(handle, access, 0, 0, 0)
        if not self.ptr:
            err = last_error()
            close(handle)
            raise OSError(err, "MapViewOfFile failed")
        if size is None:
            mbi = _MBI()
            kernel32.VirtualQuery(self.ptr, ctypes.byref(mbi), ctypes.sizeof(mbi))
            size = mbi.RegionSize
        self.size = size
        self.array = np.frombuffer((ctypes.c_uint8 * size).from_address(self.ptr), dtype=np.uint8)

    @classmethod
    def create(cls, name: str, size: int) -> "SharedMemory":
        h = kernel32.CreateFileMappingW(INVALID_HANDLE_VALUE, None, PAGE_READWRITE, 0, size, name)
        if not h:
            raise OSError(last_error(), f"CreateFileMapping({name}) failed")
        return cls(h, FILE_MAP_ALL_ACCESS, size)

    @classmethod
    def open(cls, name: str, access: int = FILE_MAP_WRITE) -> "SharedMemory | None":
        h = kernel32.OpenFileMappingW(access, False, name)
        if not h:
            return None
        return cls(h, access)

    def close(self) -> None:
        self.array = None
        if self.ptr:
            kernel32.UnmapViewOfFile(self.ptr)
            self.ptr = None
        close(self.handle)
        self.handle = None
