"""EMCON（辐射管制）面板：控制各平台辐射源/干扰机开关。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.environment import Environment


class EmconPanel(QWidget):
    state_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.title = QLabel("EMCON 辐射管制")
        self.title.setStyleSheet("color:#ecf0f1; font-weight:bold;")
        layout.addWidget(self.title)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["平台", "系统", "类型", "状态"])
        self.table.setStyleSheet(
            "QTableWidget { background-color:#161a20; color:#ecf0f1; gridline-color:#2c3038; }"
            "QHeaderView::section { background-color:#1e242c; color:#ecf0f1; }"
        )
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)
        self._loading = False
        self._components: list[tuple] = []  # (row, component)

    def populate(self, env: Environment) -> None:
        self._loading = True
        self._components = []
        self.table.setRowCount(0)
        for platform in env.platforms.values():
            for emitter in platform.emitters:
                self._add_row(platform, emitter, "雷达/辐射源")
            for jammer in platform.jammers:
                self._add_row(platform, jammer, "干扰机")
        self.table.resizeColumnsToContents()
        self._loading = False

    def _add_row(self, platform, component, kind: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set(row, 0, platform.name)
        self._set(row, 1, component.name)
        self._set(row, 2, kind)
        item = QTableWidgetItem("开机")
        item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        item.setCheckState(Qt.CheckState.Checked if component.emcon_state == "on"
                           else Qt.CheckState.Unchecked)
        self.table.setItem(row, 3, item)
        self._components.append((row, component))

    def _set(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        self.table.setItem(row, col, item)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        if item.column() != 3:
            return
        for row, component in self._components:
            if row == item.row():
                component.emcon_state = "on" if item.checkState() == Qt.CheckState.Checked else "off"
                self.state_changed.emit()
                return
