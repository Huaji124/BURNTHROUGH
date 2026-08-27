"""干扰机实体：有源干扰吊舱/舰载干扰机。

Phase 3 增加：
- 干扰样式：瞄准式噪声 / 阻塞式噪声，影响干扰带宽
- 干扰扇区：以干扰机航向为中心的半角扇区（360° 为全向）
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Jammer:
    id: str
    name: str
    mode: list[str]                   # noise / deception
    band: list[str]                   # S / X / Ku
    freq_min_hz: float
    freq_max_hz: float
    power_w: float
    gain_db: float
    spot_bandwidth_hz: float = 20_000_000      # 瞄准式噪声带宽
    barrage_bandwidth_hz: float = 500_000_000  # 阻塞式噪声带宽
    current_mode: str = "spot_noise"           # spot_noise / barrage_noise
    sector_half_deg: float = 360.0             # 干扰扇区半角，360=全向
    techniques: list[str] = field(default_factory=list)
    role: str = "ecm"                  # ecm / comm
    active_technique: str = "none"    # none / rgpo / vgpo / false_target / tws_gain
    look_through_enabled: bool = False
    look_through_period_s: float = 2.0
    look_through_duration_s: float = 0.2
    reaction_time_s: float = 0.5
    max_targets: int = 4
    emcon_state: str = "off"          # on / off
    platform_id: str | None = None

    @property
    def is_jamming(self) -> bool:
        return self.emcon_state == "on"

    @property
    def gain_linear(self) -> float:
        return 10.0 ** (self.gain_db / 10.0)

    @property
    def bandwidth_hz(self) -> float:
        """当前干扰样式的有效带宽。"""
        if self.current_mode == "barrage_noise":
            return self.barrage_bandwidth_hz
        return self.spot_bandwidth_hz

    def covers_frequency(self, freq_hz: float) -> bool:
        return self.freq_min_hz <= freq_hz <= self.freq_max_hz

    def set_mode(self, mode: str) -> None:
        if mode in ("spot_noise", "barrage_noise"):
            self.current_mode = mode

    def set_technique(self, technique: str) -> None:
        if technique in ("none", "rgpo", "vgpo", "false_target", "tws_gain"):
            self.active_technique = technique

    def has_deception(self) -> bool:
        return self.active_technique != "none" and self.is_jamming
