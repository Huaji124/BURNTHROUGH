"""从 china_full.json 生成单个单位文件到 data/units/。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "china_full.json"
OUT = ROOT / "data" / "units"


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    for p in data["platforms"]:
        pid = f"{p['kind']}-{p['raw']['ID']}"
        unit = {
            "platform": p["raw"],
            "kind": p["kind"],
            "sensor_ids": p.get("sensor_ids", []),
            "mount_ids": p.get("mount_ids", []),
            "loadout_ids": p.get("loadout_ids", []),
            "magazine_ids": p.get("magazine_ids", []),
            "propulsion_ids": p.get("propulsion_ids", []),
            "signatures": p.get("signatures", []),
        }
        # 只保存该平台引用的组件，减小文件量
        unit["sensors"] = {str(k): data["sensors"][str(k)]
                           for k in unit["sensor_ids"] if str(k) in data["sensors"]}
        unit["mounts"] = {str(k): data["mounts"][str(k)]
                          for k in unit["mount_ids"] if str(k) in data["mounts"]}
        unit["loadouts"] = {str(k): data["loadouts"][str(k)]
                            for k in unit["loadout_ids"] if str(k) in data["loadouts"]}
        unit["loadout_weapons"] = [lw for lw in data.get("loadout_weapons", [])
                                   if lw.get("ID") in unit["loadout_ids"]]
        unit["magazines"] = {str(k): data["magazines"][str(k)]
                             for k in unit["magazine_ids"] if str(k) in data["magazines"]}
        unit["magazine_weapons"] = [mw for mw in data.get("magazine_weapons", [])
                                    if mw.get("ID") in unit["magazine_ids"]]
        weapon_ids = set()
        for lw in unit["loadout_weapons"]:
            if lw.get("WeaponID") is not None:
                weapon_ids.add(lw["WeaponID"])
        for mw in unit["magazine_weapons"]:
            if mw.get("WeaponID") is not None:
                weapon_ids.add(mw["WeaponID"])
        unit["weapons"] = {str(k): data["weapons"][str(k)]
                           for k in weapon_ids if str(k) in data["weapons"]}
        unit["propulsions"] = {str(k): data["propulsions"][str(k)]
                               for k in unit["propulsion_ids"] if str(k) in data["propulsions"]}
        unit["propulsion_performance"] = [pp for pp in data.get("propulsion_performance", [])
                                          if pp.get("ID") in unit["propulsion_ids"]]
        out = OUT / f"{pid}.json"
        out.write_text(json.dumps(unit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"生成 {len(data['platforms'])} 个单位文件到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
