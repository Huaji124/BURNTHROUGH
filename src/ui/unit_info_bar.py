"""底边栏：显示选中单位信息与常用操作按钮。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from core.environment import Environment


class UnitInfoBar(QWidget):
    radar_menu_requested = Signal()
    fire_clicked = Signal()
    emcon_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(42)
        self.setStyleSheet(
            "QWidget { background:#1e242c; color:#ecf0f1; font-size:12px; }"
            "QPushButton { background:#2c3540; border:1px solid #3d4753;"
            " padding:3px 10px; border-radius:3px; }"
            "QPushButton:hover { background:#3d4753; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self.icon_label = QLabel("")
        self.icon_label.setStyleSheet("font-size:16px;")
        layout.addWidget(self.icon_label)

        self.name_label = QLabel("未选中任何单位")
        self.name_label.setStyleSheet("font-weight:bold;")
        layout.addWidget(self.name_label)

        self.motion_label = QLabel("")
        layout.addWidget(self.motion_label)

        self.weapons_label = QLabel("")
        layout.addWidget(self.weapons_label, 1)

        self.radar_btn = QPushButton("雷达菜单")
        self.radar_btn.clicked.connect(self.radar_menu_requested)
        layout.addWidget(self.radar_btn)

        self.fire_btn = QPushButton("开火")
        self.fire_btn.setStyleSheet("QPushButton { background:#a93226; }")
        self.fire_btn.clicked.connect(self.fire_clicked)
        layout.addWidget(self.fire_btn)

        self.emcon_btn = QPushButton("EMCON")
        self.emcon_btn.clicked.connect(self.emcon_clicked)
        layout.addWidget(self.emcon_btn)

    def show_platforms(self, env: Environment, platform_ids: list[str]) -> None:
        if not platform_ids:
            self.icon_label.setText("")
            self.name_label.setText("未选中任何单位")
            self.motion_label.setText("")
            self.weapons_label.setText("")
            return

        if len(platform_ids) == 1:
            p = env.platforms.get(platform_ids[0])
            if p is None:
                return
            self.icon_label.setText("✈" if p.kind == "aircraft" else "▣")
            side_cn = {"red": "红方", "blue": "蓝方", "neutral": "中立"}.get(p.side, p.side)
            self.name_label.setText(f"{side_cn} {p.name}")
            speed_txt = f"速度 {p.speed_kt:.0f}kt"
            if p.max_speed_kt is not None:
                speed_txt += f" / 最大{p.max_speed_kt:.0f}kt"
            if p.fuel_kg is not None:
                speed_txt += f" | 油量 {p.fuel_kg:.0f}kg"
            self.motion_label.setText(
                f"{speed_txt} | 高度 {p.altitude_ft:.0f}ft | 航向 {p.heading_deg:03.0f}°")
            if p.ammo:
                ammo_parts = [f"{w} {c}/{p.magazine.get(w, 0)+c}" for w, c in p.ammo.items()]
                self.weapons_label.setText("弹药: " + " | ".join(ammo_parts[:6]))
            elif p.weapons:
                self.weapons_label.setText("武器: " + " | ".join(p.weapons))
            else:
                self.weapons_label.setText("武器: 无")
        else:
            self.icon_label.setText("▣")
            self.name_label.setText(f"已选中 {len(platform_ids)} 个单位")
            names = [env.platforms[i].name for i in platform_ids if i in env.platforms]
            self.motion_label.setText(" | ".join(names[:4]) + (" ..." if len(names) > 4 else ""))
            self.weapons_label.setText("")

    def show_contact(self, env: Environment, own_id: str, contact_key: str) -> None:
        contact_map = env.contacts.get(own_id, {})
        contact = contact_map.get(contact_key)
        if contact is None:
            return
        self.icon_label.setText("◈")
        self.name_label.setText(f"接触: {contact.emitter_name or '未知辐射源'}")
        ident = "已识别" if contact.confidence >= 0.6 else "未知"
        mem = "记忆" if contact.is_memory else "跟踪中"
        self.motion_label.setText(f"方位 {contact.bearing_deg:.1f}° | {ident} | {mem}")
        self.weapons_label.setText("")
