# 电子战（EW）海空兵推软件原型

一款以电子战为核心的现代海空兵推软件原型，设计参考《Harpoon》和
《Command: Modern Operations (CMO)》的玩法，重点模拟：

- 雷达/通信信号截获（ESM / RWR / ELINT）
- 有源干扰（噪声压制、欺骗干扰）
- 反辐射打击（ARM）
- 辐射管制（EMCON）
- 电子防护（ECCM）

## 当前阶段

Phase 0：静态射频沙盘（电磁公式计算与地图显示）。

## 技术栈

- Python 3.10+
- PySide6（Qt Widgets + QGraphicsView 地图）
- pyproj / shapely（地理计算）
- JSON（装备与想定数据）

## 目录结构

见 `docs/DEV_PLAN.md` 或开发规划文档。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
python scripts/run_headless.py   # 无界面：打印 J/S 与烧穿距离表
pytest -q                       # 运行测试
```
