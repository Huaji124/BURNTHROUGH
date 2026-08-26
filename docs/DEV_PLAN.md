# 开发计划（烧穿 BURNTHROUGH - 电子战兵推）

> 完整规划见 `/home/dsh/EW_wargame_development_plan.txt`。

## 当前阶段

- [ ] Phase 0：项目初始化（目录、骨架、装备数据）
- [x] Phase 1：静态射频沙盘（公式计算 + 无界面演示）
- [x] Phase 2：辐射源截获与 ESM（截获模型 + 接触管理 + 交叉定位 + EMCON 面板）
- [ ] Phase 3：有源干扰
- [ ] Phase 4：反辐射打击
- [ ] Phase 5：欺骗干扰与电子防护
- [ ] Phase 6：简单海战支撑模块
- [ ] Phase 7：想定与界面完善
- [ ] Phase 8：测试与扩展

## 下一步

1. `pip install -e ".[test]"`
2. `python scripts/gen_initial_data.py`
3. `python scripts/run_headless.py`
4. `pytest -q`
