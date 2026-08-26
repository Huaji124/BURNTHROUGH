"""从 CMO/MoZi 风格 SQLite 数据库中提取中国军力参考数据。

用法：
    python scripts/import_cmo_db.py [--db 路径/DB3K_HSP.db3] [--out 输出.json]

输出为一份"中国军力参考数据库" JSON：
- platforms：中国籍舰船/飞机/潜艇
- sensors：这些平台使用的传感器（含雷达/ESM/ECM 参数）
- weapons：这些平台使用的武器/发射装置

注意：
- 该脚本只做数据提取/整理，不复制原数据库。
- 生成的数据可用于公开资料整理，请自行确认数据合规性。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("/tmp/cmo_import_data/导入CMO中的中国数据/Resources/DataVariation/DB3K_HSP.db3")
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "china_units.json"

# 中国在 EnumOperatorCountry 中的 ID
CHINA_COUNTRY_ID = 2018

# 各平台的传感器/武器关联表
PLATFORM_TABLES = {
    "ship": ("DataShip", "DataShipSensors", "DataShipMounts"),
    "aircraft": ("DataAircraft", "DataAircraftSensors", "DataAircraftMounts"),
    "submarine": ("DataSubmarine", "DataSubmarineSensors", "DataSubmarineMounts"),
}


def fmt_freq(value: float | None) -> float | None:
    """CMO 频率单位通常为 MHz，转 Hz。"""
    if value is None or value == 0:
        return None
    return float(value) * 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.db.exists():
        print(f"找不到数据库文件: {args.db}")
        return 1

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    platforms: list[dict] = []
    sensor_ids: set[int] = set()
    weapon_ids: set[int] = set()

    for kind, (platform_table, sensor_table, mount_table) in PLATFORM_TABLES.items():
        rows = cur.execute(
            f"SELECT * FROM {platform_table} WHERE OperatorCountry=?",
            (CHINA_COUNTRY_ID,)
        ).fetchall()
        col_names = [d[1] for d in cur.execute(f"PRAGMA table_info({platform_table})").fetchall()]
        for row in rows:
            rec = dict(zip(col_names, row))
            pid = rec["ID"]
            platform = {
                "id": f"{kind}-{pid}",
                "kind": kind,
                "name": rec.get("Name"),
                "operator_country": CHINA_COUNTRY_ID,
                "sensor_ids": [],
                "weapon_ids": [],
            }
            for key in ("YearCommissioned", "YearDecommissioned", "Length", "Beam", "Draft",
                        "Height", "DisplacementEmpty", "DisplacementFull", "Crew", "SpeedKts",
                        "MaxDepth", "DamagePoints"):
                if key in rec and rec.get(key) not in (None, 0):
                    platform[key.lower()] = rec[key]

            # 传感器
            if sensor_table:
                sensors = cur.execute(
                    f"SELECT DISTINCT ComponentID FROM {sensor_table} WHERE ID=?",
                    (pid,)
                ).fetchall()
                for (sid,) in sensors:
                    sensor_ids.add(sid)
                    platform["sensor_ids"].append(sid)

            # 武器/发射装置
            if mount_table:
                mounts = cur.execute(
                    f"SELECT DISTINCT ComponentID FROM {mount_table} WHERE ID=?",
                    (pid,)
                ).fetchall()
                for (wid,) in mounts:
                    weapon_ids.add(wid)
                    platform["weapon_ids"].append(wid)

            platforms.append(platform)

    # 提取传感器详情
    def sensor_details(sid: int) -> dict | None:
        row = cur.execute("SELECT * FROM DataSensor WHERE ID=?", (sid,)).fetchone()
        if row is None:
            return None
        cols = [d[1] for d in cur.execute("PRAGMA table_info(DataSensor)").fetchall()]
        r = dict(zip(cols, row))
        role = r.get("Role")
        role_name = None
        role_row = cur.execute("SELECT Description FROM EnumSensorRole WHERE ID=?", (role,)).fetchone()
        if role_row:
            role_name = role_row[0]
        return {
            "id": sid,
            "name": r.get("Name"),
            "role_id": role,
            "role": role_name,
            "frequency_lower_hz": fmt_freq(r.get("FrequencyLower")),
            "frequency_upper_hz": fmt_freq(r.get("FrequencyUpper")),
            "range_max_km": (r.get("RangeMax") or 0) * 1.852 if r.get("RangeMax") else None,
            "radar_peak_power_w": r.get("RadarPeakPower") or None,
            "radar_prf_hz": r.get("RadarPRF") or None,
            "radar_beamwidth_deg": r.get("RadarHorizontalBeamwidth") or None,
            "scan_interval_s": r.get("ScanInterval") or None,
            "esm_sensitivity_dbm": r.get("ESMSensitivity") or None,
            "esm_df_accuracy_deg": r.get("DirectionFindingAccuracy") or None,
            "ecm_gain": r.get("ECMGain") or None,
            "ecm_peak_power_w": r.get("ECMPeakPower") or None,
            "ecm_bandwidth_hz": fmt_freq(r.get("ECMBandwidth")),
            "ecm_max_targets": r.get("ECMNumberOfTargets") or None,
            "hypothetical": bool(r.get("Hypothetical")),
        }

    sensors = []
    for sid in sorted(sensor_ids):
        sd = sensor_details(sid)
        if sd:
            sensors.append(sd)

    # 提取武器/发射装置详情
    def weapon_details(wid: int) -> dict | None:
        row = cur.execute("SELECT * FROM DataMount WHERE ID=?", (wid,)).fetchone()
        if row is None:
            return None
        cols = [d[1] for d in cur.execute("PRAGMA table_info(DataMount)").fetchall()]
        r = dict(zip(cols, row))
        name = r.get("Name") or ""
        kind = "missile_launcher"
        if any(k in name.lower() for k in ("gun", "ciws", "aa gun", "naval gun", "gatling")):
            kind = "gun"
        elif any(k in name.lower() for k in ("torpedo", "tube", "torpedo launcher")):
            kind = "torpedo"
        return {
            "id": wid,
            "name": name,
            "kind": kind,
            "rof": r.get("ROF") or None,
            "capacity": r.get("Capacity") or None,
            "damage_points": r.get("DamagePoints") or None,
            "magazine_rof": r.get("MagazineROF") or None,
            "magazine_capacity": r.get("MagazineCapacity") or None,
        }

    weapons = []
    for wid in sorted(weapon_ids):
        wd = weapon_details(wid)
        if wd:
            weapons.append(wd)

    conn.close()

    data = {
        "source": str(args.db),
        "operator": "China",
        "platform_count": len(platforms),
        "sensor_count": len(sensors),
        "weapon_count": len(weapons),
        "platforms": platforms,
        "sensors": sensors,
        "weapons": weapons,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {args.out}")
    print(f"  平台: {len(platforms)}（舰船/飞机/潜艇）")
    print(f"  传感器: {len(sensors)}")
    print(f"  武器/发射装置: {len(weapons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
