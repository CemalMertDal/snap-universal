from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon, PrimaryPushButton, PushButton,
                            SimpleCardWidget, StrongBodyLabel, SubtitleLabel, TitleLabel)

from snap.i18n import t
from snap.ui.widgets import LevelMeter, PreviewView, StatusDot, muted


class HomePage(QWidget):
    start_clicked = Signal()
    capture_clicked = Signal()
    toggle_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("home")
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 20, 36, 28)
        root.setSpacing(12)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(TitleLabel(t("home.title"), self))
        sub = CaptionLabel(t("home.subtitle"), self)
        muted(sub)
        titles.addWidget(sub)
        head.addLayout(titles)
        head.addStretch(1)
        self.dot = StatusDot(self)
        self.status_label = StrongBodyLabel(t("status.stopped"), self)
        head.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addSpacing(6)
        head.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(head)

        self.preview = PreviewView(self)
        root.addWidget(self.preview, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.start_btn = PrimaryPushButton(self)
        self.start_btn.setMinimumWidth(130)
        self.capture_btn = PushButton(self)
        self.capture_btn.setIcon(FluentIcon.CAMERA)
        self.capture_btn.setText(t("home.capture"))
        self.toggle_btn = PushButton(self)
        self.toggle_btn.setIcon(FluentIcon.HIDE)
        self.toggle_btn.setText(t("home.toggle"))
        for b in (self.start_btn, self.capture_btn, self.toggle_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        self.steps = CaptionLabel(t("home.steps"), self)
        muted(self.steps)
        buttons.addWidget(self.steps)
        root.addLayout(buttons)

        card = SimpleCardWidget(self)
        cl = QHBoxLayout(card)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setSpacing(16)
        mic_col = QVBoxLayout()
        mic_col.setSpacing(6)
        mic_head = QHBoxLayout()
        mic_head.addWidget(StrongBodyLabel(t("home.mic_level"), card))
        mic_head.addStretch(1)
        self.mic_hint = CaptionLabel(t("home.mic_hint"), card)
        muted(self.mic_hint)
        mic_head.addWidget(self.mic_hint)
        mic_col.addLayout(mic_head)
        self.meter = LevelMeter(card)
        mic_col.addWidget(self.meter)
        cl.addLayout(mic_col, 3)
        info = QVBoxLayout()
        info.setSpacing(4)
        self.effect_label = BodyLabel("", card)
        self.output_label = CaptionLabel("", card)
        muted(self.output_label)
        info.addWidget(self.effect_label)
        info.addWidget(self.output_label)
        cl.addLayout(info, 2)
        root.addWidget(card)

        self.start_btn.clicked.connect(self.start_clicked)
        self.capture_btn.clicked.connect(self.capture_clicked)
        self.toggle_btn.clicked.connect(self.toggle_clicked)
        self.set_running(False)

    # ------------------------------------------------------------ updates
    def set_running(self, running: bool, busy: bool = False) -> None:
        self.start_btn.setText(t("home.stop") if running else t("home.start"))
        self.start_btn.setIcon(FluentIcon.PAUSE if running else FluentIcon.PLAY)
        self.start_btn.setEnabled(not busy)
        self.capture_btn.setEnabled(running)
        self.toggle_btn.setEnabled(running)
        if not running:
            self.preview.clear()
            self.preview.set_overlay("")
            self.meter.set_level(0)
            self.dot.set_state("stopped")
            self.status_label.setText(t("status.stopped"))
            self.output_label.setText("")

    def set_effect_name(self, name: str) -> None:
        self.effect_label.setText(t("home.effect", name=name))

    def update_status(self, st) -> None:
        if not st.running:
            return
        if st.countdown:
            self.preview.set_overlay(t("home.countdown", n=st.countdown))
        elif st.capturing:
            self.preview.set_overlay(t("home.capturing"))
        else:
            self.preview.set_overlay("")
        if st.mode == "live" and not st.has_plate:
            self.dot.set_state("warning")
            self.status_label.setText(t("status.no_plate"))
        else:
            self.dot.set_state(st.mode)
            self.status_label.setText(t(f"status.{st.mode}"))
        self.steps.setVisible(not st.has_plate)
        self.capture_btn.setEnabled(st.mode == "live" and not st.capturing)
        self.meter.set_active(st.snap_enabled and st.mic_ok)
        self.meter.set_level(st.mic_level if st.mic_ok else 0.0)
        self.mic_hint.setText(t("home.mic_hint") if st.snap_enabled else t("home.mic_off"))
        fps = f" · {st.fps:.0f} FPS" if st.fps else ""
        self.output_label.setText(t("home.output", name=st.vcam_name) + fps)
