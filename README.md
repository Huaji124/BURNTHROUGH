# 烧穿 BURNTHROUGH

电子战（EW）海空兵推软件原型

一款以电子战为核心的现代海空兵推软件原型，设计参考《Harpoon》和
《Command: Modern Operations (CMO)》的玩法，重点模拟：

- 雷达/通信信号截获（ESM / RWR / ELINT）
- 有源干扰（噪声压制、干扰扇区、多目标分配）
- 反辐射打击（ARM）
- 辐射管制（EMCON）
- 电子防护（ECCM，后续接入）

## 当前阶段

已完成 Phase 1–4 的核心功能：

- **Phase 1** 静态射频沙盘与电磁圈渲染
- **Phase 2** ESM 辐射源截获、接触管理、DOA 交叉定位
- **Phase 3** 有源干扰深化：瞄准/阻塞噪声、干扰扇区、多目标分配
- **Phase 4** 反辐射导弹飞行、记忆攻击、失的判定
- **Phase 5** 欺骗干扰与电子防护：RGPO/VGPO/假目标、ECCM
  - 假目标接入 ARM 制导：欺骗干扰可使反辐射导弹脱靶
- **Phase 6** 火力闭环基础：ASM 反舰导弹、CIWS 近防拦截
- 交互层：选中/框选、航路点拖拽、右键菜单、攻击指令、想定保存/加载
- 蒙特卡洛批量推演脚本
- UI：频谱监视面板、假目标列表

## 技术栈

- Python 3.10+
- PySide6（Qt Widgets + QGraphicsView 地图）
- pyproj / shapely（地理计算）
- JSON（装备与想定数据）
- pytest（测试）
- ruff（代码检查）

## 目录结构

```
src/
├── core/          # 模拟内核
├── ui/            # PySide6 界面
├── common/        # 地理 / 单位换算 / 投影
├── data_loader/   # JSON 加载
└── tests/         # 单元测试
scripts/           # 无界面演示、蒙特卡洛、UI 启动
data/              # 装备数据和想定
docs/              # 开发文档
```

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[test]"

python scripts/run_ui.py           # 启动图形界面
python scripts/run_headless.py     # 无界面：打印 J/S 与烧穿距离表
python scripts/run_monte_carlo.py 20  # 蒙特卡洛突防概率
pytest -q                          # 运行测试
```

## 界面操作

| 按键 | 功能 |
|---|---|
| `Space` | 暂停 / 继续 |
| `R` | 雷达 开机 / 关机 |
| `J` | 干扰机 开机 / 关机 |
| `F` | 复位视图 |
| 滚轮 | 缩放地图 |
| 左键拖拽 | 框选 |
| 右键 | 上下文菜单 / 设置航路点 |
| 中键拖拽 | 平移地图 |

## 测试

当前测试数量：**22 passed**

## 注意事项

- 装备参数均为公开资料或虚构近似值，不涉及保密/管制数据。
- 当前为单机沙盘模式，联网/导演模式后续接入。
