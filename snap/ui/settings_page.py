from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, ComboBox, ExpandLayout, FluentIcon, HyperlinkCard, PushButton,
                            ScrollArea, SettingCard, SettingCardGroup, Slider, SwitchButton, TitleLabel)

from snap import REPO_URL, __version__
from snap.core.settings import BACKENDS, RESOLUTIONS, THEMES, Settings
from snap.i18n import t
from snap.ui.widgets import fixed_height


class ComboCard(SettingCard):
    changed = Signal(object)

    def __init__(self, icon, title, content, parent=None):
        super().__init__(icon, title, content, parent)
        self.combo = ComboBox(self)
        self.combo.setMinimumWidth(260)
        self.hBoxLayout.addWidget(self.combo, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.combo.currentIndexChanged.connect(self._emit)
        self._values = []

    def set_options(self, options, current) -> None:
        """options: list of (value, label)."""
        self.combo.blockSignals(True)
        self.combo.clear()
        self._values = [v for v, _ in options]
        for _, label in options:
            self.combo.addItem(label)
        if current in self._values:
            self.combo.setCurrentIndex(self._values.index(current))
        elif self._values:
            self.combo.setCurrentIndex(0)
        self.combo.blockSignals(False)

    def value(self):
        i = self.combo.currentIndex()
        return self._values[i] if 0 <= i < len(self._values) else None

    def _emit(self, _index) -> None:
        self.changed.emit(self.value())


class SwitchCard(SettingCard):
    changed = Signal(bool)

    def __init__(self, icon, title, content, checked, parent=None):
        super().__init__(icon, title, content, parent)
        self.switch = SwitchButton(self)
        self.switch.setOnText(" ")
        self.switch.setOffText(" ")
        self.switch.setChecked(checked)
        self.hBoxLayout.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.switch.checkedChanged.connect(self.changed)


class SliderCard(SettingCard):
    changed = Signal(float)

    def __init__(self, icon, title, content, lo, hi, step, value, parent=None):
        super().__init__(icon, title, content, parent)
        self.step = step
        self.slider = Slider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(int(round(lo / step)), int(round(hi / step)))
        self.slider.setFixedWidth(220)
        self.slider.setValue(int(round(value / step)))
        self.label = BodyLabel("", self)
        self.label.setMinimumWidth(32)
        self.hBoxLayout.addWidget(self.label, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(10)
        self.hBoxLayout.addWidget(self.slider, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.slider.valueChanged.connect(self._on)
        self._on(self.slider.value(), emit=False)

    def _on(self, v, emit=True) -> None:
        value = v * self.step
        self.label.setText(f"{value:g}")
        if emit:
            self.changed.emit(value)


class InfoCard(SettingCard):
    def __init__(self, icon, title, content, value, parent=None):
        super().__init__(icon, title, content, parent)
        self.hBoxLayout.addWidget(BodyLabel(value, self), 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)


class SettingsPage(ScrollArea):
    """Emits changed(key) after it has updated and saved the Settings object."""
    changed = Signal(str)
    refresh_devices = Signal()

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setObjectName("settings")
        self.view = QWidget(self)
        self.view.setObjectName("settingsView")
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.enableTransparentBackground()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        outer = QVBoxLayout(self.view)
        outer.setContentsMargins(36, 20, 36, 28)
        outer.setSpacing(12)
        outer.addWidget(fixed_height(TitleLabel(t("settings.title"), self.view)))
        body = QWidget(self.view)
        self.layout_ = ExpandLayout(body)
        self.layout_.setSpacing(24)
        self.layout_.setContentsMargins(0, 8, 0, 0)
        outer.addWidget(body)
        outer.addStretch(1)

        s = settings
        # devices
        g = SettingCardGroup(t("settings.devices"), body)
        self.camera = ComboCard(FluentIcon.CAMERA, t("settings.camera"), t("settings.camera_desc"), g)
        self.mic = ComboCard(FluentIcon.MICROPHONE, t("settings.microphone"), t("settings.microphone_desc"), g)
        self.resolution = ComboCard(FluentIcon.ZOOM, t("settings.resolution"), t("settings.resolution_desc"), g)
        self.resolution.set_options([(r, r.replace("x", " × ")) for r in RESOLUTIONS], s.resolution)
        self.backend = ComboCard(FluentIcon.VIDEO, t("settings.backend"), t("settings.backend_desc"), g)
        self.backend.set_options([(b, t(f"backend.{b}")) for b in BACKENDS], s.backend)
        refresh = SettingCard(FluentIcon.SYNC, t("settings.refresh"), None, g)
        refresh_btn = PushButton(refresh)
        refresh_btn.setIcon(FluentIcon.SYNC)
        refresh_btn.setText(t("settings.refresh"))
        refresh.hBoxLayout.addWidget(refresh_btn, 0, Qt.AlignmentFlag.AlignRight)
        refresh.hBoxLayout.addSpacing(16)
        for c in (self.camera, self.mic, self.resolution, self.backend, refresh):
            g.addSettingCard(c)
        self.layout_.addWidget(g)

        # snap
        g = SettingCardGroup(t("settings.snap"), body)
        self.snap_enabled = SwitchCard(FluentIcon.MEGAPHONE, t("settings.snap_enabled"),
                                       t("settings.snap_enabled_desc"), s.snap_enabled, g)
        self.sensitivity = SliderCard(FluentIcon.SPEED_HIGH, t("settings.sensitivity"),
                                      t("settings.sensitivity_desc"), 1, 10, 0.5, s.sensitivity, g)
        g.addSettingCard(self.snap_enabled)
        g.addSettingCard(self.sensitivity)
        self.layout_.addWidget(g)

        # hotkeys
        g = SettingCardGroup(t("settings.hotkeys"), body)
        g.addSettingCard(InfoCard(FluentIcon.HIDE, t("settings.hotkey_toggle"), t("settings.hotkeys_desc"),
                                  "Ctrl + Shift + X", g))
        g.addSettingCard(InfoCard(FluentIcon.CAMERA, t("settings.hotkey_capture"), t("settings.hotkeys_desc"),
                                  "Ctrl + Shift + C", g))
        self.layout_.addWidget(g)

        # appearance
        g = SettingCardGroup(t("settings.appearance"), body)
        self.theme = ComboCard(FluentIcon.BRUSH, t("settings.theme"), t("settings.theme_desc"), g)
        self.theme.set_options([(v, t(f"theme.{v}")) for v in THEMES], s.theme)
        self.language = ComboCard(FluentIcon.LANGUAGE, t("settings.language"), t("settings.language_desc"), g)
        self.language.set_options([("", t("lang.auto")), ("tr", t("lang.tr")), ("en", t("lang.en"))], s.language)
        g.addSettingCard(self.theme)
        g.addSettingCard(self.language)
        self.layout_.addWidget(g)

        # behaviour
        g = SettingCardGroup(t("settings.behaviour"), body)
        self.close_to_tray = SwitchCard(FluentIcon.MINIMIZE, t("settings.close_to_tray"),
                                        t("settings.close_to_tray_desc"), s.close_to_tray, g)
        self.preview = SwitchCard(FluentIcon.VIEW, t("settings.preview"), t("settings.preview_desc"),
                                  s.preview, g)
        g.addSettingCard(self.close_to_tray)
        g.addSettingCard(self.preview)
        self.layout_.addWidget(g)

        # about
        g = SettingCardGroup(t("settings.about"), body)
        g.addSettingCard(HyperlinkCard(REPO_URL, t("settings.github"), FluentIcon.GITHUB, "Snap",
                                       t("settings.about_desc", version=__version__), g))
        self.layout_.addWidget(g)

        self._bind(self.camera, "camera")
        self._bind(self.mic, "microphone")
        self._bind(self.resolution, "resolution")
        self._bind(self.backend, "backend")
        self._bind(self.snap_enabled, "snap_enabled")
        self._bind(self.sensitivity, "sensitivity")
        self._bind(self.theme, "theme")
        self._bind(self.language, "language")
        self._bind(self.close_to_tray, "close_to_tray")
        self._bind(self.preview, "preview")
        refresh_btn.clicked.connect(self.refresh_devices)

    def _bind(self, card, key: str) -> None:
        def apply(value):
            if value is None:
                return
            setattr(self.settings, key, value)
            self.settings.save()
            self.changed.emit(key)
        card.changed.connect(apply)

    def set_devices(self, cameras: list[tuple[int, str]], mics: list[tuple[int, str]]) -> None:
        cam_opts = [(n, n) for _, n in cameras] or [("", t("settings.no_camera"))]
        mic_opts = [(n, n) for _, n in mics] or [("", t("settings.no_mic"))]
        self.camera.set_options(cam_opts, self.settings.camera)
        self.mic.set_options(mic_opts, self.settings.microphone)
        # remember what is actually selected when the saved device is gone
        for card, key in ((self.camera, "camera"), (self.mic, "microphone")):
            if card.value() is not None and card.value() != getattr(self.settings, key):
                setattr(self.settings, key, card.value())
        self.settings.save()

    def set_running(self, running: bool) -> None:
        for card in (self.camera, self.resolution, self.backend):
            card.combo.setEnabled(not running)
            card.setToolTip(t("settings.locked") if running else "")
