"""合并中国数据与 CMO 世界数据（除中国）为完整 CMO 数据。

输出 data/cmo_all_full.json（商用数据，仅本地，已忽略）。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHINA = ROOT / "data" / "china_full.json"
WORLD = ROOT / "data" / "cmo_world_full.json"
OUT = ROOT / "data" / "cmo_all_full.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_dicts(base: dict, extra: dict) -> dict:
    """合并两个以字符串 ID 为 key 的字典，base 优先保留字段。"""
    merged = dict(base)
    for k, v in extra.items():
        if k not in merged:
            merged[k] = v
        else:
            # 如果两个来源都有，保留字段更完整的版本
            if len(v) > len(merged[k]):
                merged[k] = v
    return merged


def dedupe_records(records: list[dict]) -> list[dict]:
    """按所有字段的 tuple 去重。"""
    seen = set()
    out = []
    for r in records:
        key = tuple(sorted((k, str(v)) for k, v in r.items()))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def main() -> int:
    china = load_json(CHINA)
    world = load_json(WORLD)

    merged = {
        "source": "CMO 完整数据（中国 + 世界除中国）合并",
        "note": "仅本地研究与个人推演参考，请勿公开分发",
        "platforms": world["platforms"] + china["platforms"],
        "sensors": merge_dicts(world["sensors"], china["sensors"]),
        "mounts": merge_dicts(world["mounts"], china["mounts"]),
        "loadouts": merge_dicts(world["loadouts"], china["loadouts"]),
        "magazines": merge_dicts(world["magazines"], china["magazines"]),
        "propulsions": merge_dicts(world["propulsions"], china["propulsions"]),
        "comms": merge_dicts(world["comms"], china["comms"]),
        "fuel": merge_dicts(world["fuel"], china["fuel"]),
        "loadout_weapons": dedupe_records(
            world.get("loadout_weapons", []) + china.get("loadout_weapons", [])),
        "magazine_weapons": dedupe_records(
            world.get("magazine_weapons", []) + china.get("magazine_weapons", [])),
        "propulsion_performance": dedupe_records(
            world.get("propulsion_performance", []) + china.get("propulsion_performance", [])),
        "platform_count": len(world["platforms"]) + len(china["platforms"]),
        "sensor_count": len(merged_sensors := merge_dicts(world["sensors"], china["sensors"])),
        "mount_count": len(merged_mounts := merge_dicts(world["mounts"], china["mounts"])),
        "loadout_count": len(merged_loadouts := merge_dicts(world["loadouts"], china["loadouts"])),
        "magazine_count": len(merged_magazines := merge_dicts(world["magazines"], china["magazines"])),
        "propulsion_count": len(merged_propulsions := merge_dicts(world["propulsions"], china["propulsions"])),
        "comm_count": len(merged_comms := merge_dicts(world["comms"], china["comms"])),
        "fuel_count": len(merged_fuel := merge_dicts(world["fuel"], china["fuel"])),
    }
    # 把上面计算用的临时变量引用替换为正式字典（避免重复计算）
    merged["sensors"] = merged_sensors
    merged["mounts"] = merged_mounts
    merged["loadouts"] = merged_loadouts
    merged["magazines"] = merged_magazines
    merged["propulsions"] = merged_propulsions
    merged["comms"] = merged_comms
    merged["fuel"] = merged_fuel

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"已生成 {OUT} ({size_mb:.1f} MB)")
    print(f"  平台 {merged['platform_count']} | 传感器 {merged['sensor_count']} | 武器/装置 {merged['mount_count']} | 挂载 {merged['loadout_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
