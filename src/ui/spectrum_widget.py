"""频谱瀑布图 / 频谱柱状图面板。

Phase 3 实现：显示各辐射源的频段与功率。
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


class SpectrumWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # TODO(Phase 3): 使用 QCustomPlot 或自绘实现频谱显示
