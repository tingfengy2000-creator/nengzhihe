# 能智核实时接口增量手册（v8：预览修复与余电附加路径）

本文件是 v6 接口手册的增量说明。服务仍只监听 `127.0.0.1:18765`；完整请求字段、异步任务和 Windows 启动方式见 [`phase2b_realtime_api_manual_v6.md`](phase2b_realtime_api_manual_v6.md)。本轮没有修改前端，所有数值由后端 Python 工具计算。

## 1. 默认房间与服务质量

`room` 可以携带 `thermal_mass_kj_per_m2`（默认100）和 `pre_cool_minutes`（默认60）。负荷响应的 `load_context.adequacy_rule` 描述适用规则；`service_quality` 只在占用/制冷活动时段计 `capacity_shortfall_hours`、温度缺口和湿度缺口，预冷能耗仍进入 `load_series`。1台/2台的差异是当前未校准冷却情景的计算结果，不是实测楼宇能力。

## 2. 年度风光接口中的余电路径

`POST /api/operation/pv/run` 和 `POST /api/operation/hybrid/run` 可以携带：

```json
{
  "storage": {
    "capacities_kwh": [0, 5, 10, 20, 50],
    "round_trip_efficiency": 0.90,
    "quote": {
      "cny_per_kwh": 1800,
      "installation_cny": 6000,
      "maintenance_cny_per_year": 300,
      "life_years": 10,
      "source": "用户示例报价"
    },
    "export": {
      "price_cny_per_kwh": 0.25,
      "connection_cny": 5000,
      "source": "用户余电上网情景"
    }
  }
}
```

响应中每个 PV/风光候选都有 `surplus_paths`；S0/0kWp候选也保留零余电结果，便于对账：

```json
{
  "surplus_paths": {
    "surplus_kwh_year1": 123.4,
    "storage": {
      "status": "calculated",
      "candidates": [
        {
          "capacity_kwh": 5,
          "recovered_kwh_year1": 42.1,
          "initial_investment_cny": 15000,
          "annual_bill_saving_cny": 26.8,
          "study_period_net_benefit_cny": -15100.0,
          "simple_payback_years": null,
          "economics_status": "complete"
        }
      ],
      "recommended_capacity_kwh": 0,
      "economics_basis": "独立理想调度上限，不进入四方案或主推荐"
    },
    "export": {
      "path": {
        "surplus_kwh_year1": 123.4,
        "annual_revenue_cny": 30.85,
        "study_period_revenue_cny": 308.5,
        "economics_status": "complete"
      }
    }
  }
}
```

储能与卖电从同一份“发电减当时自用”的无储能余电独立起算；二者不互相扣减，也不改变 S0–S3 的匹配、经济排序或主推荐。容量0不产生储能固定成本；非零容量缺任一报价字段返回 `economics_status:"incomplete"`，不会把缺失报价当作0。卖电价缺失时仍返回物理余电，但卖电经济字段为 `null/incomplete`；未填 `connection_cny` 明确按0并回显。完整契约见 `operation_planning/protocol/storage_surplus_paths_contract.md`。

## 3. 广州电价与高温尖峰

`guangzhou_industrial_lt1kv_202610` 的 `verified` 为 `true`。档案元数据回传官方95598 URL、有效期、适用区域和排除项；公告 PDF 在 `docs/evidence/tariffs/guangdong_agency_tariff_202610_official.pdf`，SHA-256 `36648B430E5F729037DF3D8766232057FEADF518BD39692BFE1EFE3758C91212`。

除7–9月固定尖峰时段外，若输入天气提供逐时 `temperature_2m`，日最高气温达到35℃的其他月份日期，在11:00–12:00及15:00–17:00按尖峰计费。价格响应的 `tariff` 元数据包含：

- `high_temp_super_peak_days`：实际触发规则的日期；
- `high_temp_days` / `high_temp_day_count`：输入天气中日最高温达到阈值的全部日期及数量；
- `high_temp_super_peak_day_count`：上述日期数；
- `super_peak_day_count` / `super_peak_dates_in_window`：固定季节尖峰和高温尖峰合并后的覆盖统计；
- `high_temp_rule`：阈值、时段、缺温度时不启用的说明。

高温尖峰只影响购电/外送费用；不会改变天气、负荷、光伏或风电物理轨迹。将2024天气套用2026档案必须在请求中显式设置 `tariff_application:"current_tariff_on_reference_weather"`，结果是价格情景而非2024历史账单。

## 4. 典型周/月预览修复

`POST /api/operation/hybrid/preview` 的接口和时段选择规则沿用 v6；本轮修复了运行外残差被计入预览缺口的问题。`scope` 仍为 `preview_period_physics_only`，不返回全年经济、碳价、回本或容量推荐。预览逐时字段应与年度同一时间窗切片完全一致；验证证据见 `operation_planning/results/phase2b_carbon_5090/preview_v8_equivalence.json` 和 `scripts/verify_preview_v8_5090.py`。

## 5. 证据与限制

年度 v8 HTTP回放（含6个案例、输入/输出哈希、报价和余电字段）见 `operation_planning/results/phase2b_carbon_5090/replay_cases_v8.json`，查看版见 `docs/handoff/replay_viewer/replay_cases_v8.json`，运行清单见同目录 `run_manifest_v8.json`。三档只是固定示例；用户输入、屋顶可用面积、报价、并网条件和空调负荷适用性仍需确认。系统不声称现场精度、真实节能、售电资格或电池投资回报。
