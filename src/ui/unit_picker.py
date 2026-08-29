"""单个单位选择器：按国家/类型选择单位（本地 units + CMO 世界各国）。"""

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

ROOT = Path(__file__).resolve().parents[2]
UNITS_DIR = ROOT / "data" / "units"
COUNTRY_DIR = ROOT / "data" / "cmo_full_by_country"


class UnitPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("加载单位")
        self.resize(700, 520)
        self.selected_local_path: Path | None = None
        self.selected_country: tuple[Path, str] | None = None  # (country_dir, platform_id)
        self._country_combo_items: list[tuple[str, str | None]] = []  # (label, country_dir or None)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("国家:"))
        self.country_combo = QComboBox()
        self.country_combo.currentIndexChanged.connect(self._refresh)
        top.addWidget(self.country_combo)
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

        self._populate_countries()
        self._refresh()

    def _populate_countries(self) -> None:
        self.country_combo.clear()
        self._country_combo_items = [("中国本地", None)]
        if COUNTRY_DIR.exists():
            for cdir in sorted(COUNTRY_DIR.iterdir()):
                if not cdir.is_dir():
                    continue
                country_file = cdir / "country.json"
                name = cdir.name
                if country_file.exists():
                    try:
                        name = json.loads(country_file.read_text(encoding="utf-8")).get("name", cdir.name)
                    except (OSError, ValueError, KeyError):
                        name = cdir.name
                self._country_combo_items.append((name, str(cdir)))
        for label, _ in self._country_combo_items:
            self.country_combo.addItem(label)

    def _refresh(self, *_args) -> None:
        idx = self.country_combo.currentIndex()
        if idx < 0:
            return
        _, cdir = self._country_combo_items[idx]
        kind_filter = self.kind_combo.currentText()
        self.list_widget.clear()
        if cdir is None:
            self._populate_local(kind_filter)
        else:
            self._populate_country(Path(cdir), kind_filter)

    def _populate_local(self, kind_filter: str) -> None:
        if not UNITS_DIR.exists():
            return
        for path in sorted(UNITS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                raw = data.get("platform", {})
                name = raw.get("Name") or path.stem
                kind = data.get("kind", "ship")
                if kind_filter != "全部" and kind != kind_filter:
                    continue
                item = QListWidgetItem(f"{name}  [{kind}]")
                item.setData(Qt.ItemDataRole.UserRole, ("local", str(path)))
                self.list_widget.addItem(item)
            except (OSError, ValueError, KeyError):
                continue

    def _populate_country(self, cdir: Path, kind_filter: str) -> None:
        pf = cdir / "platforms.json"
        if not pf.exists():
            return
        try:
            platforms = json.loads(pf.read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            return
        for p in platforms:
            raw = p.get("raw", p)
            name = raw.get("Name") or raw.get("ID")
            kind = p.get("kind") or raw.get("kind") or "ship"
            pid = raw.get("ID")
            if kind_filter != "全部" and kind != kind_filter:
                continue
            item = QListWidgetItem(f"{name}  [{kind}]")
            item.setData(Qt.ItemDataRole.UserRole, ("country", str(cdir), str(pid)))
            self.list_widget.addItem(item)

    def _accept_item(self, *_args) -> None:
        current = self.list_widget.currentItem()
        if current is None:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if data[0] == "local":
            self.selected_local_path = Path(data[1])
            self.selected_country = None
        else:
            self.selected_local_path = None
            self.selected_country = (Path(data[1]), data[2])
        self.accept()
