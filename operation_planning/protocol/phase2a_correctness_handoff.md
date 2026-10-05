# 阶段二 A 正确性与真实 Agent 修复交接

本轮在 `fix/phase2a-correctness-agent` 从 `a808c39d0aa4d398065aa7ef4f76fa701acf2927` 独立接续。旧 `results/pv_phase2a/`、前三轮记录和前端均保留；本轮没有推送、发布或修改其他项目。

## 已修复

- `lifecycle_compare` 逐年保持空调负荷不变，只按年衰减光伏交流功率，再逐时重算自用、购电、外送和弃电；每年保存负荷/光伏守恒误差。0kWp 不承担光伏报价、维护、更换、残值或接入费。
- Open-Meteo 方位转换为 `0→180`、`-90→90`、`90→270`、`180→0`（pvlib 约定）。辐照明确绑定到 `[timestamp, timestamp+interval)`，太阳位置使用区间中点。
- 真实时间戳必须与声明间隔逐项一致；重复、倒序、过长间隔、缺测、NaN、非有限值和负辐照拒绝进入计算。
- 电价沿用 `operation_planning.tariffs` 的 `TariffProfile`；常数电价标记为用户情景。非零报价或外送价缺失时仍保留物理结果，但经济状态为 incomplete，不把 0kWp 胜出称为已证明最优。
- PV 报告保留第一阶段温度、湿度、容量缺口及 cooling-only 服务状态；存在服务缺口时推荐带条件说明。
- Agent API 不再先算报告再朗读。自然语言先形成受限修改，随后由模型按 `interpret_request → validate_task → read_load_context → check_weather_inputs → generate_candidates → compute_pv_generation → match_load_hourly → calculate_lifecycle → prepare_report` 触发实际工具；模型失败不会由确定性结果冒充成功。

## 复现与结果

- 短时序回归：`python tests/test_phase2a_correctness.py`
- 原阶段二回归：`python tests/test_phase2_pv.py`
- 全量修复结果：`python scripts/phase2a_correctness_demo.py`
- 真实本地模型任务：`python scripts/phase2a_agent_task.py`
- Agent 变体（晚间使用时段、组件报价变化、外送价缺失澄清）：`results/pv_phase2a_correctness/agent_task_variants.json`
- 真实 Agent 任务固定表单预算 9000 元，用户请求“预算改为6000元，其他条件不变”；结果记录在 `results/pv_phase2a_correctness/agent_budget_6000.json`，预算进入场景对象并将预算容量上限重算为约 1.622 kWp。

`results/pv_phase2a_correctness/counterexamples_before_after.json` 记录了旧生命周期 0kWp 累计购电成本 8060.746751414448 元与修复后 8243.780182079508 元（目标值 8243.780182079507 元）的对照。`guangzhou_2024_full_chain_corrected.json` 保留 0/1/2/3 kWp 全部候选的汇总和逐时 CSV 证据；同目录还包括广州 2024 的 10/15 年现金流、使用时段和屋顶/预算变化，以及广州/北京/哈尔滨 2023–2025 固定 2 kWp 九组时间年结果。

## 当前结论边界

广州 2024 当前报价、常数购电价、无外送和未校准冷却负荷情景下，0 kWp 的净现金流现值最高；这不是真实楼宇投资结论。非零报价、外送价格、现场屋顶条件或服务水平缺失时，系统只给出物理与匹配结果并保留未决。第一阶段负荷仍是城市级情景，不证明实际节能、采购价格、并网审批或人工提效。
