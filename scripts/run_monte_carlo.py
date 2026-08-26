"""蒙特卡洛批量推演：反辐射打击突防概率统计。

用法：
    python scripts/run_monte_carlo.py [次数]

每次推演：
- 红方驱逐舰发射 1 枚反辐射导弹攻击蓝方电子战机
- ARM 命中概率 0.85（可被近防/机动/诱饵拦截）
- 统计命中率、失的率、蓝方生存率
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.demo import build_demo_environment


def run_single(seed: int) -> dict:
    env = build_demo_environment()
    env.rng.seed(seed)
    env.arm_hit_probability = 0.85
    env.add_attack_order("red_ddg", "blue_ew")

    max_time_s = 300
    while env.time_s < max_time_s:
        env.step(1.0)
        if any(m.result in ("hit", "miss", "lost_lock") for m in env.missiles):
            break

    result = {"blue_alive": env.platforms["blue_ew"].alive}
    for m in env.missiles:
        result["missile_result"] = m.result or "in_flight"
    result["esm_contacts"] = len(env.contacts.get("red_ddg", {}))
    return result


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    print(f"蒙特卡洛推演：反辐射打击，共 {n} 次\n")
    outcomes = Counter()
    blue_alive = 0
    esm_total = 0

    for seed in range(n):
        r = run_single(seed)
        outcomes[r["missile_result"]] += 1
        if r["blue_alive"]:
            blue_alive += 1
        esm_total += r["esm_contacts"]

    print(f"{'结果':<14}{'次数':>8}{'比例':>10}")
    for key in ("hit", "miss", "lost_lock", "in_flight"):
        count = outcomes.get(key, 0)
        print(f"{key:<14}{count:>8}{count/n:>9.1%}")
    print(f"\n蓝方电子战机生存率: {blue_alive/n:.1%}")
    print(f"红方平均 ESM 接触数: {esm_total/n:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
