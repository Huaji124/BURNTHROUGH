"""从合并的完整 CMO 数据按国家/地区拆分完整明细（可推送版）。

输出目录：
    data/cmo_full_by_country/<country_slug>/
        country.json
        platforms.json
        sensors.json
        mounts.json
        loadouts.json
        loadout_weapons.json
        magazines.json
        magazine_weapons.json
        propulsions.json
        propulsion_performance.json
        comms.json
        fuel.json
        signatures.json (若存在)
    data/cmo_full_by_country/index.json

保留完整挂载/弹药/推进/通信/燃料/信号特征明细。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path('/mnt/c/Users/29938/Downloads/《指挥：现代作战》英文免安装版/Command Modern Operations/DB/DB3K_480.db3')
DEFAULT_SRC = ROOT / "data" / "cmo_all_full.json"
DEFAULT_OUT = ROOT / "data" / "cmo_full_by_country"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "unknown"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    if not args.src.exists():
        print(f"找不到源文件: {args.src}")
        return 1

    country_names = {}
    if args.db.exists():
        conn = sqlite3.connect(args.db)
        country_names = {cid: name for cid, name in
                         conn.execute("SELECT ID, Description FROM EnumOperatorCountry")}
        conn.close()

    data = load_json(args.src)
    platforms = data["platforms"]
    all_sensors = data.get("sensors", {})
    all_mounts = data.get("mounts", {})
    all_loadouts = data.get("loadouts", {})
    all_magazines = data.get("magazines", {})
    all_propulsions = data.get("propulsions", {})
    all_comms = data.get("comms", {})
    all_fuel = data.get("fuel", {})
    loadout_weapons = data.get("loadout_weapons", [])
    magazine_weapons = data.get("magazine_weapons", [])
    propulsion_performance = data.get("propulsion_performance", [])

    by_country: dict[int, list[dict]] = {}
    for p in platforms:
        cid = p["raw"].get("OperatorCountry")
        by_country.setdefault(cid, []).append(p)

    index = {"source": "清洗版完整 CMO 数据（按国家拆分）", "country_count": len(by_country),
             "platform_count": len(platforms), "countries": []}

    for cid, plats in sorted(by_country.items()):
        cname = country_names.get(cid, f"Country-{cid}")
        slug = slugify(cname)
        out_dir = args.out / slug
        out_dir.mkdir(parents=True, exist_ok=True)

        sensor_ids = set(); mount_ids = set(); loadout_ids = set()
        magazine_ids = set(); propulsion_ids = set(); comm_ids = set(); fuel_ids = set()
        for p in plats:
            sensor_ids.update(p.get("sensor_ids", []))
            mount_ids.update(p.get("mount_ids", []))
            loadout_ids.update(p.get("loadout_ids", []))
            magazine_ids.update(p.get("magazine_ids", []))
            propulsion_ids.update(p.get("propulsion_ids", []))
            comm_ids.update(p.get("comm_ids", []))
            fuel_ids.update(p.get("fuel_ids", []))

        save_json(out_dir / "country.json", {"id": cid, "name": cname, "slug": slug})
        save_json(out_dir / "platforms.json", plats)
        save_json(out_dir / "sensors.json", {str(k): v for k, v in all_sensors.items() if int(k) in sensor_ids})
        save_json(out_dir / "mounts.json", {str(k): v for k, v in all_mounts.items() if int(k) in mount_ids})
        save_json(out_dir / "loadouts.json", {str(k): v for k, v in all_loadouts.items() if int(k) in loadout_ids})
        save_json(out_dir / "loadout_weapons.json", [r for r in loadout_weapons if r.get("ID") in loadout_ids])
        save_json(out_dir / "magazines.json", {str(k): v for k, v in all_magazines.items() if int(k) in magazine_ids})
        save_json(out_dir / "magazine_weapons.json", [r for r in magazine_weapons if r.get("ID") in magazine_ids])
        save_json(out_dir / "propulsions.json", {str(k): v for k, v in all_propulsions.items() if int(k) in propulsion_ids})
        save_json(out_dir / "propulsion_performance.json", [r for r in propulsion_performance if r.get("ID") in propulsion_ids])
        save_json(out_dir / "comms.json", {str(k): v for k, v in all_comms.items() if int(k) in comm_ids})
        save_json(out_dir / "fuel.json", {str(k): v for k, v in all_fuel.items() if int(k) in fuel_ids})
        # 信号特征
        sig_list = [sig for p in plats for sig in p.get("signatures", [])]
        if sig_list:
            save_json(out_dir / "signatures.json", sig_list)

        index["countries"].append({
            "id": cid, "name": cname, "slug": slug,
            "platform_count": len(plats),
            "sensor_count": len(sensor_ids),
            "mount_count": len(mount_ids),
            "loadout_count": len(loadout_ids),
            "magazine_count": len(magazine_ids),
            "propulsion_count": len(propulsion_ids),
        })
        print(f"  {cname:<40} {len(plats):>5} 平台 | 挂载 {len(loadout_ids):>5}")

    save_json(args.out / "index.json", index)
    print(f"\n完成！输出目录: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
