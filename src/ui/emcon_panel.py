"""EMCON（辐射管制）面板：控制本方雷达/电台/干扰机开关。"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QTableWidget


class EmconPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["平台", "辐射源", "类型", "状态"])
        # TODO(Phase 2): 绑定 EMCON 状态到模拟内核
