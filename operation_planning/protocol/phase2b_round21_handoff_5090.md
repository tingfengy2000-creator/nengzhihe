# 第21节回交：本机联调与接口收尾

分支fix/5090-round21，起点13c26feee1e8d5de3ed121cfe1cb44f317c9ea5c。真实取证代码版本及状态详见 results/round21_local_5090/run_manifest.json；最终证据提交SHA以Git历史/回报为准，不在文件中手填自身SHA。

## 实现

1. PV/Hybrid的escalation_sensitivity增加当前用户涨幅并唯一标is_current。复用已有年度轨迹，按“目标涨幅因子/已存涨幅因子”重新计价，避免3%被乘两次；当前档总成本/增量与候选一致，g=0历史结果不改。
2. custom_user在明确current_tariff_on_reference_weather下保留单月来源有效期并映射全年参考天气。新增tariff.custom_tariff_echo：base_tariff_id、version、effective_start/end、prices_cny_per_kwh、prices别名、periods、application、note。strict日期校验继续保留。
3. 实际PV=0且风机=0的候选省略surplus_paths/storage_upper_bound；历史精简回放仅做字段显示适配，不重算旧物理结果，完整旧回放保留。
4. 卖电payback_status统一“无需额外投入”、缺价、价格不为正、无可卖余电等中文原因。

联调定点修复：PV修改字段别名缺失、显式no-op误追问、目录型号ID提示、模糊预算不得猜比例、显式PV单位与数值一致性保护。不扩模型或架构；失败输出仍失败，不用规则冒充。

## 验证与结果

45项unittest通过；13项风光专项、阶段二A正确性专项、6项storage专项通过。新测试 tests/test_phase2b_round21.py；扩展 tests/test_agent_parse_contract.py 和 test_phase2b_tariff_escalation.py。完整命令/日志在run_manifest。

14种真实浏览器输入最终8项采用并计算、1项目录外型号unsupported、1项追问、4项failed（含两种風机表达及kWp单位错误）。所有首次/重复记录保留，不称通过率提升实验。解析HTTP0.285–0.891秒；成功案例浏览器预览0.300–0.304秒、全年2.934–5.225秒。最终完整自定义分时电价＋3%任务预览0.494秒、全年8.090秒，后端7.260秒。

最终任务S0成本4115.565531341元，3%敏感性当前档也为4115.565531341；旧错误档4751.990866589保留在final_guard审计。0%敏感性3590.028662656。负荷316.302507805 kWh、8784小时，单月来源有效期不截断参考天气年。改变仅在敏感性重计价，物理与主候选费用不变。

## 审核入口与边界

- docs/handoff/screenshots/frontend_round2/5090_local/acceptance.md：浏览器字段、采用、计算、离线规则、3D、PDF和未修前端问题。
- results/round21_local_5090/task_records.json：原始模型JSON、实际任务与结果摘要、行号、哈希。
- results/round21_local_5090/{http_events.jsonl,confirmed,final_guard,final_economics}：按源码版本保留原始审计。
- docs/handoff/replay_viewer/replay_cases_ui_v9.json：7,747,894字节，保留回本字段、当前敏感性标记；完整历史v9不改。

需求文档、frontend_redesign和operation_planning/ui不修改。仅普通推送此分支，不改main、PR/Release、比赛材料或其他项目。本轮是正确性/可用性验证，不作为新算法、实测楼宇精度、节能或人工提效佐证。
