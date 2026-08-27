"""从 CMO 世界数据导出 JSON（data/cmo_world_full.json）构建烧穿环境。

该文件较大且为本地参考数据（已 .gitignore），适合在本地运行游戏时加载。
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
    if role_id <= 2100:
        return "search_radar"
    if role_id < 2200:
        return "multifunction_radar"
    return "fire_control_radar"


def _sensor_to_components(sensor: dict, platform_id: str) -> tuple[list[Emitter], list[Receiver], list[Jammer]]:
    """将一个 DataSensor 记录映射为本项目组件。"""
    emitters: list[Emitter] = []
    receivers: list[Receiver] = []
    jammers: list[Jammer] = []
    rid = sensor.get("Role")
    sid = str(sensor.get("ID"))

    if sensor.get("RadarPeakPower") or (rid in SENSOR_ROLE_RADAR):
        emitters.append(Emitter(
            id=f"cmo-world-{sid}",
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

    if sensor.get("ESMSensitivity") or (rid in SENSOR_ROLE_RWR | SENSOR_ROLE_ESM):
        receivers.append(Receiver(
            id=f"cmo-world-{sid}-esm",
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

    if sensor.get("ECMPeakPower") or sensor.get("ECMGain") or (rid in SENSOR_ROLE_ECM):
        jammers.append(Jammer(
            id=f"cmo-world-{sid}-ecm",
            name=sensor.get("Name") or f"ECM {sid}",
            mode=["noise", "deception"],
            band=["S", "X", "Ku"],
            freq_min_hz=_hz(sensor.get("FrequencyLower")),
            freq_max_hz=_hz(sensor.get("FrequencyUpper")),
            power_w=float(sensor.get("ECMPeakPower") or 100),
            gain_db=float(sensor.get("ECMGain") or 10),
            spot_bandwidth_hz=20_000_000,
            barrage_bandwidth_hz=500_000_000,
            current_mode="spot_noise",
            max_targets=int(sensor.get("ECMNumberOfTargets") or 4),
            techniques=["spot_noise", "barrage_noise", "rgpo", "vgpo", "false_target"],
            sector_half_deg=180.0,
            emcon_state="on",
            platform_id=platform_id,
        ))
    return emitters, receivers, jammers


def _build_from_data(data: dict, side: str = "blue",
                     limit_platforms: int | None = None) -> Environment:
    """从 CMO 风格数据字典构建环境。"""
    env = Environment()
    selected = data["platforms"]
    if limit_platforms is not None:
        selected = selected[:limit_platforms]

    for p in selected:
        raw = p.get("raw", {})
        pid = f"{p['kind']}-{raw.get('ID')}"
        name = raw.get("Name") or pid

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

        for sid in p.get("sensor_ids", []):
            sensor = data["sensors"].get(str(sid))
            if not sensor:
                continue
            emitters, receivers, jammers = _sensor_to_components(sensor, platform.id)
            platform.emitters.extend(emitters)
            platform.receivers.extend(receivers)
            platform.jammers.extend(jammers)

        for wid in p.get("mount_ids", []):
            mount = data["mounts"].get(str(wid))
            if not mount:
                continue
            mname = mount.get("Name") or ""
            platform.weapons.append(mname)
            if (any(k in mname.lower() for k in ("ciws", "近距离", "phalanx", "1130", "730", "h/pj-14", "h/pj-12"))
                    or "近距离" in mname):
                platform.ciws = True
                platform.ciws_hit_probability = 0.4
            if "gun" in mname.lower() or "naval gun" in mname.lower():
                platform.gun_range_km = max(platform.gun_range_km, 8.0)
                platform.gun_hit_probability = max(platform.gun_hit_probability, 0.15)
            if (any(k in mname.lower() for k in ("ssm", "anti-ship", "harpoon", "exocet", "tomahawk"))
                    and "ssm" not in platform.weapons):
                platform.weapons.append("ssm")

        platform.extra_loadouts = {
            "loadout_ids": p.get("loadout_ids", []),
            "magazine_ids": p.get("magazine_ids", []),
            "propulsion_ids": p.get("propulsion_ids", []),
            "operator_country": raw.get("OperatorCountry"),
            "year_commissioned": raw.get("YearCommissioned"),
        }
        env.add_platform(platform)

    env.data_source = str(data.get("source", ""))
    return env


def load_cmo_world_environment(path: str | Path = "data/cmo_world_full.json",
                               side: str = "blue",
                               limit_platforms: int | None = None) -> Environment:
    """加载 CMO 世界数据合并 JSON（老格式）。"""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return _build_from_data(data, side=side, limit_platforms=limit_platforms)


def load_cmo_country_environment(country_dir: str | Path, side: str = "blue",
                                 limit_platforms: int | None = None) -> Environment:
    """从 cmo_full_by_country/<slug>/ 目录加载一个国家。

    目录需包含 platforms.json / sensors.json / mounts.json。
    """
    base = Path(country_dir)
    data = {
        "platforms": json.loads((base / "platforms.json").read_text(encoding="utf-8")),
        "sensors": json.loads((base / "sensors.json").read_text(encoding="utf-8")),
        "mounts": json.loads((base / "mounts.json").read_text(encoding="utf-8")),
        "weapons": json.loads((base / "weapons.json").read_text(encoding="utf-8")) if (base / "weapons.json").exists() else {},
        "loadout_weapons": json.loads((base / "loadout_weapons.json").read_text(encoding="utf-8")) if (base / "loadout_weapons.json").exists() else [],
        "loadouts": json.loads((base / "loadouts.json").read_text(encoding="utf-8")) if (base / "loadouts.json").exists() else {},
    }
    return _build_from_data(data, side=side, limit_platforms=limit_platforms)
