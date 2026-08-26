"""Phase 1 无界面演示：打印 J/S 与烧穿距离表。

用法：
    python scripts/run_headless.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core import propagation


def fmt(km: float) -> str:
    return f"{km:8.1f} km"


def main() -> int:
    print("=" * 72)
    print("烧穿 BURNTHROUGH —— 电子战静态射频沙盘：J/S 与烧穿距离演示")
    print("=" * 72)

    # 雷达参数（Type 346 搜索雷达演示值）
    pt = 1_000_000.0          # W
    gt_db = 40.0              # dB
    gt = 10 ** (gt_db / 10)
    sigma = 1000.0            # m²
    lam = propagation.wavelength_m(3_000_000_000)  # 3 GHz -> 0.1 m
    br = 1_000_000.0          # 1 MHz
    nf = 5.0
    loss = 6.0
    snr_min_db = 13.0
    snr_min = 10 ** (snr_min_db / 10)

    # 干扰机参数（演示值）
    pj = 100.0                # W
    gj_db = 20.0              # dB
    gj = 10 ** (gj_db / 10)
    bj = 20_000_000.0         # 20 MHz 瞄准式噪声

    r_max = propagation.radar_max_range_m(pt, gt, gt, sigma, lam, br, nf, loss, snr_min)
    print(f"\n无干扰最大探测距离      : {fmt(r_max/1000)}")

    r_bt_ssj = propagation.burn_through_self_screen_m(pt, gt, sigma, pj, gj, br, bj)
    print(f"自卫干扰烧穿距离        : {fmt(r_bt_ssj/1000)}")

    rj_soj = 200_000.0        # 远距干扰机距雷达 200 km
    r_bt_soj = propagation.burn_through_standoff_m(pt, gt, sigma, pj, gj, br, bj, rj_soj)
    print(f"远距干扰烧穿距离(SOJ)   : {fmt(r_bt_soj/1000)}（干扰机在 {rj_soj/1000:.0f} km 外）")

    print("\n目标距离        J/S (SOJ)      雷达能否检测")
    print("-" * 50)
    for r_km in [20, 40, 60, 80, 90, 100, 120, 150, 200]:
        r = r_km * 1000.0
        js = propagation.js_standoff(pj, gj, rj_soj, r, pt, gt, sigma, br, bj)
        js_db = 10 * math.log10(js) if js > 0 else -math.inf
        can_detect = js < 1.0 and r <= r_max
        print(f"{r_km:6.0f} km     {js_db:8.1f} dB      {'是' if can_detect else '否'}")

    print("\nESM 截获（一程传播）示例：")
    esm_gain_db = 0.0
    esm_gain = 10 ** (esm_gain_db / 10)
    esm_sens_dbm = -75.0
    esm_sens_w = 10 ** (esm_sens_dbm / 10) / 1000
    r_esm = propagation.esm_max_range_m(pt, gt, esm_gain, lam, esm_sens_w)
    print(f"ESM 对雷达理论最大截获距离: {fmt(r_esm/1000)}")
    for r_km in [200, 400, 600, 800]:
        p_dbm = propagation.esm_received_power_dbm(pt, gt, esm_gain, lam, r_km * 1000)
        print(f"  {r_km:5.0f} km 处 ESM 接收功率: {p_dbm:8.1f} dBm"
              f"  {'可截获' if p_dbm >= esm_sens_dbm else '不可截获'}")
    print("\n注：实际截获还受雷达视距、波束扫描概率、信号分选限制。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
