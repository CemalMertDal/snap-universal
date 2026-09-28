"""Writer for the "Unity Video Capture" DirectShow device.

The device (receiver) creates a mutex, a "sent" event and a shared-memory block when an
app opens the camera; the sender opens them, creates the "want" event and writes RGBA
frames stored bottom-up behind a small header.
"""
import struct

import cv2
import numpy as np

from snap.core.vcam import _win32
from snap.core.vcam.base import VCamError

DEVICE_NAME = "Unity Video Capture"
MUTEX = "UnityCapture_Mutx"
EVENT_WANT = "UnityCapture_Want"
EVENT_SENT = "UnityCapture_Sent"
DATA = "UnityCapture_Data"
HEADER_FORMAT = "<Iiiiiiii"      # maxSize, width, height, stride, format, resizemode, mirrormode, timeout
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
FORMAT_UINT8 = 0
RESIZE_LINEAR = 1
TIMEOUT_MS = 1000


def pack_header(width: int, height: int, max_size: int = 0) -> bytes:
    return struct.pack(HEADER_FORMAT, max_size, width, height, width, FORMAT_UINT8, RESIZE_LINEAR, 0,
                       TIMEOUT_MS)


def to_rgba_bottom_up(frame_bgr: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA)[::-1])


class UnityCaptureOutput:
    name = DEVICE_NAME

    def __init__(self, width: int, height: int, fps: float):
        self.size = (width, height)
        self.mutex = self.want = self.sent = None
        self.mem = None

    def _open(self) -> bool:
        k = _win32.kernel32
        mutex = k.OpenMutexW(_win32.SYNCHRONIZE, False, MUTEX)
        if not mutex:
            return False                      # nobody is watching the camera yet
        k.WaitForSingleObject(mutex, 1000)
        try:
            want = k.CreateEventW(None, False, False, EVENT_WANT)
            sent = k.OpenEventW(_win32.EVENT_MODIFY_STATE, False, EVENT_SENT)
            mem = _win32.SharedMemory.open(DATA, _win32.FILE_MAP_WRITE) if sent else None
        finally:
            k.ReleaseMutex(mutex)
        if not (want and sent and mem):
            for h in (want, sent, mutex):
                _win32.close(h)
            return False
        self.mutex, self.want, self.sent, self.mem = mutex, want, sent, mem
        return True

    def send(self, frame_bgr: np.ndarray) -> None:
        if self.mem is None and not self._open():
            return
        rgba = to_rgba_bottom_up(frame_bgr)
        max_size = int(self.mem.array[:4].view(np.uint32)[0])
        if rgba.nbytes > max_size or HEADER_SIZE + rgba.nbytes > self.mem.size:
            raise VCamError("failed", "frame too large for Unity Capture")
        k = _win32.kernel32
        if k.WaitForSingleObject(self.mutex, 200) not in (_win32.WAIT_OBJECT_0, _win32.WAIT_ABANDONED):
            return
        try:
            buf = self.mem.array
            buf[4:HEADER_SIZE] = np.frombuffer(pack_header(*self.size)[4:], np.uint8)
            buf[HEADER_SIZE:HEADER_SIZE + rgba.nbytes] = rgba.reshape(-1)
        finally:
            k.ReleaseMutex(self.mutex)
        k.SetEvent(self.sent)

    def close(self) -> None:
        if self.mem is not None:
            self.mem.close()
            self.mem = None
        for attr in ("want", "sent", "mutex"):
            _win32.close(getattr(self, attr))
            setattr(self, attr, None)
