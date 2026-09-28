"""Builds the real window offscreen with fake devices; catches wiring/API mistakes."""
import contextlib
import io

import numpy as np
import pytest

with contextlib.redirect_stdout(io.StringIO()):
    import qfluentwidgets  # noqa: F401
from PySide6.QtWidgets import QApplication

from snap.core import devices
from snap.core.settings import Settings
from snap.core.engine import Status


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch):
    from snap.ui import main_window
    monkeypatch.setattr(devices, "list_cameras", lambda: [(0, "Cam A"), (1, "Cam B")])
    monkeypatch.setattr(devices, "list_mics", lambda: [(3, "Mic X"), (4, "Mic Y")])
    monkeypatch.setattr(devices, "default_mic", lambda: 4)
    monkeypatch.setattr(main_window.MainWindow, "_setup_hotkeys", lambda self: setattr(self, "_hotkeys", []))
    w = main_window.MainWindow(Settings())
    yield w
    w._quitting = True
    w._shutdown()
    w.deleteLater()


def test_window_builds_and_pages_switch(window):
    for page in (window.home, window.effects_page, window.settings_page):
        window.switchTo(page)
        assert window.stackedWidget.currentWidget() is page


def test_devices_fill_settings(window):
    assert window.settings.camera == "Cam A"
    assert window.settings.microphone == "Mic Y"          # system default when nothing saved
    assert window.settings_page.camera.combo.count() == 2


def test_effect_card_click_updates_settings(window):
    window.effects_page.cards["dust"].clicked.emit()
    assert window.settings.effect == "dust"
    assert window.effects_page.cards["dust"].selected
    assert not window.effects_page.cards["cloud"].selected


def test_status_updates_render(window):
    st = Status(running=True, mode="live", has_plate=False, countdown=2, capturing=True, fps=29.7,
                vcam_name="OBS Virtual Camera", effect="cloud", mic_ok=True, mic_level=0.8)
    window._set_running(True)
    window._on_status(st)
    window.home.preview.set_frame(np.zeros((90, 160, 3), np.uint8))
    window.home.meter.set_level(0.5)
    window.home.grab()
    window.effects_page.grab()
    window.settings_page.grab()
    assert "2" in window.home.preview._overlay


def test_settings_change_is_saved(window, tmp_path):
    window.settings_page.sensitivity.slider.setValue(16)     # 8.0
    assert window.settings.sensitivity == 8.0
    assert Settings.load().sensitivity == 8.0
