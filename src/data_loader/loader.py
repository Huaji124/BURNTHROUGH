"""JSON 装备/想定数据加载工具。"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_equipment(category: str, equipment_id: str) -> dict:
    """从 data/<category>/<id>.json 加载装备定义。"""
    path = DATA_DIR / category / f"{equipment_id}.json"
    return load_json(path)


def load_all_equipment(category: str) -> list[dict]:
    """加载某类全部 JSON 装备。"""
    folder = DATA_DIR / category
    if not folder.exists():
        return []
    result = []
    for p in sorted(folder.glob("*.json")):
        result.append(load_json(p))
    return result
