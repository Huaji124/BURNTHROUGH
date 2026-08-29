"""地理/地球几何计算。

约定：
- 经纬度均为十进制度（float）
- 方位角：正北 0°，顺时针
- 距离：海里（nm）
"""

from __future__ import annotations

import math

EARTH_RADIUS_NM = 3440.065  # 地球平均半径（海里）
EARTH_RADIUS_M = EARTH_RADIUS_NM * 1852.0


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """大圆距离（海里）。

    对浮点误差做钳位：a 理论上落在 [0, 1]，但在对跖点等边界上可能因舍入
    略微超过 1，直接 asin 会抛出 math domain error。该函数在仿真中每帧被
    调用数千次，必须保证不因边界输入崩溃。
    """
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * EARTH_RADIUS_NM * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """大圆起始方位角（度，正北为 0）。"""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def destination_point(lat: float, lon: float, bearing_deg: float, dist_nm: float) -> tuple[float, float]:
    """从起点出发，沿方位角走指定距离后的位置（海里）。"""
    angular = dist_nm / EARTH_RADIUS_NM
    theta = math.radians(bearing_deg)
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    p2 = math.asin(
        math.sin(p1) * math.cos(angular)
        + math.cos(p1) * math.sin(angular) * math.cos(theta)
    )
    l2 = l1 + math.atan2(
        math.sin(theta) * math.sin(angular) * math.cos(p1),
        math.cos(angular) - math.sin(p1) * math.sin(p2),
    )
    return math.degrees(p2), (math.degrees(l2) + 180.0) % 360.0 - 180.0


def radar_horizon_nm(height_ft: float, target_height_ft: float = 0.0) -> float:
    """雷达视距（海里），输入高度单位英尺。

    公式：Rh = 1.23 * (sqrt(h_radar) + sqrt(h_target))
    """
    return 1.23 * (math.sqrt(max(height_ft, 0.0)) + math.sqrt(max(target_height_ft, 0.0)))


def relative_bearing_deg(own_lat: float, own_lon: float, own_heading_deg: float,
                         target_lat: float, target_lon: float) -> float:
    """目标相对方位（度）：0° 为舰首正前方，右舷 90°。"""
    true = initial_bearing_deg(own_lat, own_lon, target_lat, target_lon)
    return (true - own_heading_deg + 360.0) % 360.0
