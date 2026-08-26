"""模拟引擎（时间推进）。

Phase 1 只提供接口占位，当前静态射频沙盘不需要时间推进。
后续 Phase 2 引入运动/扫描截获概率时在此实现主循环。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .environment import Environment
from .event import SimEvent


@dataclass
class SimClock:
    time_s: float = 0.0
    time_scale: float = 1.0          # 1 = 实时, 60 = 1 分钟/秒
    running: bool = False

    def step(self, dt_s: float) -> None:
        if self.running:
            self.time_s += dt_s * self.time_scale


@dataclass
class Simulation:
    environment: Environment = field(default_factory=Environment)
    clock: SimClock = field(default_factory=SimClock)
    events: list[SimEvent] = field(default_factory=list)

    def tick(self, dt_s: float = 1.0) -> list[SimEvent]:
        """推进一帧，返回本帧新事件（Phase 2 实现）。"""
        self.clock.step(dt_s)
        new_events: list[SimEvent] = []
        # TODO(Phase 2): 平台运动、ESM 扫描截获、接触更新
        return new_events

    def log(self, event: SimEvent) -> None:
        self.events.append(event)
