# 结果快照

* `demo_day153_search.json`：12 个候选的单日期真实官方 FMU 回放，供工作台案例和复核使用。
* `experiments/frozen_comparison.json`：2 个开发日期块和 6 个时间留出日期块的 A0/A1/A2 比较。全体候选和逐例失败原因保留在报告中。
* `experiments/agent_comparison.json`：16 个冻结自然语言任务的 B0/B1/B2 记录；没有参与者模拟，不能解释为用户提效。
* `experiments/external_physical_validation.json`：OEDI/LBNL `MZVAV-2-1.csv` 六个物理实验日期块的单位、时间轴、点位准入和 APAR-inspired 专业筛查对照；因缺少区温、能耗和实际执行器反馈，不计入 BOPTEST 反事实方案成绩。
* `runs/`：按物理输入哈希缓存的逐候选 `SimulationResult`。缓存只减少重复 FMU 回放，不改变逻辑任务身份。

所有数值来自本地官方 FMU 输出和程序计算。日期块来自同一模型，属于时间留出；不要将其改写成跨设备、真实建筑或现场节能证据。
