"""全参数信号库编辑面板。"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

DEFAULT_JSON = Path(__file__).resolve().parents[2] / "data" / "signal_params.json"


class SignalLibraryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.title = QLabel("信号参数库（PRI/脉宽/发射类型）")
        self.title.setStyleSheet("color:#ecf0f1; font-weight:bold;")
        layout.addWidget(self.title)

        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(["ID", "PRF_min", "PRF_max", "PW_min", "PW_max", "Emission"])
        self.table.setStyleSheet(
            "QTableWidget { background-color:#161a20; color:#ecf0f1; gridline-color:#2c3038; }"
            "QHeaderView::section { background-color:#1e242c; color:#ecf0f1; }"
        )
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.load_btn = QPushButton("加载")
        self.load_btn.clicked.connect(self.load)
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save)
        self.add_btn = QPushButton("添加行")
        self.add_btn.clicked.connect(self._add_row)
        buttons.addWidget(self.load_btn)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.add_btn)
        layout.addLayout(buttons)

        self.load()

    def _add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col in range(6):
            self.table.setItem(row, col, QTableWidgetItem(""))
        self.table.item(row, 0).setText(f"sig_{row + 1}")

    def load(self) -> None:
        if not DEFAULT_JSON.exists():
            return
        data = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
        self.table.setRowCount(0)
        for sig_id, params in data.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [sig_id,
                      str(params.get("prf_min", "")),
                      str(params.get("prf_max", "")),
                      str(params.get("pw_min", "")),
                      str(params.get("pw_max", "")),
                      str(params.get("emission_type", "normal"))]
            for col, val in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(val))
        self.table.resizeColumnsToContents()

    def save(self) -> None:
        data = {}
        for row in range(self.table.rowCount()):
            items = [self.table.item(row, col) for col in range(6)]
            sid = items[0].text().strip() if items[0] else ""
            if not sid:
                continue
            data[sid] = {
                "prf_min": float(items[1].text() or 0) if items[1] else 0,
                "prf_max": float(items[2].text() or 0) if items[2] else 0,
                "pw_min": float(items[3].text() or 0) if items[3] else 0,
                "pw_max": float(items[4].text() or 0) if items[4] else 0,
                "emission_type": items[5].text().strip() or "normal" if items[5] else "normal",
            }
        DEFAULT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.title.setText("信号参数库（已保存）")
