"""频谱监视面板（简易版）。

显示当前所有开机辐射源/干扰机的频段与相对功率。
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core.environment import Environment


class SpectrumWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._env: Environment | None = None
        self._player_side: str | None = None
        self.setMinimumHeight(120)

    def set_environment(self, env: Environment) -> None:
        self._env = env
        self.update()

    def set_player_side(self, side: str | None) -> None:
        self._player_side = side
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#101418"))

        if self._env is None:
            painter.setPen(QColor("#7f8c8d"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "频谱监视（无环境）")
            painter.end()
            return

        margin = 24
        bottom = self.height() - 16
        top = 24
        left = margin
        right = self.width() - margin

        # 坐标轴
        painter.setPen(QColor("#34495e"))
        painter.drawLine(left, bottom, right, bottom)
        painter.drawLine(left, top, left, bottom)

        # 频段 0.5~18 GHz 映射
        fmin, fmax = 0.5e9, 18.0e9
        width = right - left
        labels = ["0.5", "2", "4", "8", "12", "18"]
        for label in labels:
            freq = float(label) * 1e9 if label != "0.5" else 0.5e9
            x = left + (freq - fmin) / (fmax - fmin) * width
            painter.setPen(QColor("#566573"))
            painter.drawLine(int(x), bottom, int(x), bottom + 4)
            painter.drawText(int(x) - 12, bottom + 16, f"{label} GHz")
        painter.setPen(QColor("#7f8c8d"))
        painter.drawText(left, 14, "频谱监视")

        # 收集活跃辐射源/干扰机
        sources = []
        for platform in self._env.platforms.values():
            if self._player_side is not None and platform.side != self._player_side:
                continue
            color = QColor("#e74c3c") if platform.side == "red" else QColor("#3498db")
            for e in platform.emitters:
                if e.emcon_state == "on":
                    freq = e.center_freq_hz
                    pow_dbm = 10 * math.log10(max(e.peak_power_w, 1e-6) * 1000.0)
                    sources.append((freq, pow_dbm, color, e.name, False))
            for j in platform.jammers:
                if j.emcon_state == "on":
                    freq = (j.freq_min_hz + j.freq_max_hz) / 2.0
                    pow_dbm = 10 * math.log10(max(j.power_w, 1e-6) * 1000.0)
                    sources.append((freq, pow_dbm, QColor("#9b59b6"), j.name, True))

        # 绘制柱状图
        max_pow = max([s[1] for s in sources], default=60.0)
        min_pow = 0.0
        for freq, pow_dbm, color, name, is_jammer in sources:
            x = left + (freq - fmin) / (fmax - fmin) * width
            h = (pow_dbm - min_pow) / max(max_pow - min_pow, 1.0) * (bottom - top - 8)
            h = max(h, 4.0)
            painter.setPen(QPen(color.darker(140), 1))
            painter.setBrush(color if is_jammer else color.darker(160))
            painter.drawRect(int(x) - 3, int(bottom - h), 6, int(h))
            painter.setPen(color)
            painter.drawText(int(x) - 16, int(bottom - h - 4), f"{name[:4]}")

        painter.end()
