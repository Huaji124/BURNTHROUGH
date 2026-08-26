"""蒙特卡洛批量推演：不同干扰样式 / 拦截概率下的突防概率对比。

场景：
- 蓝方电子战飞机在约 103 km 外对红方驱逐舰实施干扰
- 红方驱逐舰只有在雷达烧穿干扰、能形成火控接触时才发射反辐射导弹
- 发射后，ARM 按给定命中概率（近防/机动/诱饵）判定命中

对比维度：
- 干扰样式：瞄准式噪声 / 阻塞式噪声 / 干扰机关闭
- ARM 命中概率：0.95 / 0.85 / 0.60

输出：突防（蓝方生存）概率、红方发射率、红方雷达有效探测距离等。

用法：
    python scripts/run_monte_carlo.py [每组次数] [--arm-probs 0.95 0.85 0.60]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common.geo import haversine_nm
from core.demo import build_demo_environment

JAMMER_MODES = {
    "spot_noise": "瞄准式噪声",
    "barrage_noise": "阻塞式噪声",
    "off": "干扰机关闭",
}


def radar_detection_range_km(env) -> float | None:
    """返回红方驱逐舰搜索雷达在当前干扰态势下的有效探测距离（km）。"""
    red = env.platforms.get("red_ddg")
    if red is None:
        return None
    emitter = next((e for e in red.emitters
                    if e.role in ("multifunction_radar", "search_radar", "fire_control_radar")),
                   None)
    if emitter is None or emitter.emcon_state != "on":
        return None
    jammer = None
    for p in env.platforms.values():
        if p.side == red.side:
            continue
        for j in p.jammers:
            if j.is_jamming and j.covers_frequency(emitter.center_freq_hz):
                jammer = j
                break
    result = env.evaluate_radar_with_jamming(
        emitter, jammer, rcs_m2=1000.0, bandwidth_hz=1_000_000,
        noise_figure=5.0, loss=6.0, snr_min_db=13.0)
    return result["detection_range_km"]


def run_single(seed: int, mode: str, hit_prob: float) -> dict:
    env = build_demo_environment()
    env.rng.seed(seed)
    env.arm_hit_probability = hit_prob

    # 设置干扰样式
    for jammer in env.all_jammers():
        if mode == "off":
            jammer.emcon_state = "off"
        else:
            jammer.emcon_state = "on"
            jammer.set_mode(mode)

    red = env.platforms["red_ddg"]
    blue = env.platforms["blue_ew"]
    dist_km = haversine_nm(red.latitude, red.longitude,
                           blue.latitude, blue.longitude) * 1.852
    detection_km = radar_detection_range_km(env)

    target_emitting = any(e.is_emitting for e in blue.emitters) or \
                       any(j.is_jamming for j in blue.jammers)
    launched = False
    if detection_km is not None and dist_km <= detection_km and target_emitting:
        env.add_attack_order("red_ddg", "blue_ew")
        launched = True

    max_time_s = 300
    while env.time_s < max_time_s:
        env.step(1.0)
        if any(m.result in ("hit", "miss", "lost_lock") for m in env.missiles):
            break

    missile_result = None
    for m in env.missiles:
        missile_result = m.result or "in_flight"

    return {
        "mode": mode,
        "hit_prob": hit_prob,
        "distance_km": dist_km,
        "detection_km": detection_km,
        "launched": launched,
        "missile_result": missile_result,
        "blue_alive": blue.alive,
        "esm_contacts": len(env.contacts.get("red_ddg", {})),
    }


def main() -> int:
    args = sys.argv[1:]
    n = int(args[0]) if args and args[0].isdigit() else 100
    arm_probs = [0.95, 0.85, 0.60]
    if "--arm-probs" in args:
        idx = args.index("--arm-probs")
        arm_probs = [float(x) for x in args[idx + 1:idx + 4]]
    modes = list(JAMMER_MODES.keys())

    print(f"蒙特卡洛推演：每种组合 {n} 次\n")
    print(f"{'干扰样式':<10}{'ARM命中率':>8}{'突防率':>8}{'红方发射率':>10}"
          f"{'平均探测距离':>12}{'失的率':>8}")

    for mode in modes:
        for prob in arm_probs:
            survival = 0
            launches = 0
            lost = 0
            det_sum = 0.0
            det_count = 0
            for seed in range(n):
                r = run_single(seed, mode, prob)
                if r["blue_alive"]:
                    survival += 1
                if r["launched"]:
                    launches += 1
                if r["missile_result"] == "lost_lock":
                    lost += 1
                if r["detection_km"] is not None:
                    det_sum += r["detection_km"]
                    det_count += 1
            avg_det = det_sum / det_count if det_count else 0.0
            print(f"{JAMMER_MODES[mode]:<10}{prob:>8.2f}{survival/n:>8.1%}"
                  f"{launches/n:>10.1%}{avg_det:>12.1f} km{lost/n:>8.1%}")

    print("\n说明：")
    print("- 突防率 = 蓝方电子战机生存比例")
    print("- 红方只对正在辐射的目标发射反辐射导弹")
    print("- 干扰机关闭时，红方无 ARM 发射条件，蓝方安全但红方雷达可全程跟踪")
    return 0


if __name__ == "__main__":
    sys.exit(main())
