# 第二阶段 A 交接与验证记录

## 分支和基线

- 分支：`feature/phase2-pv-coupling`
- 起点：第一阶段 `df5082e`（`feature/regional-tariff-product-ui`）
- 旧版 `operation_planning/results/regional_product_v2/`、三段演示与第一阶段源码保留；本轮不触碰“乡艺有据”。
- 正式申报材料、PPT、视频和 GitHub 发布本轮不更新、不推送。

## 交接检查

1. **时间轴**：第一阶段缓存和第二阶段 PV 缓存都保留本地时区的逐时时间戳；2023/2025 为 8760 行，2024 为 8784 行。负荷和 PV 必须使用完全相同的时间戳、逐条间隔和年度区间，缺测不补零。逐时匹配后检查 `load=self_use+grid_import` 与 `pv=self_use+grid_export+curtailment`。
2. **天气模型标注**：Open-Meteo 历史接口请求参数为 `models=era5`，原始 JSON 没有显式 `model` 字段。因此第一阶段 manifest 改为记录 `requested_model=era5`、`response_model=null`，不把“来自 Open-Meteo”写成响应已核实 ERA5。阶段二 PV 缓存保留同样的边界。
3. **辐照单位**：`shortwave_radiation` 作为 GHI，新增 `direct_normal_irradiance` 作为 DNI、`diffuse_radiation` 作为 DHI，单位均为 W/m² 的前一小时平均；不把水平直射当法向直射，不混入瞬时变量。
4. **负荷服务范围**：`LoadSeries` 现携带温度缺口、RH 缺口、容量短缺、设备数量、模型版本、假设和 `cooling_only` 服务范围。负荷仍是未校准的城市级单房间情景；容量不足、温湿度缺口不会被裁剪成达标。
5. **设备与费用**：空调成本在 P0 和光伏候选中保持相同。光伏报价分组件、逆变器、支架、施工、接入、维护、更换和残值；缺失报价不默认为 0，缺报价时只给发电/供需结果，不给经济推荐。公开设备额定点仍受第一阶段“无完整部分负荷曲线、SHR 缺失”的限制。
6. **屋顶资源**：屋顶面积单独输入，默认组件面积假设 5 m²/kWp。房间面积或同类房间数量不会复制屋顶资源；承重、消防间距、并网审批是待现场确认条件。

## 阶段二 A 实现

- `operation_planning/pv.py`：pvlib 太阳位置、POA 辐照、SAPM 组件温度、PVWatts DC、PVWatts 逆变器交流输出；显式输入温度和 10m 风速，损失与可用率只应用一次。
- `operation_planning/weather.py::load_pv_weather`：读取 9 个地点/年份补充缓存并验证 GHI/DNI/DHI、风速、时轴。
- `match_load`：逐时电量匹配，默认不外送，余电为弃电；允许外送时按用户给出的外送功率上限计算。
- `lifecycle_compare`：P0 全部购电与 P1/P2 固定容量在同一研究期比较；购电节省、外送收入、维护、更换和残值分开列出。
- `PVPlanningAgent`：本地模型只在固定工具序列中选择阶段；所有数值由 Python 计算，模型失败会留下失败轨迹，不以模型自报数值替代结果。
- UI 新增“光伏配置”页，支持修改地点/年份、屋顶、朝向/倾角、预算、报价、外送策略、容量候选和空调使用时段，修改后真实重算。

## 当前证据

- 广州 2024 完整链：`results/pv_phase2a/guangzhou_2024_full_chain.json`。
- 屋顶/预算变化、使用时段变化、同一报价延长至15年的条件对照和固定 2 kWp 的 9 个历史年份：`results/pv_phase2a/summary.json`、`fixed_2kwp_9_years.json/csv`。广州2024默认10年/当前报价下有限候选选择0kWp；同一报价延长到15年时选择1kWp，说明推荐依赖研究期假设。
- PV 天气文件与哈希：`protocol/weather_pv_manifest.json`。
- 可复现命令：`python scripts/phase2a_demo.py`。
- 阶段二合同测试：`python tests/test_phase2_pv.py`；第一阶段合同回归在 PowerShell 使用 `$env:PYTHONPATH=(Get-Location).Path; python -c "import runpy; d=runpy.run_path('tests/test_operation_planning_contracts.py'); [v() for k,v in sorted(d.items()) if k.startswith('test_') and callable(v)]; print('phase1 contract tests: PASS')"`。

## 证据边界

当前输出证明的是在公开城市级逐时天气、未校准的单房间空调情景、用户输入屋顶与费用假设下，光伏容量如何改变逐时供需和情景成本。它不证明运营楼宇节能、并网审批通过、采购报价、真实投资回报或对所有建筑的最优容量。风电、储能和其他电器留作后续阶段。

