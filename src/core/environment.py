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

    # 编队与交战规则
    group_id: str | None = None
    roe: str = "free"                 # free / weapons_free / hold / weapons_hold
    home_lat: float | None = None
    home_lon: float | None = None
    agility: float = 0.0              # 机动性（0~?，用于命中概率修正）

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
    _false_target_seq: int = 0

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
        )
        if kind == "arm":
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
            step_m = missile.speed_mps * dt_s

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
                    elif self.rng.random() < self._hit_chance(target):
                        missile.result = "hit"
                        self._damage_platform(target, missile)
                    else:
                        missile.result = "miss"
                        self.events.append({"time": self.time_s, "kind": "missile_miss",
                                            "message": f"{missile.name} 未命中（目标机动/干扰）"})
                elif missile.kind == "aam":
                    missile.active = False
                    if actual_m < 500.0:
                        if self.rng.random() < self._hit_chance(target):
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
                    if self.rng.random() < self._hit_chance(target):
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

    def _hit_chance(self, target: Platform) -> float:
        """命中概率：基础 ARM 命中率 × 目标机动修正。"""
        base = self.arm_hit_probability
        maneuver_penalty = min(0.6, target.agility * 0.01)
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
                        if jammer.emcon_state != "on":
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
        self.update_radar_detection(dt_s)
        self.update_ir_detection(dt_s)
        self.update_sonar_detection(dt_s)
        self.update_contact_aging()
        self.cross_fix_contacts()

    def step_motion(self, dt_s: float) -> None:
        """运动模型：优先沿航路点，其次绕飞轨道，最后直线。"""
        for p in self.platforms.values():
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
                    # 视距
                    horizon_nm = 1.23 * (math.sqrt(max(radar_platform.altitude_ft, 0.0)) +
                                         math.sqrt(max(target.altitude_ft, 0.0)))
                    if dist_m > horizon_nm * 1852.0:
                        radar_map.pop(target.id, None)
                        continue
                    jammer = None
                    for other in self.platforms.values():
                        if other.side == radar_platform.side or not other.alive:
                            continue
                        for j in other.jammers:
                            if j.is_jamming and j.covers_frequency(emitter.center_freq_hz):
                                jammer = j
                                break
                        if jammer is not None:
                            break
                    result = self.evaluate_radar_with_jamming(
                        emitter, jammer, bandwidth_hz=1_000_000,
                        noise_figure=5.0, loss=6.0, snr_min_db=13.0,
                        target_platform=target)
                    detection_km = result["detection_range_km"]
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
                            contact = Contact(
                                id=f"{radar_platform.id}-r-{target.id}",
                                kind="radar_contact",
                                own_platform_id=radar_platform.id,
                                time_s=now,
                                emitter_id=target.id,
                                emitter_name=target.name,
                            )
                            radar_map[target.id] = contact
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
                if dist_km <= target.ir_detection_km:
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
                range_km = 20.0 + max(0.0, target.sonar_signature_db - 100.0) * 0.2
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
