"""接触列表 / 辐射源列表面板。"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QTableWidget


class ContactListWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["时间", "类型", "方位", "距离", "识别"])
