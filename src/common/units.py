"""单位换算工具。

兵推中常见的单位统一约定：
- 距离：米（内部计算）、海里（战术显示）
- 高度：英尺（航空常用）、米（内部）
- 速度：节（舰船）、马赫（飞机/导弹）
- 功率：W（内部）、dBm（接收机常用）
"""

from __future__ import annotations

import math

# 长度
M_PER_NM = 1852.0
FT_PER_M = 3.280839895
M_PER_FT = 0.3048

# 速度
KT_TO_MPS = M_PER_NM / 3600.0  # 1 节 = 0.514444 m/s
MPS_TO_KT = 1.0 / KT_TO_MPS
MACH_AT_SEA_LEVEL_MPS = 340.294  # 海平面标准大气声速


def nm_to_m(nm: float) -> float:
    return nm * M_PER_NM


def m_to_nm(m: float) -> float:
    return m / M_PER_NM


def ft_to_m(ft: float) -> float:
    return ft * M_PER_FT


def m_to_ft(m: float) -> float:
    return m * FT_PER_M


def kt_to_mps(kt: float) -> float:
    return kt * KT_TO_MPS


def mps_to_kt(mps: float) -> float:
    return mps * MPS_TO_KT


def mach_to_mps(mach: float) -> float:
    return mach * MACH_AT_SEA_LEVEL_MPS


def mps_to_mach(mps: float) -> float:
    return mps / MACH_AT_SEA_LEVEL_MPS


def db_to_linear(db: float) -> float:
    """分贝转线性倍数值。"""
    return 10.0 ** (db / 10.0)


def linear_to_db(linear: float) -> float:
    """线性倍数值转分贝。"""
    if linear <= 0:
        return -math.inf
    return 10.0 * math.log10(linear)


def w_to_dbm(w: float) -> float:
    """瓦转 dBm（1 mW 基准）。"""
    if w <= 0:
        return -math.inf
    return 10.0 * math.log10(w * 1000.0)


def dbm_to_w(dbm: float) -> float:
    """dBm 转瓦。"""
    return 10.0 ** (dbm / 10.0) / 1000.0
