"""2D 战术地图视图：渲染与鼠标交互。

交互规范：
- 左键点击己方/敌方单位/接触：选中；已选中己方单位时左键点敌方 -> 攻击
- 左键拖拽：框选批量选择
- 右键点击单位/接触：弹出上下文菜单
- 右键点击空白：已选中己方单位 -> 移动到该点（单次航路点）
                Shift+右键空白 -> 追加连续航路点
                未选中 -> 弹出地图菜单
- 右键拖拽框选：敌方 -> 自动分配攻击；我方 -> 编组（基础版）
- 中键拖拽：平移地图
"""

from __future__ import annotations

import math
from typing import ClassVar

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QMenu,
    QMessageBox,
    QRubberBand,
)

from common.projection import LocalProjection
from core.environment import Environment, Platform


class MapWidget(QGraphicsView):
    """可缩放/平移/框选的战术地图。"""

    selection_changed = Signal()
    command_issued = Signal(str)

    SIDE_COLORS: ClassVar[dict[str, QColor]] = {
        "red": QColor("#e74c3c"),
        "blue": QColor("#3498db"),
        "neutral": QColor("#95a5a6"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHints(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#101418")))

        self._env: Environment | None = None
        self._projection: LocalProjection | None = None
        self._jammer_on = True
        self._radar_on = True
        self._attack_mode = False

        self._platform_items: dict[str, QGraphicsItem] = {}
        self._contact_items: dict[str, list[QGraphicsItem]] = {}
        self._selected_platform_ids: set[str] = set()
        self._selected_contact: tuple[str, str] | None = None

        # 鼠标拖拽状态
        self._left_press_screen: QPoint | None = None
        self._left_press_scene: QPointF | None = None
        self._left_dragging = False
        self._right_press_screen: QPoint | None = None
        self._right_dragging = False
        self._mid_press_screen: QPoint | None = None
        self._rubber_band: QRubberBand | None = None

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
            self._projection = LocalProjection(center_lat, center_lon, px_per_km=0.5)
        self._selected_platform_ids = set()
        self._selected_contact = None
        self._rebuild()

    def refresh(self) -> None:
        self._rebuild()

    def selected_platform_ids(self) -> list[str]:
        return list(self._selected_platform_ids)

    def selected_contact(self) -> tuple[str, str] | None:
        return self._selected_contact

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

    def set_attack_mode(self, on: bool) -> None:
        self._attack_mode = on
        if on:
            if not self._selected_platform_ids:
                self.command_issued.emit("请先选中己方单位")
                self._attack_mode = False
                return
            self.command_issued.emit("攻击模式：点击敌方目标下达攻击指令")
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.viewport().unsetCursor()

    # ------------------------------------------------------------------
    # 缩放
    # ------------------------------------------------------------------
    def wheelEvent(self, event) -> None:
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    # ------------------------------------------------------------------
    # 鼠标交互
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._left_press_screen = event.position().toPoint()
            self._left_press_scene = self.mapToScene(event.position().toPoint())
            self._left_dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            self._right_press_screen = event.position().toPoint()
            self._right_dragging = False
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._mid_press_screen = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        # 左键框选
        if self._left_press_screen is not None:
            delta = (event.position().toPoint() - self._left_press_screen).manhattanLength()
            if not self._left_dragging and delta > QApplication.startDragDistance():
                self._left_dragging = True
                self._start_rubber_band(self._left_press_screen)
            if self._left_dragging:
                self._update_rubber_band(self._left_press_screen, event.position().toPoint())
        # 右键框选
        elif self._right_press_screen is not None:
            delta = (event.position().toPoint() - self._right_press_screen).manhattanLength()
            if not self._right_dragging and delta > QApplication.startDragDistance():
                self._right_dragging = True
                self._start_rubber_band(self._right_press_screen)
            if self._right_dragging:
                self._update_rubber_band(self._right_press_screen, event.position().toPoint())
        # 中键平移
        elif self._mid_press_screen is not None:
            delta = event.position().toPoint() - self._mid_press_screen
            self._mid_press_screen = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._left_dragging:
                self._finish_rubber_band()
                self._left_band_select(self._rubber_band.geometry())
            else:
                self._on_left_click(self.mapToScene(event.position().toPoint()))
            self._left_press_screen = None
            self._left_press_scene = None
            self._left_dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            if self._right_dragging:
                self._finish_rubber_band()
                self._right_band_action(self._rubber_band.geometry())
            else:
                self._on_right_click(event.globalPosition().toPoint(),
                                     self.mapToScene(event.position().toPoint()))
            self._right_press_screen = None
            self._right_dragging = False
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._mid_press_screen = None
            self.viewport().unsetCursor()
        super().mouseReleaseEvent(event)

    def _start_rubber_band(self, origin: QPoint) -> None:
        if self._rubber_band is None:
            self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self._rubber_band.setGeometry(QRect(origin, QPoint(origin.x() + 1, origin.y() + 1)))
        self._rubber_band.show()

    def _update_rubber_band(self, origin: QPoint, current: QPoint) -> None:
        if self._rubber_band is not None:
            self._rubber_band.setGeometry(QRect(origin, current).normalized())

    def _finish_rubber_band(self) -> None:
        if self._rubber_band is not None:
            self._rubber_band.hide()

    # ------------------------------------------------------------------
    # 左键
    # ------------------------------------------------------------------
    def _on_left_click(self, scene_pos: QPointF) -> None:
        env = self._env
        if env is None:
            return
        hit = self._hit_test(scene_pos)
        if hit is None:
            self._set_selection(set(), None)
            return

        kind, data = hit
        if kind == "platform":
            pid = data
            # 已选中单位 + 左键敌方 -> 攻击
            if self._selected_platform_ids:
                attackers = [i for i in self._selected_platform_ids
                             if self._can_attack(i, pid)]
                if attackers:
                    self._issue_attack_orders(attackers, pid)
                    return
            self._set_selection({pid}, None)
        elif kind == "contact":
            own_id, ckey = data
            contact = env.contacts.get(own_id, {}).get(ckey)
            if contact is None:
                return
            if self._selected_platform_ids and contact.target_platform_id:
                attackers = [i for i in self._selected_platform_ids
                             if self._can_attack(i, contact.target_platform_id)]
                if attackers:
                    self._issue_attack_orders(attackers, contact.target_platform_id)
                    return
            self._set_selection(set(), (own_id, ckey))

    def _can_attack(self, attacker_id: str, target_id: str) -> bool:
        env = self._env
        a = env.platforms.get(attacker_id)
        t = env.platforms.get(target_id)
        if a is None or t is None:
            return False
        return a.side != t.side

    def _issue_attack_orders(self, attackers: list[str], target_id: str) -> None:
        env = self._env
        for aid in attackers:
            env.add_attack_order(aid, target_id)
        names = [env.platforms[a].name for a in attackers]
        target = env.platforms[target_id].name if target_id in env.platforms else target_id
        self.command_issued.emit(f"{', '.join(names)} -> {target}：攻击指令已下达")
        self._attack_mode = False
        self.viewport().unsetCursor()
        self._rebuild()

    # ------------------------------------------------------------------
    # 右键
    # ------------------------------------------------------------------
    def _on_right_click(self, global_pos: QPoint, scene_pos: QPointF) -> None:
        env = self._env
        if env is None:
            return
        hit = self._hit_test(scene_pos)
        if hit is None:
            if self._selected_platform_ids:
                self._move_selected_to(scene_pos)
            else:
                self._show_map_menu(global_pos)
            return

        kind, data = hit
        if kind == "platform":
            self._show_platform_menu(global_pos, data)
        elif kind == "contact":
            self._show_contact_menu(global_pos, data[0], data[1])

    def _move_selected_to(self, scene_pos: QPointF) -> None:
        env = self._env
        proj = self._projection
        lat, lon = proj.from_xy(scene_pos.x(), scene_pos.y())
        append = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        moved = []
        for pid in list(self._selected_platform_ids):
            p = env.platforms.get(pid)
            if p is None:
                continue
            if p.speed_kt <= 0 and p.cruise_speed_kt <= 0:
                continue
            env.add_move_order(pid, lat, lon, append=append)
            moved.append(p.name)
        if moved:
            mode = "连续航路点" if append else "单次航路点"
            self.command_issued.emit(f"{', '.join(moved)}：{mode}已设置")
            self._rebuild()
        else:
            self.command_issued.emit("选中单位航速为 0，无法移动")

    def _left_band_select(self, band_rect: QRect) -> None:
        """左键框选：批量选择单位/接触。"""
        ids = self._items_in_band(band_rect)
        platforms = set()
        contact = None
        for kind, data in ids:
            if kind == "platform":
                platforms.add(data)
            elif kind == "contact" and contact is None:
                contact = data
        self._set_selection(platforms, contact)

    def _right_band_action(self, band_rect: QRect) -> None:
        """右键框选：敌方 -> 自动分配攻击；我方 -> 编组（基础版）。"""
        env = self._env
        ids = self._items_in_band(band_rect)
        platform_ids = [data for kind, data in ids if kind == "platform"]

        if not self._selected_platform_ids:
            self.command_issued.emit("请先选中己方单位，再右键框选敌方目标")
            return
        attackers = list(self._selected_platform_ids)
        targets = [pid for pid in platform_ids
                   if any(self._can_attack(a, pid) for a in attackers)]
        if targets:
            for target in targets[:6]:
                eligible = [a for a in attackers if self._can_attack(a, target)]
                for a in eligible[:2]:
                    env.add_attack_order(a, target)
            self.command_issued.emit(f"已为框选中的 {len(targets)} 个敌方目标分配攻击")
            self._rebuild()
            return
        # 框选我方单位 -> 编组（基础版：仅选中并提示）
        if platform_ids:
            self._set_selection(set(platform_ids), None)
            self.command_issued.emit("已框选我方单位（编组功能后续接入）")

    # ------------------------------------------------------------------
    # 命中测试与选择
    # ------------------------------------------------------------------
    def _hit_test(self, scene_pos: QPointF) -> tuple[str, object] | None:
        items = self._scene.items(scene_pos, Qt.ItemSelectionMode.IntersectsItemShape)
        for item in items:
            data = item.data(0)
            if isinstance(data, str) and data.startswith("platform::"):
                return ("platform", data.split("::", 1)[1])
            if isinstance(data, str) and data.startswith("contact::"):
                parts = data.split("::")
                if len(parts) == 3:
                    return ("contact", (parts[1], parts[2]))
        return None

    def _items_in_band(self, band_rect: QRect) -> list[tuple[str, object]]:
        scene_area = self.mapToScene(band_rect).boundingRect()
        items = self._scene.items(scene_area, Qt.ItemSelectionMode.IntersectsItemShape)
        result = []
        for item in items:
            data = item.data(0)
            if isinstance(data, str) and data.startswith("platform::"):
                result.append(("platform", data.split("::", 1)[1]))
            elif isinstance(data, str) and data.startswith("contact::"):
                parts = data.split("::")
                if len(parts) == 3:
                    result.append(("contact", (parts[1], parts[2])))
        return result

    def _set_selection(self, platform_ids: set[str], contact) -> None:
        self._selected_platform_ids = set(platform_ids)
        self._selected_contact = contact
        self._restore_selection_visuals()
        self.selection_changed.emit()

    def _restore_selection_visuals(self) -> None:
        for pid, item in self._platform_items.items():
            item.setSelected(pid in self._selected_platform_ids)
        for key, items in self._contact_items.items():
            sel = (self._selected_contact is not None and key == f"{self._selected_contact[0]}::{self._selected_contact[1]}")
            for item in items:
                item.setSelected(sel)

    # ------------------------------------------------------------------
    # 场景重建与绘制
    # ------------------------------------------------------------------
    def _rebuild(self) -> None:
        if self._env is None or self._projection is None:
            return
        self._scene.clear()
        self._platform_items = {}
        self._contact_items = {}
        self._draw_grid()
        self._draw_waypoints()
        for platform in self._env.platforms.values():
            self._draw_platform(platform)
        self._draw_ew_circles()
        self._draw_esm_contacts()
        self._draw_orders()
        self._draw_legend()
        self._restore_selection_visuals()

    def _draw_grid(self) -> None:
        proj = self._projection
        c_lat, c_lon = proj.center_lat, proj.center_lon
        span = 8.0
        step = 1.0
        pen = QPen(QColor("#2a2f3a"), 1, Qt.PenStyle.DashLine)
        font = QFont("SansSerif", 8)

        lat = math.floor((c_lat - span) / step) * step
        while lat <= c_lat + span:
            x1, y1 = proj.to_xy(lat, c_lon - span)
            x2, y2 = proj.to_xy(lat, c_lon + span)
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(pen)
            line.setZValue(0)
            self._scene.addItem(line)
            label = QGraphicsSimpleTextItem(f"{lat:.0f}°N" if lat >= 0 else f"{-lat:.0f}°S")
            label.setBrush(QBrush(QColor("#7f8c8d")))
            label.setFont(font)
            label.setPos(x1 + 3, y1 + 3)
            label.setZValue(0)
            self._scene.addItem(label)
            lat += step

        lon = math.floor((c_lon - span) / step) * step
        while lon <= c_lon + span:
            x1, y1 = proj.to_xy(c_lat - span, lon)
            x2, y2 = proj.to_xy(c_lat + span, lon)
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(pen)
            line.setZValue(0)
            self._scene.addItem(line)
            label = QGraphicsSimpleTextItem(f"{lon:.0f}°E" if lon >= 0 else f"{-lon:.0f}°W")
            label.setBrush(QBrush(QColor("#7f8c8d")))
            label.setFont(font)
            label.setPos(x1 + 3, y1 + 3)
            label.setZValue(0)
            self._scene.addItem(label)
            lon += step

    def _draw_waypoints(self) -> None:
        env = self._env
        proj = self._projection
        if not env.waypoints:
            return
        for pid, wps in env.waypoints.items():
            p = env.platforms.get(pid)
            if p is None:
                continue
            color = QColor("#e67e22")
            pts = []
            if wps:
                px, py = proj.to_xy(p.latitude, p.longitude)
                pts.append((px, py))
            for i, (lat, lon) in enumerate(wps):
                x, y = proj.to_xy(lat, lon)
                pts.append((x, y))
                rect = QGraphicsRectItem(x - 4, y - 4, 8, 8)
                rect.setPen(QPen(color, 1.5))
                rect.setBrush(QBrush(color.darker(150)))
                rect.setZValue(9)
                rect.setToolTip(f"航路点 {i+1}")
                self._scene.addItem(rect)
                label = QGraphicsSimpleTextItem(f"WP{i+1}")
                label.setBrush(QBrush(color))
                label.setFont(QFont("SansSerif", 7))
                label.setPos(x + 6, y - 6)
                label.setZValue(9)
                self._scene.addItem(label)
            if len(pts) >= 2:
                for i in range(len(pts) - 1):
                    line = QGraphicsLineItem(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
                    line.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
                    line.setZValue(1)
                    self._scene.addItem(line)

    def _draw_platform(self, platform: Platform) -> None:
        proj = self._projection
        x, y = proj.to_xy(platform.latitude, platform.longitude)
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

        item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        item.setData(0, f"platform::{platform.id}")
        item.setZValue(10)
        item.setToolTip(platform.name)
        self._platform_items[platform.id] = item

        if platform.kind == "aircraft":
            hdg = math.radians(platform.heading_deg)
            hx = x + math.sin(hdg) * 16
            hy = y - math.cos(hdg) * 16
            heading_line = QGraphicsLineItem(x, y, hx, hy)
            heading_line.setPen(QPen(color, 1, Qt.PenStyle.SolidLine))
            heading_line.setZValue(9)
            self._scene.addItem(heading_line)

        label = QGraphicsSimpleTextItem(platform.name)
        label.setBrush(QBrush(color))
        label.setFont(QFont("SansSerif", 9, QFont.Weight.Bold))
        label.setPos(x + 8, y - 6)
        label.setZValue(11)
        self._scene.addItem(label)

    def _draw_ew_circles(self) -> None:
        env = self._env
        proj = self._projection
        for platform in env.platforms.values():
            for emitter in platform.emitters:
                if emitter.emcon_state != "on":
                    continue
                if emitter.role not in ("multifunction_radar", "search_radar", "fire_control_radar"):
                    continue
                jammer = self._find_jammer_against(platform, emitter)
                result = env.evaluate_radar_with_jamming(
                    emitter, jammer, rcs_m2=1000.0, bandwidth_hz=1_000_000,
                    noise_figure=5.0, loss=6.0, snr_min_db=13.0)
                x, y = proj.to_xy(platform.latitude, platform.longitude)
                unjammed_km = result["un-jammed_range_km"] if jammer else result["detection_range_km"]
                self._draw_circle(x, y, unjammed_km, QColor("#f1c40f"),
                                  "无干扰探测圈", dashed=True)
                if jammer:
                    self._draw_circle(x, y, result["detection_range_km"],
                                      QColor("#e67e22"), "干扰后探测圈", dashed=False)
                    self._draw_circle(x, y, result["burn_through_km"],
                                      QColor("#e74c3c"), "烧穿圈", dashed=True)
                    jp = env.find_jammer_platform(jammer)
                    if jp is not None:
                        jx, jy = proj.to_xy(jp.latitude, jp.longitude)
                        line = QGraphicsLineItem(jx, jy, x, y)
                        line.setPen(QPen(QColor("#9b59b6"), 1, Qt.PenStyle.DashLine))
                        line.setZValue(2)
                        self._scene.addItem(line)
                        mid = QGraphicsSimpleTextItem("干扰")
                        mid.setBrush(QBrush(QColor("#9b59b6")))
                        mid.setFont(QFont("SansSerif", 8))
                        mid.setPos((jx + x) / 2 + 4, (jy + y) / 2 - 4)
                        mid.setZValue(3)
                        self._scene.addItem(mid)

    def _draw_esm_contacts(self) -> None:
        env = self._env
        proj = self._projection
        if not env.contacts:
            return
        for own_id, contact_map in env.contacts.items():
            own = env.platforms.get(own_id)
            if own is None:
                continue
            x0, y0 = proj.to_xy(own.latitude, own.longitude)
            for key, contact in contact_map.items():
                if contact.bearing_deg is None:
                    continue
                color = QColor("#f39c12") if contact.is_memory else QColor("#1abc9c")
                pen = QPen(color, 1.2)
                pen.setStyle(Qt.PenStyle.DashLine if contact.is_memory else Qt.PenStyle.SolidLine)
                brg = math.radians(contact.bearing_deg)
                length_px = proj.km_to_px(250.0)
                x1 = x0 + math.sin(brg) * length_px
                y1 = y0 - math.cos(brg) * length_px
                line = QGraphicsLineItem(x0, y0, x1, y1)
                line.setPen(pen)
                line.setZValue(4)
                line.setToolTip(f"{contact.emitter_name} 方位 {contact.bearing_deg:.1f}°")
                self._scene.addItem(line)

                ident = "已识别" if contact.confidence >= 0.6 else "未知"
                mem = " 记忆" if contact.is_memory else ""
                side_mark = {"friendly": " [友]", "enemy": " [敌]",
                             "neutral": " [中]", "unknown": " [未]"} \
                    .get(contact.marked_side or "", "")
                label_text = f"{contact.emitter_name} [{ident}]{side_mark}{mem}"
                label = QGraphicsSimpleTextItem(label_text)
                label.setBrush(QBrush(color))
                label.setFont(QFont("SansSerif", 8))
                label.setPos(x1 + 4, y1 - 4)
                label.setZValue(12)
                self._scene.addItem(label)

                # 可点击标记
                if contact.latitude is not None and contact.longitude is not None:
                    ex, ey = proj.to_xy(contact.latitude, contact.longitude)
                    r = 7.0
                    marker = QGraphicsEllipseItem(ex - r, ey - r, 2 * r, 2 * r)
                    marker.setPen(QPen(QColor("#1abc9c"), 1.5))
                    marker.setBrush(QBrush(QColor(26, 188, 156, 60)))
                else:
                    mx = x0 + math.sin(brg) * proj.km_to_px(120.0)
                    my = y0 - math.cos(brg) * proj.km_to_px(120.0)
                    marker = QGraphicsEllipseItem(mx - 6, my - 6, 12, 12)
                    marker.setPen(QPen(color, 1.5))
                    marker.setBrush(QBrush(color.darker(200)))
                marker.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                                QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
                marker.setData(0, f"contact::{own_id}::{key}")
                marker.setZValue(12)
                marker.setToolTip(f"{label_text}\n方位 {contact.bearing_deg:.1f}°")
                self._scene.addItem(marker)
                self._contact_items.setdefault(f"{own_id}::{key}", []).append(marker)

    def _draw_orders(self) -> None:
        env = self._env
        proj = self._projection
        for order in env.orders:
            if order["kind"] != "attack":
                continue
            attacker = env.platforms.get(order["attacker"])
            target = env.platforms.get(order["target"])
            if attacker is None or target is None:
                continue
            x1, y1 = proj.to_xy(attacker.latitude, attacker.longitude)
            x2, y2 = proj.to_xy(target.latitude, target.longitude)
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(QPen(QColor("#e74c3c"), 1.5, Qt.PenStyle.DashLine))
            line.setZValue(8)
            self._scene.addItem(line)
            label = QGraphicsSimpleTextItem("攻击")
            label.setBrush(QBrush(QColor("#e74c3c")))
            label.setFont(QFont("SansSerif", 8))
            label.setPos((x1 + x2) / 2, (y1 + y2) / 2 - 10)
            label.setZValue(9)
            self._scene.addItem(label)

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
        circle.setZValue(1)
        self._scene.addItem(circle)

        label_item = QGraphicsSimpleTextItem(f"{label} {radius_km:.0f} km")
        label_item.setBrush(QBrush(color))
        label_item.setFont(QFont("SansSerif", 8))
        label_item.setPos(x + r_px * 0.7, y - r_px * 0.7)
        label_item.setZValue(3)
        self._scene.addItem(label_item)

    def _find_jammer_against(self, victim_platform: Platform, emitter):
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

    def _draw_legend(self) -> None:
        items = [
            ("#f1c40f", "无干扰探测圈"), ("#e67e22", "干扰后探测圈"),
            ("#e74c3c", "烧穿圈/攻击线"), ("#9b59b6", "干扰连线"),
            ("#1abc9c", "ESM 接触"), ("#f39c12", "记忆接触"),
            ("#e74c3c", "红方"), ("#3498db", "蓝方"),
        ]
        font = QFont("SansSerif", 9)
        x, y = -700.0, -420.0
        for color_hex, text in items:
            line = QGraphicsLineItem(x, y + 5, x + 22, y + 5)
            line.setPen(QPen(QColor(color_hex), 2))
            line.setZValue(20)
            self._scene.addItem(line)
            label = QGraphicsSimpleTextItem(text)
            label.setBrush(QBrush(QColor("#ecf0f1")))
            label.setFont(font)
            label.setPos(x + 28, y - 4)
            label.setZValue(20)
            self._scene.addItem(label)
            y += 20

    # ------------------------------------------------------------------
    # 上下文菜单
    # ------------------------------------------------------------------
    def _show_platform_menu(self, global_pos: QPoint, pid: str) -> None:
        env = self._env
        p = env.platforms.get(pid)
        if p is None:
            return
        menu = QMenu(self)
        menu.addAction("设置航路点（然后右键地图）", lambda: self.command_issued.emit(
            "请选中该单位后，右键地图空白处设置航路点"))
        menu.addAction("编入小队", lambda: self.command_issued.emit(
            f"{p.name}：编入小队（功能待接入）"))
        menu.addAction("归队", lambda: self.command_issued.emit(
            f"{p.name}：归队（功能待接入）"))
        menu.addAction("离队", lambda: self.command_issued.emit(
            f"{p.name}：离队（功能待接入）"))
        menu.addAction("返航 / 返回出发地", lambda: self.command_issued.emit(
            f"{p.name}：返航（功能待接入）"))

        radar_menu = menu.addMenu("雷达设置")
        radar_on = any(e.is_emitting for e in p.emitters)
        radar_menu.addAction("雷达关机" if radar_on else "雷达开机",
                             lambda: self._toggle_platform_radars(pid))
        radar_menu.addAction("搜索模式", lambda: self.command_issued.emit(
            f"{p.name}：搜索模式（功能待接入）"))
        radar_menu.addAction("火控模式", lambda: self.command_issued.emit(
            f"{p.name}：火控模式（功能待接入）"))
        radar_menu.addAction("EMCON 计划", lambda: self.command_issued.emit(
            f"{p.name}：EMCON 计划（功能待接入）"))

        weapon_menu = menu.addMenu("武器设置")
        weapon_menu.addAction("自动开火", lambda: self.command_issued.emit(
            f"{p.name}：自动开火（功能待接入）"))
        weapon_menu.addAction("谨慎开火", lambda: self.command_issued.emit(
            f"{p.name}：谨慎开火（功能待接入）"))
        weapon_menu.addAction("禁止开火", lambda: self.command_issued.emit(
            f"{p.name}：禁止开火（功能待接入）"))

        menu.exec(global_pos)

    def _toggle_platform_radars(self, pid: str) -> None:
        env = self._env
        p = env.platforms.get(pid)
        if p is None:
            return
        new_state = "off" if any(e.is_emitting for e in p.emitters) else "on"
        for e in p.emitters:
            e.emcon_state = new_state
        self.command_issued.emit(f"{p.name}：雷达已{'关机' if new_state == 'off' else '开机'}")
        self._rebuild()

    def _show_contact_menu(self, global_pos: QPoint, own_id: str, ckey: str) -> None:
        env = self._env
        contact = env.contacts.get(own_id, {}).get(ckey)
        if contact is None:
            return
        menu = QMenu(self)
        for side, label in [("friendly", "标记为 友方"), ("enemy", "标记为 敌方"),
                            ("neutral", "标记为 中立"), ("unknown", "标记为 未识别")]:
            menu.addAction(label, lambda s=side: self._mark_contact(own_id, ckey, s))
        menu.addSeparator()
        menu.addAction("信息", lambda: self._show_contact_info(own_id, ckey))
        menu.addAction("询问", lambda: self.command_issued.emit(
            "询问：导演/联机模式下可用（功能待接入）"))
        menu.exec(global_pos)

    def _mark_contact(self, own_id: str, ckey: str, side: str) -> None:
        env = self._env
        contact = env.contacts.get(own_id, {}).get(ckey)
        if contact is None:
            return
        contact.marked_side = side
        side_cn = {"friendly": "友方", "enemy": "敌方", "neutral": "中立", "unknown": "未识别"}
        self.command_issued.emit(f"接触已标记为 {side_cn.get(side, side)}")
        self._rebuild()

    def _show_contact_info(self, own_id: str, ckey: str) -> None:
        env = self._env
        contact = env.contacts.get(own_id, {}).get(ckey)
        if contact is None:
            return
        ident = "已识别" if contact.confidence >= 0.6 else "未知"
        mem = "记忆" if contact.is_memory else "跟踪中"
        info = (
            f"辐射源：{contact.emitter_name or '未知'}\n"
            f"方位：{contact.bearing_deg:.1f}°\n"
            f"识别：{ident}（置信度 {contact.confidence:.0%}）\n"
            f"状态：{mem}\n"
            f"更新：{contact.last_update_s:.0f}s\n"
            f"人工标记：{contact.marked_side or '无'}"
        )
        QMessageBox.information(self, "接触信息", info)

    def _show_map_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction("取消全部航路点", self._clear_all_waypoints)
        menu.addAction("区域设置（待接入）", lambda: self.command_issued.emit(
            "区域设置功能待接入"))
        menu.exec(global_pos)

    def _clear_all_waypoints(self) -> None:
        env = self._env
        for pid in list(self._selected_platform_ids):
            env.clear_waypoints(pid)
        self.command_issued.emit("已取消选中单位的全部航路点")
        self._rebuild()
