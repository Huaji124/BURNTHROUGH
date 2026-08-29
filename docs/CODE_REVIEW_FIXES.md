# 代码审查与修复记录

> 日期：2026-08-29
> 范围：src/（34 个模块）+ scripts/（13 个脚本），约 8100 行
> 基线：29 个测试通过、ruff 默认规则无告警
> 结果：**58 个测试通过（新增 29）、ruff 全通过、UI 离屏冒烟正常**

---

## 一、崩溃与稳定性

| 位置 | 问题 | 处理 |
|---|---|---|
| `common/geo.py` `haversine_nm` | `asin(sqrt(a))` 未钳位，浮点舍入让 `a` 略大于 1 时抛 `math domain error`。该函数是全局调用最密集的几何函数 | 钳位到 [0, 1] |
| `core/environment.py` `triangulate_ranges` | 两站重合时 `d=0`，`(r1²-r2²+d²)/(2d)` 除零 | `d <= 1e-6` 直接返回 None |
| `core/environment.py` `evaluate_radar_with_jamming` | 干扰机/雷达平台未在环境中注册时，`_platform_of()` 返回 None 后被送入距离计算 | 补充空值分支，退化为无干扰结果 |
| `ui/map_widget.py` `_move_selected_to` | `self._projection` 为 None 时直接解引用 | 提前返回 |

## 二、逻辑错误

### 1. FDOA 定位完全失效（`cross_fix_fdoa`）

两处硬伤：载波频率硬编码为 `1470000000.0`（而非接触信号的真实频率）；用**单站绝对多普勒**去比对**两站多普勒差**，量纲不匹配，代价函数恒为巨大值，输出实为噪声。

修正：真实频率随接触传递（`_intercept_source` 新增 `freq_hz`，落入 `contact.extra`）；代价函数改为"预测差 vs 实测差"；阈值改为按参与站数归一化的均方根（50 Hz）。

另外发现代价曲面存在伪极小盆地，粗网格会锁错盆地。改为多分辨率搜索（0.05° → 0.01° → 0.002°），并优先用已有的测向交叉定位结果做种子。

> 实测：合成三站场景，定位误差 **30.57 km → 0.93 km**

### 2. ARM 反辐射导弹记忆攻击形同虚设（`step_missiles`）

命中判定写作 `actual_m < 500 and self._target_is_emitting(target)`——目标一停止辐射就必然走到 miss 分支。README 宣称的"雷达关机记忆攻击"实际命中率为 0。

修正：抵达锁定点后，目标仍在辐射走正常判定；已关机的仍可能命中，但概率打 0.4 折（末段无辐射源可寻的）。

> 实测（300 次蒙特卡洛）：雷达全程开机 300/300 命中；末段关机场景 **0/300 → 123/300（41%）**

### 3. 绕飞轨道持续外扩（`step_motion`）

沿切线直飞不做半径修正，实测 5 km 轨道 30 分钟后漂到 10.91 km。

修正：每帧移动后把平台投影回精确半径。另修正 `orbit_center_lon` 未参与判空、`waypoint_drag_lock` 检查放在循环内。

> 实测：60 分钟后轨道半径 **5.0000 km**（修前 30 分钟即 10.91 km）

### 4. 通信干扰事件每帧刷屏（`update_comm_jamming`）

每帧为每个受扰目标 append 一条事件，长时间推演 events 无界增长。

修正：只在"未降级 → 已降级"跃变时记录。注意坑点：函数开头会把所有平台重置为 False，必须**先快照再比对**，否则永远都是 False→True。另加 `Environment.events_max = 2000` 上限。

> 实测：600 帧 **600 条 → 1 条**；干扰机停机/重启的状态跃变仍正确记录

### 5. 导弹末速下限缺失（`step_missiles`）

`max(missile.terminal_speed_mps or 0.0, ...)`，配置缺失时下限为 0，阻力模型让导弹一路减速到停在空中、永远到不了目标。

修正：未显式配置时按标称速度 50% 兜底。

### 6. 其他

- **射程判定**：用"标称速度 × 飞行时间"，与助推/阻力模型偏差可达 30%。改为累计航程（`Missile.distance_flown_m`）
- **TDOA 阈值**：`cost < 1e14` 等价于容忍 5 ms 到达时间误差，形同虚设。改为归一化均方根阈值 2000 ns
- **雷达探测选干扰机**：只检查频段，不检查干扰扇区与多目标上限，与 `assign_jammers()` 口径不一致
- **红外探测**：完全无视距约束，水天线两侧的平台能互相"看见"。补上与雷达一致的视距判定
- **主窗口事件计数**：切换想定/加载数据后 `_last_event_count` 不重置，新想定事件数更少时状态栏彻底不再显示消息
- **地图右键菜单**：三个条目里两个文案不同却执行同一函数（复制粘贴残留）
- **平台菜单**："归队"和"离队"都调用 `_platform_leave_group`
- **`china_loader._role_name`**：死条件 `"multifunction_radar" if False else "search_radar"`

## 三、性能

### 1. `assign_jammers()` 被放在循环内部（最大一项）

`update_radar_detection` 和 `draw_ew_circles` 都在"平台 × 辐射源"的循环内调用全局干扰分配，导致每部雷达重跑一遍 O(平台² × 干扰机) 的分配。

修正：每帧只算一次，并预建 `jammer_by_id` 索引。

| 平台数 | 修复前（仅分配开销） | 修复后（整帧） | 加速比 |
|---:|---:|---:|---:|
| 20 | 2.1 ms | 0.4 ms | 5.5x |
| 60 | 47.2 ms | 3.2 ms | 14.7x |
| 120 | 360.1 ms | 13.0 ms | 27.6x |
| 200 | 1740.6 ms | 37.3 ms | **46.7x** |

UI 每 1 秒 tick 一次，这个改动直接决定大装备库能否运行。

### 2. 加载器全表线性扫描

`china_loader` 与 `cmo_world_loader` 对每架飞机的每个挂载方案都线性扫一遍 `loadout_weapons`（美国 26624 条）。改为按 ID 建索引。

> china_full.json：比较次数 **3,229,774 → 5,036（641x）**
> CMO 美国：旧写法约 5.2 亿次比较；索引后加载 1817 个平台实测 **235 ms**

## 四、数据加载器

### 1. 所有平台坐标都是 (0, 0)

CMO/MoZi 数据库不含任何经纬度字段，加载后全部单位重叠在几内亚湾一个点上。

修正：新增向日葵螺线布点（`data_loader/common.py::scatter_point`），黄金角保证任意前缀均匀、互不重叠。`center` / `spread_km` 可配，默认 (22.0, 120.0) / 250 km（与演示想定同海域）。

> 实测：美国 1817 个平台，唯一坐标 1817/1817，前 300 个单位最近邻间距 9.05 km

### 2. 挂载与弹药从未被装载

CMO 导出的 `loadout_weapons.ComponentID` 指向的武器表并未随包导出（26624 条里只有 520 条落在 `mounts.json`，且映射结果明显错位，如 "AGM-88A HARM" 映射到 "20mm M61A1 Vulcan"）。

可用信息其实就在 `loadouts[ID]` 记录本身：**Name 即武器名，Capacity 即载弹量**。据此重建映射链，并跳过 `(Reserve [Available])` 这类占位挂载。

> 实测：美国 1817 个平台，有可用导弹的平台 **0 → 578**

### 3. 舰艇完全没有武器

CMO 里舰艇的导弹挂在发射装置上，`magazine_weapons.ComponentID` 指向的是发射架本身（"Mk26 Mod 1 Twin Rail"）而不是导弹。结果 692 艘舰一艘都打不了。

修正：新增 `_infer_ship_weapons()`，仅在完全没有挂载明细时按发射装置型号保守推导——Mk41/Mk13/Mk26/VLS → 舰空导弹，Mk141/Harpoon/Exocet → 反舰导弹，鱼雷发射管 → 鱼雷。

> 实测：692 艘舰 → 332 艘有武器；161 艘潜艇 → 150 艘有武器

### 4. 武器类型推断只认中国命名

原 `_infer_weapon_kind` 只覆盖 PL-/YJ-/HQ-，NATO 命名全部落为 "weapon"，而 `_choose_weapon()` 只认 aam/sam/arm/asm，装载美系装备后一架飞机都选不到弹。

新增 `data_loader/weapon_kind.py`，覆盖中美俄欧常见命名，两个加载器共用。**匹配改为词首匹配**——朴素子串匹配曾造成明显误判：`"tor "` 命中 rap**tor** / ga**tor** / penetra**tor**，`"sm-1"` 命中 a**sm-1**35a，把集束炸弹和空地弹判成舰空弹。

已固化为 20 条用例的参数化测试。

### 5. 未被读取的数据

`signatures`、`propulsion_performance`、`fuel`、`magazines` 此前完全没加载，RCS / 最大速度 / 燃料全部走默认值。

> 实测：美国 1817 个平台，RCS 覆盖 1817（原 0）、最大速度 1650（原 0）、燃料 1625（原 0）

箔条识别补上 SRBOC / Mk36 / Nulka 等按型号命名的装置。

> 实测：带箔条的舰艇 **39 → 467 艘**

## 五、死代码

- 删除 `Environment._launch_arm` / `_launch_asm`：零引用（已被 `_launch_weapon` 取代），且制造的导弹因缺末速参数会减速到停在空中
- 主窗口三个加载入口各重复 7 行刷新代码 → 提取为 `_bind_environment()`
- `_sync_toolbar_actions` 用 `for ... break` 取首个元素 → `next(iter(...), None)`

## 六、新增文件

| 文件 | 说明 |
|---|---|
| `src/data_loader/weapon_kind.py` | 武器类型推断（词首匹配，覆盖中美俄欧命名） |
| `src/data_loader/common.py` | `index_by_id` / `scatter_point` 加载器共用工具 |
| `src/tests/test_data_loader.py` | 29 个用例，覆盖类型推断、布点、索引、两个加载器 |
| `docs/CODE_REVIEW_FIXES.md` | 本文档 |

## 七、已知遗留（需决策，未擅自修改）

1. **装载 CMO/中国数据后无法交战**：`main_window` 的三个加载入口都会整体替换 `Environment`，且全部单位被赋予同一阵营（美国数据全是 blue），场景里没有敌人。这是 UI 流程设计问题，不是加载器 bug。
2. **`cmo_full_by_country/`（85 MB）未加入 .gitignore**，同类的 `cmo_world_full.json` 已排除。
3. **`china_loader` 弹药库 `max_ammo`** 原式 `max(1, int(...) and 1 or 1)` 恒等于 1（语义不明），已改写为直白写法但**保持原行为**。是否应按弹库容量设置待定。
4. **武器类型推断的兜底推导**（第三节第 3 点）是为弥补数据缺失加的保守推断，若后续能拿到发射装置 → 弹型的完整映射表，应替换掉。
