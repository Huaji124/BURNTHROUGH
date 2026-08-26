"""演示想定：动态射频沙盘（Phase 2）。

红方：
- 驱逐舰（搜索雷达 + ESM）
- 护卫舰（ESM，与驱逐舰共同对蓝方干扰源交叉定位）
蓝方：
- 电子战飞机（绕红方驱逐舰飞行，干扰吊舱可开关）
"""

from __future__ import annotations

import math

from .environment import Environment, Platform
from .emitter import Emitter
from .receiver import Receiver
from .jammer import Jammer

RED_ESM_PARAM_LIB = ["type346_search_radar", "ecm_pod_rkz"]


def _make_esm(platform_id: str, esm_id: str, name: str) -> Receiver:
    return Receiver(
        id=esm_id,
        name=name,
        kind="esm",
        freq_min_hz=500_000_000,
        freq_max_hz=18_000_000_000,
        sensitivity_dbm=-85,
        gain_db=0,
        df_accuracy_deg=3,
        param_library=RED_ESM_PARAM_LIB,
        processing_time_s=1.5,
        platform_id=platform_id,
    )


def build_demo_environment() -> Environment:
    env = Environment()

    # 红方驱逐舰
    red_ddg = Platform(
        id="red_ddg",
        name="红方驱逐舰",
        side="red",
        kind="ship",
        latitude=22.0,
        longitude=120.0,
        altitude_ft=50.0,
        heading_deg=0.0,
        speed_kt=0.0,
    )
    red_ddg.weapons = ["反舰导弹 x8", "防空导弹 x16"]
    red_ddg.emitters.append(Emitter(
        id="type346_search_radar",
        name="Type 346 搜索雷达（演示）",
        role="multifunction_radar",
        band="S",
        freq_min_hz=2_000_000_000,
        freq_max_hz=4_000_000_000,
        peak_power_w=1_000_000,
        antenna_gain_db=40,
        pulse_width_min_us=0.5,
        pulse_width_max_us=50,
        prf_min_hz=500,
        prf_max_hz=5000,
        scan_type="mechanical_scan",
        scan_period_s=4,
        beam_width_deg=1.5,
        emcon_state="on",
        platform_id="red_ddg",
    ))
    red_ddg.receivers.append(_make_esm("red_ddg", "esm_ddg", "驱逐舰 ESM"))
    env.add_platform(red_ddg)

    # 红方护卫舰（交叉定位站）
    red_ffg = Platform(
        id="red_ffg",
        name="红方护卫舰",
        side="red",
        kind="ship",
        latitude=22.9,
        longitude=120.55,
        altitude_ft=40.0,
        heading_deg=0.0,
        speed_kt=0.0,
    )
    red_ffg.weapons = ["反舰导弹 x4", "防空导弹 x8"]
    red_ffg.receivers.append(_make_esm("red_ffg", "esm_ffg", "护卫舰 ESM"))
    env.add_platform(red_ffg)

    # 蓝方电子战飞机：绕红方驱逐舰飞行，半径约 103 km
    orbit_radius_km = 103.0
    blue_ew = Platform(
        id="blue_ew",
        name="蓝方电子战机",
        side="blue",
        kind="aircraft",
        latitude=22.0,
        longitude=121.0,
        altitude_ft=30_000,
        heading_deg=0.0,
        speed_kt=420.0,
        orbit_center_lat=22.0,
        orbit_center_lon=120.0,
        orbit_radius_km=orbit_radius_km,
        orbit_direction=1,
    )
    blue_ew.weapons = ["反辐射导弹 x2", "空空导弹 x4"]
    blue_ew.jammers.append(Jammer(
        id="ecm_pod_rkz",
        name="有源干扰吊舱（演示）",
        mode=["noise", "deception"],
        band=["S", "X", "Ku"],
        freq_min_hz=2_000_000_000,
        freq_max_hz=18_000_000_000,
        power_w=100,
        gain_db=20,
        bandwidth_hz=20_000_000,
        techniques=["spot_noise", "barrage_noise"],
        reaction_time_s=0.5,
        max_targets=4,
        emcon_state="on",
        platform_id="blue_ew",
    ))
    env.add_platform(blue_ew)

    return env
