"""从 china_full.json 构建烧穿环境的加载器。

将 CMO/MoZi 数据库导出的中国平台数据映射到本项目的核心实体：
- 平台 -> Platform
- 传感器 -> Emitter / Receiver / Jammer（按角色分类）
- 武器/发射装置 -> weapons 列表 + 近防/舰炮标志
- 挂载方案 -> 记录到 platform.system_data 备用

用法：
    from data_loader.china_loader import load_china_environment
    env = load_china_environment("data/china_full.json", side="red")
"""

from __future__ import annotations

import json
from pathlib import Path

from core.emitter import Emitter
from core.environment import Environment, Platform
from core.jammer import Jammer
from core.receiver import Receiver

SENSOR_ROLE_RADAR = set(range(2001, 2200)) | {2207, 2208, 2209}
SENSOR_ROLE_ECM = {4001, 4011, 4021, 4031, 4091}
SENSOR_ROLE_RWR = {3001}
SENSOR_ROLE_ESM = {3011, 3012, 3031, 3032, 3201, 3202}


def _hz(mhz_value: float | None) -> float:
    """CMO 数据库频率以 MHz 存储；统一转 Hz。"""
    if not mhz_value:
        return 1_000_000_000.0
    return float(mhz_value) * 1_000_000


def _role_name(role_id: int | None) -> str:
    if role_id is None:
        return "search_radar"
    if role_id in SENSOR_ROLE_RWR:
        return "multifunction_radar" if False else "search_radar"
    if role_id in SENSOR_ROLE_ECM or role_id in SENSOR_ROLE_ESM:
        return "search_radar"
    if role_id <= 2100:
        return "search_radar"
    if role_id < 2200:
        return "multifunction_radar"
    return "fire_control_radar"


def _infer_weapon_kind(name: str) -> str:
    """根据名称推断武器类型。"""
    n = name.lower()
    if "pl-" in n:
        return "aam"
    if "yj" in n or "c-8" in n or "ss-n" in n or "anti-ship" in n:
        return "asm"
    if "hq" in n or "sa-n" in n or "fl-3000" in n:
        return "sam"
    if n.startswith(("torpedo", "鱼雷", "tt")) or "torpedo" in n:
        return "torpedo"
    return "weapon"


def _sensor_to_components(sensor: dict, platform_id: str) -> tuple[list[Emitter], list[Receiver], list[Jammer]]:
    """将一个 DataSensor 记录映射为本项目组件。"""
    emitters: list[Emitter] = []
    receivers: list[Receiver] = []
    jammers: list[Jammer] = []
    rid = sensor.get("Role")
    sid = str(sensor.get("ID"))

    # 雷达发射机
    if sensor.get("RadarPeakPower") or (rid in SENSOR_ROLE_RADAR):
        emitters.append(Emitter(
            id=f"china-cmo-{sid}",
            name=sensor.get("Name") or f"传感器 {sid}",
            role=_role_name(rid),
            band="X" if _hz(sensor.get("FrequencyLower")) >= 8e9 else "S",
            freq_min_hz=_hz(sensor.get("FrequencyLower")),
            freq_max_hz=_hz(sensor.get("FrequencyUpper")),
            peak_power_w=float(sensor.get("RadarPeakPower") or 100_000),
            antenna_gain_db=0.0,
            prf_min_hz=float(sensor.get("RadarPRF") or 500),
            prf_max_hz=float(sensor.get("RadarPRF") or 5000),
            scan_period_s=float(sensor.get("ScanInterval") or 4.0),
            beam_width_deg=float(sensor.get("RadarHorizontalBeamwidth") or 1.5),
            frequency_agility=bool(sensor.get("FrequencyAgility") or False),
            pulse_compression_gain_db=float(sensor.get("RadarProcessingGainLoss") or 0),
            platform_id=platform_id,
        ))

    # ESM / RWR
    if sensor.get("ESMSensitivity") or (rid in SENSOR_ROLE_RWR | SENSOR_ROLE_ESM):
        receivers.append(Receiver(
            id=f"china-cmo-{sid}-esm",
            name=sensor.get("Name") or f"ESM {sid}",
            kind="rwr" if rid in SENSOR_ROLE_RWR else "esm",
            freq_min_hz=_hz(sensor.get("FrequencyLower")),
            freq_max_hz=_hz(sensor.get("FrequencyUpper")),
            sensitivity_dbm=float(sensor.get("ESMSensitivity") or -70),
            gain_db=0.0,
            df_accuracy_deg=float(sensor.get("DirectionFindingAccuracy") or 3),
            processing_time_s=float(sensor.get("ScanInterval") or 1.0),
            platform_id=platform_id,
        ))

    # 声呐（简化：接收机 kind=sonar）
    if rid is not None and rid >= 5001:
        receivers.append(Receiver(
            id=f"china-cmo-{sid}-sonar",
            name=sensor.get("Name") or f"声呐 {sid}",
            kind="sonar",
            freq_min_hz=0,
            freq_max_hz=0,
            sensitivity_dbm=-80,
            gain_db=0,
            df_accuracy_deg=5,
            processing_time_s=5.0,
            platform_id=platform_id,
        ))

    # 电子干扰机
    if sensor.get("ECMPeakPower") or sensor.get("ECMGain") or (rid in SENSOR_ROLE_ECM):
        jammers.append(Jammer(
            id=f"china-cmo-{sid}-ecm",
            name=sensor.get("Name") or f"ECM {sid}",
            mode=["noise", "deception"],
            band=["S", "X", "Ku"],
            freq_min_hz=_hz(sensor.get("FrequencyLower")),
            freq_max_hz=_hz(sensor.get("FrequencyUpper")),
            power_w=float(sensor.get("ECMPeakPower") or 100),
            gain_db=float(sensor.get("ECMGain") or 10),
            spot_bandwidth_hz=_hz(sensor.get("ECMBandwidth") or 20) if sensor.get("ECMBandwidth") else 20_000_000,
            barrage_bandwidth_hz=500_000_000,
            current_mode="barrage_noise" if (sensor.get("ECMBandwidth") or 0) > 500 else "spot_noise",
            max_targets=int(sensor.get("ECMNumberOfTargets") or 4),
            techniques=["spot_noise", "barrage_noise", "rgpo", "vgpo", "false_target"],
            sector_half_deg=180.0,
            emcon_state="on",
            platform_id=platform_id,
        ))

    return emitters, receivers, jammers


def load_china_environment(path: str | Path = "data/china_full.json",
                           side: str = "red",
                           limit_platforms: int | None = None) -> Environment:
    """从完整导出 JSON 构建一个环境（平台位置默认 0,0，可后续设置）。"""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    env = Environment()

    selected = data["platforms"]
    if limit_platforms is not None:
        selected = selected[:limit_platforms]

    for p in selected:
        raw = p.get("raw", {})
        pid = f"{p['kind']}-{raw.get('ID')}"
        name = raw.get("Name") or pid

        # 基础平台
        if p["kind"] == "ship":
            kind = "ship"
            speed_kt = float(raw.get("SpeedKts") or 20)
        elif p["kind"] == "submarine":
            kind = "submarine"
            speed_kt = float(raw.get("SpeedKts") or 15)
        else:
            kind = "aircraft"
            speed_kt = float(raw.get("CruiseSpeedKts") or 400)

        platform = Platform(
            id=pid,
            name=name,
            side=side,
            kind=kind,
            latitude=0.0,
            longitude=0.0,
            altitude_ft=30_000.0 if kind == "aircraft" else 0.0,
            heading_deg=0.0,
            speed_kt=speed_kt,
            cruise_speed_kt=speed_kt,
            hp=float(raw.get("DamagePoints") or 100),
        )
        if raw.get("Agility"):
            platform.agility = float(raw.get("Agility") or 0)

        # 信号特征（RCS / 红外 / 声呐）
        for sig in p.get("signatures", []):
            sig_type = sig.get("Type")
            if sig_type in (5001, 5002):
                platform.sig_radar_db_sm = float(sig.get("Front") or 0)
            elif sig_type in (4001, 4002):
                platform.sig_ir_km = float(sig.get("Front") or 0)
            elif sig_type in (1001, 1002, 1003, 1004, 2001):
                platform.sig_sonar_db = float(sig.get("Front") or 0)

        # 传感器 -> 组件
        for sid in p.get("sensor_ids", []):
            sensor = data["sensors"].get(str(sid))
            if not sensor:
                continue
            emitters, receivers, jammers = _sensor_to_components(sensor, platform.id)
            platform.emitters.extend(emitters)
            platform.receivers.extend(receivers)
            platform.jammers.extend(jammers)

        # 武器/发射装置
        for wid in p.get("mount_ids", []):
            mount = data["mounts"].get(str(wid))
            if not mount:
                continue
            mname = mount.get("Name") or ""
            platform.weapons.append(mname)
            if (any(k in mname.lower() for k in ("ciws", "近距离", "1130", "730", "h/pj-14", "h/pj-12", "h/pj-11"))
                    or "近距离" in mname):
                platform.ciws = True
                platform.ciws_hit_probability = 0.4
            if "gun" in mname.lower() or mname.lower().startswith("h/pj"):
                platform.gun_range_km = max(platform.gun_range_km, 8.0)
                platform.gun_hit_probability = max(platform.gun_hit_probability, 0.15)
            if (any(k in mname.lower() for k in ("ssm", "anti-ship", "yj", "c-8"))
                    and "ssm" not in platform.weapons):
                platform.weapons.append("ssm")

        # 挂载方案 -> 实际导弹
        for lid in p.get("loadout_ids", []):
            loadout = data["loadouts"].get(str(lid))
            if not loadout:
                continue
            for lw in data.get("loadout_weapons", []):
                if lw.get("ID") != lid:
                    continue
                weapon = data["weapons"].get(str(lw.get("WeaponID")))
                if not weapon:
                    continue
                wname = weapon.get("Name") or "? "
                kind2 = _infer_weapon_kind(wname)
                count = int(lw.get("DefaultLoad") or loadout.get("Capacity") or 1)
                platform.loadout_weapons.append({
                    "name": wname,
                    "kind": kind2,
                    "count": count,
                })
                if wname not in platform.ammo:
                    platform.ammo[wname] = count
                    platform.max_ammo[wname] = count
                if wname not in platform.magazine:
                    platform.magazine[wname] = 0

        # 弹药库
        for mid in p.get("magazine_ids", []):
            mag = data["magazines"].get(str(mid))
            if not mag:
                continue
            for mw in data.get("magazine_weapons", []):
                if mw.get("ID") != mid:
                    continue
                weapon = data["weapons"].get(str(mw.get("WeaponID")))
                if not weapon:
                    continue
                wname = weapon.get("Name") or "? "
                platform.magazine[wname] = int(mag.get("Capacity") or 0)
                if wname not in platform.ammo:
                    platform.ammo[wname] = 0
                if wname not in platform.max_ammo:
                    platform.max_ammo[wname] = max(1, int(mag.get("Capacity") or 0) and 1 or 1)

        # 推进性能 -> 最大速度/燃料
        max_speed = 0.0
        for prid in p.get("propulsion_ids", []):
            for perf in data.get("propulsion_performance", []):
                if perf.get("ID") == prid:
                    spd = float(perf.get("Speed") or 0)
                    max_speed = max(max_speed, spd)
                    plat_fuel = float(perf.get("Consumption") or 0)
                    if plat_fuel > 0:
                        platform.fuel_consumption_kg_per_h = max(
                            platform.fuel_consumption_kg_per_h, plat_fuel)
        if max_speed > 0:
            platform.max_speed_kt = max_speed
            platform.speed_kt = min(platform.speed_kt, max_speed)
            platform.cruise_speed_kt = min(platform.cruise_speed_kt, max_speed)

        fuel_cap = 0.0
        for fid in p.get("fuel_ids", []):
            f = data["fuel"].get(str(fid))
            if f:
                fuel_cap += float(f.get("Capacity") or 0)
        if fuel_cap > 0:
            platform.fuel_capacity_kg = fuel_cap
            platform.fuel_kg = fuel_cap

        # 挂载方案信息（原样保留在 extra）
        platform.extra_loadouts = {
            "loadout_ids": p.get("loadout_ids", []),
            "magazine_ids": p.get("magazine_ids", []),
            "propulsion_ids": p.get("propulsion_ids", []),
        }
        env.add_platform(platform)

    # 记录数据来源，便于 UI/日志显示
    env.data_source = str(path)
    return env
