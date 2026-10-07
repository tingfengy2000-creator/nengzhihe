# 阶段二B：5090 碳指标、同地对照与储能理想上限交接

本交接对应分支 `fix/5090-carbon-metrics`。完整回放由源码提交 `ed3f17d23121a4f97b1bdbff577d6c769ff9506d` 运行生成；当前交接分支还包含 `feat/5060-product-ui@6d976fa` 的任务要求合并提交。未修改 `operation_planning/ui/**`、`main` 或“乡艺有据”。

## 本轮新增能力

- 后端按省级电网平均排放因子计算每个候选的第1年电网排放、实际自用减碳、研究期累计减碳、减碳成本、年度粗算对照和可选碳价情景；所有数值来自 `carbon.py` 和确定性工具。
- `run_pv_planning`、`run_hybrid_planning`、API 和 Agent 现在都可以带可选 `storage` 参数。储能只生成理想调度上限，不进入经济推荐。
- `candidates[i].storage_upper_bound` 只对有发电候选写入；B=0 与无储能匹配相同，外送场景返回 `not_applicable`。
- v3 有8个完整年案例。结果原件保留完整精度和完整图表字段；viewer只保留 `timestamps`、`load_kwh`、`pv_generation_kwh`、`wind_generation_kwh`、`self_use_kwh`、`grid_import_kwh`、`curtailment_kwh` 七个逐时字段，数值四舍五入4位。

## 因子与碳价口径

广州默认使用广东省2023年电力平均因子 `0.4419 kgCO2/kWh`，数值来自生态环境部、国家统计局《公告2025年第47号》附件表3；公告正文确认该公告发布全国、区域和省级电力平均因子。2022年因子档案也保留用于历史对照。官方来源已写入 `operation_planning/data/carbon/emission_factors.json`：

- [2023年公告](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/t20251231_1139517.html)
- [2023年电力二氧化碳排放因子附件](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/W020251231726284332528.pdf)
- [2022年公告及附件](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202412/t20241226_1099413.html)

演示参考碳价为 `97.49 元/吨`，取生态环境部《全国碳市场发展报告（2025）》中2024年年底全国碳市场综合价格收盘价，写明为公开参考情景，不代表项目可成交，也不证明CCER或地方碳普惠资格。碳收益不改变原费用推荐。

## 第8节：同一地点的“不划算／划算”对照

两个主案例均使用广州2024同一份天气数据、同一组光伏/风机报价和无外送规则；差别只在项目规模、屋顶、容量和电价情景。模型只计算空调用电，未虚构工厂生产负荷。

- `primary_not_worth_it`：35㎡、1间、每间6台、单层1间，屋顶输入35㎡（可用比例0.8），2 kWp + 1台风机，恒价0.66元/kWh，10年，年空调用电 `595.376387 kWh`，服务状态 `within_modeled_scope`。S0总成本 `3929.484157元`；S1仅光伏 `8458.667059元`，相对S0增量NPV `-4529.182902元`；S3风光 `98266.141414元`，增量NPV `-94336.657257元`。S3逐时自用 `485.779016 kWh`、发电 `3123.983832 kWh`、弃电 `2638.204816 kWh`，自用率约15.55%，所以在这个小负荷、0.66元/kWh情景下不推荐加装。
- `primary_worth_it`：同一广州2024天气，4层、每层10间、共40间同类35㎡房间；屋顶按单层占地 `10×35=350㎡`，楼层不乘屋顶，2 kWp候选扩大为20 kWp，1台风机，屋顶可用约56 kWp，预算300000元。电价为明确的用户恒价敏感性情景 `1.20元/kWh`，不是广州2024官方电价。年空调用电 `23815.055498 kWh`，服务状态仍为 `within_modeled_scope`。S0总成本 `285780.665978元`；S1仅光伏总成本 `263528.465640元`，相对S0增量NPV `+22252.200337元`，年1自用 `8385.094280 kWh`、发电 `22139.867101 kWh`、弃电 `13754.772820 kWh`，自用率 `37.8733%`、弃电率 `62.1267%`，因此在该明确电价敏感性下推荐S1；S3风光总成本 `351682.154072元`、增量NPV `-65901.488095元`，说明“光伏划算”不等于风光组合必然划算。

搜索审计在 `run_manifest.json` 和结果原件的 `search_audit` 中。记录的考虑范围为同地点同天气的20/40/80间、2/10/20/40 kWp、0.66/1.20元/kWh、10年；这是有限候选范围，不是穷举证明。选中案例保存了完整S0–S3总成本、增量NPV、自用率和弃电率。0.66元/kWh下的整栋楼探索仍未形成正增量主案例，因此没有把高电价敏感性包装成广州官方事实。

这两个案例只覆盖空调负荷；真实公共建筑的照明、插座等负荷可能进一步提高光伏自用率，本回放没有把它们补造进去。

## 第9节：储能理想上限

算法按小时顺序运行：先用发电满足当时空调负荷，再用原本弃电充电，发电不足时放电；初始SOC为0，容量边界0–100%，充放功率上限均为B/2 kW，充放效率各为 `sqrt(0.90)`。只在 `allow_export=false` 情景计算，不计电池费用、衰减、替换或推荐。

固定标识为：`ideal dispatch upper bound; excludes battery cost, degradation and replacement; not a storage recommendation`。

- 小案例容量 `{0,5,10,20,50} kWh`。S3在B=0时恢复0 kWh、仍购电 `109.597371 kWh`；B=50时恢复 `109.597371 kWh`、年1额外避免 `48.431078 kgCO2`，仍有 `2463.725330 kWh`弃电。
- 整栋楼容量 `{0,50,100,200,500} kWh`。S1在B=0时恢复0 kWh、仍购电 `15429.961217 kWh`；B=500时恢复 `4852.428800 kWh`、年1额外避免 `2144.288287 kgCO2`，仍有 `7836.138988 kWh`弃电。

B=0和守恒测试见 `tests/test_phase2b_storage.py`；储能上限是物理挪移的上界，不能解读为电池投资回报或第五种方案。

## v3文件与哈希

- viewer：`docs/handoff/replay_viewer/replay_cases_v3.json`；文件 SHA-256 `80a4fc2773d38a68be31a3240f10574641a6d217d3ff8f80a067d0780436d8cc`，规范化对象哈希 `9a718d6c0e1109dfec8db3b3b19dcb1a0d943412f75b35b06d84a9c11382e9b8`
- 完整结果原件：`operation_planning/results/phase2b_carbon_5090/replay_cases_v3.json`；文件 SHA-256 `2615b330ee823925148287c3266235966fe6380118477120a341e7445d792096`，规范化对象哈希 `3621f06fcb06eaa824ad45162471b4160518baa5bb393e9e1a49a1af01ff83f8`
- 运行清单：`operation_planning/results/phase2b_carbon_5090/run_manifest.json`
- 旧七案例碳回放字节备份：`operation_planning/results/phase2b_carbon_5090/replay_cases_v3_carbon_only_7cases.json`
- API因子探针：`operation_planning/results/phase2b_carbon_5090/api_probe.json`

生成命令：

```powershell
python scripts/phase2b_carbon_replay_5090.py
python scripts/phase2b_carbon_api_probe_5090.py
```

本轮实际环境记录在 `run_manifest.json`：5090、Python 3.14.7、pvlib 0.11.2、pandas 3.0.6；天气和报价仍由现有版本化输入提供。完整回放执行源提交为 `ed3f17d23121a4f97b1bdbff577d6c769ff9506d`。

## 验证

已运行：

```powershell
python -m unittest -v tests.test_phase2b_storage tests.test_phase2b_carbon tests.test_project_load_adapter tests.test_aircost_handoff
python tests/test_phase2_pv.py
python tests/test_phase2a_correctness.py
python tests/test_phase2b_wind.py
python -m compileall -q operation_planning scripts
```

储能测试覆盖B=0结果一致、B=5短序列守恒、无外送适用条件；既有碳守恒、未知报价、外送分离、房间聚合、寿命、电价和阶段二A/B回归继续通过。

## 仍未解决的边界

- 第一阶段空调轨迹仍是未校准的城市级冷却情景，非实测楼宇全年负荷；本轮没有加入照明、插座、真实物业账单或现场屋顶核验。
- `primary_worth_it`的1.20元/kWh只是用户敏感性电价；广州2024官方分时档案尚未接入，不能写成当地实际电价下的收益。
- 风机仍使用既有公开曲线和参考密度模式，未加入当地温度/气压修正；风光方案结果不代表工程审批或采购报价。
- 储能只给理想调度上限，没有电池成本、寿命、功率电子约束或经济推荐。
- 碳排放是电网平均因子情景估算，不是经核证减排量，不包含设备制造、运输和回收隐含排放；碳价收益也未核实可交易资格。
- 逐时模型不代表分钟级波动；不同房间朝向、时段和设备差异未建模。

## 第10节复核与 v4 交付（5090，2026-10-07）

本节是对 v3 的补充；v3 文件和其字节哈希保持不变。v4 将广州官方档案作为主价，0.66 和 1.20 元/kWh 只作敏感性，不把敏感性结果写成广州2024实际账单。

### 10.1 v3 费用差异、碳价与推荐曲线

同一“1间×1台、年用电约1251.284 kWh”的费用差异 `370 / 4100 / 4470 元`可由研究期末残值口径解释：2 kWp 光伏固定资产报价为 `2×(1800+600+500+800)=7400元`，5%残值为 `370元`；1台风机固定资产报价为 `45000+15000+10000+12000=82000元`，5%残值为 `4100元`；风光组合为两者合计 `4470元`。末年残值在总成本现值中抵减，因此声明5%残值的口径比声明0%残值低上述金额。检查 `a4d4bd1` 的结果、当前 v3 输入和 `bc90c8a` 的已保存结果后，当前可追溯的 v3 / `a4d4bd1` 数字为 `S1=10117.250124`、`S2=97006.411262`、`S3=99594.101833`，并使用 `pv_quote.residual_fraction=0.05`、`wind_quote.residual_fraction=0.05`。这些是用户情景报价假设，不是已核实采购或残值合同；若某副本高出上述差额，它使用的是相同报价但0%残值（或漏记末年残值），不能与5%口径混报。

每个 v4 案例带 `carbon_price_scenarios`：`null` 不计碳收益，以及生态环境部《全国碳市场发展报告（2025）》记录的 `97.49元/吨`参考情景。碳收益不改变原费用推荐，资格字段仍是 `unverified`。每案同时保存 `chart`（固定S3）和 `chart_recommended`（由主价推荐的实际 scenario_id）；推荐为S0时曲线是零发电基线，不播放S3结论。

### 10.2 官方广州主价与三档结果

主价档案为 `guangzhou_industrial_lt1kv_202110`：广州市发展改革委公开的粤发改价格〔2021〕331号附件，广州、珠海、佛山、中山、东莞五市一般工商业不满1kV，平67.25分、谷25.56分、峰114.33分/kWh，7–9月11–12和15–17尖峰按25%上浮并按表格精度记录。来源为 [广州市居民用水用电价格政策汇编](https://fgw.gz.gov.cn/ztzl/gzsfzggwzdlyxxgkzl/ys/content/post_9497778.html)；档案有效期仍严格登记为2021-10-01至2021-12-31，v4 输入显式使用 `tariff_application=current_tariff_on_reference_weather`，含义是将已公布档案作为参考天气的现行结构情景，不是2024实际账单。默认日期校验仍严格执行。

三档主价完整结果（10年、无外送、现有用户情景报价）如下；恒价0.66/1.20和碳价参考结果均在每案内保存：

| case | 建模范围与年空调用电 | 主价推荐 | S1光伏增量NPV | S1自用率 | S1弃电 |
|---|---|---:|---:|---:|---:|
| `tier_small` | 35㎡、1间×6，`595.376 kWh` | S0 | `-2929.152 元` | `21.3257%` | `1741.838 kWh` |
| `tier_medium` | 4层×10间、40间×6，`23815.055 kWh` | S1 | `+4402.638 元` | `37.8733%` | `13754.773 kWh` |
| `tier_large` | 1层、100个35㎡空调分区、`59537.639 kWh` | S0 | `-16582.745 元` | `33.7608%` | `73326.397 kWh` |

大档在计算前先作适用性判断：可作为当前“同类房间冷却轨迹×分区数”的有界代理，因此保留为 `bounded_proxy_feasible`；不能解释为全厂能源方案。当前模型不含生产设备、工艺、照明、插座和真实厂房VRF/冷水机组，替代标识为 `tier_large_conditioned_zones`。在1.20元/kWh恒价敏感性下，大档的S1为敏感性推荐；这不改变官方主价下S0的结论。

v4 同时保留 `primary_not_worth_it`、`primary_worth_it`、三间/单台/双台房间口径和三个 v3 状态变体，共11案；状态变体中的硬约束、缺报价和 `chart_recommended` 均从主价重新计算。敏感性只重算同一匹配轨迹的经济层，避免将重复生成次数当成独立验证。

### v4 文件、运行和哈希

- 完整结果：`operation_planning/results/phase2b_carbon_5090/replay_cases_v4.json`（11案、完整逐时和逐年现金流）
- viewer：`docs/handoff/replay_viewer/replay_cases_v4.json`（S3与推荐曲线，逐时显示字段四舍五入4位）
- 运行清单：`operation_planning/results/phase2b_carbon_5090/run_manifest_v4.json`
- 运行命令：`python scripts/phase2b_carbon_replay_v4_5090.py`
- v4 生成源提交：`bcb3acea1664c48ccea3a64d3edc809f2b114d44`；机器角色5090；11案；主价执行约4分18秒
- 生成后文件 SHA-256：完整结果 `7b24e48f160577d48dc4c8d9e5682fb97398ef04c6cd343cd5cffc30a27cfffd`；viewer `1101b792e2727b7f68475dfe444a8cc2027299ed9ab8d708ba0658b7548f51ea`；manifest `e02687a8f1c1ab5aeabec59f9970b4c30d40a5861beffa6450c0caeeee4451e5`（`run_manifest_v4.json`内含同值与逐案例哈希）

## v4 未解决边界

- 广州主价档案是公开的2021-10价格表作为参考天气情景，不能声称2024实际账单；普通商业用户、需量/容量基本电费、基金附加和市场化交易未建模。
- 第一阶段负荷仍是未校准冷却情景；大档仅能代表厂房内空调分区，不能证明全厂节能、投资回收或现场适配。
- 0.66和1.20是恒价敏感性，不是官方广州事实；屋顶、报价、风机参考密度和碳价资格仍需现场/合同确认。
- 敏感性沿用同一物理轨迹并仅重算经济层，不能称为第二套天气或独立物理验证。

## 第11节 v5 交付（5090，2026-10-07）

v5 接续 `a118a54` 的第11节要求，保留 v3/v4 文件，不展示重复旧案例。正式运行源提交为 `e3cc5fbca983d95d2195f67022642705179381ea`，机器角色 5090，执行命令为：

```powershell
python scripts/phase2b_carbon_replay_v5_5090.py
python -c "import importlib.util; s=importlib.util.spec_from_file_location('v5','tests/test_phase2b_carbon_v5.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.test_v5_tiers_and_no_duplicate_primary_cases(); m.test_v5_capacity_sweep_and_roof_variants(); m.test_v5_selected_capacity_has_full_charts_and_carbon()"
```

### 主电价边界

历史 v5 的主价记录为 `guangzhou_industrial_lt1kv_202610`，当时只保存公开抄录页并标作未核验；该快照保留用于审计。第15节已用南方电网95598公告详情页和仓库中的官方PDF完成核验，当前代码与v8回放以第15节的 `verified=true` 档案为准。价格为谷 `0.32136875`、平 `0.80066875`、峰 `1.34176875`、尖峰 `1.67036875` 元/kWh；2021年广州官方档案和恒价0.66/1.20仍只作敏感性，不是主价。

### 三档主价容量比选

每档在屋顶约束内逐一计算 PV-only S1；容量行保存总成本现值、相对S0增量现值、自用率、弃电率、累计减碳和每吨减碳成本。推荐容量是完整计价、满足约束的候选中 S1 增量 NPV 最高者；若所有非零候选不为正则保留0kWp。固定的风机仍作为S2/S3对照，不把风光组合混入PV容量选择。

| 档位 | 建模年空调用电 | 容量候选（kWp） | 最划算容量 | S1增量NPV（元） | 年1发电/自用/弃电（kWh） | 自用率/弃电率 | 每吨减碳成本（元/t） |
|---|---:|---|---:|---:|---:|---:|---:|
| `tier_small` | 595.376 | 0、1、2、5.6（屋顶上限） | **1** | **+481.465** | 1106.993 / 373.729 / 733.264 | 33.761% / 66.239% | -295.491 |
| `tier_medium` | 23815.055 | 0、5、10、20、40、56（屋顶上限） | **40** | **+19258.586** | 44279.734 / 14949.175 / 29330.559 | 33.761% / 66.239% | -295.491 |
| `tier_large` | 66338.774 | 0、20、50、100、200、320（屋顶上限） | **50** | **+154089.749** | 55349.668 / 30289.578 / 25060.090 | 54.724% / 45.276% | -1173.687 |

这些数值来自正式 v5 结果；负的每吨减碳成本表示在该成本口径下增量NPV为节省，不是碳交易收入。每案仍保留完整四方案、逐时 `chart`（S3）、`chart_recommended`、年度粗算、碳价97.49元/t参考情景、理想储能上限和0.66/1.20恒价敏感性。

### 大档可行性结论

大档现在是受边界限制的“厂房空调区代理”，不是100间办公室，也不是全厂能源模型。参数为：6个空调区，每区250m²、层高6m、20人、设备显热3000W、14台现有分体机参考设备；总空调区1500m²、总84台；屋顶单独输入2000m²，可用比例0.8，PV上限320kWp；全年每天08:00–20:00，`weekdays_only=false`。250m²处于150–300m²车间分区用户情景范围，6m取轻工/装配车间6–8m量级，20人约8人/100m²，3000W为12W/m²轻工设备显热情景；这些不是实测依据。14台/区是当前热湿模型扫描中达到 `within_modeled_scope` 的最小整数台数：容量缺口、温度和湿度缺口均为0。模型仍不含生产工艺、照明、插座、VRF/冷水机组、真实厂房校准和复杂两班制，因此只能写“厂房空调区有界代理”。若要做全厂决策，可信替代是取得生产工艺、照明和实际机组数据后再建“厂区办公楼＋空调装配车间”分区模型。

### 案例去重与状态变体

v5 仅保留 `tier_small`、`tier_medium`、`tier_large` 三个主案例；`primary_not_worth_it` 和 `primary_worth_it` 仅作为 `aliases`。三档之外只保留三个状态变体：预算不足、缺光伏报价、屋顶不足。预算和缺报价变体的屋顶均为35m²，屋顶不足变体为1m²。被省略的旧对照 ID 为 `primary_adequate_three_rooms`、`comparison_undersized_one_unit`、`comparison_two_unit_reference`，它们的历史文件不删除。

### v5 文件与哈希

- 完整结果：`operation_planning/results/phase2b_carbon_5090/replay_cases_v5.json`，文件 SHA-256 `306ece200e54c8768aaa7a87493f1a5e48ff9349bbe1f3793264c7e3e66edd23`
- 评审 viewer：`docs/handoff/replay_viewer/replay_cases_v5.json`，文件 SHA-256 `882be5dbd1214685cc5691aa42497aa3f423ae76807ebe96c508dd0bf5f962ae`
- 运行清单：`operation_planning/results/phase2b_carbon_5090/run_manifest_v5.json`；其中 `source_commit=e3cc5fbca983d95d2195f67022642705179381ea`，`case_count=6`，并记录逐案例哈希
- 规范化结果对象哈希：`5e7d696229b781afb7f67a904071f0a80e3fcd2632f7283fb5bc39bf6f978231`
- 规范化 viewer 对象哈希：`bd4dab48ae7ab83c2b7cf61d1d1a4529b4f6438359f41c92e4820ddecb7bdec4`

### v5 边界

- 2026-10 主价在 v5 时为公开抄录情景；其官方PDF核验已在第15节完成。它仍是套用到参考天气的价格情景，不是2024真实账单。2021官方广州档案和0.66/1.20敏感性仍可追溯。
- 空调负荷是未校准的冷却情景；大档不含厂房生产负荷，不能证明全厂节能、现场投资回收或实际人工提效。
- 屋顶可用面积、承重、消防间距、并网和报价仍需现场/合同确认；容量扫描是有限候选，不是全局优化。
- 风机仍为1台公开曲线参考，未做当地温度/气压修正；碳价情景不代表可成交或减排资格。

## 第12节 v6：用户输入优先与实时接口回放（5090，2026-10-07）

本节接续 `feat/5060-product-ui@b99bf8b` 的接口要求；该要求以文档提交 `65b4533` 纳入本分支。三档只是示例，产品主路径是用户提交城市、年份、房间与台数、时段、屋顶、报价、电价和预算后由后端实时计算。回放脚本同样只通过 HTTP 调用，不直接导入计算函数；v5 及更早结果保留不覆盖。

### 12.1 示例修正

- `tier_small` 为1间35㎡办公房间、6台，广州2024空调年用电 `595.376387 kWh`，容量 `[0,1,2,5.6] kWp`，推荐1 kWp，S1增量NPV `+481.465元`。
- `tier_medium` 不再是小档的简单倍增：采用20个70㎡阅读区、每区8台、全年每天09:00–21:00，4层×5区，空调区总面积1400㎡；屋顶输入350㎡，明确按单层占地而非楼层相乘。年用电 `57721.348058 kWh`，容量 `[0,10,20,40,80] kWp`，80 kWp因屋顶上限排除，推荐40 kWp，S1增量NPV `+104794.508元`。
- `tier_large` 保留6个250㎡、6m高、20人、3kW设备显热、每天08:00–20:00的厂房空调区有界代理，14台/区；年用电 `66338.773814 kWh`，推荐50 kWp，S1增量NPV `+154089.749元`。这仍不是全厂能源模型。
- 三个状态变体的主卡固定1 kWp：缺报价的 S1 为 `unknown/incomplete_quote`；1㎡屋顶的 S1 为 `excluded/not_applicable`；预算变体保留固定容量的实际预算判定。状态卡不会再因容量寻优把主方案替换为0 kWp。

### 12.2 实时接口与契约

接口手册为 `docs/handoff/phase2b_realtime_api_manual_v6.md`，契约测试为 `tests/test_phase2b_api_v6.py`。已实现并在本地通过直接 Python 契约调用：

- `GET /api/operation/options`：城市、缓存年份、型号目录、含 `verified/provisional` 的电价档案、排放因子和单位表。
- `POST /api/operation/thermal/size`（及 `/thermal/compare`、`thermal/run` 的 `compare_units`）：返回1..N台的服务状态、年电量、容量缺口小时和最少达标台数。
- `POST /api/operation/hybrid/run`：接受 `pv.requested_capacities_kwp` 或 `pv.auto_capacity`，容量扫按 S1 增量NPV选择；返回碳字段、年度粗算、储能理想上限、选中容量逐时 `hourly` 和 `calculation_timing.elapsed_ms`。
- `POST /api/operation/hybrid/jobs`（`/submit`）及 `/jobs/{id}`（`/job/`、`/task/`）：全年或大容量扫可提交异步任务，进度事件只在真实容量计算完成后递增。
- 参数错误、非法JSON、未知型号/电价、缺测天气和非法外送上限返回中文 `error/message/field`。

接口短契约和请求/响应示例见 `docs/handoff/api_examples_v6.json`；对应真实短HTTP运行清单为 `operation_planning/results/phase2b_carbon_5090/api_contracts_v6/run_manifest.json`，6项测试在5090随机loopback端口通过，耗时 `1428.737 ms`。该短序列只是接口契约样例，不是年度方案演示。Windows 启动入口为 `scripts/start_operation_planning.ps1` 和 `.bat`；只使用仓库缓存天气，不调用付费API。

### 12.3 5090 HTTP 回放运行证据

正式 v6 由源码提交 `ec8a7cf8feade2a7464bb00e4ccb761391711389` 运行，命令为：

```powershell
python scripts/phase2b_carbon_replay_v6_5090.py --base-url http://127.0.0.1:18765
```

5090实际清单记录6次 HTTP 调用、总耗时 `562597.433 ms`（均值 `93766.239 ms`，最大 `163067.274 ms`）；单次全年大于约10秒，因此异步接口作为产品路径提供。每档一次请求携带有限容量列表，服务端逐候选计算并返回 `pv_capacity_sweep`，状态变体一次请求固定1 kWp。清单内保存请求/响应哈希与逐案例哈希。

- 完整结果：`operation_planning/results/phase2b_carbon_5090/replay_cases_v6.json`，SHA-256 `19e9fa832037cd44627a34e412238c6174c97dab4b81cfc6f723bfa6fd32e3ab5`。
- 评审 viewer：`docs/handoff/replay_viewer/replay_cases_v6.json`，SHA-256 `92fc5a89e545617aa684a62747b146630a8e51bc334a35a6575bd1fc6b74fa9a`。
- 运行清单：`operation_planning/results/phase2b_carbon_5090/run_manifest_v6.json`，source commit 为上述 `ec8a7cf...`。

### 12.4 电价与边界

v6运行时仍使用当时的公开抄录档案，代码保持 `verified=false/provisional=true`；该历史状态不代表当前状态。第15节随后补入官方95598详情页和PDF核验结果，旧抄录页仅作历史来源记录。

仍未证明现场精度、真实楼宇收益、人工提效、工程审批、完整建筑总负荷或全国电价适用性。光伏容量比选是有限候选，不是全局优化；第一阶段空调轨迹仍是未校准冷却情景。前端由5060分支产品化，本轮未修改前端、PPT、视频、main或“乡艺有据”。

## 第13节：计算提速与典型周/月预览（5090）

本节对应 `feat/5060-product-ui@8d14581` 的第13节要求。三档仍是预置示例，实时输入接口是主路径；v6 年度回放保留不覆盖。

### 13.1 性能基线与优化

先对冻结 v6 路径做 `cProfile` 和分段计时。以 `tier_small`（4 个 PV 容量候选，含选中容量重算，共5次 `run_hybrid`）为例，旧路径 cProfile 用时 `383.4989463 s`（该工具会放大绝对耗时），调用热点为：`pv._intervals` `363.116 s`、`hybrid._safe_intervals` `352.504 s`、`match_hybrid` `360.087 s`、`DatetimeIndex.__getitem__` `350.915 s`；`_lifecycle` `327.513 s`。全年 HTTP v6 历史记录约94 s均值、最长163 s，作为用户等待基线，不与 cProfile 绝对值混用。

修复将实际时间轴间隔验证改为一次性 `DatetimeIndex.as_unit("ns").asi8`差分，经过统一验证的序列在生命周期循环中复用间隔/数值校验，非 UI 小时序仍保留原有严格校验；生命周期只对衰减确实改变的 PV轨迹重算，固定 S0/S2 轨迹复用已验证匹配。优化不改变模型公式、报价、电价、容量候选或状态判据。

当前 5090 单进程 CPU 分段记录（`profile_optimized_v6_stage_timing.json`）为 `6.0770713 s`：天气 `0.0842505 s`、热湿负荷与项目聚合 `0.087722999 s`、价格向量 `2.9684574 s`、PV `0.5127443 s`、风电 `1.1244532 s`、逐时匹配 `0.8162230 s`、生命周期 `0.5834985 s`、储能 `0.3261956 s`；价格向量仍是主要可优化项。最终交接清单 `run_manifest_v7_performance.json` 的HTTP墙钟为：`tier_small 6.284 s`、`tier_medium 7.389 s`、`tier_large 8.774 s`，均低于10秒；在Windows单核亲和性 `0x1` 下小档为 `6.512 s`，台数比选 `max_units=50` 为 `2.980 s`，低于5秒。未在普通笔记本上虚构实测；上述是5090实测，较慢设备继续使用异步接口。

### 13.2 v6 等价性验收

以 `replay_cases_v6.json` 六个 HTTP 请求作为冻结输入，在优化服务重启后逐案回放。三档及三个状态变体的数值字段相对误差均 `0.0`（阈值 `1e-9`），推荐容量、推荐状态、候选 admission 状态和排除原因一致；状态变体的固定 `1 kWp` 仅按展示契约固定，不参与容量寻优。记录见 `operation_planning/results/phase2b_carbon_5090/v6_equivalence_result_current.json` 与 `scripts/compare_v6_equivalence_5090.py`。cProfile 文件和分段计时均保留在结果目录；其中 cProfile 绝对值含分析器开销，不用作用户等待承诺。

### 13.3 典型周/月物理预览

新增 `POST /api/operation/hybrid/preview`。请求沿用 `hybrid/run` 的地点、年份、房间、屋顶、光伏和风机字段，另加：

```json
{"preview":{"period":"typical_week","month":7,"week_rule":"fixed_calendar_day_15_to_22"}}
```

`period` 支持 `typical_week` 与 `typical_month`；未指定月份时夏季默认为7月、冬季默认为1月。典型周固定选该月15日00:00至22日00:00（左闭右开、完整168条小时记录）；典型月选所选月份首日00:00至下月首日00:00。规则不读取结果后择优，响应返回 `start`、`end_exclusive`、`month`、`selection_rule`。输入缺失完整连续区间时返回中文错误，不补0、不循环移位。

接口只计算所选区间内的热湿负荷、PV/风电物理发电和逐时匹配，不计算生命周期经济、碳价、研究期累计或全年外推。响应固定包含 `scope:"preview_period_physics_only"`、`scope_note`、S0/S1/S2/S3 的 `candidates[].intervals`（`load_kwh`、`pv_generation_kwh`、`wind_generation_kwh`、`self_use_kwh`、`grid_import_kwh`、`curtailment_kwh` 等）及区间合计、自用率和弃电率；电价、报价变化不会影响预览物理结果。未填写容量时使用屋顶上限内的默认容量并在 `pv_input` 中回显。

预览沿用同一年度热湿、pvlib、风电和 `match_hybrid` 链，按同一时间轴切片，不将时段结果按比例外推全年。`tests/test_phase2b_preview.py` 覆盖固定选择、非法月份、物理-only字段及HTTP错误；`tests/test_phase2b_performance_contract.py` 和 `scripts/verify_preview_v7_5090.py` 另验守恒与逐字段切片一致性。`docs/handoff/replay_viewer/replay_previews_v7.json` 和 `operation_planning/results/phase2b_carbon_5090/replay_previews_v7.json` 为6个真实HTTP案例（三档各夏季/冬季周），最新清单最大 `0.302 s`，低于典型周3秒目标；典型月744条记录最新清单为 `0.280 s`，低于6秒目标。预览仍不返回经济结论。

示例 HTTP 响应最小结构：

```json
{"status":"success","scope":"preview_period_physics_only","scope_note":"仅对固定典型时段执行负荷与风光逐区间物理匹配；不计算经济、碳排、回本或全年外推。","preview":{"period":"week","month":7,"start":"2024-07-15T00:00","end_exclusive":"2024-07-22T00:00","row_count":168},"candidates":[{"scenario_id":"S0_grid","summary":{"load_kwh":0,"self_use_kwh":0,"grid_import_kwh":0,"curtailment_kwh":0},"intervals":[{"timestamp":"2024-07-15T00:00","load_kwh":0,"pv_generation_kwh":0,"wind_generation_kwh":0,"self_use_kwh":0,"grid_import_kwh":0,"curtailment_kwh":0}]}],"economics":{"status":"not_calculated"}}
```

示例数据仅作预览接口回放；完整年度金额、碳和容量推荐仍以 `hybrid/run` 或异步任务结果为准。预览是物理窗口视图，不是全年代表性承诺。

### 13.4 交付边界

新增代码、测试、性能剖析、等价性记录和预览回放均不修改 `operation_planning/ui/**`、PPT、视频、`main` 或“乡艺有据”。单进程 5090 实测不能证明普通笔记本等待时间、现场楼宇精度、真实节能收益或人工提效；缺少普通笔记本实测时，前端仍应优先调用预览并在全年任务较慢时使用真实进度异步任务。

## 第14节：预览与默认空调适用性修复（5090）

本节接续 `feat/5060-product-ui@14f7dcb` 的第14节问题；原 v7 预览和回放文件保留，修复后的证据使用新文件名，不覆盖旧证据。

### 14.1 P0：典型周与全年窗口的一致性

原实现把任何正的 `capacity_shortfall_w` 都计入预览缺口时长，而全年汇总只在设备运行/制冷时段评价，因而同一小档会出现“全年 0 h、夏季周 118 h”的矛盾。修复在项目负荷切片与热湿模型中统一使用 `active`/`cooling_active` 掩码；运行时段之外的启动残差不再被当成服务缺口。若旧输入没有掩码，则保留全时段的兼容路径，但不静默补零或修改温湿度轨迹。

`tests/test_phase2b_preview.py` 现有5个直接契约测试覆盖：运行外正残差不计入缺口、跨边界区间、预览与全年同一时间窗的8个逐时字段及服务质量相等。`scripts/verify_preview_v8_5090.py` 通过 HTTP 逐案比较三档夏/冬各一周（6案、168小时窗口），当前修复结果 `max_abs_diff=0.0`、`max_relative_error=0.0`，服务状态和缺口字段逐案相同；冬季相对湿度缺口仍按模型结果保留，未改门槛掩盖。

### 14.2 P0：35㎡默认房间的达标判据

“默认35㎡需要13台”来自旧的硬编码有效热容 `1200 kJ/(m²·K)` 与启动阶段残差叠加，不是设备目录额定能力的独立证明。本轮将有效热容改为 `RoomSpec.thermal_mass_kj_per_m2`（默认100，可编辑范围50–2000），并显式加入 `pre_cool_minutes=60`；服务达标只在占用时段评价，预冷能耗仍进入负荷。采用广州2024、35㎡、08:00–18:00、默认4人/300W的当前默认情景时，最小达标配置为2台：1台保留服务缺口（约925个占用时段小时，年电量约1248.876 kWh），2台为 `within_modeled_scope`（年电量约1334.050 kWh）。显式指定旧参数 `thermal_mass_kj_per_m2=1200, pre_cool_minutes=0` 可复现历史约1251.284 kWh，便于审计；这不是实测校准。

### 14.3 工作台验收与边界

已有前端未修改；5090仅在本机按 `docs/handoff/screenshots/frontend_redesign/5090_local/acceptance.md` 记录了3D页面、7个一键场景、3种变体和打印入口检查。记录的本地IAB全年请求约6.87–7.71秒、预览约0.81–1.34秒，控制台错误/警告为0；打印按钮生成了隐藏 iframe，但当前环境不能保存系统 PDF 或逐页复检，因此不能称打印成品已通过视觉验收，仍需在Edge/Chrome人工确认。P1/P2界面功能和现场精度边界仍按前节说明，不因本修复升级为真实楼宇验证。

## 第15节：余电两条附加路径与广州电价核验（5090）

本节对应 `feat/5060-product-ui@eb0f517` 的第15节。储能与卖电均是每个发电候选下的附加卡片，使用同一无储能物理余电，既不增加S0–S3方案，也不参与主推荐；没有前端重做或模型/API付费依赖。

### 15.1 储能与卖电粗算

`POST /api/operation/pv/run` 和 `/api/operation/hybrid/run` 接受可选 `storage`：`capacities_kwh`、`round_trip_efficiency`、`quote` 和 `export`。响应在每个候选（S0保留零余电路径）下的 `surplus_paths` 中同时给出：

- `surplus_kwh_year1`：该候选逐时发电减当时自用后的物理余电；不把卖电或储能的去向反写回主匹配。
- `storage`：按时序先用发电供负荷，再以原余电充电、缺电放电的理想上限。返回容量、恢复电量、自用率变化、年分时电费节省、初始投入、研究期净收益、替换次数和简单回本期。默认效率为明确的用户情景；不含电池衰减、温度、功率电子限制、峰谷套利优化或现场并网约束。
- `export.path`：按同一余电乘用户 `price_cny_per_kwh` 的卖电粗算，另列 `connection_cny`、年/研究期收入和回本字段。缺少卖电价时保留物理余电但经济状态为 `incomplete`；不把缺价当0，也不声称已有并网资格。

第16节回放的示例报价带公开来源：储能采用 CNESA Datalink 2025 年 2 小时系统均价 553.94 元/kWh 与 2 小时 EPC 均价 1043.82 元/kWh（<https://www.esresearch.com.cn/report/info/detail/?id=6645>），以差额 489.88 元/kWh 作为容量线性安装项；这是为字段拆分的示例，不是逐项采购报价。卖电 0.25 元/kWh 参考公开行业市场化余电示例（<https://pdf.dfcfw.com/pdf/H3_AP202406141636236987_1.pdf>），同时以国家发改委市场化改革通知（<https://www.ndrc.gov.cn/xwdt/tzgg/202502/t20250209_1396067.html>）为政策边界，不称广东固定结算价。回放小档 `connection_cny=0` 表示尚未取得并网/计量报价的粗算假设。

非零储能容量缺任一报价字段时为 `incomplete`；容量0不承担电池固定费用、维护、更换或残值。外送开启时储能仍独立计算，卖电路径也独立计算，不将两者误作联合调度。`storage_upper_bound` 作为旧字段继续保留以兼容历史回放，但新审阅应读取 `surplus_paths.storage`。

请求/响应完整字段、缺价状态和手算守恒见 `operation_planning/protocol/storage_surplus_paths_contract.md`、`tests/test_phase2b_storage.py`；v8 HTTP回放及哈希见 `operation_planning/results/phase2b_carbon_5090/replay_cases_v8.json`、`run_manifest_v8.json`。v8生成后以清单的 `source_commit`、逐案例哈希和包哈希为准，旧 v3–v7 文件不覆盖。

最终5090回放（source `9ce2d2c43e0978c329bdc2d55cf4a30cd9165b53`）的三档主卡仍分别推荐 1/40/50 kWp；S1 年1物理余电分别为 700.185、19740.361、22470.873 kWh。以示例 5 kWh 电池报价计算，年分时购电节省为 123.721、1151.028、1036.800 元，10年粗算净收益为 -16762.794、-6489.721、-7632.004 元（已含初始投入和维护）；以 0.25 元/kWh 的卖电情景，年粗收入为 175.046、4935.090、5617.718 元。上述两条是同一余电的独立附加估算，不叠加进入主方案NPV。六次HTTP调用总耗时 35006.113 ms（均值 5834.352 ms，最大 9821.556 ms）；这只是5090运行记录，不是用户人工等待承诺。

### 15.2 已核验广州主价与高温尖峰

`guangzhou_industrial_lt1kv_202610` 现标记 `verified=true`，来源 URL 为南方电网95598公告详情页：
`https://95598.csg.cn/#/gd/serviceInquire/information/detail/?infoId=8a592ed919684f97bc6abd030a79b807`。
公告原件已纳入 `docs/evidence/tariffs/guangdong_agency_tariff_202610_official.pdf`，SHA-256 为 `36648B430E5F729037DF3D8766232057FEADF518BD39692BFE1EFE3758C91212`（审阅时以仓库文件哈希为准）。档案是2026年10月广州所属珠三角六市工商业单一制不满1kV电度电价，仍不含需量/容量基本电费、其他建筑负荷或未来价格承诺。

除7–9月公告尖峰外，提供逐时 `temperature_2m` 时启用高温日规则：当地日最高气温达到35℃的7–9月外日期，在11:00–12:00及15:00–17:00按尖峰价计费；不提供逐时温度时不启用。`tariff` 元数据回传 `high_temp_super_peak_days`、`high_temp_super_peak_day_count`、`super_peak_day_count` 和 `high_temp_rule`，便于追溯本次价格向量实际覆盖的日期。测试 `tests/test_phase2b_tariff_verified.py` 已验证2024-10-10的35℃日期在11:00进入尖峰，而次日同一时段仍为峰段，并检查价格向量的高温日计数。

高温规则只改变分时计费；光伏/风电物理发电、余电量和主推荐不因价格向量重算而改变。最终v8回放的全年温度输入触发 `high_temp_day_count=29`，其中7–9月外额外触发尖峰的 `high_temp_super_peak_day_count=1`（2024-06-21），合并后的 `super_peak_day_count=93`；年购电费用相对旧未启用高温规则的参考值增加约0.50元（小档S0）、30.34元（中档S0）、33.82元（大档S0），仅表示该价格情景的计费差异。不能把一次重价结果写成现场电费结算。

### 15.3 第15节验证边界

本轮新增的是可复现的余电经济附加计算和电价档案核验，不是电池投资建议、并网审批或售电合同结算；四方案与主推荐保持原定义。第一阶段空调负荷仍为未校准冷却情景，屋顶可用面积、报价、外送资格和高温日气象代表性需用户/现场确认。没有在前端、PPT、视频或“乡艺有据”中扩大能力主张。



