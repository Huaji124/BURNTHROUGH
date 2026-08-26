"""演示想定：静态射频沙盘。

红方：驱逐舰（搜索雷达开机 + ESM）
蓝方：电子战飞机（干扰吊舱可开关）
"""

from __future__ import annotations

from .environment import Environment, Platform
from .emitter import Emitter
from .receiver import Receiver
from .jammer import Jammer


def build_demo_environment() -> Environment:
    env = Environment()

    # 红方驱逐舰
    red_ship = Platform(
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
    red_ship.emitters.append(Emitter(
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
    red_ship.receivers.append(Receiver(
        id="esm_type726",
        name="雷达侦察告警设备（演示）",
        kind="esm",
        freq_min_hz=500_000_000,
        freq_max_hz=18_000_000_000,
        sensitivity_dbm=-75,
        gain_db=0,
        df_accuracy_deg=3,
        param_library=["type346_search_radar"],
        processing_time_s=1.5,
        platform_id="red_ddg",
    ))
    env.add_platform(red_ship)

    # 蓝方电子战飞机
    blue_ew = Platform(
        id="blue_ew",
        name="蓝方电子战机",
        side="blue",
        kind="aircraft",
        latitude=21.0,
        longitude=120.5,
        altitude_ft=30_000,
        heading_deg=180.0,
        speed_kt=420.0,
    )
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
