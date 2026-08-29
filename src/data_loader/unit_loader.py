"""单个单位加载器：从 data/units/<id>.json 加载一个平台到环境。"""

from __future__ import annotations

import json
from pathlib import Path

from core.environment import Environment, Platform
from data_loader.china_loader import _sensor_to_components
from data_loader.weapon_kind import infer_weapon_kind


def load_unit_file(path: str | Path, side: str = "red") -> Environment:
    """从单位 JSON 文件构建只含一个平台的环境。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    env = Environment()
    add_unit_to_environment(env, data, side=side)
    return env


def add_unit_to_environment(env: Environment, data: dict, side: str = "red") -> str:
    """把单位 JSON 数据加到已有环境，返回平台ID。"""
    raw = data.get("platform", {})
    kind = data.get("kind", "ship")
    pid = f"{kind}-{raw.get('ID')}"
    name = raw.get("Name") or pid
    if kind == "aircraft":
        speed_kt = float(raw.get("CruiseSpeedKts") or 400)
        alt = 30_000.0
    elif kind == "submarine":
        speed_kt = float(raw.get("SpeedKts") or 15)
        alt = 0.0
    else:
        speed_kt = float(raw.get("SpeedKts") or 20)
        alt = 0.0

    platform = Platform(
        id=pid,
        name=name,
        side=side,
        kind=kind,
        latitude=float(raw.get("Latitude") or 0.0),
        longitude=float(raw.get("Longitude") or 0.0),
        altitude_ft=alt,
        heading_deg=0.0,
        speed_kt=speed_kt,
        cruise_speed_kt=speed_kt,
        hp=float(raw.get("DamagePoints") or 100),
    )

    # 信号特征
    for sig in data.get("signatures", []):
        st = sig.get("Type")
        if st in (5001, 5002):
            platform.sig_radar_db_sm = float(sig.get("Front") or 0)
        elif st in (4001, 4002):
            platform.sig_ir_km = float(sig.get("Front") or 0)
        elif st in (1001, 1002, 1003, 1004, 2001):
            platform.sig_sonar_db = float(sig.get("Front") or 0)

    # 传感器
    for sid in data.get("sensor_ids", []):
        sensor = data.get("sensors", {}).get(str(sid))
        if not sensor:
            continue
        emitters, receivers, jammers = _sensor_to_components(sensor, platform.id)
        platform.emitters.extend(emitters)
        platform.receivers.extend(receivers)
        platform.jammers.extend(jammers)

    # 武器/装置
    for wid in data.get("mount_ids", []):
        mount = data.get("mounts", {}).get(str(wid))
        if not mount:
            continue
        mname = mount.get("Name") or ""
        platform.weapons.append(mname)
        if "ciws" in mname.lower() or "1130" in mname or "730" in mname or "h/pj-14" in mname or "h/pj-12" in mname:
            platform.ciws = True
            platform.ciws_hit_probability = 0.45
        if "gun" in mname.lower() or mname.lower().startswith("h/pj"):
            platform.gun_range_km = max(platform.gun_range_km, 8.0)
            platform.gun_hit_probability = max(platform.gun_hit_probability, 0.15)
        if any(k in mname.lower() for k in ("chaff", "decoy", "dl", "诱饵", "干扰弹")):
            platform.chaff_count = max(platform.chaff_count, int(mount.get("Capacity") or 12))

    # 挂载 -> 实际导弹
    for lw in data.get("loadout_weapons", []):
        weapon = data.get("weapons", {}).get(str(lw.get("WeaponID")))
        if not weapon:
            continue
        wname = weapon.get("Name") or "?"
        count = int(lw.get("DefaultLoad") or 1)
        platform.loadout_weapons.append({
            "name": wname,
            "kind": infer_weapon_kind(wname),
            "count": count,
        })
        if wname not in platform.ammo:
            platform.ammo[wname] = count
            platform.max_ammo[wname] = count
        if wname not in platform.magazine:
            platform.magazine[wname] = 0

    # 弹药库
    for mw in data.get("magazine_weapons", []):
        weapon = data.get("weapons", {}).get(str(mw.get("WeaponID")))
        if not weapon:
            continue
        wname = weapon.get("Name") or "?"
        mag = data.get("magazines", {}).get(str(mw.get("ID"))) or {}
        platform.magazine[wname] = int(mag.get("Capacity") or 0)
        if wname not in platform.max_ammo:
            platform.max_ammo[wname] = max(1, platform.magazine[wname])

    # 推进/燃料
    max_speed = 0.0
    for prid in data.get("propulsion_ids", []):
        for perf in data.get("propulsion_performance", []):
            if perf.get("ID") == prid:
                spd = float(perf.get("Speed") or 0)
                max_speed = max(max_speed, spd)
    if max_speed:
        platform.max_speed_kt = max_speed
    platform.fuel_kg = platform.fuel_capacity_kg

    env.add_platform(platform)
    return platform.id
