"""Writer for the "OBS Virtual Camera" DirectShow device.

The device reads frames from a named shared-memory ring of three NV12 frames. Layout
(little-endian): a 80-byte header, padded to 32 bytes, followed by three slots, each a
32-byte frame header (u64 timestamp first) plus the NV12 image, each slot padded to 32.
"""
import struct
import time

import cv2
import numpy as np

from snap.core.vcam import _win32
from snap.core.vcam.base import VCamError

MAPPING_NAME = "OBSVirtualCamVideo"
DEVICE_NAME = "OBS Virtual Camera"
HEADER_FORMAT = "<3I3I3I4xQ8I"   # write_idx, read_idx, state, offsets[3], type, cx, cy, interval, reserved
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
FRAME_HEADER = 32
STATE_STARTING, STATE_READY, STATE_STOPPING = 1, 2, 3


def _align32(n: int) -> int:
    return (n + 31) & ~31


def header_layout(width: int, height: int, fps: float):
    """-> (header bytes, slot offsets, total mapping size)"""
    frame = width * height * 3 // 2
    offsets = []
    pos = _align32(HEADER_SIZE)
    for _ in range(3):
        offsets.append(pos)
        pos = _align32(pos + FRAME_HEADER + frame)
    interval = int(round(10_000_000 / fps))
    header = struct.pack(HEADER_FORMAT, 0, 0, STATE_STARTING, *offsets, 0, width, height, interval,
                         *([0] * 8))
    return header, tuple(offsets), pos


def bgr_to_nv12(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    i420 = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
    out = np.empty((h * 3 // 2, w), np.uint8)
    out[:h] = i420[:h]
    quarter = (h // 2) * (w // 2)
    chroma = i420[h:].reshape(-1)
    uv = out[h:].reshape(-1)
    uv[0::2] = chroma[:quarter]
    uv[1::2] = chroma[quarter:]
    return out


class OBSOutput:
    name = DEVICE_NAME

    def __init__(self, width: int, height: int, fps: float):
        if width % 2 or height % 2:
            raise VCamError("failed", "width and height must be even")
        if _win32.mapping_exists(MAPPING_NAME):
            raise VCamError("in_use", "OBS virtual camera is already in use")
        header, self.offsets, total = header_layout(width, height, fps)
        try:
            self.mem = _win32.SharedMemory.create(MAPPING_NAME, total)
        except OSError as e:
            raise VCamError("failed", str(e)) from e
        self.mem.array[:len(header)] = np.frombuffer(header, np.uint8)
        self.idx = self.mem.array[:12].view(np.uint32)   # write_idx, read_idx, state
        self.size = (width, height)
        self.frame_bytes = width * height * 3 // 2

    def send(self, frame_bgr: np.ndarray) -> None:
        if self.mem is None:
            return
        nv12 = bgr_to_nv12(frame_bgr)
        inc = (int(self.idx[0]) + 1) & 0xFFFFFFFF
        self.idx[0] = inc
        off = self.offsets[inc % 3]
        buf = self.mem.array
        buf[off:off + 8].view(np.uint64)[0] = time.perf_counter_ns() // 100
        start = off + FRAME_HEADER
        buf[start:start + self.frame_bytes] = nv12.reshape(-1)
        self.idx[1] = inc
        self.idx[2] = STATE_READY

    def close(self) -> None:
        if self.mem is None:
            return
        self.idx[2] = STATE_STOPPING
        self.idx = None
        self.mem.close()
        self.mem = None
