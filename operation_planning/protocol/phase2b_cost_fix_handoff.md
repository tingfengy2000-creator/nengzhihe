# 阶段二B统一成本与约束回归修复交接

基线提交：`bbbedafa6890711f317d4fce8286a327453b7c68`

本分支只修正阶段二B的经济定义、候选准入、输入守恒与 Agent 重复计算；不扩展风电、储能、城市或设备类型，不更新申报材料。

## 统一规则

- 初始投入在 `t=0`；运行、维护、更换和残值在对应年份年末计入并按该年份折现。
- `npv_cny` 是净现金流现值，`total_cost_npv_cny` 是其相反数，`incremental_npv_vs_s0_cny` 才用于与只购电基线比较。
- 光伏逆变器更换费为 `容量(kWp) × 逆变器单价 × 更换比例`；组件、支架、施工和接入费不进入该项。
- 风光组合只使用 `shared_connection_cny` 或两个组件报价都明确为 0 的无接入费情景，不再取两个报价的最大值。
- 非零候选报价、外送价格或约束不完整时保留物理结果和 S0 基准，推荐状态为 `not_available`，不能宣称“不安装最划算”。
- 光伏固定配置按 `roof_area_m2 × usable_fraction × 0.2 kWp/m²` 检查；超限标记 `not_applicable`。匹配入口拒绝 NaN、负功率、负外送上限和非有限价格。

## 可复现命令

```powershell
cd E:\比赛\nengzhihe
python tests/test_phase2b_wind.py
python tests/test_phase2a_correctness.py
python tests/test_phase2_pv.py
python scripts/phase2b_wind_demo.py
python scripts/phase2b_wind_agent.py
python scripts/phase2b_cost_fix_evidence.py
```

五项本地模型任务记录在 `results/phase2b_cost_fix/agent_task_records.json`。计算工具在首次 `compute_generation` 阶段执行一次完整规划，后续 `match_supply_demand` 和 `calculate_lifecycle` 读取同一中间结果；记录中的 `full_plan_calls=1` 可核查。预算减少三分之一和 18—22 点使用时段修改均进入受校验任务对象；缺少外送价格的任务保持澄清状态。

## 结果证据

- `results/phase2b_cost_fix/regression_evidence.json`：105/110/10% 得 `-5.0` 元；2 kWp、600 元/kWp、15% 在第12年更换费 `180.0` 元；0台风机固定投入 `0.0` 元；缺报价推荐不可得；1 m² 屋顶的 2 kWp 标为不适用；NaN 被拒绝。
- `results/phase2b_cost_fix/guangzhou_2024_full_chain.json`：修复后广州2024四方案逐时链及生命周期结果。
- `results/phase2b_cost_fix/fixed_configuration_9_groups.json`：3个城市×3个缓存天气年份的固定配置汇总。
- `results/phase2b_cost_fix/legacy_agent_task_records.json`：基线 Agent 记录副本；旧目录 `results/phase2b_wind/` 保留不改。

广州2024默认配置的物理轨迹未因费用修复改变；新经济字段把 S0 的绝对净现金流现值显示为 `-8258.47` 元，并把 S1/S2/S3 相对 S0 的增量分别保留为约 `-1858.78/-88747.94/-91335.63` 元。当前假设下四个非零候选均有完整报价且约束可行，因此推荐仍为 S0；这只是给定情景中的有限比较，不是工程审批或全局最优。
