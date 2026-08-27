"""从 CMO/MoZi 风格 SQLite 数据库完整导出中国军力参考数据。

与 import_cmo_db.py 不同，本脚本导出：
- 平台原始字段
- 平台传感器、武器/发射装置、挂载方案、弹药库
- 推进系统及其性能
- 信号特征（雷达/红外/视觉/声呐）
- 通信系统

输出 data/china_full.json，作为完整原始参考数据。

用法：
    python scripts/export_china_full.py [--db 路径] [--out 路径]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("/tmp/cmo_import_data/导入CMO中的中国数据/Resources/DataVariation/DB3K_HSP.db3")
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "china_full.json"
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
        "aircraft_facilities": "DataShipAircraftFacilities",
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
        "aircraft_facilities": "DataAircraftFacility",
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
        "aircraft_facilities": None,
    },
}


def table_as_dicts(cur: sqlite3.Cursor, table: str) -> list[dict]:
    """读取整表为 dict 列表。"""
    cols = [d[1] for d in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    return [dict(zip(cols, row)) for row in cur.execute(f"SELECT * FROM {table}").fetchall()]


def table_counts(cur: sqlite3.Cursor, table: str) -> int:
    try:
        return cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


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

    # 需要导出的唯一引用集合
    sensor_ids: set[int] = set()
    mount_ids: set[int] = set()
    weapon_ids: set[int] = set()
    loadout_ids: set[int] = set()
    magazine_ids: set[int] = set()
    propulsion_ids: set[int] = set()
    comm_ids: set[int] = set()
    fuel_ids: set[int] = set()

    platforms: list[dict] = []

    for kind, cfg in PLATFORM_TABLES.items():
        table = cfg["table"]
        rows = cur.execute(
            f"SELECT * FROM {table} WHERE OperatorCountry=?", (CHINA_COUNTRY_ID,)
        ).fetchall()
        cols = [d[1] for d in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        for row in rows:
            rec = dict(zip(cols, row))
            pid = rec["ID"]
            platform: dict = {
                "kind": kind,
                "raw": rec,
                "sensor_ids": [],
                "mount_ids": [],
                "loadout_ids": [],
                "magazine_ids": [],
                "propulsion_ids": [],
                "comm_ids": [],
                "fuel_ids": [],
            }
            # 传感器
            if cfg.get("sensors"):
                for (sid,) in cur.execute(
                        f"SELECT DISTINCT ComponentID FROM {cfg['sensors']} WHERE ID=?", (pid,)):
                    sensor_ids.add(sid)
                    platform["sensor_ids"].append(sid)
            # 武器/发射装置
            if cfg.get("mounts"):
                for (wid,) in cur.execute(
                        f"SELECT DISTINCT ComponentID FROM {cfg['mounts']} WHERE ID=?", (pid,)):
                    mount_ids.add(wid)
                    platform["mount_ids"].append(wid)
            # 飞机挂载
            if cfg.get("loadouts"):
                for (lid,) in cur.execute(
                        f"SELECT DISTINCT ComponentID FROM {cfg['loadouts']} WHERE ID=?", (pid,)):
                    loadout_ids.add(lid)
                    platform["loadout_ids"].append(lid)
            # 弹药库
            if cfg.get("magazines"):
                for (mid,) in cur.execute(
                        f"SELECT DISTINCT ComponentID FROM {cfg['magazines']} WHERE ID=?", (pid,)):
                    magazine_ids.add(mid)
                    platform["magazine_ids"].append(mid)
            # 推进
            if cfg.get("propulsion"):
                for (prid,) in cur.execute(
                        f"SELECT DISTINCT ComponentID FROM {cfg['propulsion']} WHERE ID=?", (pid,)):
                    propulsion_ids.add(prid)
                    platform["propulsion_ids"].append(prid)
            # 通信
            if cfg.get("comms"):
                for (cid,) in cur.execute(
                        f"SELECT DISTINCT ComponentID FROM {cfg['comms']} WHERE ID=?", (pid,)):
                    comm_ids.add(cid)
                    platform["comm_ids"].append(cid)
            # 燃料
            if cfg.get("fuel"):
                for (fid,) in cur.execute(
                        f"SELECT DISTINCT ComponentID FROM {cfg['fuel']} WHERE ID=?", (pid,)):
                    fuel_ids.add(fid)
                    platform["fuel_ids"].append(fid)
            # 信号特征
            sig_table = cfg.get("signatures")
            if sig_table:
                sigs = cur.execute(f"SELECT * FROM {sig_table} WHERE ID=?", (pid,)).fetchall()
                sig_cols = [d[1] for d in cur.execute(f"PRAGMA table_info({sig_table})").fetchall()]
                platform["signatures"] = [dict(zip(sig_cols, r)) for r in sigs]
            platforms.append(platform)

    # --- 导出引用组件 ---
    # 传感器
    sensors: dict[int, dict] = {}
    if sensor_ids:
        for sid in sorted(sensor_ids):
            row = cur.execute("SELECT * FROM DataSensor WHERE ID=?", (sid,)).fetchone()
            if row:
                cols = [d[1] for d in cur.execute("PRAGMA table_info(DataSensor)").fetchall()]
                sensors[sid] = dict(zip(cols, row))
    # 武器/发射装置
    mounts: dict[int, dict] = {}
    if mount_ids:
        for wid in sorted(mount_ids):
            row = cur.execute("SELECT * FROM DataMount WHERE ID=?", (wid,)).fetchone()
            if row:
                cols = [d[1] for d in cur.execute("PRAGMA table_info(DataMount)").fetchall()]
                mounts[wid] = dict(zip(cols, row))
    # 挂载
    loadouts: dict[int, dict] = {}
    loadout_weapons: list[dict] = []
    if loadout_ids:
        for lid in sorted(loadout_ids):
            row = cur.execute("SELECT * FROM DataLoadout WHERE ID=?", (lid,)).fetchone()
            if row:
                cols = [d[1] for d in cur.execute("PRAGMA table_info(DataLoadout)").fetchall()]
                loadouts[lid] = dict(zip(cols, row))
                for wrow in cur.execute("SELECT * FROM DataLoadoutWeapons WHERE ID=?", (lid,)).fetchall():
                    wcols = [d[1] for d in cur.execute("PRAGMA table_info(DataLoadoutWeapons)").fetchall()]
                    lw = dict(zip(wcols, wrow))
                    # 挂载武器引用的是 DataWeaponRecord，需继续指向 DataWeapon
                    lw["WeaponID"] = None
                    rec = cur.execute("SELECT * FROM DataWeaponRecord WHERE ID=?", (lw.get("ComponentID"),)).fetchone()
                    if rec:
                        rec_cols = [d[1] for d in cur.execute("PRAGMA table_info(DataWeaponRecord)").fetchall()]
                        rec_dict = dict(zip(rec_cols, rec))
                        lw["WeaponID"] = rec_dict.get("ComponentID")
                        lw["DefaultLoad"] = rec_dict.get("DefaultLoad")
                        if rec_dict.get("ComponentID") is not None:
                            weapon_ids.add(rec_dict["ComponentID"])
                    loadout_weapons.append(lw)
    # 弹药库
    magazines: dict[int, dict] = {}
    magazine_weapons: list[dict] = []
    if magazine_ids:
        for mid in sorted(magazine_ids):
            row = cur.execute("SELECT * FROM DataMagazine WHERE ID=?", (mid,)).fetchone()
            if row:
                cols = [d[1] for d in cur.execute("PRAGMA table_info(DataMagazine)").fetchall()]
                magazines[mid] = dict(zip(cols, row))
                for wrow in cur.execute("SELECT * FROM DataMagazineWeapons WHERE ID=?", (mid,)).fetchall():
                    wcols = [d[1] for d in cur.execute("PRAGMA table_info(DataMagazineWeapons)").fetchall()]
                    mw = dict(zip(wcols, wrow))
                    mw["WeaponID"] = None
                    rec = cur.execute("SELECT * FROM DataWeaponRecord WHERE ID=?", (mw.get("ComponentID"),)).fetchone()
                    if rec:
                        rec_cols = [d[1] for d in cur.execute("PRAGMA table_info(DataWeaponRecord)").fetchall()]
                        rec_dict = dict(zip(rec_cols, rec))
                        mw["WeaponID"] = rec_dict.get("ComponentID")
                        if rec_dict.get("ComponentID") is not None:
                            weapon_ids.add(rec_dict["ComponentID"])
                    magazine_weapons.append(mw)
    # 推进
    propulsion: dict[int, dict] = {}
    propulsion_performance: list[dict] = []
    if propulsion_ids:
        for prid in sorted(propulsion_ids):
            row = cur.execute("SELECT * FROM DataPropulsion WHERE ID=?", (prid,)).fetchone()
            if row:
                cols = [d[1] for d in cur.execute("PRAGMA table_info(DataPropulsion)").fetchall()]
                propulsion[prid] = dict(zip(cols, row))
                for prow in cur.execute("SELECT * FROM DataPropulsionPerformance WHERE ID=?", (prid,)).fetchall():
                    pcols = [d[1] for d in cur.execute("PRAGMA table_info(DataPropulsionPerformance)").fetchall()]
                    propulsion_performance.append(dict(zip(pcols, prow)))
    # 通信
    comms: dict[int, dict] = {}
    if comm_ids:
        for cid in sorted(comm_ids):
            row = cur.execute("SELECT * FROM DataComm WHERE ID=?", (cid,)).fetchone()
            if row:
                cols = [d[1] for d in cur.execute("PRAGMA table_info(DataComm)").fetchall()]
                comms[cid] = dict(zip(cols, row))
    # 燃料/油箱
    fuel: dict[int, dict] = {}
    if fuel_ids:
        for fid in sorted(fuel_ids):
            row = cur.execute("SELECT * FROM DataFuel WHERE ID=?", (fid,)).fetchone()
            if row:
                cols = [d[1] for d in cur.execute("PRAGMA table_info(DataFuel)").fetchall()]
                fuel[fid] = dict(zip(cols, row))

    # 补齐挂载/弹库引用的武器/发射装置（mount_ids 可能在导出过程中扩充）
    for wid in sorted(mount_ids):
        if wid in mounts:
            continue
        row = cur.execute("SELECT * FROM DataMount WHERE ID=?", (wid,)).fetchone()
        if row:
            cols = [d[1] for d in cur.execute("PRAGMA table_info(DataMount)").fetchall()]
            mounts[wid] = dict(zip(cols, row))

    # 导出挂载/弹库引用的具体武器（DataWeapon）
    weapons: dict[int, dict] = {}
    if weapon_ids:
        for wid in sorted(weapon_ids):
            row = cur.execute("SELECT * FROM DataWeapon WHERE ID=?", (wid,)).fetchone()
            if row:
                cols = [d[1] for d in cur.execute("PRAGMA table_info(DataWeapon)").fetchall()]
                weapons[wid] = dict(zip(cols, row))

    conn.close()

    data = {
        "source": str(args.db),
        "operator": "China",
        "platform_count": len(platforms),
        "sensor_count": len(sensors),
        "mount_count": len(mounts),
        "weapon_count": len(weapons),
        "loadout_count": len(loadouts),
        "magazine_count": len(magazines),
        "propulsion_count": len(propulsion),
        "comm_count": len(comms),
        "fuel_count": len(fuel),
        "platforms": platforms,
        # 以字符串 ID 为 key 便于 JSON 序列化
        "sensors": {str(k): v for k, v in sensors.items()},
        "mounts": {str(k): v for k, v in mounts.items()},
        "weapons": {str(k): v for k, v in weapons.items()},
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
    print(f"已生成完整导出: {args.out}")
    print(f"  平台 {len(platforms)}，传感器 {len(sensors)}，武器/装置 {len(mounts)}")
    print(f"  挂载方案 {len(loadouts)}，弹药库 {len(magazines)}，推进 {len(propulsion)}")
    print(f"  武器条目 {len(weapons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
