"""2D 战术地图视图。

Phase 1：静态射频沙盘可视化
- 局部切平面投影
- 网格与比例尺
- 平台图标（红/蓝/中立）
- 雷达无干扰探测圈、干扰后探测圈、烧穿圈
- 干扰机—雷达连线
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem, \
    QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView

from common.projection import LocalProjection

from core.environment import Environment, Platform
from core.propagation import wavelength_m


class MapWidget(QGraphicsView):
    """可缩放/平移的战术地图。"""

    SIDE_COLORS = {
        "red": QColor("#e74c3c"),
        "blue": QColor("#3498db"),
        "neutral": QColor("#95a5a6"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHints(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#101418")))

        self._env: Environment | None = None
        self._projection: LocalProjection | None = None
        self._jammer_on = True
        self._radar_on = True

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def set_environment(self, env: Environment) -> None:
        self._env = env
        if env.platforms:
            lats = [p.latitude for p in env.platforms.values()]
            lons = [p.longitude for p in env.platforms.values()]
            center_lat = sum(lats) / len(lats)
            center_lon = sum(lons) / len(lons)
            # 初始缩放：能看见 700 km 量级的探测圈
            self._projection = LocalProjection(center_lat, center_lon, px_per_km=0.5)
        self._rebuild()

    def refresh(self) -> None:
        """根据环境当前状态重建场景。"""
        self._rebuild()

    def set_jammer_on(self, on: bool) -> None:
        self._jammer_on = on
        for jammer in self._env.all_jammers() if self._env else []:
            jammer.emcon_state = "on" if on else "off"
        self._rebuild()

    def set_radar_on(self, on: bool) -> None:
        self._radar_on = on
        for emitter in self._env.all_emitters() if self._env else []:
            emitter.emcon_state = "on" if on else "off"
        self._rebuild()

    # ------------------------------------------------------------------
    # 缩放
    # ------------------------------------------------------------------
    def wheelEvent(self, event) -> None:  # noqa: N802
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    # ------------------------------------------------------------------
    # 场景重建
    # ------------------------------------------------------------------
    def _rebuild(self) -> None:
        if self._env is None or self._projection is None:
            return
        self._scene.clear()
        self._draw_grid()
        for platform in self._env.platforms.values():
            self._draw_platform(platform)
        self._draw_ew_circles()
        self._draw_esm_contacts()
        self._draw_legend()

    def _draw_grid(self) -> None:
        """绘制经纬度网格线。"""
        proj = self._projection
        c_lat, c_lon = proj.center_lat, proj.center_lon
        span = 8.0  # 中心 ±8 度
        step = 1.0

        pen = QPen(QColor("#2a2f3a"), 1, Qt.PenStyle.DashLine)
        font = QFont("SansSerif", 8)

        lat = math.floor((c_lat - span) / step) * step
        while lat <= c_lat + span:
            x1, y1 = proj.to_xy(lat, c_lon - span)
            x2, y2 = proj.to_xy(lat, c_lon + span)
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(pen)
            self._scene.addItem(line)
            label = QGraphicsSimpleTextItem(f"{lat:.0f}°N" if lat >= 0 else f"{-lat:.0f}°S")
            label.setBrush(QBrush(QColor("#7f8c8d")))
            label.setFont(font)
            label.setPos(x1 + 3, y1 + 3)
            self._scene.addItem(label)
            lat += step

        lon = math.floor((c_lon - span) / step) * step
        while lon <= c_lon + span:
            x1, y1 = proj.to_xy(c_lat - span, lon)
            x2, y2 = proj.to_xy(c_lat + span, lon)
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(pen)
            self._scene.addItem(line)
            label = QGraphicsSimpleTextItem(f"{lon:.0f}°E" if lon >= 0 else f"{-lon:.0f}°W")
            label.setBrush(QBrush(QColor("#7f8c8d")))
            label.setFont(font)
            label.setPos(x1 + 3, y1 + 3)
            self._scene.addItem(label)
            lon += step

    def _draw_platform(self, platform: Platform) -> None:
        proj = self._projection
        x, y = proj.to_xy(platform.latitude, platform.longitude)

        # 平台符号：舰船方块 / 飞机三角
        size = 10.0
        color = self.SIDE_COLORS.get(platform.side, QColor("#95a5a6"))
        pen = QPen(color, 2)
        brush = QBrush(color.darker(160))

        if platform.kind == "aircraft":
            pts = [QPointF(x, y - size * 0.7), QPointF(x - size * 0.7, y + size * 0.6),
                   QPointF(x, y + size * 0.25), QPointF(x + size * 0.7, y + size * 0.6)]
            item = self._scene.addPolygon(pts, pen, brush)
        else:
            item = self._scene.addRect(x - size / 2, y - size / 2, size, size, pen, brush)

        item.setToolTip(platform.name)

        # 航向指示线（飞机）
        if platform.kind == "aircraft":
            hdg = math.radians(platform.heading_deg)
            hx = x + math.sin(hdg) * 16
            hy = y - math.cos(hdg) * 16
            heading_line = QGraphicsLineItem(x, y, hx, hy)
            heading_line.setPen(QPen(color, 1, Qt.PenStyle.SolidLine))
            self._scene.addItem(heading_line)

        label = QGraphicsSimpleTextItem(platform.name)
        label.setBrush(QBrush(color))
        label.setFont(QFont("SansSerif", 9, QFont.Weight.Bold))
        label.setPos(x + 8, y - 6)
        self._scene.addItem(label)

    def _draw_ew_circles(self) -> None:
        """绘制雷达探测圈与烧穿圈。"""
        env = self._env
        proj = self._projection

        for platform in env.platforms.values():
            for emitter in platform.emitters:
                if emitter.emcon_state != "on":
                    continue
                if emitter.role not in ("multifunction_radar", "search_radar", "fire_control_radar"):
                    continue

                # 找到干扰本雷达的干扰机（简单规则：对立阵营 + 频段覆盖）
                jammer = self._find_jammer_against(platform, emitter)
                result = env.evaluate_radar_with_jamming(
                    emitter, jammer, rcs_m2=1000.0, bandwidth_hz=1_000_000,
                    noise_figure=5.0, loss=6.0, snr_min_db=13.0,
                )

                x, y = proj.to_xy(platform.latitude, platform.longitude)
                unjammed_km = result["un-jammed_range_km"] if jammer else result["detection_range_km"]
                self._draw_circle(x, y, unjammed_km,
                                  QColor("#f1c40f"), "无干扰探测圈", dashed=True)

                if jammer:
                    det_km = result["detection_range_km"]
                    bt_km = result["burn_through_km"]
                    self._draw_circle(x, y, det_km,
                                      QColor("#e67e22"), "干扰后探测圈", dashed=False)
                    self._draw_circle(x, y, bt_km,
                                      QColor("#e74c3c"), "烧穿圈", dashed=True)

                    # 干扰连线
                    jp = env.find_jammer_platform(jammer)
                    if jp is not None:
                        jx, jy = proj.to_xy(jp.latitude, jp.longitude)
                        line = QGraphicsLineItem(jx, jy, x, y)
                        line.setPen(QPen(QColor("#9b59b6"), 1, Qt.PenStyle.DashLine))
                        self._scene.addItem(line)
                        mid = QGraphicsSimpleTextItem("干扰")
                        mid.setBrush(QBrush(QColor("#9b59b6")))
                        mid.setFont(QFont("SansSerif", 8))
                        mid.setPos((jx + x) / 2 + 4, (jy + y) / 2 - 4)
                        self._scene.addItem(mid)

    def _find_jammer_against(self, victim_platform: Platform, emitter):
        """寻找正在干扰该雷达的干扰机。"""
        env = self._env
        for other in env.platforms.values():
            if other.side == victim_platform.side:
                continue
            for jammer in other.jammers:
                if jammer.emcon_state != "on":
                    continue
                if not jammer.covers_frequency(emitter.center_freq_hz):
                    continue
                return jammer
        return None

    def _draw_circle(self, x: float, y: float, radius_km: float,
                     color: QColor, label: str, dashed: bool) -> None:
        proj = self._projection
        r_px = max(proj.km_to_px(radius_km), 1.0)
        circle = QGraphicsEllipseItem(x - r_px, y - r_px, 2 * r_px, 2 * r_px)
        pen = QPen(color, 1.5)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        circle.setPen(pen)
        circle.setBrush(QBrush(QColor(0, 0, 0, 0)))
        self._scene.addItem(circle)

        label_item = QGraphicsSimpleTextItem(f"{label} {radius_km:.0f} km")
        label_item.setBrush(QBrush(color))
        label_item.setFont(QFont("SansSerif", 8))
        label_item.setPos(x + r_px * 0.7, y - r_px * 0.7)
        self._scene.addItem(label_item)

    def _draw_esm_contacts(self) -> None:
        """绘制 ESM 辐射源接触：测向线 + 交叉定位点。"""
        env = self._env
        proj = self._projection
        if not env.contacts:
            return

        for own_id, contact_map in env.contacts.items():
            own = env.platforms.get(own_id)
            if own is None:
                continue
            x0, y0 = proj.to_xy(own.latitude, own.longitude)
            for contact in contact_map.values():
                if contact.bearing_deg is None:
                    continue
                # 测向线：从己方平台沿方位画 250 km
                color = QColor("#f39c12") if contact.is_memory else QColor("#1abc9c")
                pen = QPen(color, 1.2)
                pen.setStyle(Qt.PenStyle.DashLine if contact.is_memory else Qt.PenStyle.SolidLine)
                brg = math.radians(contact.bearing_deg)
                length_px = proj.km_to_px(250.0)
                x1 = x0 + math.sin(brg) * length_px
                y1 = y0 - math.cos(brg) * length_px
                line = QGraphicsLineItem(x0, y0, x1, y1)
                line.setPen(pen)
                line.setToolTip(f"{contact.emitter_name} 方位 {contact.bearing_deg:.1f}°")
                self._scene.addItem(line)

                # 已识别/未知 标签
                ident = "已识别" if contact.confidence >= 0.6 else "未知"
                label = QGraphicsSimpleTextItem(
                    f"{contact.emitter_name} [{ident}] {'记忆' if contact.is_memory else ''}")
                label.setBrush(QBrush(color))
                label.setFont(QFont("SansSerif", 8))
                label.setPos(x1 + 4, y1 - 4)
                self._scene.addItem(label)

                # 交叉定位估计位置
                if contact.latitude is not None and contact.longitude is not None:
                    ex, ey = proj.to_xy(contact.latitude, contact.longitude)
                    r = 7.0
                    ellipse = QGraphicsEllipseItem(ex - r, ey - r, 2 * r, 2 * r)
                    ellipse.setPen(QPen(QColor("#1abc9c"), 1.5))
                    ellipse.setBrush(QBrush(QColor(26, 188, 156, 60)))
                    ellipse.setToolTip(f"交叉定位估计: {contact.latitude:.3f}, {contact.longitude:.3f}")
                    self._scene.addItem(ellipse)

    def _draw_legend(self) -> None:
        items = [
            ("#f1c40f", "无干扰探测圈"),
            ("#e67e22", "干扰后探测圈"),
            ("#e74c3c", "烧穿圈"),
            ("#9b59b6", "干扰连线"),
            ("#e74c3c", "红方"), ("#3498db", "蓝方"),
        ]
        font = QFont("SansSerif", 9)
        x, y = -500.0, -420.0
        for color_hex, text in items:
            line = QGraphicsLineItem(x, y + 5, x + 22, y + 5)
            line.setPen(QPen(QColor(color_hex), 2))
            self._scene.addItem(line)
            label = QGraphicsSimpleTextItem(text)
            label.setBrush(QBrush(QColor("#ecf0f1")))
            label.setFont(font)
            label.setPos(x + 28, y - 4)
            self._scene.addItem(label)
            y += 20
