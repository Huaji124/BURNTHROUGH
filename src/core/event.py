"""模拟事件模型：日志、发现、发射、命中等。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SimEvent:
    time_s: float
    kind: str                        # emitter_on / emitter_off / esm_detection / ...
    message: str
    severity: str = "info"           # info / warning / critical
    related_platform_id: str | None = None
    extra: dict = field(default_factory=dict)
