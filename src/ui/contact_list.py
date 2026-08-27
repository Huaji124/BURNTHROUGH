"""接触列表 / 辐射源列表面板（支持右键人工标记）。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QLabel,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.environment import Environment


class ContactListWidget(QWidget):
    marked_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player_side: str | None = None
        self._env: Environment | None = None
        self._row_contacts: dict[int, tuple[str, str]] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.title = QLabel("传感器接触（雷达/红外/声呐/ESM）")
        self.title.setStyleSheet("color:#ecf0f1; font-weight:bold;")
        layout.addWidget(self.title)

        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels(["时间", "己方", "辐射源", "方位/距离", "识别", "状态", "标记"])
        self.table.setStyleSheet(
            "QTableWidget { background-color:#161a20; color:#ecf0f1; gridline-color:#2c3038; }"
            "QHeaderView::section { background-color:#1e242c; color:#ecf0f1; }"
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table)

    def set_player_side(self, side: str | None) -> None:
        self._player_side = side

    def update_contacts(self, env: Environment) -> None:
        self._env = env
        self._row_contacts = {}
        self.table.setRowCount(0)

        # 雷达接触
        for own_id, radar_map in getattr(env, "radar_contacts", {}).items():
            own = env.platforms.get(own_id)
            if own is None or (self._player_side is not None and own.side != self._player_side):
                continue
            for contact in radar_map.values():
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._fill_row(row, contact, own, f"[雷达] {contact.emitter_name or contact.emitter_id or '?'}",
                               "已识别", "记忆" if contact.is_memory else "雷达跟踪")
        # 红外/视觉接触
        for own_id, ir_map in getattr(env, "ir_contacts", {}).items():
            own = env.platforms.get(own_id)
            if own is None or (self._player_side is not None and own.side != self._player_side):
                continue
            for contact in ir_map.values():
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._fill_row(row, contact, own, f"[红外] {contact.emitter_name or contact.emitter_id or '?'}",
                               "已识别", "记忆" if contact.is_memory else "红外跟踪")
        # 声呐接触
        for own_id, sonar_map in getattr(env, "sonar_contacts", {}).items():
            own = env.platforms.get(own_id)
            if own is None or (self._player_side is not None and own.side != self._player_side):
                continue
            for contact in sonar_map.values():
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._fill_row(row, contact, own, f"[声呐] {contact.emitter_name or contact.emitter_id or '?'}",
                               "已识别", "记忆" if contact.is_memory else "声呐跟踪")
        # ESM 辐射源接触
        for own_id, contact_map in env.contacts.items():
            own = env.platforms.get(own_id)
            if own is None or (self._player_side is not None and own.side != self._player_side):
                continue
            for contact in contact_map.values():
                row = self.table.rowCount()
                self.table.insertRow(row)
                bearing = f"{contact.bearing_deg:.1f}°" if contact.bearing_deg is not None else "-"
                self._fill_row(row, contact, own, contact.emitter_name or contact.emitter_id or "?",
                               "已识别" if contact.confidence >= 0.6 else "未知",
                               "记忆" if contact.is_memory else "跟踪中",
                               bearing)
        self.table.resizeColumnsToContents()

    def _fill_row(self, row: int, contact, own, source_text: str,
                  ident: str, status: str, bearing_or_range: str | None = None) -> None:
        self._row_contacts[row] = (own.id, contact.id)
        self._set(row, 0, f"{contact.last_update_s:4.0f}s")
        self._set(row, 1, own.name if own else "")
        self._set(row, 2, source_text)
        if bearing_or_range is None:
            if contact.range_m is not None:
                self._set(row, 3, f"{contact.range_m/1852.0:.0f}nm")
            else:
                self._set(row, 3, "-")
        else:
            self._set(row, 3, bearing_or_range)
        self._set(row, 4, ident)
        item = self._set(row, 5, status)
        # 颜色区分
        color = QColor("#f39c12") if contact.is_memory else QColor("#ecf0f1")
        item.setForeground(color)
        self._set(row, 6, contact.marked_side or "")

    def _on_context_menu(self, pos) -> None:
        if self._env is None:
            return
        row = self.table.rowAt(pos.y())
        if row < 0 or row not in self._row_contacts:
            return
        own_id, contact_id = self._row_contacts[row]
        contact = self._env.contacts.get(own_id, {}).get(contact_id)
        if contact is None:
            for attr in ("radar_contacts", "ir_contacts", "sonar_contacts"):
                pass
            # 从所有传感器接触中查找
            contact = None
            for source in ("contacts", "radar_contacts", "ir_contacts", "sonar_contacts"):
                contact = getattr(self._env, source, {}).get(own_id, {}).get(contact_id)
                if contact is not None:
                    break
        if contact is None:
            return
        menu = QMenu(self)
        for side, label in [("friendly", "标记为 友方"), ("enemy", "标记为 敌方"),
                            ("neutral", "标记为 中立"), ("unknown", "标记为 未识别")]:
            menu.addAction(label, lambda s=side: self._mark(own_id, contact_id, s))
        menu.addSeparator()
        confirm = menu.addAction("清除标记")
        confirm.triggered.connect(lambda: self._mark(own_id, contact_id, ""))
        menu.exec(self.table.mapToGlobal(pos))

    def _mark(self, own_id: str, contact_id: str, side: str) -> None:
        if self._env is None:
            return
        contact = None
        for source in ("contacts", "radar_contacts", "ir_contacts", "sonar_contacts"):
            contact = getattr(self._env, source, {}).get(own_id, {}).get(contact_id)
            if contact is not None:
                break
        if contact is not None:
            contact.marked_side = side
            self.marked_changed.emit()

    def _set(self, row: int, col: int, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setForeground(QColor("#ecf0f1"))
        self.table.setItem(row, col, item)
        return item
