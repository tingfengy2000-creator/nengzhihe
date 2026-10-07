# 5090 任务：碳指标、对照案例、储能上限 + 回放数据补齐（前端重构前置）

- 发起：5060（2026-10-07），用户已确认网站方向（品牌暂定“能见度”，定位“低碳改造决策助手”）。
- 前端重构要等本任务完成、5060 审查通过后才开工。
- 起点：`feat/5060-product-ui` 最新提交（本文件所在提交；已合并 `fix/5090-room-contract-replay@5b955c0`，代码与 `a0f1f2f` 相同，之后只增加了本文件）。
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
- `claimed_avoided_kgco2 = covered_kwh × 因子`；`claimed_bill_saving_cny_year1 = covered_kwh × 电价`（分时电价时用 S0 年电费 / 年用电 的平均电价，并写明）；
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
2. 按“不划算”主案例（1×6 小办公室）、新源码重新生成 3 个状态变体：预算不足（让风机和组合被排除）、缺光伏报价、屋顶面积不足；每个变体带完整 `input`、`total_cost_npv_cny` 和逐时数据。
3. `input` 记录完整报价假设（光伏各项单价、风机各项费用、运维、残值、替换）、`hub_height_m`、`hellman_exponent`、排放因子 ID、碳价情景。
4. 每个 `chart` 写明 `scenario_id`（5060 从数据核对过，现主演示的逐时自用总量 486 kWh 与“光伏+小风机”一致，请确认）。
5. 碳价情景：主演示给两组——`null`（不计碳收益）和一个参考价。参考价请你们选一个有公开来源的数值并写进 `carbon_price_note`（例如广东碳普惠核证减排量某次公开成交价，或全国碳市场某期均价），注明日期和链接，标为“情景，不代表可成交”。5060 看到一条公开报道：2026-08-19 一笔广东碳普惠核证减排量以 40.51 元/吨成交（https://m.sfccn.com/2026/8-19/zNMDE1MzNfMjIxMzkzNA.html），仅供参考，是否采用由你们判断。

## 6. 之前未答复的问题（请在同一轮回答）

1. 同一场景（1 间 × 1 台，年用电 1251.284 kWh）新回放（`bc90c8a`）比旧回放（`a4d4bd1`）的加装方案总花费分别高 370.00 / 4100.00 / 4470.00 元，只用电网相同，发电和购电相同。请说明是哪项假设变化，v3 回放以哪个口径为准。
2. 上面第 5 节 3、4 条（报价、轮毂高度、`scenario_id`）。

## 6.5 数据体积

`replay_cases_v3.json` 预计有 8 个案例，每个带 8784 小时序列。逐时字段只保留页面需要的 7 列（`timestamps`、`load_kwh`、`pv_generation_kwh`、`wind_generation_kwh`、`self_use_kwh`、`grid_import_kwh`、`curtailment_kwh`，外送案例再加 `grid_export_kwh`），数值保留 4 位小数；完整精度留在结果目录原件中。

## 7. 验证与回交

- 单元测试：守恒（`avoided = self_use × 因子`）、S0 减碳为 0、储能 B=0 时 `recovered=0` 且结果与无储能一致、储能逐时能量守恒（充入×√η ≥ 电量变化，放出 ≤ 电量×√η）、`unknown` 方案费用类碳字段为 `null`、碳价为空时碳收益为 `null`、外送不并入自用减碳、粗算 `covered_kwh ≤ 年用电`。
- 完整年回放：广州 2024 主演示与三间案例；给出主演示各方案的 `avoided_tco2_study_period`、`cost_per_tco2_cny`、粗算对照，写在交接说明里。
- 交接说明：`operation_planning/protocol/phase2b_carbon_handoff_5090.md`，列出字段表、公式、因子来源、边界、命令、SHA。
- 回复 5060：分支、提交 SHA、新回放文件路径、主演示关键数字、仍未解决的问题。

## 8. 新增一对对照案例：同一地方，一个不划算、一个划算（用户 2026-10-07 决定）

用户认为 35㎡ 小办公室规模太小。决定保留它作为“不划算”案例，再在**同一个广州 2024 天气**下找一个规模更大、模型能正确覆盖的“划算”案例，证明工具不是固定说“不装”。

约束：
- 模型只计算空调负荷，不做工厂生产负荷（没有可公开的真实工厂数据，硬做会失真）。候选对象限于“一整栋由同类房间组成的公共建筑”，例如教学楼、办公楼、图书馆、门诊楼。
- 可调整的情景变量（请列出你们实际试过的组合）：同类房间数（如 20–80 间）、是否全周使用（`weekdays_only=false`，对应每天开放的建筑）、使用时段、光伏容量（按屋顶面积上限）、电价、是否装风机。
- **屋顶面积必须与楼的规模自洽**：多层楼的可装光伏屋顶面积 ≈ 单层占地，不是“房间数 × 房间面积”。请写明假设的层数、每层房间数和屋顶面积，光伏容量受 `roof_area_m2 × usable_fraction` 上限约束。
- **电价注意**：现有 `tariffs.py` 里的广东档案是“粤北山区（河源等）工商业单一制 2026-07”，**不适用于广州**；而且档案有效期是 2026 年 7 月，套到 2024 年全年天气上会被 `validate_profile` 拒绝（这是正确行为，不要绕过）。可选做法：(a) 继续用恒定电价情景（如 0.66 元/kWh，或另取一个注明来源的广州工商业平均电价情景值）；(b) 新增“广东珠三角五市工商业”官方代理购电电价档案，并说明用它评价 2024 天气的口径（例如作为“现行电价情景”显式声明）。无论哪种，都要在 `input` 和交接说明里写清楚。
- **不允许为了得到“划算”去改报价。** 光伏和风机单价保持现有用户情景口径；若认为大容量系统单价应更低，必须引用公开来源并单独作为一组敏感性结果，不能混进主结论。
- 如果在合理范围内找不到“加装光伏比只用电网省钱”的组合，就如实报告搜索范围和最接近的结果，不要编造。

输出：
1. 搜索记录：每组条件的 S0–S3 总花费、增量现值、自用率、浪费比例（放在结果目录，供答辩追问）。
2. 选一个代表性的“划算”案例写入 `replay_cases_v3.json`，`case_id` 建议 `primary_worth_it`，`demo_role` 标 `primary_worth_it`；原 1×6 小办公室标 `primary_not_worth_it`。两者都带完整逐时数据、碳字段、粗算对照和第 9 节储能上限。
3. 交接说明写清两者差在哪里（用电规模、周末是否用电、电价等），这是页面讲“为什么一个划算一个不划算”的依据。
4. 边界：只计空调用电。真实建筑里照明、插座等负荷也会用掉光伏发电，所以这里的自用率偏保守；页面会注明。

## 9. 储能只算“理想上限”（不作为第五种方案）

用户决定先不做完整储能方案，只回答“加一块电池最多能把多少浪费的电挪到空调用电时段”。请在逐时匹配结果上做一个简单的理想调度：

- 电池只用“当时没人用的发电”（curtailment）充电，不从电网充电；有空调用电且发电不足时放电；
- 参数（用户情景，写进 `input`）：容量 B ∈ {0, 5, 10, 20, 50} kWh（整栋楼案例可按规模放大，如 {0, 50, 100, 200, 500}），充、放电功率上限各为 B/2 kW，往返效率 0.90（充、放各取 √0.90），初始电量 0，SOC 0–100%，按时间顺序逐小时贪心调度（先满足当时空调用电，剩余发电充电，发电不足时放电）；
- 只在 `allow_export=false` 的案例上计算（外送时多余电量的去向与储能竞争，本轮不处理）；
- 输出 `candidates[i].storage_upper_bound`（只对有发电的方案）：每个 B 的 `recovered_kwh_year1`（电池实际放给空调的电量，已扣损耗）、`charged_kwh_year1`、`remaining_curtailment_kwh_year1`、`grid_import_kwh_year1`、`additional_avoided_kgco2_year1`；
- 明确标注：`"ideal dispatch upper bound; excludes battery cost, degradation and replacement; not a storage recommendation"`。不计电池投资，所以不给储能的 10 年总账和推荐。

预期并欢迎如实呈现的结论：小办公室周末和冬季不开空调，加电池也挪不过去多少；全周使用的整栋楼可能挽回更多。

5060 会在前端把它做成“加一块电池能挽回多少”的滑块或分档展示，并注明不含电池成本。

5060 收到后先审查字段和数字，再把 `replay_cases_v3.json` 加入只读白名单，然后才交给 claude.ai/code cloud 做前端重构。
