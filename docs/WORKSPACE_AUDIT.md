# 工作区检查报告（烧穿 BURNTHROUGH）

> 检查时间：2026-08-29
> 工作区：`C:\Users\29938\BURNTHROUGH`
> 结论：项目结构完整、代码与数据齐备、Git 工作区干净；唯一缺口是虚拟环境未安装 pytest。

---

## 一、项目概览

**烧穿 BURNTHROUGH** —— 以电子战（EW）为核心的现代海空兵推软件原型，玩法参考
《Harpoon》与《Command: Modern Operations (CMO)》。

| 项目 | 值 |
|---|---|
| 版本 | 0.1.0 |
| 主要语言 | Python（>=3.10） |
| 代码规模 | 8129 行 / 47 个 .py 文件（src 34 + scripts 13） |
| UI 框架 | PySide6 6.11.2（Qt Widgets + QGraphicsView 地图） |
| 数据层 | JSON（装备库 + 想定），约 88 MB |
| Git 分支 | main，无未提交改动 |
| 最近提交 | `02bc26e` 修复 CIWS 测试舰未禁用默认舰炮 |

---

## 二、目录结构

```
BURNTHROUGH/
├── src/                 # 应用源码（34 个 .py）
│   ├── core/            # 模拟内核（10 个文件，环境/辐射源/干扰机/导弹等）
│   ├── ui/              # PySide6 界面（10 个文件）
│   ├── common/          # 地理计算 / 单位换算 / 投影（4 个文件）
│   ├── data_loader/     # JSON 数据加载（4 个文件）
│   └── tests/           # 单元测试（4 个文件，29 个用例）
├── scripts/             # 13 个辅助/数据加工脚本
├── data/                # 装备数据与想定（88 MB）
├── docs/                # 5 份开发文档
├── .venv/               # 已建虚拟环境
├── 一键启动.bat          # 自动建环境 + 启动 UI
├── 打包EXE.bat          # PyInstaller 打包
├── pyproject.toml       # 项目配置（pytest / setuptools）
├── README.md / LICENSE  # 说明与 MIT 许可证
└── .gitignore
```

---

## 三、源码明细（按行数）

### src/core（模拟内核）
| 文件 | 行数 | 职责 |
|---|---:|---|
| `environment.py` | 1844 | **核心**：平台/环境容器，含 ESM 截获、雷达/红外/声呐探测、干扰评估、交叉定位（TDOA/FDOA）、欺骗干扰、导弹飞行与毁伤 |
| `demo.py` | 185 | 演示想定：红方驱逐舰+护卫舰 vs 蓝方电子战飞机 |
| `propagation.py` | 160 | 雷达方程 / 干扰方程 / 传播损耗，单位统一为 W、m、线性增益 |
| `scenario.py` | 68 | 想定 JSON 保存与加载（dataclasses.asdict） |
| `emitter.py` | 67 | 发射机实体（雷达、通信、数据链） |
| `jammer.py` | 65 | 干扰机实体（瞄准/阻塞噪声、干扰扇区） |
| `missile.py` | 39 | 反辐射导弹（ARM）模型 |
| `contact.py` | 31 | 接触模型（radar_contact / emitter_contact） |
| `receiver.py` | 34 | 接收机实体（雷达通道 / ESM / RWR） |

### src/ui（界面层）
| 文件 | 行数 | 职责 |
|---|---:|---|
| `map_widget.py` | 801 | 2D 战术地图：选中/框选/航路点拖拽/右键菜单/攻击指令 |
| `map_renderer.py` | 784 | 渲染辅助（抽离"画什么"逻辑） |
| `main_window.py` | 410 | 主窗口：地图+底边栏+接触列表+EMCON+频谱；版本号 `f941d32` |
| `contact_list.py` | 162 | 接触/辐射源列表，支持右键人工标记 |
| `unit_info_bar.py` | 106 | 底边栏：选中单位弹药/油量/最大速度 |
| `spectrum_widget.py` | 97 | 频谱监视面板 |
| `signal_library_panel.py` | 92 | 全参数信号库编辑 |
| `emcon_panel.py` | 84 | EMCON 辐射管制面板 |
| `weapon_panel.py` | 83 | 武器栏：武器槽选择与手动攻击 |
| `false_target_panel.py` | 61 | 假目标列表 |

### src/common / src/data_loader
- `common/geo.py`（66）、`projection.py`（36）、`units.py`（78）
- `data_loader/china_loader.py`（311）中国军力装载、`cmo_world_loader.py`（202）全球 CMO 装载、`loader.py`（31）

### scripts（13 个）
- **运行类**：`run_ui.py`、`run_headless.py`（打印 J/S 与烧穿距离表）、`run_monte_carlo.py`（蒙特卡洛突防概率）、`run_china_sandbox.py`
- **数据加工类**：`gen_initial_data.py`、`import_cmo_db.py`、`export_china_full.py`、`export_cmo_world.py`、`split_cmo_world.py`、`merge_all_cmo.py`、`merge_type003.py`、`clean_cmo_data.py`、`export_clean_full_by_country.py`

---

## 四、数据资产（data/，约 88 MB）

| 路径 | 大小 | 内容 |
|---|---:|---|
| `cmo_full_by_country/` | 85 MB | **120 个国家目录 / 1561 个 JSON**，拆分后的全球 CMO 装备明细（挂载/弹药/推进） |
| `china_full.json` | 2.7 MB | 中国军力完整数据（305 平台/238 传感器/129 武器/802 挂载/58 弹药库/129 推进） |
| `china_units.json` | 260 KB | 中国军力精简版（platforms/sensors/weapons） |
| `environment/` | 93 KB | `coastlines.json`、`terrain.json`、`world_land.json` |
| `platforms/` | 7 KB | 阿利·伯克级、EA-18G、003 型福建舰 |
| `sensors/` | 7 KB | ALR-67 RWR、先进 ESM、726 型 ESM |
| `weapons/` | 7 KB | 鹰击-91 反辐射、鱼叉反舰、标准-2 |
| `emitters/` | 7 KB | AN/APG-66、AN/SPY-1D、346 型搜索雷达 |
| `jammers/` | 2 KB | 干扰机定义 |
| `scenarios/` | 8 KB | `demo_ew.json` 演示想定 |
| `signal_params.json` | 1 KB | 346 型雷达、AN/SPY-1D 信号参数 |
| `china_type003_fujian.json` | 4 KB | 福建舰单舰数据 |

---

## 五、文档（docs/，5 份）

| 文档 | 行数 | 内容 |
|---|---:|---|
| `DEV_PLAN.md` | 54 | 开发计划：Phase 1–6 已完成，Phase 7（导演/联网、教学想定）与 Phase 8（测试扩展、性能优化、3D 可视化）待开发 |
| `ROADMAP_NEXT.md` | 113 | 下一步方案：按 P0/P1/P2 列出模型缺口清单（环境层 DEM/波导、传感器层 3D 波束与信号分选、武器层 3D 弹道与末段机动、指挥层） |
| `CHINA_EQUIPMENT_REPORT.md` | 387 | 中国装备清单：99 舰 / 136 机 / 17 潜 / 112 武器 |
| `CMO_WORLD_EQUIPMENT_REPORT.md` | 196 | 全球（除中国）装备报告：8156 平台 / 2989 传感器 / 1603 武器 / 24908 挂载 |
| `SEA_POWER_US_2026_ACTIVE.md` | 75 | 美军单位 2026 年在役评估：65 个舰船型号中仅 3 类仍可用，36 个机型中仅 2 类 |

---

## 六、运行状态检查

| 检查项 | 结果 |
|---|---|
| 虚拟环境 `.venv` | ✅ 已创建 |
| 核心依赖 | ✅ numpy 2.2.6、pyproj 3.7.1、shapely 2.1.2、PySide6 6.11.2、pyinstaller 6.22.2 |
| 项目安装 | ✅ burnthrough 0.1.0（editable 模式已安装） |
| **pytest** | ❌ **未安装**，无法运行测试（README/DEV_PLAN 标注应有 24–27 项测试） |
| Git 工作区 | ✅ 干净，无未提交文件 |
| 构建/打包 | ✅ `打包EXE.bat` 使用 PyInstaller（windowed，附带 data 目录） |

### 建议

1. 安装测试依赖：`.venv\Scripts\python.exe -m pip install pytest`（或 `pip install -e ".[test]"`）
2. 源码中含 27 个 `__pycache__` 下的 `.pyc` 文件——已被 .gitignore 覆盖，无影响
3. 仓库中未跟踪的超大数据文件（`cmo_world_full.json` 55.7 MB 等）已在 .gitignore 中排除，但 `cmo_full_by_country/`（85 MB）**未排除**，如不希望入库建议加入忽略规则
