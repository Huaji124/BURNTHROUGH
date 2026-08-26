"""干扰机实体：有源干扰吊舱/舰载干扰机。"""

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
    bandwidth_hz: float               # 干扰带宽（阻塞式通常大）
    techniques: list[str] = field(default_factory=list)  # spot_noise / barrage_noise / RGPO ...
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

    def covers_frequency(self, freq_hz: float) -> bool:
        return self.freq_min_hz <= freq_hz <= self.freq_max_hz
