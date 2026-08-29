"""单个单位选择器：按类型/名称选择 data/units 下的单位。"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

UNITS_DIR = Path(__file__).resolve().parents[2] / "data" / "units"


class UnitPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("加载单位")
        self.resize(600, 500)
        self.selected_path: Path | None = None
        self._items: list[tuple[str, str, str]] = []  # (name, kind, path)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("类型:"))
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(["全部", "aircraft", "ship", "submarine"])
        self.kind_combo.currentTextChanged.connect(self._refresh)
        top.addWidget(self.kind_combo)
        layout.addLayout(top)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._accept_item)
        layout.addWidget(self.list_widget)

        bottom = QHBoxLayout()
        self.load_btn = QPushButton("加载")
        self.load_btn.clicked.connect(self._accept_item)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(self.load_btn)
        bottom.addWidget(self.cancel_btn)
        layout.addLayout(bottom)

        self._load_units()
        self._refresh()

    def _load_units(self) -> None:
        if not UNITS_DIR.exists():
            return
        for path in sorted(UNITS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                raw = data.get("platform", {})
                name = raw.get("Name") or path.stem
                kind = data.get("kind", "ship")
                self._items.append((name, kind, str(path)))
            except (OSError, ValueError, KeyError):
                continue

    def _refresh(self, *_args) -> None:
        kind_filter = self.kind_combo.currentText()
        self.list_widget.clear()
        for name, kind, path in self._items:
            if kind_filter != "全部" and kind != kind_filter:
                continue
            item = QListWidgetItem(f"{name}  [{kind}]")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list_widget.addItem(item)

    def _accept_item(self, *_args) -> None:
        current = self.list_widget.currentItem()
        if current is None:
            return
        self.selected_path = Path(current.data(Qt.ItemDataRole.UserRole))
        self.accept()
