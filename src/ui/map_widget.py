"""2D 地图视图（QGraphicsView 实现）。

Phase 1 占位：后续实现经纬度投影、海岸线、平台图标、
探测范围圈、干扰扇区、烧穿圈等。
"""

from __future__ import annotations

from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene


class MapWidget(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHints(QPainter.RenderHint.Antialiasing)
