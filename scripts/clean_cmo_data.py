"""清洗 CMO 合并数据为可公开、轻量、自包含的参考版。

清洗策略：
- 移除原始数据库路径、内部 CMO 表结构、注释类字段
- 平台/传感器/武器保留核心参数
- 生成新的平台 ID（cmo-<id>）
- 挂载/弹药/推进不再逐条展开，只保留每平台数量汇总
- 输出 data/cmo_reference.json

用法：
    python scripts/clean_cmo_data.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "cmo_all_full.json"
OUT = ROOT / "data" / "cmo_reference.json"

import sqlite3

DB_DEFAULT = Path('/mnt/c/Users/29938/Downloads/《指挥：现代作战》英文免安装版/Command Modern Operations/DB/DB3K_480.db3')


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    if not SRC.exists():
        print("找不到源文件:", SRC)
        return 1

    data = load_json(SRC)
    # 国家 ID -> 名称
    country_names = {}
    if DB_DEFAULT.exists():
        conn = sqlite3.connect(DB_DEFAULT)
        country_names = {cid: name for cid, name in
                         conn.execute("SELECT ID, Description FROM EnumOperatorCountry")}
        conn.close()

    platforms = []
    sensor_ids = set()
    mount_ids = set()
    for p in data["platforms"]:
        raw = p.get("raw", {})
        cid = raw.get("OperatorCountry")
        name = raw.get("Name") or ""
        pid = f"cmo-{p['kind']}-{raw.get('ID')}"
        platforms.append({
            "id": pid,
            "name": name,
            "kind": p["kind"],
            "operator": country_names.get(cid, str(cid)),
            "year_commissioned": raw.get("YearCommissioned"),
            "year_decommissioned": raw.get("YearDecommissioned"),
            "length_m": raw.get("Length"),
            "beam_m": raw.get("Beam"),
            "draft_m": raw.get("Draft"),
            "displacement_full_t": raw.get("DisplacementFull"),
            "crew": raw.get("Crew"),
            "speed_kt": raw.get("SpeedKts"),
            "damage_points": raw.get("DamagePoints"),
            "sensor_count": len(p.get("sensor_ids", [])),
            "mount_count": len(p.get("mount_ids", [])),
            "loadout_count": len(p.get("loadout_ids", [])),
            "magazine_count": len(p.get("magazine_ids", [])),
            "propulsion_count": len(p.get("propulsion_ids", [])),
        })
        sensor_ids.update(p.get("sensor_ids", []))
        mount_ids.update(p.get("mount_ids", []))

    sensors = []
    for sid in sorted(sensor_ids):
        s = data["sensors"].get(str(sid))
        if not s:
            continue
        sensors.append({
            "id": sid,
            "name": s.get("Name"),
            "role_id": s.get("Role"),
            "frequency_lower_mhz": s.get("FrequencyLower"),
            "frequency_upper_mhz": s.get("FrequencyUpper"),
            "radar_peak_power_w": s.get("RadarPeakPower"),
            "esm_sensitivity_dbm": s.get("ESMSensitivity"),
            "ecm_peak_power_w": s.get("ECMPeakPower"),
            "scan_interval_s": s.get("ScanInterval"),
        })

    mounts = []
    for wid in sorted(mount_ids):
        m = data["mounts"].get(str(wid))
        if not m:
            continue
        mounts.append({
            "id": wid,
            "name": m.get("Name"),
            "rof": m.get("ROF"),
            "capacity": m.get("Capacity"),
            "damage_points": m.get("DamagePoints"),
        })

    result = {
        "source": "CMO 数据清洗参考版（非原始数据库，仅公开参考）",
        "note": "由 data/cmo_all_full.json 清洗生成，删除原始路径与内部字段；请自行确认合规性",
        "platform_count": len(platforms),
        "sensor_count": len(sensors),
        "mount_count": len(mounts),
        "platforms": platforms,
        "sensors": sensors,
        "mounts": mounts,
    }
    save_json(OUT, result)
    size = OUT.stat().st_size / 1024
    print(f"已生成 {OUT} ({size:.1f} KB)")
    print(f"  平台 {len(platforms)} | 传感器 {len(sensors)} | 武器/装置 {len(mounts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
