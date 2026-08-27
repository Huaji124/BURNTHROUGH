"""反辐射导弹（ARM）简易模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Missile:
    id: str
    name: str
    attacker_id: str
    target_id: str
    lat: float
    lon: float
    speed_mps: float = 850.0          # 约 2.5 马赫
    range_km: float = 150.0
    memory_if_shutdown: bool = True
    memory_time_s: float = 5.0        # 辐射源关机后记忆攻击时间
    decoyed: bool = False             # 是否被欺骗干扰诱骗
    active: bool = True
    flight_time_s: float = 0.0
    no_emission_time: float = 0.0
    last_locked_lat: float | None = None
    last_locked_lon: float | None = None
    result: str | None = None         # hit / miss / lost_lock
    kind: str = "arm"                 # arm / asm
    current_speed_mps: float | None = None
    terminal_speed_mps: float | None = None
    decel_mps2: float | None = None
    max_g: float = 20.0
    altitude_ft: float = 0.0
    cruise_alt_ft: float | None = None
    climb_rate_ft_s: float = 800.0
    guidance: str = "active_radar"       # active_radar / passive_ir / sarh / anti_radiation / active_homing
    all_aspect: bool = True              # 全向弹（否则受尾部限制）
    boost_duration_s: float = 0.0        # 助推段时长
    boost_accel_mps2: float = 0.0        # 助推段加速度
    drag_coefficient: float = 0.02       # 燃尽后阻力系数（简化）
