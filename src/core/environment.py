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
from pathlib import Path

from common.geo import destination_point, haversine_nm, initial_bearing_deg

from . import propagation
from .contact import Contact
from .emitter import Emitter
from .jammer import Jammer
from .missile import Missile
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
    alive: bool = True              # 是否存活（被击毁后不再运动/辐射）
    emitters: list[Emitter] = field(default_factory=list)
    receivers: list[Receiver] = field(default_factory=list)
    jammers: list[Jammer] = field(default_factory=list)
    weapons: list[str] = field(default_factory=list)   # 武器列表，如 ["ssm"]
    hp: float = 100.0                # 简化生命值
    ciws: bool = False               # 近防系统
    ciws_hit_probability: float = 0.4
    ciws_range_km: float = 3.0
    gun_range_km: float = 8.0       # 舰炮对海/对空拦截距离
    gun_hit_probability: float = 0.2
    system_damage: dict[str, float] = field(default_factory=lambda: {
        "sensor": 100.0, "weapon": 100.0, "mobility": 100.0, "power": 100.0})

    # 信号特征（来自 CMO 数据库）
    sig_radar_db_sm: float | None = None
    sig_ir_km: float | None = None
    sig_sonar_db: float | None = None

    # 挂载与弹药
    loadout_weapons: list[dict] = field(default_factory=list)   # 实际可用导弹
    ammo: dict[str, int] = field(default_factory=dict)          # 待发/装填中
    max_ammo: dict[str, int] = field(default_factory=dict)      # 最大待发数
    magazine: dict[str, int] = field(default_factory=dict)      # 弹库储量
    reload_time_s: float = 12.0
    reload_timers: dict[str, float] = field(default_factory=dict)

    # 软杀伤
    chaff_count: int = 0
    decoy_count: int = 0
    active_decoy_count: int = 0
    soft_kill_probability: float = 0.4

    # 编队与交战规则
    group_id: str | None = None
    roe: str = "free"                 # free / weapons_free / hold / weapons_hold
    home_lat: float | None = None
    home_lon: float | None = None
    agility: float = 0.0              # 机动性（0~?，用于命中概率修正）

    comm_degraded: bool = False

    # 推进与续航
    max_speed_kt: float | None = None
    fuel_kg: float | None = None
    fuel_capacity_kg: float = 100_000.0
    fuel_consumption_kg_per_h: float = 1_000.0
    # 绕飞轨道（可选）：绕某点做圆周运动
    orbit_center_lat: float | None = None
    orbit_center_lon: float | None = None
    orbit_radius_km: float | None = None
    orbit_direction: int = 1          # 1 逆时针（正横右转），-1 顺时针


    @property
    def rcs_m2(self) -> float:
        """雷达截面积（m²）。优先使用数据库信号特征 dBsm。"""
        if self.sig_radar_db_sm is not None:
            return 10 ** (self.sig_radar_db_sm / 10.0)
        return 1000.0

    @property
    def ir_detection_km(self) -> float:
        """红外探测距离（km），无数据时返回默认 20km。"""
        return self.sig_ir_km if self.sig_ir_km is not None else 20.0

    @property
    def sonar_signature_db(self) -> float:
        """被动声呐信号强度（dB），无数据时返回 120dB。"""
        return self.sig_sonar_db if self.sig_sonar_db is not None else 120.0


@dataclass
class FalseTarget:
    """欺骗干扰产生的假目标。"""
    id: str
    radar_platform_id: str
    jammer_id: str
    latitude: float
    longitude: float
    age_s: float = 0.0
    technique: str = ""
    active: bool = True


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
    radar_contacts: dict[str, dict[str, Contact]] = field(default_factory=dict)
    ir_contacts: dict[str, dict[str, Contact]] = field(default_factory=dict)
    sonar_contacts: dict[str, dict[str, Contact]] = field(default_factory=dict)
    pending_esm: list[dict] = field(default_factory=list)
    pending_radar: list[dict] = field(default_factory=list)
    waypoint_drag_lock: bool = False
    waypoints: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    orders: list[dict] = field(default_factory=list)  # 攻击/移动等指令
    missiles: list[Missile] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    _missile_seq: int = 0
    rng: random.Random = field(default_factory=lambda: random.Random(12345))
    memory_ttl_s: float = 20.0        # 信号丢失后保留记忆接触的时长
    contact_ttl_s: float = 60.0       # 接触总生存时间
    arm_hit_probability: float = 1.0  # ARM 命中概率（蒙特卡洛时可调）
    false_contacts: dict[str, list[FalseTarget]] = field(default_factory=dict)

    # 环境层（Phase 7 环境）
    terrain_obstacles: list[dict] = field(default_factory=list)
    coastlines: list[dict] = field(default_factory=list)  # 简化海岸线多边形
    atmospheric_k: float = 4.0 / 3.0    # 大气折射系数（4/3 地球半径）
    sea_state: int = 3                  # 海况 0~9
    rain_mm_h: float = 0.0              # 降雨强度
    visibility_km: float = 30.0         # 能见度
    wind_speed_kt: float = 0.0          # 风速
    cloud_cover_pct: float = 0.0        # 云量 0~100
    humidity_pct: float = 60.0          # 湿度 0~100
    sound_speed_profile_m_s: list[float] = field(default_factory=list)
    _false_target_seq: int = 0

    # ------------------------------------------------------------------
    # 基础注册/查询
    # ------------------------------------------------------------------
    def add_platform(self, platform: Platform) -> None:
        self.platforms[platform.id] = platform

    def load_signal_library(self, path: str | Path) -> None:
        """从 JSON 加载多参数信号库并应用到所有 ESM/RWR 接收机。"""
        import json as _json
        data = _json.loads(Path(path).read_text(encoding="utf-8"))
        for rec in self.all_receivers():
            if rec.kind in ("esm", "rwr"):
                rec.signal_params = data

    def add_terrain_obstacle(self, lat: float, lon: float, radius_km: float,
                             height_ft: float = 500.0) -> None:
        self.terrain_obstacles.append({
            "lat": lat, "lon": lon, "radius_km": radius_km, "height_ft": height_ft})

    def load_terrain_from_json(self, path: str | Path) -> None:
        import json as _json
        data = _json.loads(Path(path).read_text(encoding="utf-8"))
        for ob in data.get("terrain_obstacles", []):
            self.add_terrain_obstacle(
                ob["lat"], ob["lon"], ob.get("radius_km", 20.0),
                ob.get("height_ft", 500.0))

    def load_coastlines_from_json(self, path: str | Path) -> None:
        import json as _json
        data = _json.loads(Path(path).read_text(encoding="utf-8"))
        self.coastlines.extend(data.get("coastlines", []))

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

    # ------------------------------------------------------------------
    # 武器发射与导弹飞行（Phase 4 反辐射打击）
    # ------------------------------------------------------------------
    def _consume_ammo(self, attacker: Platform, weapon_name: str) -> bool:
        """消耗一发弹药；如果无弹药机制则始终允许。"""
        if not attacker.ammo:
            return True
        if attacker.ammo.get(weapon_name, 0) <= 0:
            return False
        attacker.ammo[weapon_name] -= 1
        return True

    def _reload_systems(self, dt_s: float) -> None:
        """弹药库向待发弹补充。"""
        for p in self.platforms.values():
            if not p.alive:
                continue
            for weapon, stored in list(p.magazine.items()):
                ready = p.ammo.get(weapon, 0)
                max_ready = p.max_ammo.get(weapon, 1)
                if ready < max_ready and stored > 0:
                    timer = p.reload_timers.get(weapon, 0.0) + dt_s
                    if timer >= p.reload_time_s:
                        p.ammo[weapon] = min(ready + 1, max_ready)
                        p.magazine[weapon] -= 1
                        timer = 0.0
                    p.reload_timers[weapon] = timer

    def _choose_weapon(self, attacker: Platform, target: Platform) -> tuple[str, dict] | None:
        """根据挂载方案选择攻击武器。"""
        for lw in attacker.loadout_weapons:
            name = lw.get("name", "")
            kind = lw.get("kind", "weapon")
            if target.kind == "ship" and kind == "asm":
                return name, lw
            if target.kind == "aircraft" and kind in ("aam", "sam", "arm"):
                return name, lw
        if target.kind == "ship" and "ssm" in attacker.weapons:
            return "反舰导弹", {"name": "反舰导弹", "kind": "asm", "range_km": 120, "speed_mps": 300}
        if (target.kind == "aircraft"
                and (any(e.is_emitting for e in target.emitters)
                     or any(j.is_jamming for j in target.jammers))):
            # 无专用挂载时，若目标正在辐射，使用反辐射导弹
            return "反辐射导弹", {"name": "反辐射导弹", "kind": "arm", "range_km": 150, "speed_mps": 850}
        return None

    def _launch_weapon(self, attacker: Platform, target: Platform, weapon_name: str, spec: dict) -> bool:
        """通用导弹发射。"""
        kind = spec.get("kind", "arm")
        if not self._consume_ammo(attacker, weapon_name):
            self.events.append({"time": self.time_s, "kind": "no_ammo",
                                "message": f"{attacker.name} {weapon_name} 弹药不足，无法发射"})
            return False
        self._missile_seq += 1
        missile = Missile(
            id=f"{kind}-{self._missile_seq}",
            name=weapon_name,
            kind=kind,
            attacker_id=attacker.id,
            target_id=target.id,
            lat=attacker.latitude,
            lon=attacker.longitude,
            speed_mps=float(spec.get("speed_mps", 300.0)),
            range_km=float(spec.get("range_km", 120.0)),
            memory_if_shutdown=(kind == "arm"),
            current_speed_mps=float(spec.get("speed_mps", 300.0)),
            terminal_speed_mps=float(spec.get("speed_mps", 300.0)) * 0.85,
            decel_mps2=float(spec.get("decel_mps2", 1.5)),
            max_g=float(spec.get("max_g", 20.0)),
            altitude_ft=attacker.altitude_ft,
            cruise_alt_ft=target.altitude_ft if target else 0.0,
            climb_rate_ft_s=float(spec.get("climb_rate_ft_s", 800.0)),
            guidance=str(spec.get("guidance", "active_radar")),
            all_aspect=bool(spec.get("all_aspect", True)),
            boost_duration_s=float(spec.get("boost_duration_s", 2.0)),
            boost_accel_mps2=float(spec.get("boost_accel_mps2", 150.0)),
            drag_coefficient=float(spec.get("drag_coefficient", 0.02)),
        )
        if kind == "arm":
            missile.guidance = "anti_radiation"
            missile.all_aspect = True
            missile.boost_duration_s = 2.0
            missile.boost_accel_mps2 = 120.0
            missile.last_locked_lat = target.latitude
            missile.last_locked_lon = target.longitude
        self.missiles.append(missile)
        return True

    def process_attack_orders(self) -> None:
        """将未处理的攻击指令转化为反辐射导弹发射。"""
        for order in self.orders:
            if order["kind"] != "attack" or order.get("processed"):
                continue
            attacker = self.platforms.get(order["attacker"])
            target = self.platforms.get(order["target"])
            order["processed"] = True
            if attacker is None or target is None or not attacker.alive or not target.alive:
                order["result"] = "invalid"
                continue
            dist_km = haversine_nm(attacker.latitude, attacker.longitude,
                                   target.latitude, target.longitude) * 1.852
            if dist_km > 150.0:
                order["result"] = "out_of_range"
                self.events.append({"time": self.time_s, "kind": "attack_order",
                                    "message": f"{attacker.name} 攻击 {target.name}：目标超出射程"})
                continue
            # 根据挂载方案选择武器
            weapon = self._choose_weapon(attacker, target)
            if weapon is None:
                order["result"] = "no_weapon"
                self.events.append({"time": self.time_s, "kind": "no_weapon",
                                    "message": f"{attacker.name} 未选择适合 {target.name} 的武器"})
                continue
            weapon_name, spec = weapon
            if dist_km > float(spec.get("range_km", 150.0)):
                order["result"] = "out_of_range"
                self.events.append({"time": self.time_s, "kind": "attack_order",
                                    "message": f"{attacker.name} 攻击 {target.name}：目标超出射程"})
                continue
            if self._launch_weapon(attacker, target, weapon_name, spec):
                order["result"] = "launched"
                self.events.append({"time": self.time_s, "kind": "launch",
                                    "message": f"{attacker.name} 向 {target.name} 发射 {weapon_name}"})
            else:
                order["result"] = "no_ammo"

    def _launch_arm(self, attacker_id: str, target_id: str) -> None:
        attacker = self.platforms.get(attacker_id)
        target = self.platforms.get(target_id)
        if attacker is None or target is None:
            return
        self._missile_seq += 1
        missile = Missile(
            id=f"arm-{self._missile_seq}",
            name="反辐射导弹",
            kind="arm",
            attacker_id=attacker_id,
            target_id=target_id,
            lat=attacker.latitude,
            lon=attacker.longitude,
            speed_mps=850.0,
            range_km=150.0,
            memory_if_shutdown=True,
        )
        missile.last_locked_lat = target.latitude
        missile.last_locked_lon = target.longitude
        self.missiles.append(missile)

    def _launch_asm(self, attacker_id: str, target_id: str) -> None:
        """发射反舰导弹（ASM）。"""
        attacker = self.platforms.get(attacker_id)
        target = self.platforms.get(target_id)
        if attacker is None or target is None:
            return
        self._missile_seq += 1
        missile = Missile(
            id=f"asm-{self._missile_seq}",
            name="反舰导弹",
            kind="asm",
            attacker_id=attacker_id,
            target_id=target_id,
            lat=attacker.latitude,
            lon=attacker.longitude,
            speed_mps=300.0,
            range_km=120.0,
            memory_if_shutdown=False,
        )
        self.missiles.append(missile)

    def step_missiles(self, dt_s: float) -> None:
        """导弹飞行、制导与命中判定（简化模型）。"""
        for missile in list(self.missiles):
            if not missile.active:
                continue
            target = self.platforms.get(missile.target_id)
            missile.flight_time_s += dt_s
            if missile.flight_time_s * missile.speed_mps > missile.range_km * 1000.0:
                missile.active = False
                missile.result = "miss"
                self.events.append({"time": self.time_s, "kind": "missile_miss",
                                    "message": f"{missile.name} 燃料耗尽，未命中"})
                continue
            if target is None or not target.alive:
                missile.active = False
                missile.result = "miss"
                continue

            if missile.kind in ("asm", "aam"):
                missile.last_locked_lat = target.latitude
                missile.last_locked_lon = target.longitude
                missile.no_emission_time = 0.0
            elif self._target_is_emitting(target):
                missile.no_emission_time = 0.0
                if not missile.decoyed and not self._try_decoy_missile(missile, target):
                    missile.last_locked_lat = target.latitude
                    missile.last_locked_lon = target.longitude
            else:
                missile.no_emission_time += dt_s
                if missile.memory_if_shutdown and missile.no_emission_time > missile.memory_time_s:
                    missile.active = False
                    missile.result = "lost_lock"
                    self.events.append({"time": self.time_s, "kind": "missile_lost",
                                        "message": f"{missile.name} 丢失辐射源，失的"})
                    continue

            aim_lat = missile.last_locked_lat if missile.last_locked_lat is not None else target.latitude
            aim_lon = missile.last_locked_lon if missile.last_locked_lon is not None else target.longitude
            dist_m = haversine_nm(missile.lat, missile.lon, aim_lat, aim_lon) * 1852.0
            step_m = (missile.current_speed_mps or missile.speed_mps) * dt_s

            if dist_m <= step_m or dist_m < 100.0:
                missile.lat, missile.lon = aim_lat, aim_lon
                actual_m = haversine_nm(missile.lat, missile.lon,
                                        target.latitude, target.longitude) * 1852.0

                if missile.kind == "asm":
                    missile.active = False
                    # 舰炮拦截（远层）
                    if (target.gun_range_km > 0 and dist_m <= target.gun_range_km * 1000.0
                            and self.rng.random() < target.gun_hit_probability):
                        missile.result = "miss"
                        self.events.append({"time": self.time_s, "kind": "missile_intercepted",
                                            "message": f"{missile.name} 被 {target.name} 舰炮拦截"})
                    # 近防拦截（近层）
                    elif (target.ciws and dist_m <= target.ciws_range_km * 1000.0
                          and self.rng.random() < target.ciws_hit_probability):
                        missile.result = "miss"
                        self.events.append({"time": self.time_s, "kind": "missile_intercepted",
                                            "message": f"{missile.name} 被 {target.name} 近防系统拦截"})
                    elif self._try_soft_kill(target, missile):
                        missile.result = "miss"
                        self.events.append({"time": self.time_s, "kind": "missile_decoyed",
                                            "message": f"{missile.name} 被 {target.name} 箔条/诱饵诱骗"})
                    elif self.rng.random() < self._hit_chance(target, missile):
                        missile.result = "hit"
                        self._damage_platform(target, missile)
                    else:
                        missile.result = "miss"
                        self.events.append({"time": self.time_s, "kind": "missile_miss",
                                            "message": f"{missile.name} 未命中（目标机动/干扰）"})
                elif missile.kind == "aam":
                    missile.active = False
                    if actual_m < 500.0:
                        if self._try_soft_kill(target, missile):
                            missile.result = "miss"
                            self.events.append({"time": self.time_s, "kind": "missile_decoyed",
                                                "message": f"{missile.name} 被 {target.name} 箔条/诱饵诱骗"})
                        elif self.rng.random() < self._hit_chance(target, missile):
                            missile.result = "hit"
                            self._damage_platform(target, missile)
                        else:
                            missile.result = "miss"
                            self.events.append({"time": self.time_s, "kind": "missile_miss",
                                                "message": f"{missile.name} 未命中（目标机动/干扰）"})
                    else:
                        missile.result = "miss"
                        self.events.append({"time": self.time_s, "kind": "missile_miss",
                                            "message": f"{missile.name} 未命中（目标机动）"})
                elif actual_m < 500.0 and self._target_is_emitting(target) and not missile.decoyed:
                    missile.active = False
                    if self._try_soft_kill(target, missile):
                        missile.result = "miss"
                        self.events.append({"time": self.time_s, "kind": "missile_decoyed",
                                            "message": f"{missile.name} 被 {target.name} 箔条/诱饵诱骗"})
                    elif self.rng.random() < self._hit_chance(target, missile):
                        missile.result = "hit"
                        self._damage_platform(target, missile)
                    else:
                        missile.result = "miss"
                        self.events.append({"time": self.time_s, "kind": "missile_miss",
                                            "message": f"{missile.name} 未命中（目标机动/近防拦截）"})
                elif missile.decoyed:
                    missile.active = False
                    missile.result = "miss"
                    self.events.append({"time": self.time_s, "kind": "missile_decoyed",
                                        "message": f"{missile.name} 被欺骗干扰诱骗，未命中"})
                else:
                    missile.active = False
                    missile.result = "miss"
                    self.events.append({"time": self.time_s, "kind": "missile_miss",
                                        "message": f"{missile.name} 未命中（辐射源已关机/机动）"})
            else:
                bearing = initial_bearing_deg(missile.lat, missile.lon, aim_lat, aim_lon)
                missile.lat, missile.lon = destination_point(
                    missile.lat, missile.lon, bearing, step_m / 1852.0)

            # 3D 简化弹道：按爬升率调整高度
            if missile.cruise_alt_ft is not None:
                delta = missile.cruise_alt_ft - missile.altitude_ft
                step_alt = missile.climb_rate_ft_s * dt_s
                if abs(delta) <= step_alt:
                    missile.altitude_ft = missile.cruise_alt_ft
                else:
                    missile.altitude_ft += step_alt if delta > 0 else -step_alt

            # 基于能量的助推-惯性模型（参考 CMO 教程）
            if missile.current_speed_mps is None:
                missile.current_speed_mps = missile.speed_mps
            if missile.boost_duration_s > 0 and missile.flight_time_s <= missile.boost_duration_s:
                missile.current_speed_mps += missile.boost_accel_mps2 * dt_s
            else:
                drag = missile.drag_coefficient * missile.current_speed_mps
                if missile.decel_mps2 is not None:
                    drag = max(drag, missile.decel_mps2)
                missile.current_speed_mps -= drag * dt_s
            missile.current_speed_mps = max(missile.terminal_speed_mps or 0.0, missile.current_speed_mps)

    def _try_soft_kill(self, target: Platform, missile: Missile) -> bool:
        """目标发射箔条/诱饵/有源诱饵软杀伤，成功则导弹被诱骗。"""
        if missile.kind not in ("asm", "aam", "arm"):
            return False
        if target.chaff_count <= 0 and target.decoy_count <= 0 and target.active_decoy_count <= 0:
            return False
        if self.rng.random() >= target.soft_kill_probability:
            return False
        if target.chaff_count > 0:
            target.chaff_count -= 1
        elif target.decoy_count > 0:
            target.decoy_count -= 1
        elif target.active_decoy_count > 0:
            target.active_decoy_count -= 1
        return True

    def _hit_chance(self, target: Platform, missile: Missile | None = None) -> float:
        """命中概率：基础 ARM 命中率 × 目标机动修正 × 导弹过载能力。"""
        base = self.arm_hit_probability
        maneuver_penalty = min(0.6, target.agility * 0.01)
        if missile is not None and missile.max_g > 0 and target.agility > missile.max_g * 0.8:
            maneuver_penalty = min(0.8, maneuver_penalty + 0.1)
        return max(0.05, base * (1.0 - maneuver_penalty))

    def _try_decoy_missile(self, missile: Missile, target: Platform) -> bool:
        """尝试让导弹被目标欺骗干扰诱骗。

        返回 True 表示导弹本帧被诱骗，last_locked 已指向假目标点。
        """
        jammer = self._find_decoy_jammer(target)
        if jammer is None:
            return False
        if self.rng.random() > 0.7:
            return False
        decoy_lat, decoy_lon = self._find_decoy_point(missile, target, jammer)
        if decoy_lat is None:
            return False
        missile.last_locked_lat = decoy_lat
        missile.last_locked_lon = decoy_lon
        missile.decoyed = True
        return True

    def _find_decoy_jammer(self, target: Platform):
        """返回目标平台上正在施放欺骗干扰的干扰机（若有）。"""
        for jammer in target.jammers:
            if jammer.is_jamming and jammer.has_deception():
                return jammer
        return None

    def _find_decoy_point(self, missile: Missile, target: Platform,
                          jammer: Jammer) -> tuple[float | None, float | None]:
        """为导弹选择一个假目标点。

        优先使用已生成的 FalseTarget（距导弹较近者），
        否则按欺骗技术生成一个偏移点。
        """
        candidates: list[FalseTarget] = []
        for radar_targets in self.false_contacts.values():
            for t in radar_targets:
                if t.active and t.jammer_id == jammer.id:
                    candidates.append(t)
        if candidates:
            best = min(candidates,
                       key=lambda t: haversine_nm(missile.lat, missile.lon,
                                                  t.latitude, t.longitude))
            return best.latitude, best.longitude
        # 无现成假目标时，随机生成偏移 3~15 km
        offset_km = self.rng.uniform(3.0, 15.0)
        bearing = self.rng.uniform(0.0, 360.0)
        lat_off = offset_km / 111.32
        lon_off = offset_km / (111.32 * math.cos(math.radians(target.latitude)) + 1e-9)
        brg = math.radians(bearing)
        return (target.latitude + lat_off * math.cos(brg),
                target.longitude + lon_off * math.sin(brg))

    @staticmethod
    def _target_is_emitting(target: Platform) -> bool:
        return any(e.is_emitting for e in target.emitters) or                any(j.is_jamming for j in target.jammers)

    def _damage_platform(self, target: Platform, missile: Missile) -> None:
        """导弹命中后的简化分系统损伤。"""
        damage = 60.0 if missile.kind == "asm" else 120.0
        target.hp = max(0.0, target.hp - damage)
        if target.hp <= 0:
            self._destroy_platform(target, missile)
            return

        # 分系统随机受损
        for sys_name in ("sensor", "weapon", "mobility", "power"):
            if sys_name not in target.system_damage:
                target.system_damage[sys_name] = 100.0
            reduction = self.rng.uniform(0.0, damage * 0.6)
            target.system_damage[sys_name] = max(0.0, target.system_damage[sys_name] - reduction)

        damages = [name for name, v in target.system_damage.items() if v <= 20.0]
        if target.system_damage.get("sensor", 100.0) <= 20.0:
            for e in target.emitters:
                e.emcon_state = "off"
        if target.system_damage.get("mobility", 100.0) <= 20.0:
            target.speed_kt = 0.0
        if target.system_damage.get("power", 100.0) <= 20.0:
            for e in target.emitters:
                e.emcon_state = "off"
            for j in target.jammers:
                j.emcon_state = "off"
        if damages:
            self.events.append({"time": self.time_s, "kind": "damage",
                                "message": f"{missile.name} 命中 {target.name}，"
                                           f"{'/'.join(damages)}受损"})
        else:
            self.events.append({"time": self.time_s, "kind": "damage",
                                "message": f"{missile.name} 命中 {target.name}，造成损伤"})

    def _destroy_platform(self, target: Platform, missile: Missile) -> None:
        target.alive = False
        target.hp = 0.0
        target.system_damage = {"sensor": 0.0, "weapon": 0.0, "mobility": 0.0, "power": 0.0}
        for e in target.emitters:
            e.emcon_state = "off"
        for j in target.jammers:
            j.emcon_state = "off"
        target.speed_kt = 0.0
        self.events.append({"time": self.time_s, "kind": "hit",
                            "message": f"{missile.name} 命中 {target.name}，目标被摧毁"})

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

    def assign_jammers(self) -> dict[str, str]:
        """为每部雷达分配干扰机（简单贪心分配，考虑 max_targets）。

        返回 {emitter_id: jammer_id}。
        """
        assignment: dict[str, str] = {}
        jammer_load: dict[str, int] = {}
        for j in self.active_jammers():
            jammer_load[j.id] = 0

        for platform in self.platforms.values():
            if not platform.alive:
                continue
            for emitter in platform.emitters:
                if emitter.emcon_state != "on":
                    continue
                if emitter.role not in ("multifunction_radar", "search_radar",
                                        "fire_control_radar"):
                    continue
                best_jammer = None
                best_score = -1.0
                for other in self.platforms.values():
                    if not other.alive or other.side == platform.side:
                        continue
                    for jammer in other.jammers:
                        if not self._jammer_actively_jamming(jammer):
                            continue
                        if jammer_load.get(jammer.id, 0) >= jammer.max_targets:
                            continue
                        if not jammer.covers_frequency(emitter.center_freq_hz):
                            continue
                        if not self._jammer_sector_ok(jammer, other, platform):
                            continue
                        # 瞄准式噪声效果优于阻塞式：带宽越窄，J/S 越高
                        score = jammer.power_w * jammer.gain_linear / max(jammer.bandwidth_hz, 1.0)
                        if score > best_score:
                            best_score = score
                            best_jammer = jammer
                if best_jammer is not None:
                    assignment[emitter.id] = best_jammer.id
                    jammer_load[best_jammer.id] = jammer_load.get(best_jammer.id, 0) + 1
        return assignment

    def _jammer_actively_jamming(self, jammer: Jammer) -> bool:
        """考虑间断观察法：干扰机在观察窗口内不干扰。"""
        if not jammer.is_jamming:
            return False
        if getattr(jammer, "look_through_enabled", False):
            period = max(getattr(jammer, "look_through_period_s", 2.0), 0.1)
            duration = min(getattr(jammer, "look_through_duration_s", 0.2), period)
            cycle = self.time_s % period
            if cycle < duration:
                return False
        return True

    def _jammer_sector_ok(self, jammer: Jammer, jammer_platform: Platform,
                          radar_platform: Platform) -> bool:
        """检查雷达是否在干扰机的干扰扇区内。"""
        if jammer.sector_half_deg >= 180.0:
            return True
        bearing = initial_bearing_deg(jammer_platform.latitude, jammer_platform.longitude,
                                      radar_platform.latitude, radar_platform.longitude)
        rel = (bearing - jammer_platform.heading_deg + 360.0) % 360.0
        return rel <= jammer.sector_half_deg or (360.0 - rel) <= jammer.sector_half_deg

    # ------------------------------------------------------------------
    # 时间推进
    # ------------------------------------------------------------------
    def step(self, dt_s: float = 1.0) -> None:
        """推进一帧：运动 -> 武器发射/飞行 -> ESM 截获 -> 接触老化 -> 交叉定位。"""
        self.time_s += dt_s
        self.step_motion(dt_s)
        self.process_attack_orders()
        self._reload_systems(dt_s)
        self.step_missiles(dt_s)
        self.update_deception(dt_s)
        self.update_esm(dt_s)
        self._process_pending_esm(dt_s)
        self.update_radar_detection(dt_s)
        self._process_pending_radar(dt_s)
        self.update_ir_detection(dt_s)
        self.update_sonar_detection(dt_s)
        self.update_comm_jamming(dt_s)
        self.update_contact_aging()
        self.cross_fix_contacts()
        self.cross_fix_radar_ranges()
        self.cross_fix_tdoa()
        self.cross_fix_fdoa()

    def step_motion(self, dt_s: float) -> None:
        """运动模型：优先沿航路点，其次绕飞轨道，最后直线。"""
        for p in self.platforms.values():
            if self.waypoint_drag_lock:
                break
            if not p.alive or p.speed_kt <= 0:
                continue
            # 推进限制与燃料
            if p.max_speed_kt is not None:
                p.speed_kt = min(p.speed_kt, p.max_speed_kt)
            if p.fuel_kg is not None:
                p.fuel_kg = max(0.0, p.fuel_kg - p.fuel_consumption_kg_per_h * dt_s / 3600.0)
                if p.fuel_kg <= 0.0:
                    p.speed_kt = 0.0
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
                        self._on_reach_final_waypoint(p)
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

    def _on_reach_final_waypoint(self, p: Platform) -> None:
        """到达最后一个航路点：舰船停船，飞机盘旋待命。"""
        if p.kind == "aircraft":
            # 在到达点上方建立盘旋轨道，保持巡航速度
            p.orbit_center_lat = p.latitude
            p.orbit_center_lon = p.longitude
            p.orbit_radius_km = 5.0
            p.orbit_direction = 1
            if p.cruise_speed_kt > 0:
                p.speed_kt = p.cruise_speed_kt
        else:
            p.speed_kt = 0.0  # 停船

    # ------------------------------------------------------------------
    # 欺骗干扰与电子防护（Phase 5）
    # ------------------------------------------------------------------
    def update_deception(self, dt_s: float) -> None:
        """为每部雷达生成/维持欺骗干扰假目标。

        干扰机主动使用 RGPO / VGPO / 假目标（false_target）时，
        只有雷达的 ECCM（频率捷变/脉冲压缩/旁瓣对消）不足才可能被欺骗。
        """
        # 老化并清理旧假目标
        for radar_id, targets in list(self.false_contacts.items()):
            for t in targets:
                t.age_s += dt_s
                if t.age_s > 30.0:
                    t.active = False
            self.false_contacts[radar_id] = [t for t in targets if t.active]

        for radar_platform in self.platforms.values():
            if not radar_platform.alive:
                continue
            for emitter in radar_platform.emitters:
                if emitter.emcon_state != "on":
                    continue
                if emitter.role not in ("multifunction_radar", "search_radar",
                                        "fire_control_radar"):
                    continue
                # 本帧是否已有干扰该雷达的干扰机？
                jammer = None
                for other in self.platforms.values():
                    if other.id == radar_platform.id or other.side == radar_platform.side:
                        continue
                    if not other.alive:
                        continue
                    for j in other.jammers:
                        if not j.is_jamming or not j.has_deception():
                            continue
                        if not j.covers_frequency(emitter.center_freq_hz):
                            continue
                        if not self._jammer_sector_ok(j, other, radar_platform):
                            continue
                        jammer = j
                        break
                    if jammer is not None:
                        break
                if jammer is None:
                    continue

                # 检查是否已存在同干扰机对同雷达的假目标
                existing = [t for t in self.false_contacts.get(radar_platform.id, [])
                            if t.jammer_id == jammer.id]
                if existing:
                    continue

                if self.rng.random() > self._deception_success_probability(emitter):
                    continue

                jammer_platform = self.platforms.get(jammer.platform_id)
                if jammer_platform is None:
                    continue
                lat, lon = self._generate_false_target(
                    radar_platform, jammer, jammer_platform)
                self._false_target_seq += 1
                self.false_contacts.setdefault(radar_platform.id, []).append(FalseTarget(
                    id=f"false-{self._false_target_seq}",
                    radar_platform_id=radar_platform.id,
                    jammer_id=jammer.id,
                    latitude=lat,
                    longitude=lon,
                    age_s=0.0,
                    technique=jammer.active_technique,
                ))

    @staticmethod
    def _deception_success_probability(emitter: Emitter) -> float:
        """欺骗干扰成功率 = 基础成功率 - 雷达 ECCM 抵抗力。"""
        base = 0.75
        return max(0.05, base - emitter.ecm_resistance)

    def _generate_false_target(self, radar_platform: Platform,
                               jammer: Jammer, jammer_platform: Platform) -> tuple[float, float]:
        """根据欺骗技术生成假目标位置。"""
        bearing = initial_bearing_deg(radar_platform.latitude, radar_platform.longitude,
                                      jammer_platform.latitude, jammer_platform.longitude)
        if jammer.active_technique == "rgpo":
            # 距离拖引：沿雷达-干扰机连线向远处多拉 8~30 km
            offset_km = self.rng.uniform(8.0, 30.0)
            lon_offset = offset_km / (111.32 * math.cos(math.radians(radar_platform.latitude)) + 1e-9)
            lat_offset = offset_km / 111.32
            brg = math.radians(bearing)
            return (radar_platform.latitude + lat_offset * math.cos(brg),
                    radar_platform.longitude + lon_offset * math.sin(brg))
        elif jammer.active_technique == "vgpo":
            # 速度拖引：简单用横向随机偏移 5~15 km
            offset_km = self.rng.uniform(5.0, 15.0)
            perp = (bearing + 90.0) % 360.0
            lon_offset = offset_km / (111.32 * math.cos(math.radians(jammer_platform.latitude)) + 1e-9)
            lat_offset = offset_km / 111.32
            brg = math.radians(perp)
            return (jammer_platform.latitude + lat_offset * math.cos(brg),
                    jammer_platform.longitude + lon_offset * math.sin(brg))
        else:  # false_target
            offset_km = self.rng.uniform(3.0, 20.0)
            bearing_off = self.rng.uniform(0.0, 360.0)
            lon_offset = offset_km / (111.32 * math.cos(math.radians(jammer_platform.latitude)) + 1e-9)
            lat_offset = offset_km / 111.32
            brg = math.radians(bearing_off)
            return (jammer_platform.latitude + lat_offset * math.cos(brg),
                    jammer_platform.longitude + lon_offset * math.sin(brg))

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
                    if not own.alive or not other.alive:
                        continue
                    for source in self._active_sources_of(other):
                        result = self._intercept_source(esm, own, other, source, dt_s)
                        if result is None:
                            continue
                        self.pending_esm.append({
                            "available_at": self.time_s + esm.processing_time_s,
                            "own": own,
                            "esm": esm,
                            "other": other,
                            "source": source,
                            "result": result,
                        })

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
        horizon_nm = self._get_horizon_nm(own, other)
        horizon_m = horizon_nm * 1852.0
        if r_m > horizon_m:
            return None
        if self._line_of_sight_blocked(own.latitude, own.longitude,
                                       other.latitude, other.longitude,
                                       own.altitude_ft, other.altitude_ft):
            return None

        if not esm.covers_frequency(freq_hz):
            return None

        # EW101 单向链路方程 + 大气损耗
        pt_dbm = 10.0 * math.log10(max(power_w, 1e-12) * 1000.0)
        range_km = r_m / 1000.0
        atm_loss = propagation.atmospheric_loss_db(freq_hz, range_km)
        power_dbm = propagation.one_way_link_power_dbm(
            pt_dbm, 10.0 * math.log10(max(gain, 1e-6)),
            esm.gain_db, range_km, freq_hz / 1e6, atm_loss)
        if power_dbm < esm.sensitivity_dbm:
            return None

        # 扫描截获概率：扫描雷达需要波束扫过 ESM；干扰机等常开信号概率为 1
        p = self._scan_intercept_probability(src, dt_s)
        sidelobe = False
        if p < 1.0 and self.rng.random() > p:
            # 主瓣未截获：尝试副瓣截获（EW101 副瓣侦察）
            sidelobe_gain = float(getattr(src, "sidelobe_gain_db", -20.0) or -20.0)
            power_sidelobe_dbm = power_dbm + sidelobe_gain
            p_sl = min(0.5, dt_s * 0.2)
            if power_sidelobe_dbm >= esm.sensitivity_dbm and self.rng.random() < p_sl:
                sidelobe = True
            else:
                return None

        true_bearing = initial_bearing_deg(own.latitude, own.longitude,
                                           other.latitude, other.longitude)
        # 测向误差
        if esm.df_accuracy_deg is not None and esm.df_accuracy_deg > 0:
            bearing = (true_bearing + self.rng.gauss(0.0, esm.df_accuracy_deg) + 360.0) % 360.0
        else:
            bearing = true_bearing

        toa_ns = None
        if esm.toa_accuracy_ns > 0:
            toa_ns = r_m / 299792458.0 * 1e9 + self.rng.gauss(0.0, esm.toa_accuracy_ns)
        doppler_hz = None
        if esm.fdoa_accuracy_hz > 0:
            doppler_hz = self._compute_doppler_hz(own, other, freq_hz) \
                + self.rng.gauss(0.0, esm.fdoa_accuracy_hz)

        identified = source_id in esm.param_library
        pulse_match = False
        if not identified and esm.signal_params:
            src_prf_min = getattr(src, "prf_min_hz", None)
            src_prf_max = getattr(src, "prf_max_hz", None)
            src_pw_min = getattr(src, "pulse_width_min_us", None)
            src_pw_max = getattr(src, "pulse_width_max_us", None)
            for params in esm.signal_params.values():
                prf_ok = (src_prf_min is not None and src_prf_max is not None
                          and params.get("prf_min", 0) <= src_prf_max
                          and params.get("prf_max", 1e12) >= src_prf_min)
                pw_ok = (src_pw_min is not None and src_pw_max is not None
                         and params.get("pw_min", 0) <= src_pw_max
                         and params.get("pw_max", 1e9) >= src_pw_min)
                if prf_ok and pw_ok:
                    identified = True
                    pulse_match = True
                    break
        return {
            "source_id": source_id,
            "pulse_match": pulse_match,
            "source_name": source_name,
            "bearing_deg": bearing,
            "true_bearing_deg": true_bearing,
            "range_km": r_m / 1000.0,
            "power_dbm": power_dbm,
            "toa_ns": toa_ns,
            "doppler_hz": doppler_hz,
            "sidelobe": sidelobe,
            "identified": identified,
            "confidence": (0.6 if sidelobe else 0.9) if identified else (0.2 if sidelobe else 0.35),
        }

    @staticmethod
    def _scan_intercept_probability(source, dt_s: float) -> float:
        """根据辐射源扫描方式估计 dt 时间内的截获概率。"""
        scan_period = getattr(source, "scan_period_s", None)
        beam_width = getattr(source, "beam_width_deg", None)
        if scan_period is None or scan_period <= 0:
            return 1.0  # 常开/干扰
        scans = dt_s / scan_period
        factor = 1.0
        emission = getattr(source, "emission_type", "normal") or "normal"
        if emission == "fh":
            factor = 0.3
        elif emission == "lfm":
            factor = 0.5
        elif emission == "dsss":
            factor = 0.2
        if beam_width is None or beam_width <= 0:
            return min(1.0, scans * factor)
        # 每转主瓣扫过 ESM 的概率约 beam_width/360
        return min(1.0, scans * max(beam_width / 360.0, 0.05) * factor)

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
            "toa_ns": result.get("toa_ns"),
            "doppler_hz": result.get("doppler_hz"),
        }

    def _get_horizon_nm(self, a: Platform, b: Platform) -> float:
        """考虑大气折射系数后的雷达视距（海里）。"""
        base = 1.23 * (math.sqrt(max(a.altitude_ft, 0.0)) +
                       math.sqrt(max(b.altitude_ft, 0.0)))
        return base * math.sqrt(self.atmospheric_k / (4.0 / 3.0))

    def _line_of_sight_blocked(self, lat1: float, lon1: float, lat2: float, lon2: float,
                                alt1_ft: float = 0.0, alt2_ft: float = 0.0) -> bool:
        """地形遮蔽：沿视线采样多个点，障碍物高度超过视线高度即遮挡。"""
        if not self.terrain_obstacles:
            return False
        samples = 8
        for i in range(samples + 1):
            t = i / samples
            mlat = lat1 + (lat2 - lat1) * t
            mlon = lon1 + (lon2 - lon1) * t
            m_alt = alt1_ft + (alt2_ft - alt1_ft) * t
            for ob in self.terrain_obstacles:
                d = haversine_nm(mlat, mlon, ob["lat"], ob["lon"]) * 1.852
                if d < ob.get("radius_km", 20.0):
                    ob_h = ob.get("height_ft", 500.0)
                    # 地面/海面障碍高度若高于该点视线高度则遮挡
                    if ob_h > m_alt:
                        return True
        return False

    @staticmethod
    def _platform_velocity_mps(p: Platform) -> tuple[float, float]:
        """返回平台速度的东/北分量（m/s）。"""
        v = p.speed_kt * 0.514444
        brg = math.radians(p.heading_deg)
        return v * math.sin(brg), v * math.cos(brg)

    def _compute_doppler_hz(self, own: Platform, other: Platform, freq_hz: float) -> float:
        """简化多普勒：接收机与发射机沿视线方向相对速度产生的频移。"""
        c = 299792458.0
        v_own_e, v_own_n = self._platform_velocity_mps(own)
        v_other_e, v_other_n = self._platform_velocity_mps(other)
        bearing = math.radians(initial_bearing_deg(own.latitude, own.longitude,
                                                  other.latitude, other.longitude))
        u_e, u_n = math.sin(bearing), math.cos(bearing)
        relative = (v_own_e * u_e + v_own_n * u_n) - (v_other_e * u_e + v_other_n * u_n)
        return freq_hz * relative / c

    def _weather_penalty(self) -> float:
        """天气对雷达/光学/ESM 的通用衰减系数（0.3~1.0）。"""
        penalty = 1.0
        penalty -= min(0.4, self.sea_state * 0.04)
        penalty -= min(0.3, self.rain_mm_h / 50.0 * 0.3)
        visibility = max(self.visibility_km, 1.0)
        penalty -= min(0.2, (30.0 - visibility) / 30.0 * 0.2)
        penalty -= min(0.15, self.wind_speed_kt / 50.0 * 0.15)
        penalty -= min(0.1, self.cloud_cover_pct / 100.0 * 0.1)
        penalty -= min(0.1, max(0.0, self.humidity_pct - 80.0) / 20.0 * 0.1)
        return max(0.3, penalty)

    def _sonar_environment_factor(self) -> float:
        """海况/降雨/声速剖面共同影响声呐。"""
        f = 1.0 - self.sea_state * 0.08 - min(0.2, self.rain_mm_h / 100.0)
        if self.sound_speed_profile_m_s:
            # 声速剖面分层越稳定（速度差小）越好；这里用简单平均差值
            avg = sum(self.sound_speed_profile_m_s) / len(self.sound_speed_profile_m_s)
            var = max(1.0, max(self.sound_speed_profile_m_s) - min(self.sound_speed_profile_m_s))
            f *= max(0.6, 1.0 - min(1.0, var / avg * 0.5))
        return max(0.35, f)

    def update_radar_detection(self, dt_s: float) -> None:
        """雷达接触主流程：使用目标 RCS/红外特征决定是否发现。

        生成 radar_contacts[雷达平台][目标平台] = Contact。
        """
        now = self.time_s
        for radar_platform in self.platforms.values():
            if not radar_platform.alive:
                continue
            for emitter in radar_platform.emitters:
                if emitter.emcon_state != "on":
                    continue
                if emitter.role not in ("multifunction_radar", "search_radar",
                                        "fire_control_radar"):
                    continue
                # 本平台对敌方目标的雷达接触
                radar_map = self.radar_contacts.setdefault(radar_platform.id, {})
                for target in self.platforms.values():
                    if target.id == radar_platform.id or target.side == radar_platform.side:
                        continue
                    if not target.alive:
                        continue
                    dist_m = _distance_m(radar_platform, target)
                    # 波束仰角覆盖：低于/高于仰角范围视为盲区
                    dh_m = (target.altitude_ft - radar_platform.altitude_ft) * 0.3048
                    elev_deg = math.degrees(math.atan2(dh_m, max(dist_m, 1.0)))
                    if elev_deg < emitter.elevation_min_deg or elev_deg > emitter.elevation_max_deg:
                        radar_map.pop(target.id, None)
                        continue
                    # 火控雷达盲区：天线后/侧向盲扇区
                    if emitter.blind_sector_half_deg > 0:
                        rel_bearing = (initial_bearing_deg(
                            radar_platform.latitude, radar_platform.longitude,
                            target.latitude, target.longitude) - radar_platform.heading_deg + 360.0) % 360.0
                        center = emitter.blind_sector_center_deg
                        delta = (rel_bearing - center + 180.0) % 360.0 - 180.0
                        if abs(delta) <= emitter.blind_sector_half_deg:
                            radar_map.pop(target.id, None)
                            continue
                    # 视距与地形遮蔽
                    horizon_nm = self._get_horizon_nm(radar_platform, target)
                    if dist_m > horizon_nm * 1852.0:
                        radar_map.pop(target.id, None)
                        continue
                    if self._line_of_sight_blocked(radar_platform.latitude, radar_platform.longitude,
                                                   target.latitude, target.longitude,
                                                   radar_platform.altitude_ft, target.altitude_ft):
                        radar_map.pop(target.id, None)
                        continue
                    jammer = None
                    for other in self.platforms.values():
                        if other.side == radar_platform.side or not other.alive:
                            continue
                        for j in other.jammers:
                            if self._jammer_actively_jamming(j) and j.covers_frequency(emitter.center_freq_hz):
                                jammer = j
                                break
                        if jammer is not None:
                            break
                    result = self.evaluate_radar_with_jamming(
                        emitter, jammer, bandwidth_hz=1_000_000,
                        noise_figure=5.0, loss=6.0, snr_min_db=13.0,
                        target_platform=target)
                    detection_km = result["detection_range_km"] * self._weather_penalty()
                    if dist_m <= detection_km * 1000.0:
                        contact = radar_map.get(target.id)
                        # 扫描周期影响首次发现/重新截获概率；已跟踪则每帧刷新
                        p_scan = min(1.0, dt_s / max(emitter.scan_period_s, 0.1))
                        if contact is not None and contact.is_memory and self.rng.random() > p_scan:
                            continue
                        if contact is not None and not contact.is_memory:
                            pass  # 已跟踪，正常更新
                        elif contact is None and self.rng.random() > p_scan:
                            continue
                        if contact is None:
                            # 雷达处理延迟：新目标先进入待处理队列
                            self.pending_radar.append({
                                "available_at": now + emitter.processing_time_s,
                                "radar_platform": radar_platform,
                                "emitter": emitter,
                                "target": target,
                                "detection_km": detection_km,
                                "dist_m": dist_m,
                                "jammer": jammer,
                            })
                            continue
                        contact.bearing_deg = initial_bearing_deg(
                            radar_platform.latitude, radar_platform.longitude,
                            target.latitude, target.longitude)
                        contact.range_m = dist_m
                        contact.latitude = target.latitude
                        contact.longitude = target.longitude
                        contact.time_s = now
                        contact.last_update_s = now
                        contact.is_memory = False
                        contact.confidence = 0.95
                        contact.extra = {"detection_km": detection_km}
                        if jammer is not None and jammer.active_technique == "tws_gain":
                            contact.confidence = min(contact.confidence, 0.55)
                            contact.extra["tws_degraded"] = True
                    else:
                        contact = radar_map.get(target.id)
                        if contact is not None and now - contact.last_update_s > self.memory_ttl_s:
                            radar_map.pop(target.id, None)
                        elif contact is not None:
                            contact.is_memory = True

    def update_ir_detection(self, dt_s: float) -> None:
        """红外探测主流程：无源可见光/红外发现目标。"""
        now = self.time_s
        for own in self.platforms.values():
            if not own.alive:
                continue
            ir_map = self.ir_contacts.setdefault(own.id, {})
            for target in self.platforms.values():
                if target.id == own.id or target.side == own.side or not target.alive:
                    continue
                dist_km = haversine_nm(own.latitude, own.longitude,
                                       target.latitude, target.longitude) * 1.852
                if self._line_of_sight_blocked(own.latitude, own.longitude,
                                               target.latitude, target.longitude,
                                               own.altitude_ft, target.altitude_ft):
                    ir_map.pop(target.id, None)
                    continue
                if dist_km <= target.ir_detection_km * self._weather_penalty():
                    contact = ir_map.get(target.id)
                    if contact is None:
                        contact = Contact(
                            id=f"{own.id}-ir-{target.id}",
                            kind="ir_contact",
                            own_platform_id=own.id,
                            time_s=now,
                            emitter_id=target.id,
                            emitter_name=target.name,
                        )
                        ir_map[target.id] = contact
                    contact.bearing_deg = initial_bearing_deg(
                        own.latitude, own.longitude, target.latitude, target.longitude)
                    contact.range_m = dist_km * 1000.0
                    contact.latitude = target.latitude
                    contact.longitude = target.longitude
                    contact.time_s = now
                    contact.last_update_s = now
                    contact.is_memory = False
                    contact.confidence = 0.9
                else:
                    contact = ir_map.get(target.id)
                    if contact is not None and now - contact.last_update_s > self.memory_ttl_s:
                        ir_map.pop(target.id, None)
                    elif contact is not None:
                        contact.is_memory = True

    def update_sonar_detection(self, dt_s: float) -> None:
        """声呐探测主流程：己方声呐对水面/水下目标形成接触。"""
        now = self.time_s
        for own in self.platforms.values():
            if not own.alive:
                continue
            if not any(r.kind == "sonar" for r in own.receivers):
                continue
            sonar_map = self.sonar_contacts.setdefault(own.id, {})
            for target in self.platforms.values():
                if target.id == own.id or target.side == own.side or not target.alive:
                    continue
                if target.kind not in ("ship", "submarine"):
                    continue
                dist_km = haversine_nm(own.latitude, own.longitude,
                                       target.latitude, target.longitude) * 1.852
                # 简化声呐方程：目标信号越强，探测距离越远
                range_km = (20.0 + max(0.0, target.sonar_signature_db - 100.0) * 0.2) \
                    * self._sonar_environment_factor()
                if dist_km <= range_km:
                    contact = sonar_map.get(target.id)
                    if contact is None:
                        contact = Contact(
                            id=f"{own.id}-sonar-{target.id}",
                            kind="sonar_contact",
                            own_platform_id=own.id,
                            time_s=now,
                            emitter_id=target.id,
                            emitter_name=target.name,
                        )
                        sonar_map[target.id] = contact
                    contact.bearing_deg = initial_bearing_deg(
                        own.latitude, own.longitude, target.latitude, target.longitude)
                    contact.range_m = dist_km * 1000.0
                    contact.latitude = target.latitude
                    contact.longitude = target.longitude
                    contact.time_s = now
                    contact.last_update_s = now
                    contact.is_memory = False
                    contact.confidence = 0.75
                else:
                    contact = sonar_map.get(target.id)
                    if contact is not None and now - contact.last_update_s > self.memory_ttl_s:
                        sonar_map.pop(target.id, None)
                    elif contact is not None:
                        contact.is_memory = True

    def update_comm_jamming(self, dt_s: float) -> None:
        """通信电子战简化模型：敌方通信干扰机使己方通信降级。"""
        for p in self.platforms.values():
            p.comm_degraded = False
        for jammer_platform in self.platforms.values():
            if not jammer_platform.alive:
                continue
            for jammer in jammer_platform.jammers:
                if jammer.role != "comm" or not jammer.is_jamming:
                    continue
                for target in self.platforms.values():
                    if target.side == jammer_platform.side or not target.alive:
                        continue
                    target.comm_degraded = True
                    self.events.append({"time": self.time_s, "kind": "comm_jamming",
                                        "message": f"{target.name} 通信受 {jammer.name} 干扰"})

    def _process_pending_radar(self, dt_s: float) -> None:
        """处理已到处理时间的雷达新接触。"""
        still = []
        for item in self.pending_radar:
            if self.time_s >= item["available_at"]:
                radar_platform = item["radar_platform"]
                target = item["target"]
                radar_map = self.radar_contacts.setdefault(radar_platform.id, {})
                contact = radar_map.get(target.id)
                if contact is None:
                    contact = Contact(
                        id=f"{radar_platform.id}-r-{target.id}",
                        kind="radar_contact",
                        own_platform_id=radar_platform.id,
                        time_s=self.time_s,
                        emitter_id=target.id,
                        emitter_name=target.name,
                    )
                    radar_map[target.id] = contact
                contact.bearing_deg = initial_bearing_deg(
                    radar_platform.latitude, radar_platform.longitude,
                    target.latitude, target.longitude)
                contact.range_m = item["dist_m"]
                contact.latitude = target.latitude
                contact.longitude = target.longitude
                contact.time_s = self.time_s
                contact.last_update_s = self.time_s
                contact.is_memory = False
                contact.confidence = 0.95
                contact.extra = {"detection_km": item["detection_km"]}
                jammer = item.get("jammer")
                if jammer is not None and jammer.active_technique == "tws_gain":
                    contact.confidence = min(contact.confidence, 0.55)
                    contact.extra["tws_degraded"] = True
            else:
                still.append(item)
        self.pending_radar = still

    def _process_pending_esm(self, dt_s: float) -> None:
        """处理已到处理时间的 ESM 截获结果。"""
        still_pending = []
        for item in self.pending_esm:
            if self.time_s >= item["available_at"]:
                self._update_contact(
                    item["own"], item["esm"], item["other"], item["source"], item["result"])
            else:
                still_pending.append(item)
        self.pending_esm = still_pending

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

    def cross_fix_radar_ranges(self) -> None:
        """多站测距交叉定位：使用雷达距离信息提高位置估计。"""
        for contact_map in self.radar_contacts.values():
            for contact in contact_map.values():
                ranges = []
                for own2, map2 in self.radar_contacts.items():
                    c = map2.get(contact.emitter_id)
                    if c is None or c.range_m is None:
                        continue
                    p = self.platforms.get(own2)
                    if p is None:
                        continue
                    ranges.append((p.latitude, p.longitude, c.range_m / 1000.0))
                if len(ranges) >= 2:
                    lat, lon = triangulate_ranges(ranges)
                    if lat is not None:
                        contact.latitude = lat
                        contact.longitude = lon

    def cross_fix_tdoa(self) -> None:
        """到达时间差（TDOA）多站定位：3 个以上 ESM 接收机粗网格搜索。"""
        groups: dict[str, list[tuple[float, float, float, str, Contact]]] = {}
        for own_id, contact_map in self.contacts.items():
            own = self.platforms.get(own_id)
            if own is None:
                continue
            for contact in contact_map.values():
                toa = contact.extra.get("toa_ns")
                if toa is None or contact.emitter_id is None:
                    continue
                groups.setdefault(contact.emitter_id, []).append(
                    (own.latitude, own.longitude, toa, own_id, contact))

        for entries in groups.values():
            if len(entries) < 3:
                continue
            lat0 = sum(e[0] for e in entries) / len(entries)
            lon0 = sum(e[1] for e in entries) / len(entries)
            ref_lat, ref_lon, ref_toa, _, _ = entries[0]
            best_lat, best_lon, best_cost = lat0, lon0, 1e18
            for i in range(-20, 21):
                for j in range(-20, 21):
                    lat = lat0 + i * 0.1
                    lon = lon0 + j * 0.1
                    cost = 0.0
                    for e in entries[1:]:
                        d0 = haversine_nm(ref_lat, ref_lon, lat, lon) * 1.852
                        d = haversine_nm(e[0], e[1], lat, lon) * 1.852
                        predicted_diff = (d - d0) / 299792458.0 * 1e9
                        measured_diff = e[2] - ref_toa
                        cost += (predicted_diff - measured_diff) ** 2
                    if cost < best_cost:
                        best_cost = cost
                        best_lat, best_lon = lat, lon
            if best_cost < 1e14:
                for _, _, _, _, contact in entries:
                    contact.latitude = best_lat
                    contact.longitude = best_lon
                    contact.extra["tdoa_fix"] = True

    def cross_fix_fdoa(self) -> None:
        """多普勒差（FDOA）三站定位：网格搜索。"""
        groups: dict[str, list[tuple[float, float, float, str, Contact]]] = {}
        for own_id, contact_map in self.contacts.items():
            own = self.platforms.get(own_id)
            if own is None:
                continue
            for contact in contact_map.values():
                dop = contact.extra.get("doppler_hz")
                if dop is None or contact.emitter_id is None:
                    continue
                groups.setdefault(contact.emitter_id, []).append(
                    (own.latitude, own.longitude, dop, own_id, contact))
        for entries in groups.values():
            if len(entries) < 3:
                continue
            lat0 = sum(e[0] for e in entries) / len(entries)
            lon0 = sum(e[1] for e in entries) / len(entries)
            ref = entries[0]
            ref_dop = ref[2]
            best_lat, best_lon, best_cost = lat0, lon0, 1e18
            for i in range(-20, 21):
                for j in range(-20, 21):
                    lat = lat0 + i * 0.1
                    lon = lon0 + j * 0.1
                    cost = 0.0
                    for e in entries[1:]:
                        platform = self.platforms.get(e[3])
                        if platform is None:
                            continue
                        v_e, v_n = self._platform_velocity_mps(platform)
                        # 接收机指向源的方向
                        brg = math.radians(initial_bearing_deg(
                            platform.latitude, platform.longitude, lat, lon))
                        u_e, u_n = math.sin(brg), math.cos(brg)
                        pred_dop = (1470000000.0 * (v_e * u_e + v_n * u_n) / 299792458.0)
                        cost += (pred_dop - (e[2] - ref_dop)) ** 2
                    if cost < best_cost:
                        best_cost = cost
                        best_lat, best_lon = lat, lon
            if best_cost < 1e8:
                for _, _, _, _, contact in entries:
                    contact.latitude = best_lat
                    contact.longitude = best_lon
                    contact.extra["fdoa_fix"] = True

    # ------------------------------------------------------------------
    # 传播链路（Phase 1 已有）
    # ------------------------------------------------------------------
    def evaluate_radar_with_jamming(self, emitter: Emitter, jammer: Jammer | None,
                                    rcs_m2: float = 1000.0,
                                    bandwidth_hz: float = 1e6,
                                    noise_figure: float = 5.0,
                                    loss: float = 6.0,
                                    snr_min_db: float = 13.0,
                                    target_platform: Platform | None = None) -> dict:
        """计算某部雷达在有/无指定干扰机时的探测与烧穿距离。

        如果传入 target_platform，则使用该目标的信号特征（RCS）替代 rcs_m2。
        """
        if target_platform is not None and target_platform.rcs_m2:
            rcs_m2 = target_platform.rcs_m2
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


def triangulate_ranges(ranges: list[tuple[float, float, float]]) -> tuple[float, float] | None:
    """多站测距交叉定位：两条距离圆交点（局部切平面近似）。"""
    if len(ranges) < 2:
        return None
    center_lat = sum(r[0] for r in ranges) / len(ranges)
    center_lon = sum(r[1] for r in ranges) / len(ranges)
    cos_lat = math.cos(math.radians(center_lat))
    R = 6371.0088

    def to_xy(lat, lon):
        return R * math.radians(lon - center_lon) * cos_lat, R * math.radians(lat - center_lat)

    def from_xy(x, y):
        return center_lat + math.degrees(y / R), center_lon + math.degrees(x / (R * cos_lat))

    (lat1, lon1, r1), (lat2, lon2, r2) = ranges[0], ranges[1]
    x1, y1 = to_xy(lat1, lon1)
    x2, y2 = to_xy(lat2, lon2)
    d = math.hypot(x2 - x1, y2 - y1)
    if d > r1 + r2 or d < abs(r1 - r2):
        return None
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    h = math.sqrt(max(h2, 0.0))
    xm = x1 + a * (x2 - x1) / d
    ym = y1 + a * (y2 - y1) / d
    rx = -(y2 - y1) * h / d
    ry = (x2 - x1) * h / d
    # 取离两平台中点最近的交点
    mx = (x1 + x2) / 2
    my = (y1 + y2) / 2
    p1 = (xm + rx, ym + ry)
    p2 = (xm - rx, ym - ry)
    best = p1 if (p1[0]-mx)**2 + (p1[1]-my)**2 <= (p2[0]-mx)**2 + (p2[1]-my)**2 else p2
    return from_xy(*best)
