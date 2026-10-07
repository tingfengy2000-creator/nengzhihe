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
