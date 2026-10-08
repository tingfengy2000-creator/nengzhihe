# Phase 2B round 20 handoff (5090)

本轮接续 `fix/5090-redesign-followup@290eb58`，只处理第20节三个前端依赖项。没有改写 `docs/handoff/5090_carbon_request.md` 或 `docs/handoff/frontend_redesign/`。

## 敏感性结果口径

- `escalation_sensitivity[].incremental_npv_vs_s0_cny` 统一为 `S0总成本现值 - 推荐方案总成本现值`，与候选层同号；正数表示相对只购电方案节省。
- 原 `simple_payback_years` 保留，含义固定为“按第1年节省”的简单回本年限，并返回 `simple_payback_note`。
- 新增 `cumulative_payback_year`：按每年涨幅后的基准购电成本与候选购电成本差额，扣除候选维护、更换费用并计入外送及残值，逐年累计净节省；首次达到初始投入的年份即为回本年。研究期内未达到时为 `null`，`payback_note` 明确说明。
- 光伏、风光API和精简回放使用同一符号和回本字段；`g=0`敏感性行与候选层节省字段逐位对照。

## 一句话理解字段

`operation_planning/agent_parse.py` 的只读解析字段现在包括：

- `hybrid.tariff_escalation_rate`：例如“电价每年涨3%”解析为 `0.03`；
- `hybrid.wind.turbine_count`：风机台数，沿用混合任务实际嵌套路径；
- `storage.quote.cny_per_kwh`：储能单价；
- `storage.capacities_kwh`：储能可选容量列表。

储能报价和容量不再被标为“不支持”。“储能峰谷套利”“保证回本”等超出当前附加卡片能力的承诺仍会进入 `unsupported`，不会被静默接受。解析仍只返回建议，不执行任何计算。

## 验证与回放

```powershell
python -m unittest discover -s tests -p 'test*.py'
python scripts/compact_replay_v9.py --input operation_planning/results/phase2b_carbon_5090/replay_cases_v9.json --output docs/handoff/replay_viewer/replay_cases_ui_v9.json
```

本轮全量 unittest 为34项通过；精简回放6案、7,861,244 bytes，小于8 MiB。精简文件 SHA-256 为 `9ab63f08381618f7f4dc77a8eacc5a8b29241edd32fd89ce544b152b9b9f4a6b`；完整物理回放保留，精简文件只从已保存逐年经济结果派生。
