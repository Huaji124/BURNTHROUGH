"""数据源加载器共用工具。"""

from __future__ import annotations

import math
from collections import defaultdict

# 布点默认中心：与演示想定同一海域（台湾海峡一带）
DEFAULT_CENTER = (22.0, 120.0)


def index_by_id(records: list[dict]) -> dict[object, list[dict]]:
    """按 ID 建索引，返回 {ID: [记录, ...]}。

    loadout_weapons / magazine_weapons / propulsion_performance 都是上万条的
    扁平列表。若对每个平台的每个挂载方案都线性扫一遍全表，整体复杂度是
    O(平台数 × 挂载数 × 表长)——美国一国数据就要上十亿次比较。
    """
    index: dict[object, list[dict]] = defaultdict(list)
    for r in records:
        index[r.get("ID")].append(r)
    return index


def scatter_point(i: int, n: int, center: tuple[float, float] = DEFAULT_CENTER,
                  spread_km: float = 250.0) -> tuple[float, float]:
    """向日葵螺线布点：把 n 个单位均匀撒在中心点周围的圆盘内。

    CMO/MoZi 数据库里不含任何经纬度字段，此前所有平台都被放在 (0, 0)，
    全部重叠在几内亚湾同一个点上。这里用黄金角螺线做确定性散布：
    任意前缀都近似均匀，且单位之间不会互相压住。
    """
    if n <= 1:
        return center
    radius_km = spread_km * math.sqrt((i + 0.5) / n)
    theta = math.radians(i * 137.508)
    dlat = (radius_km * math.cos(theta)) / 111.32
    dlon = (radius_km * math.sin(theta)) / (
        111.32 * math.cos(math.radians(center[0])) + 1e-9)
    return center[0] + dlat, center[1] + dlon
