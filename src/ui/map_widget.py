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

from typing import ClassVar

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QMenu,
    QMessageBox,
    QRubberBand,
)

from common.projection import LocalProjection
from core.environment import Environment

from .map_renderer import (
    WaypointRect as _WaypointRect,
)
from .map_renderer import (
    draw_coastlines,
    draw_esm_contacts,
    draw_ew_circles,
    draw_false_targets,
    draw_grid,
    draw_ir_contacts,
    draw_jammer_sectors,
    draw_legend,
    draw_map_background,
    draw_missiles,
    draw_orders,
    draw_platform,
    draw_radar_contacts,
    draw_sonar_contacts,
    draw_terrain_obstacles,
    draw_waypoints,
)


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
        self.setBackgroundBrush(QBrush(QColor("#c9e3f2")))

        self._env: Environment | None = None
        self._projection: LocalProjection | None = None
        self._jammer_on = True
        self._radar_on = True
        self._attack_mode = False

        self._platform_items: dict[str, QGraphicsItem] = {}
        self._contact_items: dict[str, list[QGraphicsItem]] = {}
        self._waypoint_items: list[_WaypointRect] = []
        self._waypoint_press = False
        self._waypoint_moved = False
        self._waypoint_drag_item: _WaypointRect | None = None
        self._selected_platform_ids: set[str] = set()
        self._selected_contact: tuple[str, str] | None = None
        self._player_side: str = "red"

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
            self._projection = LocalProjection(0.0, 0.0, px_per_km=0.02)
        self._selected_platform_ids = set()
        self._selected_contact = None
        self.fit_to_world()
        self._rebuild()

    def fit_to_world(self) -> None:
        """将初始视图缩放到世界范围。"""
        if self._projection is None:
            return
        tl = self._projection.to_xy(90, -180)
        br = self._projection.to_xy(-90, 180)
        rect = QRectF(QPointF(*tl), QPointF(*br))
        self.resetTransform()
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(0, 0)
        self._apply_inverse_scale()
        self._update_text_visibility()

    def _apply_inverse_scale(self) -> None:
        """反向缩放：让标记为 screen 的元素在屏幕上固定大小。"""
        scale = abs(self.transform().m11())
        if scale <= 0:
            return
        for item in self._scene.items():
            if item.data(1) != "screen":
                continue
            item.setScale(1.0 / scale)
            anchor = item.data(2)
            if anchor is not None:
                ax, ay, ox, oy = anchor
                item.setPos(ax + ox / scale, ay + oy / scale)

    def _update_text_visibility(self) -> None:
        """根据当前缩放级别显示/隐藏地图文字标签。"""
        # 文字固定屏幕大小且始终显示（与图标一致）
        for item in self._scene.items():
            if isinstance(item, QGraphicsSimpleTextItem):
                item.setVisible(True)

    def refresh(self) -> None:
        self._rebuild()

    def selected_platform_ids(self) -> list[str]:
        return list(self._selected_platform_ids)

    def selected_contact(self) -> tuple[str, str] | None:
        return self._selected_contact

    def set_player_side(self, side: str) -> None:
        self._player_side = side
        self._selected_platform_ids = set()
        self._selected_contact = None
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
        self._apply_inverse_scale()
        self._update_text_visibility()

    # ------------------------------------------------------------------
    # 鼠标交互
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            hit = self._hit_test(scene_pos)
            if hit is not None and hit[0] == "waypoint":
                pid, idx = hit[1]
                self._waypoint_press = True
                self._waypoint_moved = False
                self._waypoint_drag_item = self._find_waypoint_item(pid, idx)
                if self._env is not None:
                    self._env.waypoint_drag_lock = True
            else:
                self._left_press_screen = event.position().toPoint()
                self._left_press_scene = scene_pos
                self._left_dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            self._right_press_screen = event.position().toPoint()
            self._right_dragging = False
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._mid_press_screen = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        # 航路点手动拖拽（不使用 QGraphicsItem 内建移动，避免冲突）
        if self._waypoint_press and self._waypoint_drag_item is not None:
            scene_pos = self.mapToScene(event.position().toPoint())
            self._waypoint_drag_item.setPos(scene_pos)
            if self._env is not None and self._projection is not None:
                pid = self._waypoint_drag_item._pid
                idx = self._waypoint_drag_item._idx
                wps = self._env.waypoints.get(pid)
                if wps is not None and 0 <= idx < len(wps):
                    lat, lon = self._projection.from_xy(scene_pos.x(), scene_pos.y())
                    wps[idx] = (lat, lon)
                    self._waypoint_moved = True
        # 左键框选
        if self._left_press_screen is not None and not self._waypoint_press:
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
            if self._waypoint_press:
                if self._env is not None:
                    self._env.waypoint_drag_lock = False
                if self._waypoint_moved:
                    self._rebuild()
                self._waypoint_press = False
                self._waypoint_moved = False
                self._waypoint_drag_item = None
            elif self._left_dragging:
                self._finish_rubber_band()
                self._left_band_select(self._rubber_band.geometry())
                self._left_press_screen = None
                self._left_press_scene = None
                self._left_dragging = False
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
        if a.side == t.side:
            return False
        return a.roe != "hold"

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
        elif kind == "waypoint":
            self._show_waypoint_menu(global_pos, data[0], data[1])

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
            if isinstance(data, str) and data.startswith("waypoint::"):
                parts = data.split("::")
                if len(parts) == 3:
                    return ("waypoint", (parts[1], int(parts[2])))
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
        self._apply_inverse_scale()
        self._update_text_visibility()
        self._restore_selection_visuals()
        self.selection_changed.emit()

    def _find_waypoint_item(self, pid: str, idx: int) -> _WaypointRect | None:
        """按平台ID和序号查找航路点矩形。"""
        for item in self._waypoint_items:
            if item._pid == pid and item._idx == idx:
                return item
        return None

    def _on_waypoint_moved(self, pid: str, idx: int, pos: QPointF) -> None:
        """航路点被拖拽后，更新环境中的经纬度。"""
        env = self._env
        proj = self._projection
        if env is None or proj is None:
            return
        wps = env.waypoints.get(pid)
        if wps and 0 <= idx < len(wps):
            lat, lon = proj.from_xy(pos.x(), pos.y())
            wps[idx] = (lat, lon)
            self._waypoint_moved = True

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
        self._waypoint_items = []
        draw_map_background(self._scene, self._env, self._projection)
        if not self._env.world_land:
            draw_grid(self._scene, self._projection)
            draw_coastlines(self._scene, self._env, self._projection)
        self._waypoint_items = draw_waypoints(
            self._scene, self._env, self._projection, self._on_waypoint_moved)
        draw_jammer_sectors(self._scene, self._env, self._projection, self._player_side)
        for platform in self._env.platforms.values():
            if platform.side != self._player_side:
                continue
            draw_platform(self._scene, platform, self._projection,
                          self.SIDE_COLORS, self._platform_items)
        draw_ew_circles(self._scene, self._env, self._projection, self._player_side)
        draw_false_targets(self._scene, self._env, self._projection, self._player_side)
        draw_esm_contacts(self._scene, self._env, self._projection,
                          self._contact_items, self._player_side)
        draw_radar_contacts(self._scene, self._env, self._projection, self._player_side)
        draw_ir_contacts(self._scene, self._env, self._projection, self._player_side)
        draw_sonar_contacts(self._scene, self._env, self._projection, self._player_side)
        draw_orders(self._scene, self._env, self._projection, self._player_side)
        draw_missiles(self._scene, self._env, self._projection, self._player_side)
        if not self._env.world_land:
            draw_legend(self._scene, self._projection, self._player_side)
        self._apply_inverse_scale()
        self._update_text_visibility()
        self._restore_selection_visuals()

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
        menu.addAction("编入小队", lambda: self._platform_join_group(pid))
        menu.addAction("归队", lambda: self._platform_leave_group(pid))
        menu.addAction("离队", lambda: self._platform_leave_group(pid))
        menu.addAction("返航 / 返回出发地", lambda: self._platform_return_home(pid))

        radar_menu = menu.addMenu("雷达设置")
        radar_on = any(e.is_emitting for e in p.emitters)
        radar_menu.addAction("雷达关机" if radar_on else "雷达开机",
                             lambda: self._toggle_platform_radars(pid))
        radar_menu.addAction("搜索模式", lambda: self._set_radar_mode(pid, "search"))
        radar_menu.addAction("火控模式", lambda: self._set_radar_mode(pid, "fire"))
        radar_menu.addAction("EMCON 计划：关闭全部雷达", lambda: self._emcon_plan(pid))

        weapon_menu = menu.addMenu("武器设置")
        weapon_menu.addAction("自动开火", lambda: self._set_roe(pid, "free"))
        weapon_menu.addAction("谨慎开火", lambda: self._set_roe(pid, "weapons_free"))
        weapon_menu.addAction("禁止开火", lambda: self._set_roe(pid, "hold"))

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

    def _platform_join_group(self, pid: str) -> None:
        env = self._env
        p = env.platforms.get(pid)
        if p is None:
            return
        # 已选中的己方单位编为同组
        group_ids = [i for i in self._selected_platform_ids if i in env.platforms]
        grp = next((env.platforms[i].group_id for i in group_ids
                    if env.platforms[i].group_id is not None), None)
        if grp is None:
            grp = f"group-{pid}"
        for i in group_ids:
            env.platforms[i].group_id = grp
        p.group_id = grp
        self.command_issued.emit(f"{p.name} 已编入小队 {grp}")
        self._rebuild()

    def _platform_leave_group(self, pid: str) -> None:
        env = self._env
        p = env.platforms.get(pid)
        if p is None:
            return
        p.group_id = None
        self.command_issued.emit(f"{p.name} 已离队")
        self._rebuild()

    def _platform_return_home(self, pid: str) -> None:
        env = self._env
        p = env.platforms.get(pid)
        if p is None:
            return
        if p.home_lat is None or p.home_lon is None:
            p.home_lat = p.latitude
            p.home_lon = p.longitude
            self.command_issued.emit(f"{p.name}：当前点已设为出发地")
        else:
            env.add_move_order(pid, p.home_lat, p.home_lon)
            self.command_issued.emit(f"{p.name}：正在返回出发地")
        self._rebuild()

    def _set_radar_mode(self, pid: str, mode: str) -> None:
        env = self._env
        p = env.platforms.get(pid)
        if p is None:
            return
        val = "search_radar" if mode == "search" else "fire_control_radar"
        for e in p.emitters:
            e.role = val
            e.emcon_state = "on"
        cn = "搜索" if mode == "search" else "火控"
        self.command_issued.emit(f"{p.name}：雷达切换为{cn}模式")
        self._rebuild()

    def _emcon_plan(self, pid: str) -> None:
        env = self._env
        p = env.platforms.get(pid)
        if p is None:
            return
        for e in p.emitters:
            e.emcon_state = "off"
        self.command_issued.emit(f"{p.name}：EMCON 计划已执行（本平台雷达全部关机）")
        self._rebuild()

    def _set_roe(self, pid: str, roe: str) -> None:
        env = self._env
        p = env.platforms.get(pid)
        if p is None:
            return
        p.roe = roe
        cn = {"free": "自动开火", "weapons_free": "谨慎开火", "hold": "禁止开火"}.get(roe, roe)
        self.command_issued.emit(f"{p.name}：交战规则 = {cn}")
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
            "询问已记录（单机版不响应，导演/联机模式生效）"))
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

    def _show_waypoint_menu(self, global_pos: QPoint, pid: str, idx: int) -> None:
        menu = QMenu(self)
        menu.addAction("删除此航路点", lambda: self._delete_waypoint(pid, idx))
        menu.exec(global_pos)

    def _delete_waypoint(self, pid: str, idx: int) -> None:
        env = self._env
        wps = env.waypoints.get(pid)
        if wps and 0 <= idx < len(wps):
            del wps[idx]
            if not wps:
                env.waypoints.pop(pid, None)
            self.command_issued.emit(f"已删除航路点 {idx + 1}")
            self._rebuild()

    def _show_map_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction("取消全部航路点", self._clear_all_waypoints)
        menu.addAction("取消全部航路点", self._clear_all_waypoints)
        menu.addAction("区域设置（简化版：清除全部航路点）", self._clear_all_waypoints)
        menu.exec(global_pos)

    def _clear_all_waypoints(self) -> None:
        env = self._env
        for pid in list(self._selected_platform_ids):
            env.clear_waypoints(pid)
        self.command_issued.emit("已取消选中单位的全部航路点")
        self._rebuild()
