# 阶段二B：项目总负荷衔接交接（5090）

本页记录从单房间热湿轨迹到光伏/风光匹配的最小跨模块适配。它不改变热湿、光伏或风电公式，也不把不同朝向、时段或设备的房间自动组团。

## 交接锚点

- 基线：`fix/5090-aircost-handoff`，`1c0cc6f8455bb520dfe9a6805536696edd389726`
- 本轮分支：`fix/5090-project-load-handoff`
- 本轮执行源码提交：`611598be93e282cbc473287f5b3d8f173fe86793`
- 本轮完整年证据提交：`5d7e3d483a0943788133b892d6dffc4e5c2c7dd0`
- 本轮 HTTP API 契约探针源码：`dc2de4277e12e914993281c0bb3fa1e6e4106a8a`
- 本轮 HTTP API 契约证据：`fa506041a55886beb8adbe63bda3722632935c1d`
- 机器角色：5090；正式实验与回放只在此环境执行。

`990f25327599c8795682592c75653bc5e84a96af` 及更早的交接提交只保留为历史记录，不是本轮 5060 的起点。改名授权仍然有效，但不改变仓库名、包名、API、字段 ID 或历史证据目录。

## 负荷契约

`simulate_room` 始终生成一间房间的轨迹；其中 `units_per_room` 已经进入单房间设备能力和用电。`room_count` 只在 `operation_planning.project_load.aggregate_project_load` 中应用一次，得到项目级 `load_series` 后才交给 PV 和 Hybrid 匹配。

适配器保留原始单房间结果和 `single_room_summary`，并写入：

- `load_series.scope = "project; same-room aggregation of single-room trace"`；
- `load_series.project_aggregation`：聚合数量、源 scope 和一次性乘 `room_count` 的规则；
- `project_load_contract`：单位、来源、数量和单房间结果是否保留。

直接把未适配的 `room_count > 1` 轨迹传给 `run_pv_planning` 或 `run_hybrid_planning` 会拒绝，而不会静默按一间房计算。匹配后的自用、购电、外送和弃电不会再乘房间数，发电设备容量也不会随房间数放大。

## 5090验证

命令：

```powershell
python -m unittest -v tests.test_project_load_adapter tests.test_aircost_handoff
python scripts/phase2b_project_load_handoff_5090.py
```

短空调成本测试属于契约样例，不是年度方案演示；完整广州 2024 回放才是本轮正式证据。结果位于 `operation_planning/results/phase2b_project_load_handoff_5090/`。

已验证：

1. `room_count=1` 的单房间功率和年度电量保持一致；
2. 三间同类房间、每间两台的项目负荷为单房间同配置的 3 倍；
3. 固定 2 kWp 光伏和 1 台风机时，发电量不因房间数改变，匹配内部守恒检查通过；
4. 空调成本页、PV 和 Hybrid 的项目年度负荷一致；
5. `0 kWp + 0 台风机` 的 S0 购电量等于项目总负荷；
6. 同一适配器重复调用不会再次乘 `room_count`。

PV 和 Hybrid HTTP API 也用三行契约样例验证：三间同类房间的 `load_context` 与 S0 购电量均等于同一项目负荷；样例明确标为契约测试，不替代完整年结果。

这只证明同类房间的负荷衔接和守恒。它不证明多房间之间存在不同天气、朝向、使用时段、设备型号或独立服务状态的组团模型，也不证明现场精度、节能收益或生产验收。

## 5060边界

5060 可以并行做页面和业务产品化，但必须直接读取 API 返回的项目级 `load_context`、`project_load_contract` 和结果；前端不得重新聚合电量。多房间风光比较在读取本轮证据前不得显示为已验证能力。新增输入若超出同类房间适配范围，应显示待 5090 验算或拒绝，不得沿用一间房的旧答案。
