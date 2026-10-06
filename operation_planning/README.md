# 能智核工作台

展示主张：**先试算，再决策。**

当前增强分支在保留 BOPTEST `bestest_air` 方案工作台的基础上，加入第一阶段空调选型闭环：城市或用户 CSV 天气 → 单房间热湿负荷 → 公开额定点设备响应 → 逐时电量 → 逐月费用 → 用户报价驱动的全生命周期现金流。页面不向设备下发控制，结果不等同于现场楼宇预测。

## 启动

```powershell
python operation_planning/run_server.py
# http://127.0.0.1:18765
```

第一阶段 API：

- `GET /api/operation/weather/sites`：查看 3 城市 2023–2025 缓存年份。
- `POST /api/operation/weather/import`：导入含 `timestamp,temp_c,rh_percent,pressure_hpa,solar_w_m2` 的用户 CSV。
- `POST /api/operation/thermal/run`：按城市/年份或导入天气运行单房间热湿模型；可传 `equipment_quote` 覆盖采购、安装、维护参考值。
- `GET /api/operation/equipment`：查看型号来源和限制。

完整数据哈希和范围说明见 `protocol/weather_manifest.json`、`protocol/weather_pv_manifest.json`、`protocol/first_stage_model.md`、`protocol/phase2a_handoff.md`、`results/regional_product_v2/`。第二阶段 A 已加入光伏配置页与 `POST /api/operation/pv/run`：同一空调负荷时间轴接入 GHI/DNI/DHI，逐时计算 PV 交流发电、供需匹配和有限候选生命周期成本；风电、储能和其他电器仍未接入。

第一阶段三个可复现演示可运行 `python scripts/first_stage_demo.py`；第二阶段 A 证据可运行 `python scripts/phase2a_demo.py`，输出广州 2024 完整链、使用时段和屋顶/预算变化、以及固定 2 kWp 的 9 个历史年份比较到 `results/pv_phase2a/`。

## 证据边界

天气是 Open-Meteo Historical Weather API 城市级再分析；第一阶段请求 ERA5 但响应未给出显式模型字段，manifest 保留该边界，不把来源名称当成响应模型，按 CC BY 4.0 归因，不是楼宇微气候实测。热湿模型是可审计的集总参考模型；PsychroLib 2.5.0 以 MIT 许可证随项目分发。三条设备记录是公开网页/能效标签的额定点，SHR、报价和完整部分负荷曲线缺失时会在结果中保持待补或参考情景。`results/regional_product_v2/summary.json` 的 27 条组合用于复现地区、年份与型号变化，不能写成实测精度、节能收益或采购承诺。

阶段二运行依赖锁定在仓库根目录 `requirements-phase2.txt`（pvlib 0.11.2）；Windows 可先执行 `python -m pip install -r requirements-phase2.txt`。旧轮次诊断源码、结果和发布包保持原状；本分支只在 `operation_planning/` 增加独立产品链。

### 空调成本接口（5090交接修复）

`POST /api/operation/thermal/run` 接受 `room.room_count`、`room.units_per_room`（旧 `equipment_count` 仍兼容）以及 `quote_scope`。单房间热模型已把每间房的设备台数计入能力和电量，生命周期只按 `room_count` 聚合同类房间；逐台报价按 `room_count × units_per_room`，每房间报价按 `room_count`，项目报价只计一次。研究期、用户预计寿命和保修期分别由 `study_years`、`expected_life_years`、`warranty_years` 传入；寿命覆盖只影响更换事件，不改变既有负荷轨迹。

电价二选一：`annual_price_cny_per_kwh` 为用户恒价情景，或 `tariff_id`/`custom_tariff` 为现有 `TariffProfile`。分时价格复用 `tariffs.integrate_power` 按负荷区间切分；电价档案未覆盖评价日期时返回错误，不套用其他日期。响应中的 `input_contract`、`result.room`、`result.load_series` 和 `cost.lifecycle` 是同一任务对象的口径来源。
