# Round5：APAR 专业基线与公开控制实验响应核验

本轮是 `enhance/apar-physical-validation` 独立增强分支，基于 `42ea87e`。前两轮、round4 发布版、审核记录和现有前端/邀测机制保持不变；本轮只新增 `round5/`，没有发布新版本或推送远端。

## 结论先看

- 先核验官方 OpenEI submission 910，再选择其中与此前保留文件逐字节一致的 `SZVAV.csv`：同一 FLEXLAB X3A 单区 VAV AHU 的 11 个整日控制实验；它不是运营楼宇试点。OpenEI 页面级摘要同时将整个集合描述为模拟 AFDD 数据，故交付使用下载清单对 SZVAV 的更窄描述，不把提交 910 整体称为物理实测。
- APAR 规则来自 NISTIR 6994 Table 2.1，并按 SZVAV 的点位、控制顺序和单位适配。没有设计最小室外风量点，因此规则 2、18 保留为不可检验，未用控制指令冒充流量分数。
- 5 个开发日（其中 2 个正常日仅作校准）曾用于开发；原 6 个整日留出日已经在早期预检中被查看，因此本轮响应机制的 11 日结果标记为开发与已知留出重检，不能称未经开发的外部验证。标签在引擎外加入，仅用于最终评分。
- 新增一项固定的“后续响应证据”机制：在首个 15 分钟稳定窗口后，寻找两段后续的盘管关闭窗口，用请求的 OA/RA 比例和实测 MA 残差核验风路响应。基线、加机制和消融使用相同记录与校准。
- 在这 11 个控制实验日上，故障检出保持 9/11；风阀疑点错误归因由 3 条降为 0 条，支持性疑点精度从 1/4（25%）升为 1/1（100%），风阀事件召回仍为 1/2。该结果是有限开发/失败分析证据，不是跨设备或运营现场性能。
- 物理实验能证明的是有界条件下的规则触发、误报和未决状态，不能证明运营建筑故障定位、节能或人工提效。

## 可复现

```powershell
$py = 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -X utf8 -m unittest discover -s round5/tests -v
& $py -X utf8 round5/scripts/inspect_development.py
& $py -X utf8 round5/scripts/run_apar.py
& $py -X utf8 round5/scripts/score_external.py
& $py -X utf8 round5/scripts/run_response_mechanism.py
& $py -X utf8 round5/scripts/score_response_mechanism.py
& $py -X utf8 round5/integration/run_public_case.py
```

`run_apar.py` 会在允许读取留出数据前写入并校验 `protocol/frozen_methods.json`。输入契约仅包含已允许的温度、状态和控制点；日期、实验标签、故障名和注入参数不进入诊断函数。

## 关键文件

- `src/adapter.py`：单位、缺失标记、真实时间轴和点位边界。
- `src/apar.py`：NIST APAR 适配、稳定窗口、证据一致性核验和补证动作。
- `src/response_evidence.py`：盘管关闭后的后续请求响应残差机制；没有独立阀位/流量反馈时仍保留未决。
- `protocol/metric_contract.json`：疑点检出、故障检出、定位、动作正确性和覆盖率定义。
- `protocol/apar_adaptation.md`、`external_source_screening.md`：专业规则及来源筛选边界。
- `protocol/openei_source_confirmation.md`：OpenEI 官方入口、下载哈希、清单与 SZVAV 选择边界。
- `protocol/response_evidence_mechanism.md`、`response_mechanism_freeze.json`：A/B/C 机制、参数冻结和不能称外部验证的原因。
- `results/external_metrics.json`：标签在引擎外加入后的分组结果。
- `results/apar_physical_case_results.json`：逐实验日、逐方法的可复现结果。
- `results/response_mechanism_metrics.json`：专业基线、能智核机制和必要消融的逐事件结果与分组指标。
- `integration/public_case_output/case_card.html`：从公开源实时重算的可阅读工作台核验卡。
- `results/invalid_preflight_*`：第一版错误使用最小室外风量校准的审计痕迹，不得用于申报成绩。

真人邀测仍沿用 round4 包；本轮不模拟参与者，也不填造核查时间、遗漏或提效结果。
