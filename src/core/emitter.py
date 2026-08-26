"""发射机实体：雷达、通信电台、数据链等主动辐射源。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Emitter:
    id: str
    name: str
    role: str                        # multifunction_radar / fire_control_radar / search_radar / radio
    band: str                        # S / X / Ku ...
    freq_min_hz: float
    freq_max_hz: float
    peak_power_w: float
    antenna_gain_db: float
    pulse_width_min_us: float = 0.5
    pulse_width_max_us: float = 50.0
    prf_min_hz: float = 500.0
    prf_max_hz: float = 5000.0
    scan_type: str = "mechanical_scan"
    scan_period_s: float = 4.0
    beam_width_deg: float = 1.5
    emcon_state: str = "on"          # on / off
    platform_id: str | None = None   # 载体平台 ID

    @property
    def is_emitting(self) -> bool:
        return self.emcon_state == "on"

    @property
    def center_freq_hz(self) -> float:
        return (self.freq_min_hz + self.freq_max_hz) / 2.0

    @property
    def gain_linear(self) -> float:
        return 10.0 ** (self.antenna_gain_db / 10.0)

    def covers_frequency(self, freq_hz: float) -> bool:
        return self.freq_min_hz <= freq_hz <= self.freq_max_hz
