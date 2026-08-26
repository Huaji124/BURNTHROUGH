"""想定保存/加载（JSON）。

使用 dataclasses.asdict 序列化平台、传感器、干扰机、武器配置。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .emitter import Emitter
from .environment import Environment, Platform
from .jammer import Jammer
from .receiver import Receiver


def save_scenario(env: Environment, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "name": path.stem,
        "time_s": env.time_s,
        "waypoints": env.waypoints,
        "platforms": {},
    }
    for pid, platform in env.platforms.items():
        data["platforms"][pid] = dataclasses.asdict(platform)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_scenario(path: str | Path) -> Environment:
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return env_from_dict(data)


def env_to_dict(env: Environment) -> dict:
    data = {
        "version": 1,
        "name": "scenario",
        "time_s": env.time_s,
        "waypoints": dict(env.waypoints),
        "platforms": {},
    }
    for pid, platform in env.platforms.items():
        data["platforms"][pid] = dataclasses.asdict(platform)
    return data


def env_from_dict(data: dict) -> Environment:
    env = Environment()
    env.time_s = float(data.get("time_s", 0.0))
    env.waypoints = {k: [tuple(wp) for wp in v] for k, v in data.get("waypoints", {}).items()}
    for pd in data.get("platforms", {}).values():
        emitter_dicts = pd.get("emitters", [])
        receiver_dicts = pd.get("receivers", [])
        jammer_dicts = pd.get("jammers", [])
        platform_fields = {k: v for k, v in pd.items()
                           if k not in ("emitters", "receivers", "jammers")}
        platform = Platform(**platform_fields)
        platform.emitters = [Emitter(**e) for e in emitter_dicts]
        platform.receivers = [Receiver(**r) for r in receiver_dicts]
        platform.jammers = [Jammer(**j) for j in jammer_dicts]
        env.add_platform(platform)
    return env
