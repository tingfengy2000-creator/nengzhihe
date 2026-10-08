# Phase 2B round 19 handoff (5090)

日期：2026-10-08  
范围：`hybrid.tariff_escalation_rate`、四档 `escalation_sensitivity`、18.4 精简回放字段。

## 已实现

- `PVScenario` 与 `HybridScenario` 均接受 `tariff_escalation_rate`，范围为 -0.05 至 0.10，默认 0；`pv/run` 可从 `pv` 或共享 `hybrid` 对象读取，风光接口从 `hybrid` 读取。
- 逐年购电价格为当前逐时价格乘以 `(1+g)^(year-1)`。价格只作用于购电，发电、自用、购电电量、外送和弃电的物理轨迹不变；上网价格不随之调整。
- 光伏与风光生命周期对每年价格重算，时间分段电价使用原有逐时价格向量。储能附加卡按同一系数累计各年的少交电费，卖电粗算保持原规则。
- 结果含 `tariff_escalation:{rate,applies_to,note}` 和 `escalation_sensitivity`（`g=-2%,0,+2%,+4%` 的 S0/推荐方案成本现值、差额、简单回本年限）。
- 精简回放脚本保留 `simple_payback_years`、`annual_saving_after_maintenance_cny`，并从已保存逐年现金流派生四档敏感性；没有重跑物理模型。

## 验证

运行命令：

```powershell
python -m unittest discover -s tests -p 'test*.py'
python scripts/compact_replay_v9.py --input operation_planning/results/phase2b_carbon_5090/replay_cases_v9.json --output docs/handoff/replay_viewer/replay_cases_ui_v9.json
```

本轮契约测试 `tests/test_phase2b_tariff_escalation.py` 与全量 unittest 均通过；精简回放6案、7,856,874 bytes，小于8 MiB。默认 `g=0`，原有物理回放文件未覆盖。

## 适用边界

年涨幅是用户设定的敏感性情景，不是未来电价预测。分时结构按当前档案固定，外送价格不随之增长。敏感性表只复用逐年已算的购电成本，不把电价情景当作新的物理实验或独立验证。
