"""接收机实体：雷达接收通道、ESM/RWR、通信接收机。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Receiver:
    id: str
    name: str
    kind: str                        # radar / esm / rwr / comint
    freq_min_hz: float
    freq_max_hz: float
    sensitivity_dbm: float
    gain_db: float = 0.0
    df_accuracy_deg: float | None = None   # 测向精度（ESM/RWR）
    param_library: list[str] = field(default_factory=list)  # 可识别的辐射源类型 ID
    signal_params: dict[str, dict] = field(default_factory=dict)  # 多参数信号库
    toa_accuracy_ns: float = 0.0       # 到达时间测量精度（0=无TOA）
    fdoa_accuracy_hz: float = 0.0      # 多普勒测量精度（0=无FDOA）
    processing_time_s: float = 1.0
    platform_id: str | None = None

    @property
    def sensitivity_w(self) -> float:
        return 10.0 ** (self.sensitivity_dbm / 10.0) / 1000.0

    @property
    def gain_linear(self) -> float:
        return 10.0 ** (self.gain_db / 10.0)

    def covers_frequency(self, freq_hz: float) -> bool:
        return self.freq_min_hz <= freq_hz <= self.freq_max_hz
