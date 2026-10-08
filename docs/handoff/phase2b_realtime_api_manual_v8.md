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
      "cny_per_kwh": 553.94,
      "installation_cny_per_kwh": 489.88,
      "maintenance_cny_per_year": 300,
      "life_years": 10,
      "source": "CNESA Datalink：2025年储能中标价格分析（2小时系统与EPC均价）",
      "source_url": "https://www.esresearch.com.cn/report/info/detail/?id=6645",
      "source_note": "2小时系统553.94 + 2小时EPC差额489.88；容量线性安装项，仅作示例拆分"
    },
    "export": {
      "price_cny_per_kwh": 0.25,
      "connection_cny": 0,
      "source": "华福证券：分布式光伏行业深度（公开市场化余电示例）",
      "source_url": "https://www.ndrc.gov.cn/xwdt/tzgg/202502/t20250209_1396067.html",
      "reference_url": "https://pdf.dfcfw.com/pdf/H3_AP202406141636236987_1.pdf",
      "policy_source": "国家发展改革委：关于深化新能源上网电价市场化改革的通知",
      "source_note": "公开行业案例以0.25元/kWh作市场化余电示例；政策要求市场化结算，不代表广东固定上网价；小档并网投入按0元粗算"
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

## 6. 只读任务理解接口（第18节增量）

这两个接口只负责探测本地模型和把中文请求解析为**待核验修改项**；它们不调用热湿、光伏、风电、匹配或生命周期计算。解析成功也不等于规划任务成功，后续仍须将 `changes` 合并到权威任务对象并经过原有校验。

### 6.1 `GET /api/operation/agent/status`

服务端只探测配置指定的 loopback `/v1/models`，超时或配置缺失都返回可读的离线状态，不泄露模型路径、机器路径或账号信息。

在线响应：

```json
{
  "available": true,
  "mode": "local_model",
  "label": "本地大模型",
  "checked_at": "2026-10-08T01:23:45Z",
  "reason": null
}
```

离线响应：

```json
{
  "available": false,
  "mode": "local_model",
  "label": "本地大模型",
  "checked_at": "2026-10-08T01:23:45Z",
  "reason": "本地模型未启动"
}
```

### 6.2 `POST /api/operation/agent/parse`

请求必须同时提供非空中文 `request` 和完整的 `current_task` 对象。接口只接受当前任务词汇表中的字段，模型返回的 `from` 会被服务端用 `current_task` 的值覆盖，防止模型伪造旧值。当前允许的修改路径包括：

`room.units_per_room`、`room.room_count`、`room.start_hour`、`room.end_hour`、`room.area_m2`、`room.equipment_id`、`hybrid.budget_cny`、`hybrid.budget_multiplier`、`hybrid.pv_capacity_kwp`（兼容表单路径 `pv.capacity_kwp`）、`hybrid.allow_export`、`hybrid.import_price_cny_per_kwh`、`hybrid.export_price_cny_per_kwh`。

成功且无追问：

```json
{
  "status": "ok",
  "changes": [
    {"field": "hybrid.budget_cny", "from": 90000, "to": 60000, "label": "预算"}
  ],
  "unsupported": [],
  "question": null,
  "model": "local_model",
  "latency_ms": 182.4
}
```

有不支持内容时不能静默丢弃；即使其他修改可解析，也必须在 `unsupported` 中列出原意：

```json
{
  "status": "ok",
  "changes": [],
  "unsupported": ["把储能设置为每天自动套利"],
  "question": null,
  "model": "local_model",
  "latency_ms": 205.1
}
```

缺少关键参数或原话存在冲突时返回 `needs_clarification`，不得自行猜测：

```json
{
  "status": "needs_clarification",
  "changes": [],
  "unsupported": [],
  "question": "请给出晚上使用时段的开始和结束时间，例如18:00到22:00。",
  "model": "local_model",
  "latency_ms": 190.7
}
```

空请求、错误的 `current_task` 或模型输出结构非法时返回 `failed`，并给出中文 `reason`；本地模型未配置、未启动或请求超时时返回 `unavailable`，例如：

```json
{
  "status": "unavailable",
  "changes": [],
  "unsupported": [],
  "question": null,
  "reason": "未找到本地模型配置",
  "model": "local_model",
  "latency_ms": 0.3
}
```

六个中文契约样例（示意请求文本；数值修改必须由用户原话或已确认相对量提供）：

| 场景 | 中文请求 | 预期状态 | 关键响应 |
|---|---|---|---|
| 台数 | `每间改成3台空调` | `ok` | `room.units_per_room=3` |
| 型号 | `型号换成midea_gaia12` | `ok` | `room.equipment_id=midea_gaia12`；目录外品牌进入 `unsupported` |
| 预算 | `预算改为60000元，其他条件不变` | `ok` | `hybrid.budget_cny=60000` |
| 使用时段 | `使用时间改为18:00到22:00` | `ok` | `room.start_hour=18`、`room.end_hour=22` |
| 卖电开关 | `不卖电，余电全部弃用` | `ok` | `hybrid.allow_export=false` |
| 光伏容量 | `光伏容量改为2kWp` | `ok` | `hybrid.pv_capacity_kwp=2` 或 `pv.capacity_kwp=2` |

另外四类边界样例：

| 场景 | 中文请求 | 预期状态 | 关键响应 |
|---|---|---|---|
| 不支持能力 | `请把储能每天按峰谷价自动套利并保证回本` | `ok`（有不支持项） | `unsupported` 列出储能套利/回本承诺，不能伪造 `changes` |
| 信息不足追问 | `把空调改成晚上使用` | `needs_clarification` | `question` 请求开始/结束时间 |
| 本地离线 | 任意非空请求，模型未启动 | `unavailable` | `reason=本地模型未启动`；不调用规划计算 |
| 输入无效 | `request=""` 或缺少 `current_task` | `failed` | 中文 `reason`；HTTP入口当前统一带 `field=request`，message说明具体缺失项 |

`unsupported`、`needs_clarification`、`unavailable` 和 `failed` 都是可见状态，不得由确定性兜底结果改写为 Agent 成功。真正的计算仍使用 `/api/operation/pv/run`、`/api/operation/hybrid/run` 或异步任务；参数校验、报价缺失、外送价缺失及服务缺口的原有错误语义继续有效。
