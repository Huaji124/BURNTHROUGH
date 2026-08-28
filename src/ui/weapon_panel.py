"""下方武器栏：显示选中单位的可用武器槽，可手动选择武器。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.environment import Environment


class WeaponPanel(QWidget):
    weapon_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setStyleSheet(
            "QWidget { background:#1e242c; color:#ecf0f1; font-size:12px; }"
            "QPushButton { background:#2c3540; border:1px solid #3d4753;"
            " padding:3px 10px; border-radius:3px; }"
            "QPushButton:checked { background:#3498db; }"
            "QPushButton:hover { background:#3d4753; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        self.title = QLabel("武器栏（手动选择后点击目标攻击）")
        self.title.setStyleSheet("font-weight:bold;")
        layout.addWidget(self.title)
        self.buttons_layout = QHBoxLayout()
        layout.addLayout(self.buttons_layout)
        self._buttons: list[QPushButton] = []

    def show_platform(self, env: Environment, platform_id: str | None) -> None:
        self.clear_buttons()
        if platform_id is None:
            self.title.setText("武器栏（未选中单位）")
            return
        p = env.platforms.get(platform_id)
        if p is None:
            return
        self.title.setText(f"武器栏 - {p.name}")
        for lw in p.loadout_weapons:
            name = lw.get("name", "")
            ammo = p.ammo.get(name, 0)
            btn = QPushButton(f"{name} x{ammo}")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, n=name: self._on_click(n))
            self.buttons_layout.addWidget(btn)
            self._buttons.append(btn)
        if not self._buttons:
            label = QLabel("无武器")
            self.buttons_layout.addWidget(label)

    def clear_buttons(self) -> None:
        for b in self._buttons:
            b.deleteLater()
        self._buttons = []

    def _on_click(self, name: str) -> None:
        for b in self._buttons:
            if b.text().startswith(name):
                b.setChecked(True)
            else:
                b.setChecked(False)
        self.weapon_selected.emit(name)
