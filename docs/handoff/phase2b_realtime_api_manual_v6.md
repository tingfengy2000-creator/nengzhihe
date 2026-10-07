# 能智核实时计算接口手册（v6）

接口只监听 `127.0.0.1`，默认端口 `18765`。所有数值由 Python 工具计算，前端不复制公式。

## 选项

`GET /api/operation/options` 返回 `cities`（缓存城市与年份）、`years`、`equipment_models`（型号、额定制冷量、COP、来源）、`tariffs`（电价档案及 `verified`/`notes`）、`carbon_factors`（kgCO2/kWh）和单位表。

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

## 错误

参数错误返回 HTTP 400：`{"status":"failed","error":"中文说明","message":"中文说明","field":"pv.requested_capacities_kwp"}`。`field` 是可直接定位表单控件的字段路径；未知型号、电价档案、缺测天气、负容量和非法外送上限都会拒绝计算。

## Windows 启动

双击 `scripts/start_operation_planning.bat`，或执行 `powershell -ExecutionPolicy Bypass -File scripts/start_operation_planning.ps1`。脚本使用仓库缓存天气，不启动模型、不调用付费 API，并自动打开 `http://127.0.0.1:18765/`。依赖安装见 `requirements-phase2.txt`。
