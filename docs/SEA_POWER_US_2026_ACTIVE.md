# Sea Power v0.8.2 美国单位 2026 年可用性评估

> 基于 `all_data` 中的 `usn_*` / `usaf_*` / `usmc_*` 数据文件，按 2026 年仍在役/可用情况整理。
> 仅供参考；实际状态以官方发布为准。

## 一、美国海军舰船（USN，65 个基础型号）

### ✅ 2026 年仍可能可用（3 类）

| 数据文件 | 型号 | 说明 |
|---|---|---|
| `usn_cvn_nimitz` | 尼米兹级航空母舰 | 2026 年仍有多艘服役 |
| `usn_ssn_los_angeles` | 洛杉矶级攻击核潜艇 | 2026 年仍有较多数服役 |
| `usn_cg_ticonderoga` | 提康德罗加级导弹巡洋舰 | **少量仍服役**，但正加速退役，2027 年前计划全部退出现役 |

### ❌ 2026 年已退役/不可用（62 类）

- 补给/维修：`ae_kilauea`、`ao_t2`、`aoe_sacramento`、`takr_algol`
- 护航舰：`avp_barnegat`、`bb_iowa`、`clg_oklahoma_city`
- 巡洋舰：`cg_belknap`、`cg_leahy`、`cgn_alaska`、`cgn_california`、`cgn_long_beach`、`cgn_virginia`
- 航母：`cv_america_79`、`cv_forrestal_75`、`cv_kitty_hawk`、`cvn_enterprise`
- 驱逐舰：`dd_gearing*`、`dd_spruance*`、`ddg_adams*`、`ddg_coontz*`、`ddg_kidd*`、`ddg_mahan`
- 护卫舰：`ff_garcia`、`ff_knox*`、`ffg_brooke`、`ffg_oliver_hazard_perry`
- 两栖/运输：`lha_tarawa`、`lka_charleston`、`lpd_austin`、`lsm_lsm1`、`lst_newport`
- 扫雷/巡逻：`msc_adjutant`、`mso_aggressive`、`pb_pgm-39`、`phm_pegasus`
- 测试艇：`septar_qst-35`
- 战略核潜艇：`ssbn_franklin`、`ssbn_james_madison`、`ssbn_lafayette`
- 其他核潜艇：`ssn_permit*`、`ssn_skipjack*`、`ssn_sturgeon*`

---

## 二、美国飞机（USN/USAF/USMC，36 个基础型号）

### ✅ 2026 年仍可能可用（2 类）

| 数据文件 | 型号 | 说明 |
|---|---|---|
| `usaf_e-3a` | E-3 望楼预警机 | E-3 家族仍服役（多为 B/C/G，但在役体系相同） |
| `usaf_f-15c` | F-15C 鹰式战斗机 | 2026 年美国空军/空中国民警卫队仍有服役 |

### ⚠️ 2026 年可能仅剩训练/假想敌用途（1-2 类）

| 数据文件 | 型号 | 说明 |
|---|---|---|
| `usaf_f-5a` / `usaf_f-5e` | F-5 虎式战斗机 | 已退役一线任务，但仍被美国海军/空军用作**假想敌/教练机** |
| `usn_fa-18a` | F/A-18A 大黄蜂 | 一线已退役；部分可能用于支持单位，主体已换装超级大黄蜂 |

### ❌ 2026 年已不可用（约 33 类）

- 轰炸机：`b-52d`、`b-52g`（现役仅 B-52H，本包没有 B-52H）
- 运输/特种：`c-141b`、`vc-137c`、`kc-135a`、`hh-3`
- 战斗/攻击机：`f-4d`、`f-4e`、`a-3b`、`a-6e`、`a-7e`、`f-14a`、`f-4j`、`ra-5c`、`s-3a`
- 电子战：`ea-6b`、`eka-3b`、`ka-3b`、`ra-3b`
- 预警/巡护：`e-2c`（现役为 E-2D）、`p-2h`、`p-3c`（现役为 P-8A）、`sh-3h`、`sh-2f`、`ch-46`
- 直升机：`ah-1t`、`sh-2f`、`sh-3h`、`vh-?`
- 无人机/试验：`qh-50c`、`qh-50d`、`v-19a`

---

## 三、结论

- **舰船可用率：约 3 / 65 ≈ 5%**
- **飞机可用率：约 2 / 36 ≈ 6%**
- 如果算上“部分可能仍有少量/训练用途”，也仅约 **5-8 类** 可算 2026 年仍能用。

### 核心可用装备

1. 尼米兹级航母
2. 洛杉矶级攻击核潜艇
3. 提康德罗加级巡洋舰（少数/退役中）
4. E-3 预警机
5. F-15C 战斗机
6. （边界）F/A-18A、F-5 假想敌

> 本数据包定位是**冷战 1980 年代**，因此大部分美国装备到 2026 年已经退役。
