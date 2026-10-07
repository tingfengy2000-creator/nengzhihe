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
