"""从 CMO/MoZi 风格 SQLite 数据库导出"除中国外"的全部装备参考数据。

该脚本适合本地研究使用；生成的 JSON 可能较大，请勿直接提交到公开仓库。

用法：
    python scripts/export_cmo_world.py --db "DB3K_480.db3" --out data/cmo_world_full.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = Path('/mnt/c/Users/29938/Downloads/《指挥：现代作战》英文免安装版/Command Modern Operations/DB/DB3K_480.db3')
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "cmo_world_full.json"
CHINA_COUNTRY_ID = 2018

PLATFORM_TABLES = {
    "ship": {
        "table": "DataShip",
        "sensors": "DataShipSensors",
        "mounts": "DataShipMounts",
        "comms": "DataShipComms",
        "fuel": "DataShipFuel",
        "magazines": "DataShipMagazines",
        "propulsion": "DataShipPropulsion",
        "signatures": "DataShipSignatures",
    },
    "aircraft": {
        "table": "DataAircraft",
        "sensors": "DataAircraftSensors",
        "mounts": "DataAircraftMounts",
        "comms": "DataAircraftComms",
        "fuel": "DataAircraftFuel",
        "magazines": None,
        "propulsion": "DataAircraftPropulsion",
        "signatures": "DataAircraftSignatures",
        "loadouts": "DataAircraftLoadouts",
    },
    "submarine": {
        "table": "DataSubmarine",
        "sensors": "DataSubmarineSensors",
        "mounts": "DataSubmarineMounts",
        "comms": None,
        "fuel": None,
        "magazines": None,
        "propulsion": None,
        "signatures": "DataSubmarineSignatures",
        "loadouts": None,
    },
}


def table_cols(cur: sqlite3.Cursor, table: str) -> list[str]:
    return [d[1] for d in cur.execute(f"PRAGMA table_info({table})").fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.db.exists():
        print(f"找不到数据库: {args.db}")
        return 1
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    sensor_ids = set(); mount_ids = set(); loadout_ids = set()
    magazine_ids = set(); propulsion_ids = set(); comm_ids = set(); fuel_ids = set()
    platforms = []

    for kind, cfg in PLATFORM_TABLES.items():
        table = cfg["table"]
        rows = cur.execute(f"SELECT * FROM {table}").fetchall()
        cols = table_cols(cur, table)
        for row in rows:
            rec = dict(zip(cols, row))
            if rec.get("OperatorCountry") == CHINA_COUNTRY_ID:
                continue
            pid = rec["ID"]
            platform = {"kind": kind, "raw": rec, "sensor_ids": [], "mount_ids": [],
                        "loadout_ids": [], "magazine_ids": [], "propulsion_ids": [],
                        "comm_ids": [], "fuel_ids": []}
            if cfg.get("sensors"):
                for (sid,) in cur.execute(f"SELECT DISTINCT ComponentID FROM {cfg['sensors']} WHERE ID=?", (pid,)):
                    sensor_ids.add(sid); platform["sensor_ids"].append(sid)
            if cfg.get("mounts"):
                for (wid,) in cur.execute(f"SELECT DISTINCT ComponentID FROM {cfg['mounts']} WHERE ID=?", (pid,)):
                    mount_ids.add(wid); platform["mount_ids"].append(wid)
            if cfg.get("loadouts"):
                for (lid,) in cur.execute(f"SELECT DISTINCT ComponentID FROM {cfg['loadouts']} WHERE ID=?", (pid,)):
                    loadout_ids.add(lid); platform["loadout_ids"].append(lid)
            if cfg.get("magazines"):
                for (mid,) in cur.execute(f"SELECT DISTINCT ComponentID FROM {cfg['magazines']} WHERE ID=?", (pid,)):
                    magazine_ids.add(mid); platform["magazine_ids"].append(mid)
            if cfg.get("propulsion"):
                for (prid,) in cur.execute(f"SELECT DISTINCT ComponentID FROM {cfg['propulsion']} WHERE ID=?", (pid,)):
                    propulsion_ids.add(prid); platform["propulsion_ids"].append(prid)
            if cfg.get("comms"):
                for (cid,) in cur.execute(f"SELECT DISTINCT ComponentID FROM {cfg['comms']} WHERE ID=?", (pid,)):
                    comm_ids.add(cid); platform["comm_ids"].append(cid)
            if cfg.get("fuel"):
                for (fid,) in cur.execute(f"SELECT DISTINCT ComponentID FROM {cfg['fuel']} WHERE ID=?", (pid,)):
                    fuel_ids.add(fid); platform["fuel_ids"].append(fid)
            sig_table = cfg.get("signatures")
            if sig_table:
                sig_cols = table_cols(cur, sig_table)
                platform["signatures"] = [dict(zip(sig_cols, r)) for r in cur.execute(
                    f"SELECT * FROM {sig_table} WHERE ID=?", (pid,)).fetchall()]
            platforms.append(platform)

    def fetch_dict(table: str, ids: set[int]) -> dict[int, dict]:
        result = {}
        for i in sorted(ids):
            row = cur.execute(f"SELECT * FROM {table} WHERE ID=?", (i,)).fetchone()
            if row:
                result[i] = dict(zip(table_cols(cur, table), row))
        return result

    sensors = fetch_dict("DataSensor", sensor_ids)
    mounts = fetch_dict("DataMount", mount_ids)
    loadouts = fetch_dict("DataLoadout", loadout_ids)
    magazines = fetch_dict("DataMagazine", magazine_ids)
    propulsion = fetch_dict("DataPropulsion", propulsion_ids)
    comms = fetch_dict("DataComm", comm_ids)
    fuel = fetch_dict("DataFuel", fuel_ids)

    loadout_weapons = []
    if loadout_ids:
        cols = table_cols(cur, "DataLoadoutWeapons")
        for lid in sorted(loadout_ids):
            for r in cur.execute("SELECT * FROM DataLoadoutWeapons WHERE ID=?", (lid,)).fetchall():
                loadout_weapons.append(dict(zip(cols, r)))
    magazine_weapons = []
    if magazine_ids:
        cols = table_cols(cur, "DataMagazineWeapons")
        for mid in sorted(magazine_ids):
            for r in cur.execute("SELECT * FROM DataMagazineWeapons WHERE ID=?", (mid,)).fetchall():
                magazine_weapons.append(dict(zip(cols, r)))
    propulsion_performance = []
    if propulsion_ids:
        cols = table_cols(cur, "DataPropulsionPerformance")
        for prid in sorted(propulsion_ids):
            for r in cur.execute("SELECT * FROM DataPropulsionPerformance WHERE ID=?", (prid,)).fetchall():
                propulsion_performance.append(dict(zip(cols, r)))

    conn.close()

    data = {
        "source": str(args.db),
        "note": "CMO 世界数据（排除中国）本地参考导出，未经许可请勿公开分发",
        "platform_count": len(platforms),
        "sensor_count": len(sensors),
        "mount_count": len(mounts),
        "loadout_count": len(loadouts),
        "magazine_count": len(magazines),
        "propulsion_count": len(propulsion),
        "comm_count": len(comms),
        "fuel_count": len(fuel),
        "platforms": platforms,
        "sensors": {str(k): v for k, v in sensors.items()},
        "mounts": {str(k): v for k, v in mounts.items()},
        "loadouts": {str(k): v for k, v in loadouts.items()},
        "loadout_weapons": loadout_weapons,
        "magazines": {str(k): v for k, v in magazines.items()},
        "magazine_weapons": magazine_weapons,
        "propulsions": {str(k): v for k, v in propulsion.items()},
        "propulsion_performance": propulsion_performance,
        "comms": {str(k): v for k, v in comms.items()},
        "fuel": {str(k): v for k, v in fuel.items()},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    size_mb = args.out.stat().st_size / 1024 / 1024
    print(f"已导出 {args.out} ({size_mb:.1f} MB)")
    print(f"  非中国平台 {len(platforms)} | 传感器 {len(sensors)} | 武器/装置 {len(mounts)} | 挂载 {len(loadouts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
