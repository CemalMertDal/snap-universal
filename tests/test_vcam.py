import struct
import threading
import time

import cv2
import numpy as np
import pytest

from snap.core import vcam
from snap.core.vcam import obs, unitycapture
from snap.core.vcam.base import VCamError


# ---------------------------------------------------------------- OBS layout
def test_obs_header_layout():
    header, offsets, total = obs.header_layout(1280, 720, 30)
    assert len(header) == 80
    frame = 1280 * 720 * 3 // 2
    assert offsets[0] == 96
    slot = (32 + frame + 31) & ~31
    assert offsets == (96, 96 + slot, 96 + 2 * slot)
    assert total == 96 + 3 * slot
    fields = struct.unpack("<3I3I3I4xQ8I", header)
    assert fields[:3] == (0, 0, obs.STATE_STARTING)
    assert fields[3:6] == offsets
    assert fields[6:9] == (0, 1280, 720)
    assert fields[9] == 333333
    assert struct.unpack_from("<II", header, 28) == (1280, 720)
    assert struct.unpack_from("<Q", header, 40)[0] == 333333


def test_nv12_layout_and_round_trip():
    frame = np.zeros((48, 64, 3), np.uint8)
    frame[:, :32] = (40, 200, 90)       # BGR
    frame[:, 32:] = (230, 30, 160)
    nv12 = obs.bgr_to_nv12(frame)
    assert nv12.shape == (72, 64) and nv12.dtype == np.uint8
    i420 = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
    assert np.array_equal(nv12[:48], i420[:48])
    u = i420[48:60].reshape(-1)
    assert np.array_equal(nv12[48:].reshape(-1)[0::2], u)
    back = cv2.cvtColor(nv12, cv2.COLOR_YUV2BGR_NV12)
    assert np.abs(back[4:-4, 4:28].astype(int) - (40, 200, 90)).max() <= 4
    assert np.abs(back[4:-4, 36:-4].astype(int) - (230, 30, 160)).max() <= 4


# ---------------------------------------------------------------- UnityCapture layout
def test_unitycapture_header():
    fields = struct.unpack("<Iiiiiiii", unitycapture.pack_header(640, 480, 99))
    assert fields == (99, 640, 480, 640, 0, 1, 0, 1000)


def test_unitycapture_rows_are_bottom_up_rgba():
    frame = np.zeros((4, 3, 3), np.uint8)
    frame[0] = (255, 0, 0)       # top row blue (BGR)
    frame[-1] = (0, 0, 255)      # bottom row red
    rgba = unitycapture.to_rgba_bottom_up(frame)
    assert rgba.shape == (4, 3, 4)
    assert tuple(rgba[0, 0]) == (255, 0, 0, 255)    # first stored row = bottom = red
    assert tuple(rgba[-1, 0]) == (0, 0, 255, 255)


# ---------------------------------------------------------------- selection
def test_open_output_without_drivers(monkeypatch):
    monkeypatch.setattr(vcam, "devices_registered", lambda: {"Some Webcam"})
    for backend in ("auto", "obs", "unitycapture"):
        with pytest.raises(VCamError) as e:
            vcam.open_output(backend, 640, 480, 30)
        assert e.value.code == "not_installed"


def test_odd_size_rejected():
    with pytest.raises(VCamError):
        obs.OBSOutput(641, 480, 30)


# ---------------------------------------------------------------- live
def _obs_index():
    try:
        from pygrabber.dshow_graph import FilterGraph
        names = FilterGraph().get_input_devices()
    except Exception:
        return None
    return names.index(obs.DEVICE_NAME) if obs.DEVICE_NAME in names else None


@pytest.mark.live
def test_live_obs_virtual_camera_round_trip():
    index = _obs_index()
    if index is None:
        pytest.skip("OBS Virtual Camera is not installed")
    from snap.core.vcam import _win32
    if _win32.mapping_exists(obs.MAPPING_NAME):
        pytest.skip("OBS virtual camera is in use")

    w, h = 640, 480
    pattern = np.zeros((h, w, 3), np.uint8)
    colours = {(0, 0): (255, 0, 0), (0, 1): (0, 255, 0), (1, 0): (0, 0, 255), (1, 1): (255, 255, 255)}
    for (r, c), bgr in colours.items():
        pattern[r * h // 2:(r + 1) * h // 2, c * w // 2:(c + 1) * w // 2] = bgr

    out = obs.OBSOutput(w, h, 30)
    stop = threading.Event()

    def pump():
        while not stop.is_set():
            out.send(pattern)
            time.sleep(1 / 30)

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    try:
        assert cap.isOpened()
        deadline = time.time() + 8
        ok_frame = None
        while time.time() < deadline:
            ok, frame = cap.read()
            if not ok:
                continue
            fh, fw = frame.shape[:2]
            probes = {(r, c): frame[int((r + 0.5) * fh / 2), int((c + 0.5) * fw / 2)].astype(int)
                      for r, c in colours}
            if all(np.abs(probes[k] - colours[k]).max() <= 30 for k in colours):
                ok_frame = frame
                break
        assert ok_frame is not None, f"last probes: {probes}"
    finally:
        cap.release()
        stop.set()
        t.join()
        out.close()
