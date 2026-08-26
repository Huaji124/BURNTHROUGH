"""接触（Contact）模型。

区分两类接触：
- radar_contact：雷达回波形成的目标接触（有距离/方位/速度）
- emitter_contact：ESM 截获形成的辐射源接触（只有测向和参数，可能仅有方位线）
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Contact:
    id: str
    kind: str                        # radar_contact / emitter_contact
    own_platform_id: str
    time_s: float
    latitude: float | None = None    # 定位解算位置（可能缺失）
    longitude: float | None = None
    bearing_deg: float | None = None # 测向方位
    range_m: float | None = None     # 雷达接触才有
    speed_kt: float | None = None
    emitter_id: str | None = None    # 若已识别，关联辐射源
    emitter_name: str | None = None
    confidence: float = 0.0          # 识别置信度 0~1
    is_memory: bool = False          # 是否记忆接触（信号已丢失）
    last_update_s: float = 0.0
    extra: dict = field(default_factory=dict)
