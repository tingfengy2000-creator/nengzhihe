# 阶段二B：5090 碳指标与 v3 回放交接

本交接对应分支 `fix/5090-carbon-metrics`。本轮只增加后端碳排放计算、年度粗算对照、碳因子只读接口和 v3 回放；未修改 `operation_planning/ui/**`，旧回放文件保留。

## 本轮新增能力

- `operation_planning/carbon.py` 读取版本化官方因子，并按广州、北京、哈尔滨默认选择最新省级“电力平均”因子。请求可显式传 `factor_id`，未知 ID 拒绝；碳价必须是非负有限数。
- `run_pv_planning`、`run_hybrid_planning` 以及 PV/Hybrid Agent 的真实确定性计算路径接受可选 `carbon` 参数。数值仍由 Python 工具计算，模型只传递受校验任务。
- `GET /api/operation/carbon/factors` 返回只读因子目录。
- 每个候选有 `carbon` 和 `annual_offset_estimate`；报告顶层有 `carbon_context`。年度粗算只用于并排解释，不参与推荐。

## 因子来源与默认口径

2023 年排放因子来自生态环境部、国家统计局《公告 2025 年第 47 号》及其附件《2023 年电力二氧化碳排放因子》：

- 全国电力平均：`0.5306 kgCO2/kWh`；南方区域：`0.4042`；广东省级：`0.4419`。广东值取附件表 3，答记者问页面只说明趋势，不代替附件数值。
- 同一附件还保留全国“不含市场化交易非化石能源”`0.6096`和全国化石能源电力`0.8273`，作为可选对照。
- 2022 年档案保留全国 `0.5366`、南方 `0.3869`、广东 `0.4403`、北京 `0.5580`、黑龙江 `0.5368`，来源为《公告 2024 年第 33 号》。

原文和附件链接写在 `operation_planning/data/carbon/emission_factors.json` 每条记录中：

- [2023 年公告](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/t20251231_1139517.html)；[2023 年附件 PDF](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/W020251231726284332528.pdf)
- [2022 年公告及附件](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202412/t20241226_1099413.html)

碳价演示使用 `97.49 元/吨`，这是生态环境部《全国碳市场发展报告（2025）》记载的 2024 年年底全国碳市场综合价格收盘价。它只是公开参考情景，不表示本项目可成交，也不证明 CCER 或地方碳普惠资格。报告链接：[全国碳市场发展报告（2025）](https://www.mee.gov.cn/ywgz/ydqhbh/wsqtkz/202509/W020250927515316322073.pdf)。

## 计算口径

对候选方案，令 `f` 为所选电网平均因子，`I0` 为同一负荷、无本地发电时的购电量，`I_s` 为方案购电量，`U_s` 为当时实际自用电量：

```text
grid_emissions_year1 = I_s × f
avoided_year1 = (I0 - I_s) × f = U_s × f
avoided_study_period = Σ_year((I0 - I_s,year) × f) / 1000
```

每年使用固定负荷重新匹配，光伏只按既有衰减模型更新发电；弃电不进入自用减碳，外送电量和 `export_avoided_kgco2_year1` 单列。碳收益总额为累计减碳吨数乘用户情景碳价；现值字段按费用相同的年末折现率折现。碳收益不改变原经济推荐。

`cost_per_tco2_cny = -incremental_npv_vs_s0_cny / avoided_tco2_study_period`。缺报价或减碳为零时返回 `null` 并给状态，不把未计价候选说成最优。

`annual_offset_estimate` 使用 `min(年发电量, 年空调用电)` 的常见年度抵扣算法，明确忽略逐时供需时序，仅作对照。主演示中它把光伏、风机的年发电都看成可抵扣，正是页面要揭示的粗算偏差。

## v3 主演示关键数字

主演示为广州 2024、1 间、每间 6 台的容量充足模型参考，年空调用电 `595.376387 kWh`，服务状态 `within_modeled_scope`，仍明确是未校准、仅制冷的情景，不是采购建议。

所用因子为广东 2023 `0.4419 kgCO2/kWh`。主演示 `S3_pv_wind`（2 kWp + 1 台风机）逐时自用 `485.779016 kWh`，与 5060 看到的约 486 kWh 一致；第 1 年避免排放 `214.665747 kgCO2`，10 年累计 `2.138088 tCO2`，每吨减碳多花 `44121.96880175 元/tCO2`（费用完整的用户情景）。同一候选的年度粗算把 `263.096826 kgCO2` 作为第 1 年避免排放，仅用于对照，不参与推荐。

同一主演示同时带两组碳价：无碳价（所有收益字段为 `null`）和 `97.49 元/吨`参考情景。参考情景下 `S3` 的未折现研究期碳收益为 `208.442211 元`；资格字段固定为 `unverified`。

## 旧回放费用差异说明

`a4d4bd1` 旧回放的加装方案没有把资产残值写入回放脚本，等价于残值比例 `0%`；`bc90c8a` 房间口径回放恢复了现有报价中的 `5%` 残值。电量轨迹相同，差异因此只来自残值：

```text
S1 PV：7400 × 5% = 370 元
S2 风电：82000 × 5% = 4100 元
S3 风光：370 + 4100 = 4470 元
```

v3 以完整报价中的 `pv.residual_fraction=0.05`、`wind.residual_fraction=0.05` 为准，并在每个 case 的 `input` 保存该假设。

## 回放、测试和复现

- viewer 文件：`docs/handoff/replay_viewer/replay_cases_v3.json`
- 原件：`operation_planning/results/phase2b_carbon_5090/replay_cases_v3.json`
- 运行清单：`operation_planning/results/phase2b_carbon_5090/run_manifest.json`
- API 因子探针：`operation_planning/results/phase2b_carbon_5090/api_probe.json`
- 生成命令：`python scripts/phase2b_carbon_replay_5090.py`
- API 探针：`python scripts/phase2b_carbon_api_probe_5090.py`
- 单元契约：`python -m unittest -v tests.test_phase2b_carbon`

测试覆盖：S0 减碳为零、避免排放等于自用电乘因子、外送不并入自用减碳、年度粗算不超过年度负荷、缺报价仍保留物理碳量但费用类字段为 `null`、广东因子附件来源、只读因子目录和未知因子拒绝。已有阶段二A/B回归测试继续保留。

## 边界

这些数字是历史天气和未校准空调负荷下的电网平均因子情景估算；不包含设备制造、运输、回收隐含排放，不等于经核证减排量，不证明现场节能、实际碳交易收益或人工提效。不同房间独立朝向、设备、时段和现场电表仍未建模。
