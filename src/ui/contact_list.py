"""接触列表 / 辐射源列表面板。"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QWidget, QVBoxLayout, QLabel

from core.environment import Environment


class ContactListWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.title = QLabel("辐射源接触（ESM）")
        self.title.setStyleSheet("color:#ecf0f1; font-weight:bold;")
        layout.addWidget(self.title)

        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(["时间", "己方", "辐射源", "方位", "识别", "状态"])
        self.table.setStyleSheet(
            "QTableWidget { background-color:#161a20; color:#ecf0f1; gridline-color:#2c3038; }"
            "QHeaderView::section { background-color:#1e242c; color:#ecf0f1; }"
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

    def update_contacts(self, env: Environment) -> None:
        self.table.setRowCount(0)
        for own_id, contact_map in env.contacts.items():
            own = env.platforms.get(own_id)
            for contact in contact_map.values():
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._set(row, 0, f"{contact.last_update_s:4.0f}s")
                self._set(row, 1, own.name if own else own_id)
                self._set(row, 2, contact.emitter_name or contact.emitter_id or "?")
                self._set(row, 3, f"{contact.bearing_deg:.1f}°" if contact.bearing_deg is not None else "-")
                if contact.confidence >= 0.6:
                    self._set(row, 4, "已识别")
                else:
                    self._set(row, 4, "未知")
                status = "记忆" if contact.is_memory else "跟踪中"
                item = self._set(row, 5, status)
                if contact.is_memory:
                    item.setForeground(QColor("#f39c12"))
        self.table.resizeColumnsToContents()

    def _set(self, row: int, col: int, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setForeground(QColor("#ecf0f1"))
        self.table.setItem(row, col, item)
        return item
