"""加载中国军力参考数据并打印概要。

用法：
    python scripts/run_china_sandbox.py [平台数量]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data_loader.china_loader import load_china_environment


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    env = load_china_environment("data/china_full.json", side="red", limit_platforms=limit)
    print(f"已从 data/china_full.json 加载 {len(env.platforms)} 个中国平台")
    for p in list(env.platforms.values())[:min(limit, 8)]:
        print(f"  {p.id:24s} {p.name:36s} 传感器={len(p.emitters)+len(p.receivers)+len(p.jammers):3d} 武器={len(p.weapons)}")
    print("示例：", next(iter(env.platforms.values())).name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
