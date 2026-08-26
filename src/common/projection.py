"""局部切平面投影：经纬度 <-> 场景坐标。

用于 2D 战术地图显示，中心点为参考点。
x 向东为正，y 向南为正（屏幕坐标）。
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


class LocalProjection:
    def __init__(self, center_lat: float, center_lon: float, px_per_km: float = 2.0):
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.px_per_km = px_per_km
        self._cos_lat = math.cos(math.radians(center_lat))

    def to_xy(self, lat: float, lon: float) -> tuple[float, float]:
        """经纬度转场景坐标（像素，y 向下）。"""
        km_x = EARTH_RADIUS_KM * math.radians(lon - self.center_lon) * self._cos_lat
        km_y = EARTH_RADIUS_KM * math.radians(lat - self.center_lat)
        return km_x * self.px_per_km, -km_y * self.px_per_km

    def km_to_px(self, km: float) -> float:
        return km * self.px_per_km

    def from_xy(self, x: float, y: float) -> tuple[float, float]:
        """场景坐标转经纬度。"""
        km_x = x / self.px_per_km
        km_y = -y / self.px_per_km
        lat = self.center_lat + math.degrees(km_y / EARTH_RADIUS_KM)
        lon = self.center_lon + math.degrees(km_x / (EARTH_RADIUS_KM * self._cos_lat))
        return lat, lon
