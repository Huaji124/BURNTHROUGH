"""生成 Phase 1 使用的初始演示装备数据。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


def write_json(category: str, equipment_id: str, data: dict) -> None:
    folder = DATA_DIR / category
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{equipment_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"written: {path.relative_to(PROJECT_ROOT)}")


def main() -> int:
    write_json("emitters", "type346_search_radar", {
        "id": "type346_search_radar",
        "name": "Type 346 搜索雷达（演示参数）",
        "role": "multifunction_radar",
        "band": "S",
        "freq_min_hz": 2_000_000_000,
        "freq_max_hz": 4_000_000_000,
        "peak_power_w": 1_000_000,
        "antenna_gain_db": 40,
        "pulse_width_min_us": 0.5,
        "pulse_width_max_us": 50,
        "prf_min_hz": 500,
        "prf_max_hz": 5000,
        "scan_type": "mechanical_scan",
        "scan_period_s": 4,
        "beam_width_deg": 1.5
    })

    write_json("sensors", "esm_type726", {
        "id": "esm_type726",
        "name": "雷达侦察告警设备（演示参数）",
        "kind": "esm",
        "freq_min_hz": 500_000_000,
        "freq_max_hz": 18_000_000_000,
        "sensitivity_dbm": -75,
        "gain_db": 0,
        "df_accuracy_deg": 3,
        "param_library": ["type346_search_radar"],
        "processing_time_s": 1.5
    })

    write_json("jammers", "ecm_pod_rkz", {
        "id": "ecm_pod_rkz",
        "name": "有源干扰吊舱（演示参数）",
        "mode": ["noise", "deception"],
        "band": ["S", "X", "Ku"],
        "freq_min_hz": 2_000_000_000,
        "freq_max_hz": 18_000_000_000,
        "power_w": 200,
        "gain_db": 15,
        "bandwidth_hz": 500_000_000,
        "techniques": ["spot_noise", "barrage_noise"],
        "reaction_time_s": 0.5,
        "max_targets": 4
    })

    write_json("weapons", "arm_yuj91", {
        "id": "arm_yuj91",
        "name": "反辐射导弹（演示参数）",
        "freq_min_hz": 1_000_000_000,
        "freq_max_hz": 20_000_000_000,
        "range_km": 150,
        "speed_mach": 2.5,
        "seeker": "passive_rf",
        "home_on": "emitter",
        "memory_if_shutdown": True
    })

    print("initial data generation done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
