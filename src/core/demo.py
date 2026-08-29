"""演示想定：动态射频沙盘（Phase 2）。

红方：
- 驱逐舰（搜索雷达 + ESM）
- 护卫舰（ESM，与驱逐舰共同对蓝方干扰源交叉定位）
蓝方：
- 电子战飞机（绕红方驱逐舰飞行，干扰吊舱可开关）
"""

from __future__ import annotations

from pathlib import Path

from .environment import Environment, Platform
from .jammer import Jammer
from .receiver import Receiver

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
        toa_accuracy_ns=100.0,
        fdoa_accuracy_hz=20.0,
        processing_time_s=1.5,
        platform_id=platform_id,
    )


def _rebind_platform_components(platform: Platform) -> None:
    """平台 ID 被重命名后，同步其传感器/干扰机/接收机归属。"""
    for e in platform.emitters:
        e.platform_id = platform.id
    for r in platform.receivers:
        r.platform_id = platform.id
    for j in platform.jammers:
        j.platform_id = platform.id


def build_demo_environment() -> Environment:
    """演示想定：直接使用数据库单位（两艘055 + EA-18G）。"""
    from data_loader.unit_loader import load_country_unit_file, load_unit_file

    env = Environment()
    env.sea_state = 0
    env.rain_mm_h = 0.0
    env.visibility_km = 50.0
    env.cloud_cover_pct = 0.0
    env.humidity_pct = 50.0

    u1 = load_unit_file("data/units/ship-2834.json", side="red")
    p1 = next(iter(u1.platforms.values()))
    p1.id = "red_ddg"
    p1.name = "红方055-1"
    p1.latitude = 22.0
    p1.longitude = 120.0
    _rebind_platform_components(p1)
    env.add_platform(p1)

    u2 = load_unit_file("data/units/ship-2834.json", side="red")
    p2 = next(iter(u2.platforms.values()))
    p2.id = "red_ffg"
    p2.name = "红方055-2"
    p2.latitude = 22.5
    p2.longitude = 120.5
    _rebind_platform_components(p2)
    env.add_platform(p2)

    # 055 的生成 DB 中没有可发射反舰/反辐射武器；演示想定补充弹药，
    # 让红方舰艇可以展示导弹发射/拦截/反辐射攻击链路。
    for p in (p1, p2):
        # 数据库里的扫描周期写入处理延迟/首次截获概率；演示缩短为秒级以便观察
        for r in p.receivers:
            if r.kind in ("esm", "rwr"):
                r.processing_time_s = 1.0
        for e in p.emitters:
            if e.role in ("multifunction_radar", "search_radar", "fire_control_radar"):
                e.scan_period_s = min(e.scan_period_s, 1.0)
        if not p.loadout_weapons:
            p.loadout_weapons = [
                {"name": "反舰导弹", "kind": "asm", "range_km": 120, "speed_mps": 300, "count": 16},
                {"name": "反辐射导弹", "kind": "arm", "range_km": 150, "speed_mps": 850, "count": 4},
            ]
            p.ammo = {"反舰导弹": 16, "反辐射导弹": 4}
            p.max_ammo = {"反舰导弹": 16, "反辐射导弹": 4}
            p.weapons.append("ssm")

    u3 = load_country_unit_file("data/cmo_full_by_country/united_states", "343", side="blue", kind="aircraft")
    b = next(iter(u3.platforms.values()))
    b.id = "blue_ew"
    b.name = "蓝方EA-18G电子战机"
    b.latitude = 22.0
    b.longitude = 121.0
    _rebind_platform_components(b)
    # 补充：保证演示 EW 场景有可识别的干扰吊舱（数据库里的 AN/USQ-113
    # 通信干扰机不覆盖舰载雷达频段，因此把演示吊舱放在首位）。
    b.jammers.insert(0, Jammer(
        id="ecm_pod_rkz", name="有源干扰吊舱（演示）",
        mode=["noise", "deception"], band=["S", "X", "Ku"],
        freq_min_hz=500_000_000, freq_max_hz=18_000_000_000,
        power_w=100, gain_db=30, spot_bandwidth_hz=20_000_000,
        barrage_bandwidth_hz=500_000_000, current_mode="spot_noise",
        sector_half_deg=360.0, emcon_state="on", platform_id="blue_ew"))
    # 演示反辐射链路时不让箔条随机干扰 ARM 命中，假目标诱骗由专门测试覆盖
    b.chaff_count = 0
    env.add_platform(b)

    world_path = "data/environment/world_land.json"
    if Path(world_path).exists():
        env.load_world_land_from_json(world_path)
    return env
