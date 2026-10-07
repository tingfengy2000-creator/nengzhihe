# 5090 任务：碳排放与碳收益指标 + 回放数据补齐（前端重构前置）

- 发起：5060（2026-10-07），用户已确认网站方向（品牌暂定“能见度”，定位“低碳改造决策助手”）。
- 前端重构要等本任务完成、5060 审查通过后才开工。
- 起点：`feat/5060-product-ui` @ `a0f1f2f`（已合并 `fix/5090-room-contract-replay@5b955c0`）。
- 请新建分支 `fix/5090-carbon-metrics`，普通推送；不改 `main`，不建 PR/Release，不改前端 `operation_planning/ui/**`。

## 0. 原则

1. 所有碳指标都在后端用 Python 计算，写进 report 和回放 JSON；前端只读取显示，不做任何乘法。
2. 每个数字可追溯：排放因子要有官方文件标题、发布单位、数据年份、公告号和链接；用户情景参数（碳价）要写明是情景。
3. 不夸大：
   - 这是基于电网平均排放因子的情景估算，不是经核证的减排量；
   - 不包含光伏、风机制造、运输、回收的隐含排放；
   - 碳收益只是“如果按某个价格出售”的情景值。2 kWp 量级的小项目能否进入 CCER 或地方碳普惠，取决于方法学和备案，**本作品未核实**，页面会这样写。
4. 只有“当时用上”的自发电才替代了电网电；浪费的电不计减碳。卖给电网的电（`allow_export=true` 时）单独列出，不并入自用减碳。

## 1. 排放因子配置（新增数据文件）

新增 `operation_planning/data/carbon/emission_factors.json`，每条包含：`factor_id`、`value_kgco2_per_kwh`、`data_year`、`scope`（全国/区域/省）、`region`、`basis`（如“电力平均”“不含市场化非化石”“化石能源电力”）、`source_title`、`issuer`、`notice_no`、`published`、`url`、`retrieved`。

5060 已查到的官方数值（请逐条打开原文核对后再写入，不要只抄这里）：

| 数据年份 | 口径 | 数值 kgCO₂/kWh | 来源 |
| --- | --- | --- | --- |
| 2023 | 全国电力平均 | 0.5306 | 生态环境部、国家统计局《关于发布2023年电力二氧化碳排放因子的公告》，生态环境部 2026-01-05 答记者问：https://www.mee.gov.cn/ywdt/zbft/202601/t20260105_1139911.shtml |
| 2023 | 全国电力平均（不含市场化交易非化石能源电量） | 0.6096 | 同上 |
| 2023 | 全国化石能源电力 | 0.8273 | 同上 |
| 2023 | 南方区域电力平均 | 0.4042 | 同上 |
| 2023 | 广东省电力平均 | **待核对**（答记者问未列数值，请从公告附件取） | 同上公告附件 |
| 2022 | 全国电力平均 | 0.5366 | 生态环境部、国家统计局公告 2024 年第 33 号（2024-12-20）：https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202412/t20241226_1099413.html |
| 2022 | 广东省电力平均 | 0.4403 | 同上 |
| 2022 | 南方区域电力平均 | 0.3869 | 同上 |

默认因子：项目所在省份最新年份的“电力平均”因子（广州 → 广东 2023，若附件取不到则用 2022 并注明）。同时在 report 里给出“全国 2023”作为对照，方便答辩时说明口径差异。北京、哈尔滨按同样规则取各自省级值。

## 2. 每个方案新增的碳字段

在 hybrid（以及 PV，如方便）report 的 `candidates[i]` 下新增 `carbon` 对象；在 report 顶层新增 `carbon_context`。按你们现有生命周期逻辑逐年计算（含光伏衰减，口径与费用一致），并同时给出第 1 年值。

`carbon_context`：
- `factor`：所用因子完整记录（第 1 节字段）；`comparison_factor`：全国 2023 对照因子；
- `carbon_price_cny_per_t`：碳价情景值（来自请求，默认 `null`）及 `carbon_price_note`；
- `scope_notes`：上面第 0 节 3、4 条的固定说明。

`candidates[i].carbon`：

| 字段 | 定义 |
| --- | --- |
| `grid_emissions_kgco2_year1` | 第 1 年从电网购电 × 因子（S0 即空调全年用电对应排放） |
| `avoided_kgco2_year1` | (S0 购电 − 本方案购电) × 因子（应等于自用电量 × 因子，请做守恒检查） |
| `avoided_tco2_study_period` | 研究期内累计减碳（逐年，含衰减） |
| `curtailed_kwh_year1`、`curtailed_share` | 浪费电量及占发电比例（直接来自匹配结果，方便页面讲“浪费不减碳”） |
| `exported_kwh_year1`、`export_avoided_kgco2_year1` | 外送电量及按同一因子估算的外送替代量，单独列示，不并入 `avoided_*` |
| `cost_per_tco2_cny` | `-incremental_npv_vs_s0_cny / avoided_tco2_study_period`：每减一吨 CO₂ 比只用电网多花（正数）或省下（负数）的钱；减碳为 0 或费用不完整时为 `null`，并给 `cost_per_tco2_status` |
| `carbon_revenue_cny_study_period` | 若给了碳价：`avoided_tco2_study_period × 碳价`（是否折现请与费用口径一致并写明）；否则 `null` |
| `incremental_npv_with_carbon_cny` | 若给了碳价：`incremental_npv_vs_s0_cny + 碳收益现值`；用于回答“算上碳收益是否划算” |
| `eligibility` | 固定写 `"unverified"`，附说明：小规模项目参与 CCER/碳普惠需符合方法学与备案，未核实 |

`unknown`（缺报价）方案：碳物理量照算，`cost_per_tco2_cny` 和 `incremental_npv_with_carbon_cny` 为 `null`。`excluded` 方案照算并保留排除原因。

## 3. “年度粗算”对照（创新点页面要用）

为每个方案再算一组常见的“年度抵扣”粗算结果，放在 `candidates[i].annual_offset_estimate`：

- `covered_kwh = min(年发电量, 年空调用电)`；`claimed_coverage_rate = covered_kwh / 年用电`；
- `claimed_avoided_kgco2 = covered_kwh × 因子`；`claimed_bill_saving_cny_year1 = covered_kwh × 电价`；
- 用与正式结果相同的研究期、折现和设备费用，算 `claimed_incremental_npv_vs_s0_cny`；
- `method = "annual net offset; ignores hourly timing; for comparison only"`。

页面会把它与逐小时结果并排，说明粗算会把“浪费的电”也算成省钱和减碳。粗算只用于对照，不参与推荐。

## 4. API

- `POST /api/operation/hybrid/run`（以及 PV）请求可选：`carbon: { factor_id?: string, carbon_price_cny_per_t?: number }`；未知 `factor_id` 拒绝；碳价必须为非负有限数。
- `GET /api/operation/carbon/factors` 返回因子列表（只读）。
- 自然语言修改 schema 暂不加入碳价（避免 Agent 编造价格），如要加请单独说明。

## 5. 回放数据（前端唯一的数据源，请一并完成）

生成新文件 `docs/handoff/replay_viewer/replay_cases_v3.json`（不要覆盖已有回放字节），结果原件放 `operation_planning/results/phase2b_carbon_5090/`，附 `run_manifest.json`（源码 SHA、环境、哈希）。要求：

1. 包含现有 4 个房间口径案例（主演示 1×6、三间 3×6、对照 1×1、口径对照 1×2），全部带第 2、3 节新字段和 `carbon_context`。
2. 按主演示 1×6 场景、新源码重新生成 3 个状态变体：预算不足（让风机和组合被排除）、缺光伏报价、屋顶面积不足；每个变体带完整 `input`、`total_cost_npv_cny` 和逐时数据。
3. `input` 记录完整报价假设（光伏各项单价、风机各项费用、运维、残值、替换）、`hub_height_m`、`hellman_exponent`、排放因子 ID、碳价情景。
4. 每个 `chart` 写明 `scenario_id`（5060 从数据核对过，现主演示的逐时自用总量 486 kWh 与“光伏+小风机”一致，请确认）。
5. 碳价情景：主演示给两组——`null`（不计碳收益）和一个参考价。参考价请你们选一个有公开来源的数值并写进 `carbon_price_note`（例如广东碳普惠核证减排量某次公开成交价，或全国碳市场某期均价），注明日期和链接，标为“情景，不代表可成交”。5060 看到一条公开报道：2026-08-19 一笔广东碳普惠核证减排量以 40.51 元/吨成交（https://m.sfccn.com/2026/8-19/zNMDE1MzNfMjIxMzkzNA.html），仅供参考，是否采用由你们判断。

## 6. 之前未答复的问题（请在同一轮回答）

1. 同一场景（1 间 × 1 台，年用电 1251.284 kWh）新回放（`bc90c8a`）比旧回放（`a4d4bd1`）的加装方案总花费分别高 370.00 / 4100.00 / 4470.00 元，只用电网相同，发电和购电相同。请说明是哪项假设变化，v3 回放以哪个口径为准。
2. 上面第 5 节 3、4 条（报价、轮毂高度、`scenario_id`）。

## 7. 验证与回交

- 单元测试：守恒（`avoided = self_use × 因子`）、S0 减碳为 0、`unknown` 方案费用类碳字段为 `null`、碳价为空时碳收益为 `null`、外送不并入自用减碳、粗算 `covered_kwh ≤ 年用电`。
- 完整年回放：广州 2024 主演示与三间案例；给出主演示各方案的 `avoided_tco2_study_period`、`cost_per_tco2_cny`、粗算对照，写在交接说明里。
- 交接说明：`operation_planning/protocol/phase2b_carbon_handoff_5090.md`，列出字段表、公式、因子来源、边界、命令、SHA。
- 回复 5060：分支、提交 SHA、新回放文件路径、主演示关键数字、仍未解决的问题。

5060 收到后先审查字段和数字，再把 `replay_cases_v3.json` 加入只读白名单，然后才交给 claude.ai/code cloud 做前端重构。
