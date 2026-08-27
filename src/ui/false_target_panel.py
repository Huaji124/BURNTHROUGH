"""假目标列表面板。"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.environment import Environment


class FalseTargetPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.title = QLabel("假目标（欺骗干扰）")
        self.title.setStyleSheet("color:#ecf0f1; font-weight:bold;")
        layout.addWidget(self.title)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["目标雷达", "干扰机", "技术", "纬度", "经度"])
        self.table.setStyleSheet(
            "QTableWidget { background-color:#161a20; color:#ecf0f1; gridline-color:#2c3038; }"
            "QHeaderView::section { background-color:#1e242c; color:#ecf0f1; }"
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        self._player_side: str | None = None

    def set_player_side(self, side: str | None) -> None:
        self._player_side = side

    def update_false_targets(self, env: Environment) -> None:
        self.table.setRowCount(0)
        for radar_id, targets in env.false_contacts.items():
            radar = env.platforms.get(radar_id)
            if radar is None or (self._player_side is not None and radar.side != self._player_side):
                continue
            for t in targets:
                if not t.active:
                    continue
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._set(row, 0, radar.name if radar else radar_id)
                self._set(row, 1, t.jammer_id)
                self._set(row, 2, t.technique)
                self._set(row, 3, f"{t.latitude:.3f}")
                self._set(row, 4, f"{t.longitude:.3f}")
        self.table.resizeColumnsToContents()

    def _set(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setForeground(QColor("#ecf0f1"))
        self.table.setItem(row, col, item)
