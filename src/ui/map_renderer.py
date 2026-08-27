"""地图绘制辅助模块。

将 MapWidget 中与“画什么”相关的逻辑抽离出来，使 MapWidget 专注交互。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from common.projection import LocalProjection
from core.environment import Environment, Platform


class WaypointRect(QGraphicsRectItem):
    """可拖拽的航路点标记。"""

    def __init__(self, rect, pid: str, idx: int, on_moved):
        super().__init__(rect)
        self._pid = pid
        self._idx = idx
        self._on_moved = on_moved
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
                      QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setData(0, f"waypoint::{pid}::{idx}")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._suppress = True

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and not self._suppress:
            self._on_moved(self._pid, self._idx, self.pos())
        return super().itemChange(change, value)


def draw_coastlines(scene: QGraphicsScene, env: Environment, proj: LocalProjection) -> None:
    """绘制简化海岸线多边形。"""
    for coast in env.coastlines:
        pts = [QPointF(*proj.to_xy(lat, lon)) for lat, lon in coast.get("points", [])]
        if len(pts) < 3:
            continue
        poly = scene.addPolygon(QPolygonF(pts))
        poly.setPen(QPen(QColor("#7a9e7f"), 1))
        poly.setBrush(QBrush(QColor(93, 109, 126, 90)))
        poly.setZValue(0)
        label = QGraphicsSimpleTextItem(coast.get("name", ""))
        label.setBrush(QBrush(QColor("#5d6d7e")))
        label.setFont(QFont("SansSerif", 8))
        label.setPos(pts[0].x(), pts[0].y())
        label.setZValue(1)
        scene.addItem(label)


def draw_terrain_obstacles(scene: QGraphicsScene, env: Environment, proj: LocalProjection) -> None:
    """绘制地形障碍物（岛屿/高地）。"""
    for ob in env.terrain_obstacles:
        x, y = proj.to_xy(ob["lat"], ob["lon"])
        r = proj.km_to_px(ob.get("radius_km", 20.0))
        poly = QPolygonF()
        steps = 24
        for i in range(steps):
            a = 2.0 * math.pi * i / steps
            poly.append(QPointF(x + r * math.cos(a), y + r * math.sin(a)))
        item = scene.addPolygon(poly)
        item.setPen(QPen(QColor("#7f8c8d"), 1, Qt.PenStyle.SolidLine))
        item.setBrush(QBrush(QColor(127, 140, 141, 60)))
        item.setZValue(0)
        item.setToolTip(f"地形 {ob.get('height_ft',500)}$ft")
        label = QGraphicsSimpleTextItem("地形")
        label.setBrush(QBrush(QColor("#95a5a6")))
        label.setFont(QFont("SansSerif", 8))
        label.setPos(x - 12, y)
        label.setZValue(1)
        scene.addItem(label)


def draw_map_background(scene: QGraphicsScene, env: Environment, proj: LocalProjection) -> None:
    """绘制海洋背景 + 陆地多边形。"""
    # 海洋底色：尽量覆盖世界范围
    x1, y1 = proj.to_xy(-90, -180)
    x2, y2 = proj.to_xy(90, 180)
    ocean = scene.addRect(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1))
    ocean.setBrush(QBrush(QColor(179, 212, 240)))
    ocean.setPen(Qt.NoPen)
    ocean.setZValue(-2)
    for poly in getattr(env, 'world_land', []):
        pts = [QPointF(*proj.to_xy(lat, lon)) for lat, lon in poly if isinstance(lat,(int,float))]
        if len(pts) < 3:
            continue
        land = scene.addPolygon(QPolygonF(pts))
        land.setPen(QPen(QColor("#7a9e7f"), 1))
        land.setBrush(QBrush(QColor(176, 212, 176, 180)))
        land.setZValue(-1)
    for coast in env.coastlines:
        pts = [QPointF(*proj.to_xy(lat, lon)) for lat, lon in coast.get("points", [])]
        if len(pts) < 3:
            continue
        poly = scene.addPolygon(QPolygonF(pts))
        poly.setPen(QPen(QColor("#7a9e7f"), 1))
        poly.setBrush(QBrush(QColor(176, 212, 176, 180)))
        poly.setZValue(-1)
        label = QGraphicsSimpleTextItem(coast.get("name", ""))
        label.setBrush(QBrush(QColor("#5d6d7e")))
        label.setFont(QFont("SansSerif", 8))
        label.setPos(pts[0].x(), pts[0].y())
        label.setZValue(0)
        scene.addItem(label)


def screen_fixed(item):
    """让图标/文字在缩放时保持屏幕固定大小。"""
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
    return item


def draw_grid(scene: QGraphicsScene, proj: LocalProjection) -> None:
    """绘制经纬度网格线。"""
    c_lat, c_lon = proj.center_lat, proj.center_lon
    span = 10.0
    step = 2.0
    pen = QPen(QColor("#9db4c7"), 1, Qt.PenStyle.SolidLine)
    font = QFont("SansSerif", 9)

    lat = math.floor((c_lat - span) / step) * step
    while lat <= c_lat + span:
        x1, y1 = proj.to_xy(lat, c_lon - span)
        x2, y2 = proj.to_xy(lat, c_lon + span)
        line = QGraphicsLineItem(x1, y1, x2, y2)
        line.setPen(pen)
        line.setZValue(0)
        scene.addItem(line)
        label = QGraphicsSimpleTextItem(f"{lat:.0f}°N" if lat >= 0 else f"{-lat:.0f}°S")
        label.setBrush(QBrush(QColor("#5d6d7e")))
        label.setFont(font)
        label.setPos(x1 + 3, y1 + 3)
        label.setZValue(0)
        scene.addItem(label)
        lat += step

    lon = math.floor((c_lon - span) / step) * step
    while lon <= c_lon + span:
        x1, y1 = proj.to_xy(c_lat - span, lon)
        x2, y2 = proj.to_xy(c_lat + span, lon)
        line = QGraphicsLineItem(x1, y1, x2, y2)
        line.setPen(pen)
        line.setZValue(0)
        scene.addItem(line)
        label = QGraphicsSimpleTextItem(f"{lon:.0f}°E" if lon >= 0 else f"{-lon:.0f}°W")
        label.setBrush(QBrush(QColor("#5d6d7e")))
        label.setFont(font)
        label.setPos(x1 + 3, y1 + 3)
        label.setZValue(0)
        scene.addItem(label)
        lon += step


def draw_waypoints(scene: QGraphicsScene, env: Environment, proj: LocalProjection,
                   on_moved) -> list[WaypointRect]:
    """绘制航路点，返回可交互的矩形列表。"""
    if not env.waypoints:
        return []
    color = QColor("#e67e22")
    waypoint_items: list[WaypointRect] = []
    for pid, wps in env.waypoints.items():
        p = env.platforms.get(pid)
        if p is None:
            continue
        pts = []
        if wps:
            px, py = proj.to_xy(p.latitude, p.longitude)
            pts.append((px, py))
        for i, (lat, lon) in enumerate(wps):
            x, y = proj.to_xy(lat, lon)
            pts.append((x, y))
            rect = WaypointRect(QRectF(-5, -5, 10, 10), pid, i, on_moved)
            rect.setPos(x, y)
            rect._suppress = False
            rect.setPen(QPen(color, 1.5))
            rect.setBrush(QBrush(color.darker(150)))
            rect.setZValue(14)
            rect.setToolTip(f"航路点 {i+1}（拖拽移动，右键删除）")
            scene.addItem(rect)
            screen_fixed(rect)
            waypoint_items.append(rect)
            label = QGraphicsSimpleTextItem(f"WP{i+1}")
            label.setBrush(QBrush(color))
            label.setFont(QFont("SansSerif", 7))
            label.setPos(x + 6, y - 6)
            label.setZValue(15)
            scene.addItem(label)
            screen_fixed(label)
            screen_fixed(label)
        if len(pts) >= 2:
            for i in range(len(pts) - 1):
                line = QGraphicsLineItem(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
                line.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
                line.setZValue(1)
                scene.addItem(line)
    return waypoint_items


def draw_platform(scene: QGraphicsScene, platform: Platform, proj: LocalProjection,
                  side_colors: dict[str, QColor], platform_items: dict[str, QGraphicsItem]) -> None:
    """绘制平台图标与名称。"""
    x, y = proj.to_xy(platform.latitude, platform.longitude)
    size = 10.0
    color = side_colors.get(platform.side, QColor("#95a5a6"))
    pen = QPen(color, 2)
    brush = QBrush(color.darker(160))

    if not platform.alive:
        pen = QPen(QColor("#60666e"), 2)
        brush = QBrush(QColor("#3a3f46"))
    if platform.kind == "aircraft":
        pts = [QPointF(0, -size * 0.7), QPointF(-size * 0.7, size * 0.6),
               QPointF(0, size * 0.25), QPointF(size * 0.7, size * 0.6)]
        item = scene.addPolygon(pts, pen, brush)
    else:
        item = scene.addRect(-size / 2, -size / 2, size, size, pen, brush)
    item.setPos(x, y)
    item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                  QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                  QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
    item.setData(0, f"platform::{platform.id}")
    item.setZValue(10)
    item.setToolTip(platform.name)
    screen_fixed(item)
    platform_items[platform.id] = item

    if platform.kind == "aircraft":
        hdg = math.radians(platform.heading_deg)
        hx = math.sin(hdg) * 16
        hy = -math.cos(hdg) * 16
        heading_line = QGraphicsLineItem(0, 0, hx, hy)
        heading_line.setPen(QPen(color, 1, Qt.PenStyle.SolidLine))
        heading_line.setZValue(9)
        heading_line.setPos(x, y)
        scene.addItem(heading_line)
        screen_fixed(heading_line)

    label_text = platform.name if platform.alive else f"{platform.name} (被击毁)"
    label = QGraphicsSimpleTextItem(label_text)
    label.setBrush(QBrush(color if platform.alive else QColor("#60666e")))
    label.setFont(QFont("SansSerif", 9, QFont.Weight.Bold))
    label.setPos(x + 8, y - 6)
    label.setZValue(11)
    scene.addItem(label)
    screen_fixed(label)


def draw_ew_circles(scene: QGraphicsScene, env: Environment, proj: LocalProjection,
                    side: str | None = None) -> None:
    """绘制雷达无干扰圈、干扰后圈、烧穿圈与干扰连线。"""
    for platform in env.platforms.values():
        if side is not None and platform.side != side:
            continue
        for emitter in platform.emitters:
            if emitter.emcon_state != "on":
                continue
            if emitter.role not in ("multifunction_radar", "search_radar", "fire_control_radar"):
                continue
            # Phase 3：使用全局干扰资源分配结果
            assignment = env.assign_jammers()
            jammer_id = assignment.get(emitter.id)
            jammer = None
            if jammer_id is not None:
                for other in env.platforms.values():
                    for j in other.jammers:
                        if j.id == jammer_id:
                            jammer = j
                            break
            result = env.evaluate_radar_with_jamming(
                emitter, jammer, rcs_m2=1000.0, bandwidth_hz=1_000_000,
                noise_figure=5.0, loss=6.0, snr_min_db=13.0)
            x, y = proj.to_xy(platform.latitude, platform.longitude)
            unjammed_km = result["un-jammed_range_km"] if jammer else result["detection_range_km"]
            draw_circle(scene, proj, x, y, unjammed_km, QColor("#f1c40f"),
                        "无干扰探测圈", dashed=True)
            if jammer:
                draw_circle(scene, proj, x, y, result["detection_range_km"],
                            QColor("#e67e22"), "干扰后探测圈", dashed=False)
                draw_circle(scene, proj, x, y, result["burn_through_km"],
                            QColor("#e74c3c"), "烧穿圈", dashed=True)
                jp = env.find_jammer_platform(jammer)
                if jp is not None:
                    jx, jy = proj.to_xy(jp.latitude, jp.longitude)
                    line = QGraphicsLineItem(jx, jy, x, y)
                    line.setPen(QPen(QColor("#9b59b6"), 2, Qt.PenStyle.DashLine))
                    line.setZValue(2)
                    scene.addItem(line)
                    mid = QGraphicsSimpleTextItem("干扰")
                    mid.setBrush(QBrush(QColor("#9b59b6")))
                    mid.setFont(QFont("SansSerif", 8))
                    mid.setPos((jx + x) / 2 + 4, (jy + y) / 2 - 4)
                    mid.setZValue(3)
                    scene.addItem(mid)


def draw_jammer_sectors(scene: QGraphicsScene, env: Environment, proj: LocalProjection,
                        side: str | None = None) -> None:
    """绘制有向干扰机的干扰扇区。"""
    for platform in env.platforms.values():
        if side is not None and platform.side != side:
            continue
        if not platform.alive:
            continue
        for jammer in platform.jammers:
            if jammer.emcon_state != "on" or jammer.sector_half_deg >= 180.0:
                continue
            x, y = proj.to_xy(platform.latitude, platform.longitude)
            radius_px = proj.km_to_px(200.0)
            heading = math.radians(platform.heading_deg)
            half = math.radians(jammer.sector_half_deg)

            def pt(angle_rad, x=x, y=y, radius_px=radius_px):
                return QPointF(x + math.sin(angle_rad) * radius_px,
                               y - math.cos(angle_rad) * radius_px)
            poly = QPolygonF([QPointF(x, y),
                              pt(heading - half),
                              pt(heading - half * 0.5),
                              pt(heading),
                              pt(heading + half * 0.5),
                              pt(heading + half)])
            sector = scene.addPolygon(poly)
            sector.setPen(QPen(QColor(155, 89, 182, 120), 1))
            sector.setBrush(QBrush(QColor(155, 89, 182, 40)))
            sector.setZValue(1)
            label = QGraphicsSimpleTextItem("干扰扇区")
            label.setBrush(QBrush(QColor("#9b59b6")))
            label.setFont(QFont("SansSerif", 8))
            label.setPos(pt(heading).x(), pt(heading).y())
            label.setZValue(3)
            scene.addItem(label)
            screen_fixed(label)
            screen_fixed(label)


def draw_ir_contacts(scene: QGraphicsScene, env: Environment, proj: LocalProjection,
                      side: str | None = None) -> None:
    """绘制红外/视觉接触线。"""
    for own_id, c_map in getattr(env, "ir_contacts", {}).items():
        own = env.platforms.get(own_id)
        if own is None:
            continue
        if side is not None and own.side != side:
            continue
        for contact in c_map.values():
            target = env.platforms.get(contact.emitter_id)
            if target is None:
                continue
            x1, y1 = proj.to_xy(own.latitude, own.longitude)
            x2, y2 = proj.to_xy(target.latitude, target.longitude)
            color = QColor("#f39c12")
            pen = QPen(color, 1.0)
            pen.setStyle(Qt.PenStyle.DashLine if contact.is_memory else Qt.PenStyle.SolidLine)
            pen.setCosmetic(True)
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(pen)
            line.setZValue(4)
            scene.addItem(line)
            label = QGraphicsSimpleTextItem("红外接触")
            label.setBrush(QBrush(color))
            label.setFont(QFont("SansSerif", 8))
            label.setPos((x1 + x2) / 2, (y1 + y2) / 2 + 4)
            label.setZValue(4)
            scene.addItem(label)
            screen_fixed(label)
            screen_fixed(label)


def draw_sonar_contacts(scene: QGraphicsScene, env: Environment, proj: LocalProjection,
                         side: str | None = None) -> None:
    """绘制声呐接触线。"""
    for own_id, c_map in getattr(env, "sonar_contacts", {}).items():
        own = env.platforms.get(own_id)
        if own is None:
            continue
        if side is not None and own.side != side:
            continue
        for contact in c_map.values():
            target = env.platforms.get(contact.emitter_id)
            if target is None:
                continue
            x1, y1 = proj.to_xy(own.latitude, own.longitude)
            x2, y2 = proj.to_xy(target.latitude, target.longitude)
            color = QColor("#2ecc71")
            pen = QPen(color, 1.0)
            pen.setStyle(Qt.PenStyle.DashLine if contact.is_memory else Qt.PenStyle.SolidLine)
            pen.setCosmetic(True)
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(pen)
            line.setZValue(4)
            scene.addItem(line)
            label = QGraphicsSimpleTextItem("声呐接触")
            label.setBrush(QBrush(color))
            label.setFont(QFont("SansSerif", 8))
            label.setPos((x1 + x2) / 2, (y1 + y2) / 2 + 4)
            label.setZValue(4)
            scene.addItem(label)
            screen_fixed(label)
            screen_fixed(label)


def draw_esm_contacts(scene: QGraphicsScene, env: Environment, proj: LocalProjection,
                      contact_items: dict[str, list[QGraphicsItem]],
                      side: str | None = None) -> None:
    """绘制 ESM 辐射源接触：测向线、标记点。"""
    if not env.contacts:
        return
    for own_id, contact_map in env.contacts.items():
        own = env.platforms.get(own_id)
        if own is None:
            continue
        if side is not None and own.side != side:
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
            scene.addItem(line)

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
            scene.addItem(label)
            screen_fixed(label)
            screen_fixed(label)

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
            scene.addItem(marker)
            screen_fixed(marker)
            screen_fixed(marker)
            contact_items.setdefault(f"{own_id}::{key}", []).append(marker)


def draw_false_targets(scene: QGraphicsScene, env: Environment, proj: LocalProjection,
                        side: str | None = None) -> None:
    """绘制欺骗干扰产生的假目标。"""
    for radar_id, targets in env.false_contacts.items():
        radar = env.platforms.get(radar_id)
        if side is not None and (radar is None or radar.side != side):
            continue
        for t in targets:
            if not t.active:
                continue
            x, y = proj.to_xy(t.latitude, t.longitude)
            r = 8.0
            circle = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
            circle.setPen(QPen(QColor("#d35400"), 1.5, Qt.PenStyle.DashLine))
            circle.setBrush(QBrush(QColor(211, 84, 0, 50)))
            circle.setZValue(7)
            circle.setToolTip(f"假目标：{t.technique}（由干扰机 {t.jammer_id} 生成）")
            scene.addItem(circle)
            # 交叉线
            line1 = QGraphicsLineItem(x - r, y - r, x + r, y + r)
            line2 = QGraphicsLineItem(x - r, y + r, x + r, y - r)
            pen = QPen(QColor("#e67e22"), 1.2)
            line1.setPen(pen)
            line2.setPen(pen)
            line1.setZValue(7)
            line2.setZValue(7)
            scene.addItem(line1)
            scene.addItem(line2)
            label = QGraphicsSimpleTextItem("假目标")
            label.setBrush(QBrush(QColor("#e67e22")))
            label.setFont(QFont("SansSerif", 8))
            label.setPos(x + 10, y - 8)
            label.setZValue(8)
            scene.addItem(label)


def draw_radar_contacts(scene: QGraphicsScene, env: Environment, proj: LocalProjection,
                         side: str | None = None) -> None:
    """绘制雷达接触线。"""
    for own_id, radar_map in getattr(env, "radar_contacts", {}).items():
        own = env.platforms.get(own_id)
        if own is None:
            continue
        if side is not None and own.side != side:
            continue
        for contact in radar_map.values():
            target = env.platforms.get(contact.emitter_id)
            if target is None:
                continue
            x1, y1 = proj.to_xy(own.latitude, own.longitude)
            x2, y2 = proj.to_xy(target.latitude, target.longitude)
            color = QColor("#7f8c8d") if contact.is_memory else QColor("#2980b9")
            pen = QPen(color, 1.0)
            pen.setStyle(Qt.PenStyle.DashLine if contact.is_memory else Qt.PenStyle.SolidLine)
            pen.setCosmetic(True)
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(pen)
            line.setZValue(4)
            line.setToolTip(f"雷达接触: {target.name} / {contact.range_m/1852.0:.1f}nm")
            scene.addItem(line)
            label = QGraphicsSimpleTextItem("雷达接触")
            label.setBrush(QBrush(color))
            label.setFont(QFont("SansSerif", 8))
            label.setPos((x1 + x2) / 2, (y1 + y2) / 2 - 6)
            label.setZValue(4)
            scene.addItem(label)
            screen_fixed(label)
            screen_fixed(label)


def draw_orders(scene: QGraphicsScene, env: Environment, proj: LocalProjection,
                side: str | None = None) -> None:
    """绘制攻击指令线。"""
    for order in env.orders:
        if order["kind"] != "attack":
            continue
        attacker = env.platforms.get(order["attacker"])
        target = env.platforms.get(order["target"])
        if attacker is None or target is None:
            continue
        if side is not None and attacker.side != side:
            continue
        x1, y1 = proj.to_xy(attacker.latitude, attacker.longitude)
        x2, y2 = proj.to_xy(target.latitude, target.longitude)
        line = QGraphicsLineItem(x1, y1, x2, y2)
        line.setPen(QPen(QColor("#e74c3c"), 1.5, Qt.PenStyle.DashLine))
        line.setZValue(8)
        scene.addItem(line)
        label = QGraphicsSimpleTextItem("攻击")
        label.setBrush(QBrush(QColor("#e74c3c")))
        label.setFont(QFont("SansSerif", 8))
        label.setPos((x1 + x2) / 2, (y1 + y2) / 2 - 10)
        label.setZValue(9)
        scene.addItem(label)


def draw_missiles(scene: QGraphicsScene, env: Environment, proj: LocalProjection,
                   side: str | None = None) -> None:
    """绘制飞行中的反辐射导弹。"""
    for missile in env.missiles:
        if not missile.active:
            continue
        if side is not None:
            attacker = env.platforms.get(missile.attacker_id)
            if attacker is None or attacker.side != side:
                continue
        x, y = proj.to_xy(missile.lat, missile.lon)
        r = 5.0
        pts = [QPointF(0, -r), QPointF(-r * 0.8, r * 0.8),
               QPointF(0, r * 0.3), QPointF(r * 0.8, r * 0.8)]
        item = scene.addPolygon(pts)
        _pen = QPen(QColor("#ffffff"), 1)
        _pen.setCosmetic(True)
        item.setPen(_pen)
        item.setBrush(QBrush(QColor("#e74c3c")))
        item.setZValue(15)
        item.setPos(x, y)
        target_name = env.platforms.get(missile.target_id).name if missile.target_id in env.platforms else missile.target_id
        item.setToolTip(f"{missile.name} -> {target_name}")
        screen_fixed(item)
        label = QGraphicsSimpleTextItem("ARM")
        label.setBrush(QBrush(QColor("#e74c3c")))
        label.setFont(QFont("SansSerif", 7, QFont.Weight.Bold))
        label.setPos(x + 6, y - 6)
        label.setZValue(16)
        scene.addItem(label)


def draw_circle(scene: QGraphicsScene, proj: LocalProjection,
                x: float, y: float, radius_km: float,
                color: QColor, label: str, dashed: bool) -> None:
    """绘制探测/烧穿距离圈。"""
    r_px = max(proj.km_to_px(radius_km), 1.0)
    circle = QGraphicsEllipseItem(x - r_px, y - r_px, 2 * r_px, 2 * r_px)
    pen = QPen(color, 1.5)
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    pen.setCosmetic(True)
    circle.setPen(pen)
    circle.setBrush(QBrush(QColor(0, 0, 0, 0)))
    circle.setZValue(1)
    scene.addItem(circle)

    label_item = QGraphicsSimpleTextItem(f"{label} {radius_km:.0f} km")
    label_item.setBrush(QBrush(color))
    label_item.setFont(QFont("SansSerif", 8))
    label_item.setPos(x + r_px * 0.7, y - r_px * 0.7)
    label_item.setZValue(3)
    scene.addItem(label_item)


def find_jammer_against(env: Environment, victim_platform: Platform, emitter) -> object | None:
    """寻找当前覆盖该雷达频段且开机的干扰机（简单规则）。"""
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


def draw_legend(scene: QGraphicsScene, proj: LocalProjection, side: str | None = None) -> None:
    """绘制图例。"""
    items = [
        ("#ecf0f1", f"视角: {side or '全知'}"),
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
        scene.addItem(line)
        label = QGraphicsSimpleTextItem(text)
        label.setBrush(QBrush(QColor("#2c3e50")))
        label.setFont(font)
        label.setPos(x + 28, y - 4)
        label.setZValue(20)
        scene.addItem(label)
        y += 20
