from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, FlowLayout, FluentIcon,
                            PrimaryPushButton, ScrollArea, SimpleCardWidget, Slider, StrongBodyLabel,
                            TitleLabel, themeColor)

from snap import effects
from snap.i18n import t
from snap.ui.widgets import fixed_height, muted

RANDOM_ICON = "🎲"


class EffectCard(CardWidget):
    def __init__(self, effect_id: str, icon: str, parent=None):
        super().__init__(parent)
        self.effect_id = effect_id
        self.selected = False
        self.setFixedSize(212, 150)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        emoji = QLabel(icon, self)
        f = QFont("Segoe UI Emoji")
        f.setPointSize(26)
        emoji.setFont(f)
        lay.addWidget(emoji)
        lay.addSpacing(10)
        lay.addWidget(StrongBodyLabel(t(f"effect.{effect_id}.name"), self))
        desc = muted(CaptionLabel(t(f"effect.{effect_id}.desc"), self))
        desc.setWordWrap(True)
        lay.addWidget(desc)
        lay.addStretch(1)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.selected:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(themeColor(), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)
        p.end()


class EffectsPage(ScrollArea):
    effect_selected = Signal(str)
    duration_changed = Signal(float)
    try_clicked = Signal()

    def __init__(self, current: str, duration: float, parent=None):
        super().__init__(parent)
        self.setObjectName("effects")
        self.view = QWidget(self)
        self.view.setObjectName("effectsView")
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.enableTransparentBackground()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QVBoxLayout(self.view)
        root.setContentsMargins(36, 20, 36, 28)
        root.setSpacing(12)
        root.addWidget(fixed_height(TitleLabel(t("effects.title"), self.view)))
        root.addWidget(fixed_height(muted(CaptionLabel(t("effects.subtitle"), self.view))))

        grid_host = QWidget(self.view)
        self.flow = FlowLayout(grid_host, needAni=False)
        self.flow.setContentsMargins(0, 8, 0, 8)
        self.flow.setHorizontalSpacing(12)
        self.flow.setVerticalSpacing(12)
        self.cards: dict[str, EffectCard] = {}
        for eid in effects.effect_ids():
            self._add_card(eid, effects.EFFECTS[eid].icon)
        self._add_card(effects.RANDOM_ID, RANDOM_ICON)
        root.addWidget(grid_host)

        bottom = SimpleCardWidget(self.view)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(18, 14, 18, 14)
        bl.setSpacing(14)
        bl.addWidget(StrongBodyLabel(t("effects.duration"), bottom))
        self.slider = Slider(Qt.Orientation.Horizontal, bottom)
        self.slider.setRange(10, 40)
        self.slider.setFixedWidth(240)
        self.slider.setValue(int(round(duration * 10)))
        self.value = BodyLabel("", bottom)
        self.value.setMinimumWidth(48)
        bl.addWidget(self.slider)
        bl.addWidget(self.value)
        bl.addStretch(1)
        self.try_hint = muted(CaptionLabel(t("effects.try_hint"), bottom))
        bl.addWidget(self.try_hint)
        self.try_btn = PrimaryPushButton(bottom)
        self.try_btn.setIcon(FluentIcon.PLAY)
        self.try_btn.setText(t("effects.try"))
        bl.addWidget(self.try_btn)
        root.addWidget(bottom)
        root.addStretch(1)

        self.slider.valueChanged.connect(self._on_slider)
        self.try_btn.clicked.connect(self.try_clicked)
        self._on_slider(self.slider.value(), emit=False)
        self.select(current if current in self.cards else effects.DEFAULT_ID)
        self.set_can_try(False)

    def _add_card(self, eid: str, icon: str) -> None:
        card = EffectCard(eid, icon, self.view)
        card.clicked.connect(lambda e=eid: self._on_card(e))
        self.flow.addWidget(card)
        self.cards[eid] = card

    def _on_card(self, eid: str) -> None:
        self.select(eid)
        self.effect_selected.emit(eid)

    def _on_slider(self, value: int, emit: bool = True) -> None:
        seconds = value / 10.0
        self.value.setText(t("effects.seconds", s=f"{seconds:.1f}"))
        if emit:
            self.duration_changed.emit(seconds)

    def select(self, eid: str) -> None:
        for key, card in self.cards.items():
            card.set_selected(key == eid)

    def set_can_try(self, can: bool) -> None:
        self.try_btn.setEnabled(can)
        self.try_hint.setVisible(not can)
