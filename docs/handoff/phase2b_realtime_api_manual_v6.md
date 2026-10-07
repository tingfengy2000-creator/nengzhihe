# 能智核实时计算接口手册（v6）

接口只监听 `127.0.0.1`，默认端口 `18765`。所有数值由 Python 工具计算，前端不复制公式。

## 选项

`GET /api/operation/options` 返回 `cities`（缓存城市与年份）、`years`、`equipment_models`（型号、额定制冷量、COP、来源）、`tariffs`（电价档案及 `verified`、`provisional`、`verification_status`、`notes`）、`carbon_factors`（kgCO2/kWh）和单位表。公开抄录但未取得原始公告的电价标为 `verified:false, provisional:true`。

## 空调台数比选

`POST /api/operation/thermal/size`（`/thermal/compare` 为兼容别名；`/thermal/run` 携带 `compare_units:true` 也可）请求示例：

```json
{"site_id":"guangzhou","year":2024,"max_units":6,
 "room":{"area_m2":35,"equipment_id":"midea_msagbu12_mox201",
          "room_count":1,"units_per_room":1}}
```

响应包含 `candidates`，每项有 `units_per_room`、`service_status`、`annual_electric_kwh`、`annual_cooling_kwh`、`capacity_shortfall_hours`、`unmet_temp_degree_hours`、`unmet_rh_percent_hours`；`minimum_adequate_units_per_room` 是第一个无服务缺口的候选。每项仍是单房间轨迹，`room_count` 只由项目负荷适配层聚合一次。

## 风光实时比较

`POST /api/operation/hybrid/run` 使用 `room`、`pv`、`hybrid`、可选 `carbon` 和 `storage`。`pv.requested_capacities_kwp` 为用户指定的有限容量列表；`pv.auto_capacity:true` 在 `roof_area_m2 × usable_fraction × 0.2 kWp/m²` 上限内生成 0/25%/50%/100% 候选。响应的 `report.pv_capacity_sweep` 列出每个候选的成本、增量NPV、自用率和碳字段，`report.recommended_pv_capacity_kwp` 为计价完整且满足约束候选中增量NPV最大的容量；完整 `hourly` 只保留被选容量的四方案。

`report.calculation_timing.elapsed_ms` 是本次服务端实际计算耗时（包括负荷、发电、匹配和经济层）。

评审回放的状态卡可在 `pv.fixed_capacity_kwp` 中明确锁定用户要求的容量（例如 `1`）；这只用于展示该容量的真实 `unknown`（报价缺失）或 `excluded`（屋顶/预算硬约束）状态，不参与普通用户的容量推荐逻辑。

请求片段：

```json
{"site_id":"guangzhou","year":2024,
 "room":{"area_m2":35,"room_count":3,"units_per_room":6,
          "equipment_id":"midea_msagbu12_mox201"},
 "pv":{"roof_area_m2":35,"usable_fraction":0.8,
       "auto_capacity":true,"tariff_id":"guangzhou_industrial_lt1kv_202610",
       "tariff_application":"current_tariff_on_reference_weather"},
 "hybrid":{"pv_capacity_kwp":1,"wind":{"turbine_count":0}},
 "carbon":{"factor_id":"grid_avg_guangdong_2023"}}
```

## 异步任务

容量候选较多时使用 `POST /api/operation/hybrid/jobs`（`/hybrid/submit` 为别名），返回 `{status:"queued",job_id,progress:0}`。轮询 `GET /api/operation/hybrid/jobs/{job_id}`（`/job/`、`/task/` 为别名），`progress` 只在真实容量完成后递增，完成时 `result.report` 与同步接口相同。

任务失败时轮询仍返回 HTTP 200 的任务状态，并在顶层给出可直接展示的 `error`、`message`、`field`，同时 `result` 保留同一错误对象。例如：

```json
{"job_id":"abc123","status":"failed","progress":0,
 "error":"未支持的设备型号：unsupported_contract_model",
 "message":"未支持的设备型号：unsupported_contract_model",
 "field":"room.equipment_id"}
```

## 错误

参数错误返回 HTTP 400：`{"status":"failed","error":"中文说明","message":"中文说明","field":"pv.requested_capacities_kwp"}`。`field` 是可直接定位表单控件的字段路径；未知型号、电价档案、缺测天气、负容量和非法外送上限都会拒绝计算。

## Windows 启动

双击 `scripts/start_operation_planning.bat`，或执行 `powershell -ExecutionPolicy Bypass -File scripts/start_operation_planning.ps1`。脚本使用仓库缓存天气，不启动模型、不调用付费 API，并自动打开 `http://127.0.0.1:18765/`。依赖安装见 `requirements-phase2.txt`。

## 典型周/月物理预览（v7 API）

`POST /api/operation/hybrid/preview` 与 `hybrid/run` 使用同一输入字段，增加 `preview`：

```json
{
  "site_id":"guangzhou", "year":2024,
  "room":{"area_m2":35,"equipment_id":"midea_msagbu12_mox201","room_count":1,"units_per_room":6},
  "pv":{"roof_area_m2":35,"usable_fraction":0.8,"capacity_kwp":1},
  "hybrid":{"pv_capacity_kwp":1,"wind":{"turbine_count":0}},
  "preview":{"period":"typical_week","month":7,"week_rule":"fixed_calendar_day_15_to_22"}
}
```

`period` 可取 `typical_week` 或 `typical_month`。未提供 `month` 时，夏季默认7月、冬季默认1月；典型周固定选择该月15日00:00至22日00:00的左闭右开区间（168小时），典型月选择整月。响应回显 `preview.start`、`end_exclusive`、`month`、`selection_rule` 和 `row_count`，规则与输入无关且可复现。

该接口只做所选时间段的物理匹配，不做经济、碳、回本、容量推荐或全年外推。顶层固定字段为：

- `scope: "preview_period_physics_only"`
- `scope_note`：`仅对固定典型时段执行负荷与风光逐区间物理匹配；不计算经济、碳排、回本或全年外推。`
- `candidates`：`S0_grid`、`S1_pv`、`S2_wind`、`S3_pv_wind`，每项含 `intervals` 和 `summary`；每个区间包含 `load_kwh`、`pv_generation_kwh`、`wind_generation_kwh`、`self_use_kwh`、`grid_import_kwh`、`curtailment_kwh`，并返回区间自用率与弃电率。
- `economics.status: "not_calculated"`。

天气、热湿、光伏和风电均沿用年度同一物理链后按同一时间轴切片，不使用未来信息、不将窗口结果比例外推全年；改变报价或电价不会改变预览值。缺失完整连续窗口或 `month` 不在1–12时返回中文错误和 `field`。未填光伏容量时服务端在屋顶上限内采用默认容量并回显 `pv_input.capacity_kwp`。

实测：5090本地HTTP三档各夏季/冬季典型周共6次调用，总 `1555.882 ms`、平均 `259.314 ms`、最大 `275.359 ms`；前端可在后台并行提交全年异步任务。完整回放见 `operation_planning/results/phase2b_carbon_5090/replay_previews_v7.json`，查看版见 `docs/handoff/replay_viewer/replay_previews_v7.json`。契约测试见 `tests/test_phase2b_preview.py`。

## 性能验收（5090）

优化前 `tier_small` 四容量候选加选中重算的 cProfile 为 `383.4989463 s`（分析器开销；全年历史HTTP约94秒均值）。热点为时间轴间隔校验和 `DatetimeIndex`逐条索引。优化后采用批量纳秒差分、已验证序列复用与生命周期匹配复用，`profile_optimized_v6_stage_timing.json`记录一次真实请求 `6.0770713 s`：天气0.0843s、热湿/聚合0.0877s、价格向量2.9685s、PV0.5127s、风电1.1245s、匹配0.8162s、生命周期0.5835s、储能0.3262s。三档HTTP请求耗时约6.25/8.03/9.32秒（18769服务器elapsed），普通笔记本未虚构实测；较慢机器继续使用异步任务。

六个 v6 请求等价性验证阈值为相对误差 `1e-9`；三档和状态变体数值结果、推荐与约束状态应完全一致，记录见 `v6_equivalence_result_current.json` 及 `scripts/compare_v6_equivalence_5090.py`。固定1kWp状态变体的展示文案按回放契约保留，物理/经济数值仍来自HTTP响应。
典型月补测：`tier_small` 2024年7月744小时，本地HTTP墙钟0.2840964s，scope为preview_period_physics_only且无经济字段，低于6秒目标。



