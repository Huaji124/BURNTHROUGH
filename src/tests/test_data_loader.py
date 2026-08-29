"""数据加载器与武器类型推断的单元测试。

重点是防止两类回归：
1. 武器名称 -> 类型的推断（早先用朴素子串匹配，"tor " 命中 rapTOR、
   "sm-1" 命中 aSM-135a，把集束炸弹误判成舰空弹）
2. 加载器不再把所有平台放在 (0, 0)，且确实装载了挂载/弹药
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.geo import haversine_nm
from data_loader import weapon_kind
from data_loader.china_loader import load_china_environment
from data_loader.cmo_world_loader import _build_from_data
from data_loader.common import index_by_id, scatter_point

# ----------------------------------------------------------------------
# 武器类型推断
# ----------------------------------------------------------------------

WEAPON_KIND_CASES = [
    # (名称, 期望类型)
    ("AGM-88C HARM", "arm"),
    ("AGM-88E AARGM, Short-Range", "arm"),
    ("AGM-84D Harpoon IC", "asm"),
    ("AGM-84K SLAMER-ATA", "asm"),
    ("RIM-66G SM-1MR Standard MR", "sam"),
    ("RIM-156A SM-2ER", "sam"),
    ("AIM-9L Sidewinder", "aam"),
    ("A/A: AIM-120C AMRAAM", "aam"),
    ("Mk48 Mod 6 ADCAP Torpedo", "torpedo"),
    ("Mk82 LDGP, Short-Range", "bomb"),
    ("PL-12C", "aam"),
    ("YJ-83K", "asm"),
    ("HQ-9", "sam"),
    ("YJ-91", "arm"),
    ("SA-N-6 Grumble", "sam"),
    ("Kh-31P", "arm"),
    # 以下是曾经误判的用例：名称里含 tor-/sm-1 但不是舰空弹
    ("AGM-142A Raptor EO, AN/ASW-55 Datalink Pod", "weapon"),
    ("CBU-89/B GATOR CB", "bomb"),
    ("ASM-135A ALMV", "weapon"),
    ("GBU-12D/B LGB [Mk82], Penetrator CAS", "bomb"),
]


@pytest.mark.parametrize(("name", "expected"), WEAPON_KIND_CASES)
def test_infer_weapon_kind(name, expected):
    assert weapon_kind.infer_weapon_kind(name) == expected


def test_infer_weapon_kind_requires_word_start():
    """关键字必须出现在词首，不能是单词内部的子串。"""
    # "tor " 不应命中 rapTOR / gaTOR
    assert not weapon_kind._matches_at_word_start("raptor eo", "tor ")
    assert not weapon_kind._matches_at_word_start("gator", "tor ")
    # "sm-1" 不应命中 aSM-135a，但应命中 "sm-1mr"
    assert not weapon_kind._matches_at_word_start("asm-135a", "sm-1")
    assert weapon_kind._matches_at_word_start("rim-66 sm-1", "sm-1")
    # 串首或分隔符之后都算词首
    assert weapon_kind._matches_at_word_start("aim-9l", "aim-")
    assert weapon_kind._matches_at_word_start("a/a: aim-9l", "aim-")


# ----------------------------------------------------------------------
# 共用工具
# ----------------------------------------------------------------------

def test_index_by_id_groups_duplicates():
    records = [{"ID": 1, "v": "a"}, {"ID": 2, "v": "b"}, {"ID": 1, "v": "c"}]
    idx = index_by_id(records)
    assert len(idx[1]) == 2
    assert len(idx[2]) == 1
    assert idx[3] == []  # defaultdict，缺失键返回空列表


def test_scatter_point_unique_and_bounded():
    n = 200
    pts = [scatter_point(i, n, (22.0, 120.0), 250.0) for i in range(n)]
    assert len(set(pts)) == n, "布点必须两两不同"

    center = (22.0, 120.0)
    for lat, lon in pts:
        d_km = haversine_nm(center[0], center[1], lat, lon) * 1.852
        assert d_km <= 250.0 + 1e-6, "布点不应超出指定半径"


# ----------------------------------------------------------------------
# CMO 加载器
# ----------------------------------------------------------------------

def _synthetic_cmo_data() -> dict:
    """最小可用的 CMO 风格数据集（飞机带挂载，舰艇带发射装置）。"""
    return {
        "source": "synthetic",
        "platforms": [
            {
                "kind": "aircraft",
                "raw": {"ID": 1, "Name": "F-16C", "CruiseSpeedKts": 500,
                        "DamagePoints": 20},
                "sensor_ids": [],
                "mount_ids": [],
                "loadout_ids": [101, 102, 999],
                "magazine_ids": [],
                "propulsion_ids": [201],
                "fuel_ids": [301],
                "signatures": [{"ID": 1, "Type": 5001, "Front": 5.0}],
            },
            {
                "kind": "ship",
                "raw": {"ID": 2, "Name": "DDG-51", "SpeedKts": 30,
                        "DamagePoints": 100},
                "sensor_ids": [],
                "mount_ids": [401, 402],
                "loadout_ids": [],
                "magazine_ids": [],
                "propulsion_ids": [202],
                "fuel_ids": [],
                "signatures": [{"ID": 2, "Type": 5001, "Front": 25.5},
                               {"ID": 2, "Type": 1001, "Front": 110.0}],
            },
            {
                "kind": "ship",
                "raw": {"ID": 3, "Name": "DDG-52", "SpeedKts": 30},
                "sensor_ids": [],
                "mount_ids": [401, 402],
                "loadout_ids": [],
                "magazine_ids": [],
                "propulsion_ids": [202],
                "fuel_ids": [],
                "signatures": [],
            },
        ],
        "sensors": {},
        "mounts": {
            "401": {"ID": 401, "Name": "Mk41 VLS [61 Cells]", "Capacity": 61},
            "402": {"ID": 402, "Name": "Mk141", "Capacity": 8},
        },
        "loadouts": {
            "101": {"ID": 101, "Name": "AIM-120C AMRAAM", "Capacity": 4},
            "102": {"ID": 102, "Name": "AGM-88C HARM", "Capacity": 2},
            # 占位挂载，应被跳过
            "999": {"ID": 999, "Name": "(Reserve [Available])", "Capacity": 0},
        },
        "loadout_weapons": [],
        "magazines": {},
        "magazine_weapons": [],
        "propulsion_performance": [
            {"ID": 201, "Speed": 550, "Consumption": 3000},
            {"ID": 202, "Speed": 31, "Consumption": 800},
        ],
        "fuel": {"301": {"ID": 301, "Capacity": 3000}},
    }


def test_build_from_data_scatters_positions():
    env = _build_from_data(_synthetic_cmo_data(), side="blue")
    coords = [(p.latitude, p.longitude) for p in env.platforms.values()]
    assert len(set(coords)) == len(coords), "平台不能全部堆在同一点"
    assert all(not (lat == 0.0 and lon == 0.0) for lat, lon in coords)


def test_build_from_data_loads_aircraft_missiles():
    env = _build_from_data(_synthetic_cmo_data(), side="blue")
    f16 = next(p for p in env.platforms.values() if p.name == "F-16C")
    kinds = {lw["kind"] for lw in f16.loadout_weapons}
    assert kinds == {"aam", "arm"}, f"实际: {kinds}"
    assert f16.ammo.get("AIM-120C AMRAAM") == 4
    assert f16.ammo.get("AGM-88C HARM") == 2
    # 占位挂载不能进入可用武器
    assert all(not lw["name"].startswith("(") for lw in f16.loadout_weapons)


def test_build_from_data_infers_ship_weapons():
    """舰艇没有挂载明细时，按发射装置推导防空/反舰能力。"""
    env = _build_from_data(_synthetic_cmo_data(), side="blue")
    ddg = next(p for p in env.platforms.values() if p.name == "DDG-51")
    kinds = {lw["kind"] for lw in ddg.loadout_weapons}
    assert "sam" in kinds, "Mk41 VLS 应推导出舰空导弹"
    assert "asm" in kinds, "Mk141 应推导出反舰导弹"


def test_build_from_data_signatures_and_propulsion():
    env = _build_from_data(_synthetic_cmo_data(), side="blue")
    ddg = next(p for p in env.platforms.values() if p.name == "DDG-51")
    assert ddg.sig_radar_db_sm == 25.5
    assert ddg.sig_sonar_db == 110.0
    assert ddg.max_speed_kt == 31

    f16 = next(p for p in env.platforms.values() if p.name == "F-16C")
    assert f16.max_speed_kt == 550
    assert f16.fuel_kg == 3000.0


def test_build_from_data_respects_limit():
    env = _build_from_data(_synthetic_cmo_data(), side="blue", limit_platforms=2)
    assert len(env.platforms) == 2


# ----------------------------------------------------------------------
# 中国加载器（需要 data/china_full.json）
# ----------------------------------------------------------------------

def test_china_loader_scatters_positions():
    path = Path("data/china_full.json")
    if not path.exists():
        pytest.skip("缺少 data/china_full.json")
    env = load_china_environment(path, side="red", limit_platforms=50)
    coords = [(p.latitude, p.longitude) for p in env.platforms.values()]
    assert len(set(coords)) == len(coords)
