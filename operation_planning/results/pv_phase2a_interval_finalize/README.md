# 阶段二A正确性修复结果

本目录由 `python scripts/phase2a_interval_finalize_demo.py` 生成，未覆盖 `results/pv_phase2a`。

- `guangzhou_2024_full_chain_corrected.json`：广州 2024 完整链、晚间使用时段、屋顶/预算约束以及 10/15 年现金流；每个 0/1/2/3 kWp 候选都指向逐时 CSV。
- `candidate_evidence/`：按区间电量保存负荷、交流发电、自用、购电、外送和弃电，便于逐行检查守恒。
- `fixed_2kwp_9_years_corrected.json/csv`：广州、北京、哈尔滨 2023–2025 固定 2kWp 时间年敏感性，不称独立建筑验证。
- `counterexamples_before_after.json`：生命周期、朝向、时间轴、缺失报价/外送价修复前后对照。

第一阶段空调负荷仍是未校准的城市级冷却情景；服务缺口随报告保留。0kWp 是无光伏基准，不承担任何光伏报价项。非零报价或外送价格缺失时只交付物理结果，不证明“不安装最划算”。

- definition_tests.json：08:00→07:30区间、1700 W额定边界和0.75元分时费用的具体结果。
- ffected_metrics_before_after.json：广州 2024 受影响指标修复前后对照。

