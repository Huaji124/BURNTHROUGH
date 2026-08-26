"""模拟环境：承载平台、辐射源、干扰机，并计算传播链路。

Phase 2：
- 平台运动（直线/绕飞）
- ESM 截获模型（视距 + 灵敏度 + 扫描截获概率）
- 辐射源接触管理（记忆接触、多站交叉定位）
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from common.geo import destination_point, haversine_nm, initial_bearing_deg

from . import propagation
from .contact import Contact
from .emitter import Emitter
from .jammer import Jammer
from .receiver import Receiver


@dataclass
class Platform:
    id: str
    name: str
    side: str                         # blue / red / neutral
    kind: str                         # ship / aircraft / submarine
    latitude: float
    longitude: float
    altitude_ft: float = 0.0          # 飞机高度；舰船/地面为 0 或天线高度
    heading_deg: float = 0.0
    speed_kt: float = 0.0
    cruise_speed_kt: float = 0.0    # 巡航速度：航路点任务中用于自动恢复
    emitters: list[Emitter] = field(default_factory=list)
    receivers: list[Receiver] = field(default_factory=list)
    jammers: list[Jammer] = field(default_factory=list)
    weapons: list[str] = field(default_factory=list)   # 武器显示（Phase 6 前为占位）
    # 绕飞轨道（可选）：绕某点做圆周运动
    orbit_center_lat: float | None = None
    orbit_center_lon: float | None = None
    orbit_radius_km: float | None = None
    orbit_direction: int = 1          # 1 逆时针（正横右转），-1 顺时针


@dataclass
class Environment:
    """模拟环境（Phase 2）。

    职责：
    - 注册平台/发射机/接收机/干扰机
    - 时间推进（运动、ESM 截获、接触管理）
    - 传播链路计算
    """

    platforms: dict[str, Platform] = field(default_factory=dict)
    time_s: float = 0.0
    contacts: dict[str, dict[str, Contact]] = field(default_factory=dict)
    waypoints: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    orders: list[dict] = field(default_factory=list)  # 攻击/移动等指令
    rng: random.Random = field(default_factory=lambda: random.Random(12345))
    memory_ttl_s: float = 20.0        # 信号丢失后保留记忆接触的时长
    contact_ttl_s: float = 60.0       # 接触总生存时间

    # ------------------------------------------------------------------
    # 基础注册/查询
    # ------------------------------------------------------------------
    def add_platform(self, platform: Platform) -> None:
        self.platforms[platform.id] = platform

    # ------------------------------------------------------------------
    # 指令与航路点
    # ------------------------------------------------------------------
    def add_move_order(self, platform_id: str, lat: float, lon: float,
                       append: bool = False) -> None:
        """为平台添加移动航路点。append=False 时替换为单次航路点。"""
        platform = self.platforms.get(platform_id)
        if platform is None:
            return
        if platform.speed_kt <= 0 and platform.cruise_speed_kt > 0:
            platform.speed_kt = platform.cruise_speed_kt
        # 进入人工航路点后，取消绕飞轨道
        platform.orbit_center_lat = None
        platform.orbit_center_lon = None
        platform.orbit_radius_km = None
        if append and platform_id in self.waypoints:
            self.waypoints[platform_id].append((lat, lon))
        else:
            self.waypoints[platform_id] = [(lat, lon)]
        self.orders.append({"kind": "move", "platform": platform_id,
                            "lat": lat, "lon": lon, "time": self.time_s})

    def clear_waypoints(self, platform_id: str) -> None:
        self.waypoints.pop(platform_id, None)

    def add_attack_order(self, attacker_id: str, target_id: str) -> None:
        self.orders.append({"kind": "attack", "attacker": attacker_id,
                            "target": target_id, "time": self.time_s})

    def find_platform_by_source_id(self, source_id: str) -> Platform | None:
        for p in self.platforms.values():
            for e in p.emitters:
                if e.id == source_id:
                    return p
            for j in p.jammers:
                if j.id == source_id:
                    return p
        return None

    def all_emitters(self) -> list[Emitter]:
        result = []
        for p in self.platforms.values():
            result.extend(p.emitters)
        return result

    def all_jammers(self) -> list[Jammer]:
        result = []
        for p in self.platforms.values():
            result.extend(p.jammers)
        return result

    def all_receivers(self) -> list[Receiver]:
        result = []
        for p in self.platforms.values():
            result.extend(p.receivers)
        return result

    def active_emitters(self) -> list[Emitter]:
        return [e for e in self.all_emitters() if e.is_emitting]

    def active_jammers(self) -> list[Jammer]:
        return [j for j in self.all_jammers() if j.is_jamming]

    # ------------------------------------------------------------------
    # 时间推进
    # ------------------------------------------------------------------
    def step(self, dt_s: float = 1.0) -> None:
        """推进一帧：运动 -> ESM 截获 -> 接触老化 -> 交叉定位。"""
        self.time_s += dt_s
        self.step_motion(dt_s)
        self.update_esm(dt_s)
        self.update_contact_aging()
        self.cross_fix_contacts()

    def step_motion(self, dt_s: float) -> None:
        """运动模型：优先沿航路点，其次绕飞轨道，最后直线。"""
        for p in self.platforms.values():
            if p.speed_kt <= 0:
                continue
            dist_nm = p.speed_kt * dt_s / 3600.0

            # 1) 航路点导航
            if self.waypoints.get(p.id):
                wp_lat, wp_lon = self.waypoints[p.id][0]
                brg = initial_bearing_deg(p.latitude, p.longitude, wp_lat, wp_lon)
                dist_to_wp = haversine_nm(p.latitude, p.longitude, wp_lat, wp_lon)
                p.heading_deg = brg
                if dist_to_wp <= dist_nm:
                    p.latitude, p.longitude = wp_lat, wp_lon
                    self.waypoints[p.id].pop(0)
                    if not self.waypoints[p.id]:
                        self.waypoints.pop(p.id, None)
                        p.speed_kt = 0.0  # 到达终点后停住
                else:
                    p.latitude, p.longitude = destination_point(
                        p.latitude, p.longitude, brg, dist_nm)
                continue

            # 2) 绕飞轨道
            if p.orbit_center_lat is not None and p.orbit_radius_km is not None:
                bearing_to_center = initial_bearing_deg(p.latitude, p.longitude,
                                                        p.orbit_center_lat, p.orbit_center_lon)
                tangent = (bearing_to_center + 90.0 * p.orbit_direction + 360.0) % 360.0
                p.heading_deg = tangent
            else:
                tangent = p.heading_deg

            p.latitude, p.longitude = destination_point(
                p.latitude, p.longitude, tangent, dist_nm)

    # ------------------------------------------------------------------
    # ESM 截获与接触管理
    # ------------------------------------------------------------------
    def update_esm(self, dt_s: float) -> None:
        """每帧更新所有 ESM/RWR 接收机对辐射源的截获。"""
        for own in self.platforms.values():
            for esm in own.receivers:
                if esm.kind not in ("esm", "rwr"):
                    continue
                for other in self.platforms.values():
                    if other.id == own.id:
                        continue
                    if other.side == own.side:
                        continue  # Phase 2：只截获跨阵营辐射源
                    for source in self._active_sources_of(other):
                        result = self._intercept_source(esm, own, other, source, dt_s)
                        if result is None:
                            continue
                        self._update_contact(own, esm, other, source, result)

    def _active_sources_of(self, platform: Platform) -> list[tuple]:
        """返回平台上所有正在辐射的信号源。

        每个源为 (source, freq_hz, power_w, gain_linear, source_id, source_name)
        """
        sources: list[tuple] = []
        for e in platform.emitters:
            if e.is_emitting:
                sources.append((e, e.center_freq_hz, e.peak_power_w,
                                e.gain_linear, e.id, e.name))
        for j in platform.jammers:
            if j.is_jamming:
                freq = (j.freq_min_hz + j.freq_max_hz) / 2.0
                sources.append((j, freq, j.power_w, j.gain_linear, j.id, j.name))
        return sources

    def _intercept_source(self, esm: Receiver, own: Platform, other: Platform,
                          source: tuple, dt_s: float) -> dict | None:
        """计算 ESM 对某信号源的单帧截获结果。"""
        src, freq_hz, power_w, gain, source_id, source_name = source

        r_m = _distance_m(own, other)
        horizon_nm = 1.23 * (math.sqrt(max(own.altitude_ft, 0.0)) +
                             math.sqrt(max(other.altitude_ft, 0.0)))
        horizon_m = horizon_nm * 1852.0
        if r_m > horizon_m:
            return None

        if not esm.covers_frequency(freq_hz):
            return None

        wavelength = propagation.wavelength_m(freq_hz)
        power_dbm = propagation.esm_received_power_dbm(
            power_w, gain, esm.gain_linear, wavelength, r_m)
        if power_dbm < esm.sensitivity_dbm:
            return None

        # 扫描截获概率：扫描雷达需要波束扫过 ESM；干扰机等常开信号概率为 1
        p = self._scan_intercept_probability(src, dt_s)
        if p < 1.0 and self.rng.random() > p:
            return None

        true_bearing = initial_bearing_deg(own.latitude, own.longitude,
                                           other.latitude, other.longitude)
        # 测向误差
        if esm.df_accuracy_deg is not None and esm.df_accuracy_deg > 0:
            bearing = (true_bearing + self.rng.gauss(0.0, esm.df_accuracy_deg) + 360.0) % 360.0
        else:
            bearing = true_bearing

        identified = source_id in esm.param_library
        return {
            "source_id": source_id,
            "source_name": source_name,
            "bearing_deg": bearing,
            "true_bearing_deg": true_bearing,
            "range_km": r_m / 1000.0,
            "power_dbm": power_dbm,
            "identified": identified,
            "confidence": 0.9 if identified else 0.35,
        }

    @staticmethod
    def _scan_intercept_probability(source, dt_s: float) -> float:
        """根据辐射源扫描方式估计 dt 时间内的截获概率。"""
        scan_period = getattr(source, "scan_period_s", None)
        beam_width = getattr(source, "beam_width_deg", None)
        if scan_period is None or scan_period <= 0:
            return 1.0  # 常开/干扰
        scans = dt_s / scan_period
        if beam_width is None or beam_width <= 0:
            return min(1.0, scans)
        # 每转主瓣扫过 ESM 的概率约 beam_width/360
        return min(1.0, scans * max(beam_width / 360.0, 0.05))

    def _update_contact(self, own: Platform, esm: Receiver, other: Platform,
                        source: tuple, result: dict) -> None:
        key = result["source_id"]
        if own.id not in self.contacts:
            self.contacts[own.id] = {}

        contact = self.contacts[own.id].get(key)
        if contact is None:
            contact = Contact(
                id=f"{own.id}-{key}",
                kind="emitter_contact",
                own_platform_id=own.id,
                time_s=self.time_s,
                emitter_id=result["source_id"],
                emitter_name=result["source_name"],
            )
            self.contacts[own.id][key] = contact

        contact.bearing_deg = result["bearing_deg"]
        contact.time_s = self.time_s
        contact.last_update_s = self.time_s
        contact.is_memory = False
        contact.target_platform_id = other.id
        contact.confidence = result["confidence"]
        contact.extra = {
            "power_dbm": result["power_dbm"],
            "range_km": result["range_km"],
            "identified": result["identified"],
        }

    def update_contact_aging(self) -> None:
        """接触老化：信号丢失后进入记忆，超时后删除。"""
        for own_id, contact_map in list(self.contacts.items()):
            for key, contact in list(contact_map.items()):
                age = self.time_s - contact.last_update_s
                if age > self.contact_ttl_s:
                    del contact_map[key]
                elif age > self.memory_ttl_s:
                    contact.is_memory = True

    def cross_fix_contacts(self) -> None:
        """多站交叉定位：对同一辐射源的多条测向线求交点。"""
        # 按阵营分组平台，对每个源收集测向线
        for own_id, contact_map in self.contacts.items():
            for key, contact in contact_map.items():
                contact.latitude = None
                contact.longitude = None
                if contact.is_memory or contact.bearing_deg is None:
                    continue
                own_platform = self.platforms.get(own_id)
                if own_platform is None:
                    continue
                bearings = [(own_platform.latitude, own_platform.longitude,
                             contact.bearing_deg)]
                for other_id, other_map in self.contacts.items():
                    if other_id == own_id:
                        continue
                    other_contact = other_map.get(key)
                    if other_contact is None or other_contact.is_memory:
                        continue
                    if other_contact.bearing_deg is None:
                        continue
                    other_platform = self.platforms.get(other_id)
                    if other_platform is None:
                        continue
                    bearings.append((other_platform.latitude, other_platform.longitude,
                                     other_contact.bearing_deg))
                if len(bearings) >= 2:
                    lat, lon = triangulate_bearings(bearings)
                    if lat is not None:
                        contact.latitude = lat
                        contact.longitude = lon

    # ------------------------------------------------------------------
    # 传播链路（Phase 1 已有）
    # ------------------------------------------------------------------
    def evaluate_radar_with_jamming(self, emitter: Emitter, jammer: Jammer | None,
                                    rcs_m2: float = 1000.0,
                                    bandwidth_hz: float = 1e6,
                                    noise_figure: float = 5.0,
                                    loss: float = 6.0,
                                    snr_min_db: float = 13.0) -> dict:
        """计算某部雷达在有/无指定干扰机时的探测与烧穿距离。"""
        snr_min = 10.0 ** (snr_min_db / 10.0)
        wavelength = propagation.wavelength_m(emitter.center_freq_hz)
        r_max = propagation.radar_max_range_m(
            emitter.peak_power_w, emitter.gain_linear, emitter.gain_linear,
            rcs_m2, wavelength, bandwidth_hz, noise_figure, loss, snr_min,
        )
        if jammer is None:
            return {
                "emitter": emitter.id,
                "jammer": None,
                "detection_range_km": r_max / 1000.0,
                "burn_through_km": None,
                "js_at_burnthrough": None,
            }

        rj = _distance_m(self._platform_of(jammer), self._platform_of(emitter))
        r_bt = propagation.burn_through_standoff_m(
            emitter.peak_power_w, emitter.gain_linear, rcs_m2,
            jammer.power_w, jammer.gain_linear, bandwidth_hz, jammer.bandwidth_hz,
            rj,
        )
        effective_range = min(r_max, r_bt)
        return {
            "emitter": emitter.id,
            "jammer": jammer.id,
            "jammer_range_km": rj / 1000.0,
            "detection_range_km": effective_range / 1000.0,
            "un-jammed_range_km": r_max / 1000.0,
            "burn_through_km": r_bt / 1000.0,
        }

    def _platform_of(self, component) -> Platform | None:
        pid = getattr(component, "platform_id", None)
        return self.platforms.get(pid)

    def find_emitter_platform(self, emitter: Emitter) -> Platform | None:
        return self._platform_of(emitter)

    def find_jammer_platform(self, jammer: Jammer) -> Platform | None:
        return self._platform_of(jammer)


# ----------------------------------------------------------------------
# 几何辅助
# ----------------------------------------------------------------------
def _distance_m(a: Platform, b: Platform) -> float:
    return haversine_nm(a.latitude, a.longitude, b.latitude, b.longitude) * 1852.0


def triangulate_bearings(bearings: list[tuple[float, float, float]]) -> tuple[float, float] | None:
    """两条测向线交点（局部切平面近似）。

    bearings: [(lat, lon, bearing_deg), ...]，至少 2 条。
    返回 (lat, lon)；无法求交返回 None。
    """
    if len(bearings) < 2:
        return None

    center_lat = sum(b[0] for b in bearings) / len(bearings)
    center_lon = sum(b[1] for b in bearings) / len(bearings)
    cos_lat = math.cos(math.radians(center_lat))
    R = 6371.0088

    def to_xy(lat, lon):
        x = R * math.radians(lon - center_lon) * cos_lat
        y = R * math.radians(lat - center_lat)
        return x, y

    def from_xy(x, y):
        lat = center_lat + math.degrees(y / R)
        lon = center_lon + math.degrees(x / (R * cos_lat))
        return lat, lon

    # 用前两条测向线求交
    (lat1, lon1, brg1), (lat2, lon2, brg2) = bearings[0], bearings[1]
    x1, y1 = to_xy(lat1, lon1)
    x2, y2 = to_xy(lat2, lon2)
    # 方向向量：方位角正北 0，顺时针；x 东，y 北
    d1 = (math.sin(math.radians(brg1)), math.cos(math.radians(brg1)))
    d2 = (math.sin(math.radians(brg2)), math.cos(math.radians(brg2)))

    denom = d1[0] * d2[1] - d2[0] * d1[1]
    if abs(denom) < 1e-9:
        return None
    t = ((x2 - x1) * d2[1] - (y2 - y1) * d2[0]) / denom
    return from_xy(x1 + t * d1[0], y1 + t * d1[1])
