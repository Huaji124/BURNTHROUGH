"""将 Type 003 福建舰补充数据合并到 china_full.json 和 china_units.json。

用法：
    python scripts/merge_type003.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "china_type003_fujian.json"
FULL = ROOT / "data" / "china_full.json"
UNITS = ROOT / "data" / "china_units.json"

PLATFORM_RAW_ID = 9003
SENSOR_IDS = [900301, 900302, 900303, 900304, 900305, 900306]
MOUNT_IDS = [900401, 900402, 900403, 900404]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def build_type003_records(src: dict) -> tuple[dict, dict[str, dict], dict[str, dict], list, list]:
    """返回 (platform_full, sensors_full, mounts_full, signatures, platform_unit)"""
    p = src["platform"]
    sensors_full = {}
    sensors_unit = []
    weapons_full = {}
    weapons_unit = []

    # 传感器映射
    sensor_specs = {
        900301: ("346A型 AESA 主动相控阵雷达", 2132, 200000, 0, 0),
        900302: ("X波段 AESA 多功能相控阵雷达", 2121, 80000, 0, 0),
        900303: ("综合射频系统", 3031, 0, -75, 100),
        900304: ("Generic ESM", 3011, 0, -75, 0),
        900305: ("Generic DECM", 4011, 0, 0, 100),
        900306: ("Generic Navigation Radar", 2031, 25000, 0, 0),
    }
    for sid, (name, role, radar_power, esm_sens, ecm_power) in sensor_specs.items():
        sensors_full[str(sid)] = {
            "ID": sid,
            "Name": name,
            "Role": role,
            "RadarPeakPower": radar_power,
            "ESMSensitivity": esm_sens,
            "ECMPeakPower": ecm_power,
            "ECMGain": 10 if ecm_power else 0,
            "ECMBandwidth": 20 if ecm_power else 0,
            "ScanInterval": 1 if radar_power else 5,
        }
        sensors_unit.append({
            "id": sid,
            "name": name,
            "role_id": role,
            "radar_peak_power_w": radar_power or None,
            "esm_sensitivity_dbm": esm_sens or None,
            "ecm_peak_power_w": ecm_power or None,
        })

    # 武器映射
    weapon_specs = {
        900401: ("H/PJ-14 [Type 1130]", 4, 5, 0),
        900402: ("HQ-10 [FL-3000N]", 1, 18, 0),
        900403: ("多用途发射装置", 1, 24, 0),
        900404: ("电磁弹射器", 0, 0, 0),
    }
    for wid, (name, rof, cap, dmg) in weapon_specs.items():
        weapons_full[str(wid)] = {
            "ID": wid,
            "Name": name,
            "ROF": rof,
            "Capacity": cap,
            "DamagePoints": dmg,
        }
        weapons_unit.append({
            "id": wid,
            "name": name,
            "kind": "missile_launcher" if "电磁弹射" not in name else "catapult",
            "rof": rof,
            "capacity": cap,
        })

    signatures = []
    sig_data = src["signatures"]
    flat_sigs = []
    for key in ("passive_sonar", "active_sonar", "visual", "infrared", "radar_rcs"):
        for item in sig_data.get(key, []):
            flat_sigs.append({**item})
    for item in flat_sigs:
        # 用 sig_map 原理补充类型名称（此处只放原值）
        signatures.append({
            "ID": PLATFORM_RAW_ID,
            "Type": item.get("type") or 0,
            "Front": item.get("front", 0),
            "Side": item.get("side", 0),
            "Rear": item.get("rear", 0),
            "Top": item.get("top", 0),
        })

    platform_full = {
        "kind": "ship",
        "raw": {
            "ID": PLATFORM_RAW_ID,
            "Category": 2001,
            "Type": 2001,
            "Name": p.get("name", "Type 003 福建舰 [18 Fujian]"),
            "Comments": "用户补充数据",
            "OperatorCountry": 2018,
            "OperatorService": 2002,
            "YearCommissioned": p.get("year_commissioned", 2025),
            "YearDecommissioned": 0,
            "Length": p.get("length_m", 316.0),
            "Beam": p.get("beam_m", 76.0),
            "Draft": p.get("draft_m", 11.0),
            "DisplacementStandard": 85000.0,
            "DisplacementFull": p.get("displacement_full_t", 80000.0),
            "Crew": p.get("crew", 3000),
            "DamagePoints": p.get("damage_points", 6000),
            "MissileDefense": p.get("missile_defense", 24),
            "SpeedKts": p.get("speed_kt", 31),
            "MaxSeaState": 6,
            "Hypothetical": 0,
        },
        "sensor_ids": SENSOR_IDS,
        "mount_ids": MOUNT_IDS,
        "loadout_ids": [],
        "magazine_ids": [],
        "propulsion_ids": [],
        "comm_ids": [],
        "fuel_ids": [],
        "signatures": signatures,
    }

    platform_unit = {
        "id": "ship-type003",
        "kind": "ship",
        "name": p.get("name", "Type 003 福建舰 [18 Fujian]"),
        "operator_country": 2018,
        "sensor_ids": SENSOR_IDS,
        "weapon_ids": MOUNT_IDS,
        "yearcommissioned": p.get("year_commissioned", 2025),
        "length": p.get("length_m", 316.0),
        "beam": p.get("beam_m", 76.0),
        "draft": p.get("draft_m", 11.0),
        "displacementfull": p.get("displacement_full_t", 80000.0),
        "crew": p.get("crew", 3000),
        "damagepoints": p.get("damage_points", 6000),
    }
    return platform_full, sensors_full, weapons_full, signatures, platform_unit


def main() -> int:
    src = load_json(SRC)
    platform_full, sensors_full, weapons_full, _, platform_unit = build_type003_records(src)

    # china_full.json 合并
    full = load_json(FULL)
    if not any(p.get("raw", {}).get("ID") == PLATFORM_RAW_ID for p in full["platforms"]):
        full["platforms"].append(platform_full)
        full["sensors"].update(sensors_full)
        full["mounts"].update(weapons_full)
        full["platform_count"] = len(full["platforms"])
        full["sensor_count"] = len(full["sensors"])
        full["mount_count"] = len(full["mounts"])
        save_json(FULL, full)
        print(f"已更新 {FULL.name}: platforms={full['platform_count']}, sensors={full['sensor_count']}, mounts={full['mount_count']}")
    else:
        print(f"{FULL.name} 已包含 Type 003，跳过")

    # china_units.json 合并
    units = load_json(UNITS)
    if not any(p.get("id") == "ship-type003" for p in units["platforms"]):
        units["platforms"].append(platform_unit)
        # 添加传感器/武器
        for sid, sd in sensors_full.items():
            units["sensors"].append({
                "id": sid,
                "name": sd["Name"],
                "role_id": sd["Role"],
                "radar_peak_power_w": sd["RadarPeakPower"] or None,
                "esm_sensitivity_dbm": sd["ESMSensitivity"] or None,
                "ecm_peak_power_w": sd["ECMPeakPower"] or None,
            })
        for wid, wd in weapons_full.items():
            units["weapons"].append({
                "id": wid,
                "name": wd["Name"],
                "kind": "catapult" if "电磁弹射" in wd["Name"] else "missile_launcher",
                "rof": wd["ROF"],
                "capacity": wd["Capacity"],
            })
        units["platform_count"] = len(units["platforms"])
        units["sensor_count"] = len(units["sensors"])
        units["weapon_count"] = len(units["weapons"])
        save_json(UNITS, units)
        print(f"已更新 {UNITS.name}: platforms={units['platform_count']}, sensors={units['sensor_count']}, weapons={units['weapon_count']}")
    else:
        print(f"{UNITS.name} 已包含 Type 003，跳过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
