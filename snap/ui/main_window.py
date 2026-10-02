import threading
import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from qfluentwidgets import (Action, FluentIcon, FluentWindow, InfoBar, InfoBarPosition,
                            NavigationItemPosition, SystemTrayMenu, Theme, setTheme)

from snap import effects
from snap.core import devices
from snap.core.engine import Engine, EngineConfig
from snap.core.settings import Settings
from snap.core.sources import CameraError, CameraSource
from snap.core.vcam import VCamError, open_output
from snap.i18n import t
from snap.paths import resource_path, user_data_dir
from snap.ui.bridge import EngineBridge
from snap.ui.effects_page import EffectsPage
from snap.ui.home_page import HomePage
from snap.ui.settings_page import SettingsPage

THEMES = {"auto": Theme.AUTO, "light": Theme.LIGHT, "dark": Theme.DARK}


def apply_theme(name: str) -> None:
    setTheme(THEMES.get(name, Theme.AUTO))


class _Starter(QObject):
    done = Signal(object)     # None on success, else the exception


class MainWindow(FluentWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self._quitting = False
        self._tray_hint_shown = False
        self._starting = False

        self.bridge = EngineBridge(self)
        self.engine = Engine(on_frame=self.bridge.on_frame, on_status=self.bridge.on_status,
                             on_log=self.bridge.on_log)

        self.home = HomePage(self)
        self.effects_page = EffectsPage(settings.effect, settings.duration, self)
        self.settings_page = SettingsPage(settings, self)
        self.addSubInterface(self.home, FluentIcon.VIDEO, t("nav.home"))
        self.addSubInterface(self.effects_page, FluentIcon.PALETTE, t("nav.effects"))
        self.addSubInterface(self.settings_page, FluentIcon.SETTING, t("nav.settings"),
                             NavigationItemPosition.BOTTOM)

        icon_path = resource_path("assets", "icon.png")
        self.app_icon = QIcon(str(icon_path)) if icon_path.exists() else self.windowIcon()
        self.setWindowIcon(self.app_icon)
        self.setWindowTitle("Snap")
        self.resize(1120, 780)
        self.setMinimumSize(900, 640)
        self._center()

        self._starter = _Starter(self)
        self._starter.done.connect(self._on_started)
        self.bridge.frame.connect(self._on_frame)
        self.bridge.status.connect(self._on_status)
        self.bridge.log.connect(self._on_log)
        self.home.start_clicked.connect(self._start_stop)
        self.home.capture_clicked.connect(self.engine.capture_plate)
        self.home.toggle_clicked.connect(self.engine.toggle)
        self.effects_page.effect_selected.connect(self._on_effect)
        self.effects_page.duration_changed.connect(self._on_duration)
        self.effects_page.try_clicked.connect(self.engine.try_effect)
        self.settings_page.changed.connect(self._on_setting)
        self.settings_page.refresh_devices.connect(self.refresh_devices)

        self._update_effect_label()
        self.refresh_devices()
        self._setup_tray()
        self._setup_hotkeys()

    # ------------------------------------------------------------ setup
    def _center(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.center().x() - self.width() // 2, geo.center().y() - self.height() // 2)

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.app_icon, self)
        self.tray.setToolTip("Snap")
        menu = SystemTrayMenu(parent=self)
        menu.addActions([
            Action(FluentIcon.VIEW, t("tray.show"), triggered=self.show_window),
            Action(FluentIcon.HIDE, t("tray.toggle"), triggered=self.engine.toggle),
        ])
        menu.addSeparator()
        menu.addAction(Action(FluentIcon.CLOSE, t("tray.quit"), triggered=self.quit))
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray)
        self.tray.show()

    def _setup_hotkeys(self) -> None:
        self._hotkeys = []
        try:
            import keyboard
            self._hotkeys.append(keyboard.add_hotkey("ctrl+shift+x", self.engine.toggle))
            self._hotkeys.append(keyboard.add_hotkey("ctrl+shift+c", self.engine.capture_plate))
        except Exception as e:
            self._info("warning", t("log.hotkeys_failed", error=e))

    def _remove_hotkeys(self) -> None:
        try:
            import keyboard
            for h in self._hotkeys:
                keyboard.remove_hotkey(h)
        except Exception:
            pass
        self._hotkeys = []

    # ------------------------------------------------------------ devices
    def refresh_devices(self) -> None:
        self.cameras = devices.list_cameras()
        self.mics = devices.list_mics()
        if self.settings.microphone not in [n for _, n in self.mics]:
            default = devices.default_mic()
            self.settings.microphone = next((n for i, n in self.mics if i == default), self.settings.microphone)
        self.settings_page.set_devices(self.cameras, self.mics)

    def _camera_index(self):
        return next((i for i, n in self.cameras if n == self.settings.camera), None)

    def _mic_index(self):
        return next((i for i, n in self.mics if n == self.settings.microphone), None)

    # ------------------------------------------------------------ start / stop
    def _start_stop(self) -> None:
        if self.engine.running:
            self.engine.stop()
            self._set_running(False)
            return
        if self._starting:
            return
        cam = self._camera_index()
        if cam is None:
            self._info("error", t("err.no_camera"), t("err.title"))
            return
        s = self.settings
        w, h = s.size
        from snap.core.segmenter import PersonSegmenter
        from snap.core.snap_detector import MicListener
        cfg = EngineConfig(
            source_factory=lambda: CameraSource(cam, w, h, 30),
            output_factory=lambda ow, oh, fps: open_output(s.backend, ow, oh, fps),
            segmenter_factory=PersonSegmenter,
            mic_factory=lambda dev, sens, cb: MicListener(dev, sens, cb),
            mic_device=self._mic_index(), sensitivity=s.sensitivity, snap_enabled=s.snap_enabled,
            effect=s.effect, duration=s.duration, fps=30, preview=s.preview)
        self._starting = True
        self.home.set_running(False, busy=True)

        def work():
            try:
                self.engine.start(cfg)
                self._starter.done.emit(None)
            except Exception as e:
                self._starter.done.emit(e)
        threading.Thread(target=work, daemon=True).start()

    def _on_started(self, error) -> None:
        self._starting = False
        if error is None:
            self._set_running(True)
            return
        self._set_running(False)
        if isinstance(error, CameraError):
            msg = t("err.camera")
        elif isinstance(error, VCamError):
            msg = {"not_installed": t("err.vcam_not_installed"),
                   "in_use": t("err.vcam_in_use")}.get(error.code, t("err.vcam_failed", error=error))
        elif "model" in str(error).lower() or "mediapipe" in type(error).__module__:
            msg = t("err.model", error=error)
        else:
            msg = t("err.vcam_failed", error=error)
        self._write_log(f"start failed: {error!r}")
        self._info("error", msg, t("err.title"), duration=10000)

    def _set_running(self, running: bool) -> None:
        self.home.set_running(running)
        self.settings_page.set_running(running)
        if not running:
            self.effects_page.set_can_try(False)
        self.tray.setToolTip(f"Snap · {t('status.live') if running else t('status.stopped')}")

    # ------------------------------------------------------------ engine events
    def _on_frame(self, image) -> None:
        if self.settings.preview:
            self.home.preview.set_frame(image)

    def _on_status(self, st) -> None:
        if not st.running:
            if not self._starting:
                self._set_running(False)
            return
        self.home.update_status(st)
        self.effects_page.set_can_try(st.has_plate and st.mode == "live")
        if st.mode in ("vanishing", "gone", "appearing"):
            self.home.set_effect_name(t(f"effect.{st.effect}.name"))
        else:
            self._update_effect_label()

    def _on_log(self, key: str, kw: dict) -> None:
        self._write_log(f"{key} {kw.get('error', '')}")
        levels = {"log.plate_ok": "success", "log.need_plate": "warning",
                  "log.mic_failed": "warning", "log.engine_error": "error", "log.busy": "info"}
        if key in levels:
            self._info(levels[key], t(key, **kw))
        if key == "log.engine_error":
            self._set_running(False)

    def _info(self, level: str, content: str, title: str = "", duration: int = 3500) -> None:
        make = {"success": InfoBar.success, "warning": InfoBar.warning, "error": InfoBar.error,
                "info": InfoBar.info}[level]
        make(title, content, orient=Qt.Orientation.Horizontal, isClosable=True,
             position=InfoBarPosition.TOP, duration=duration, parent=self)

    def _write_log(self, line: str) -> None:
        try:
            with open(user_data_dir() / "snap.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")
        except OSError:
            pass

    # ------------------------------------------------------------ settings
    def _update_effect_label(self) -> None:
        self.home.set_effect_name(t(f"effect.{self.settings.effect}.name"))

    def _on_effect(self, eid: str) -> None:
        self.settings.effect = eid
        self.settings.save()
        self.engine.set_effect(eid)
        self._update_effect_label()

    def _on_duration(self, seconds: float) -> None:
        self.settings.duration = seconds
        self.settings.save()
        self.engine.set_duration(seconds)

    def _on_setting(self, key: str) -> None:
        s = self.settings
        if key == "microphone" and self.engine.running:
            self.engine.set_mic(self._mic_index())
        elif key == "snap_enabled":
            self.engine.set_snap_enabled(s.snap_enabled)
        elif key == "sensitivity":
            self.engine.set_sensitivity(s.sensitivity)
        elif key == "preview":
            self.engine.set_preview(s.preview)
            if not s.preview:
                self.home.preview.clear()
        elif key == "theme":
            apply_theme(s.theme)
        elif key == "language":
            self._info("info", t("settings.restart"))

    # ------------------------------------------------------------ window / tray
    def _on_tray(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        if not self._quitting and self.settings.close_to_tray and self.engine.running:
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.showMessage("Snap", t("tray.still_running"), self.app_icon, 3000)
            return
        self._shutdown()
        event.accept()
        QTimer.singleShot(0, QApplication.instance().quit)

    def quit(self) -> None:
        self._quitting = True
        self.close()

    def _shutdown(self) -> None:
        self._remove_hotkeys()
        self.engine.stop()
        self.settings.save()
        self.tray.hide()
