# 阶段二B第18节接口交接说明（5090）

本文件只记录第18节新增的本地模型状态/任务解析接口及第15/16节储能余电示例口径。它不改变热湿、光伏、风电、匹配、生命周期或四方案推荐，也不替代 [`phase2b_realtime_api_manual_v8.md`](../../docs/handoff/phase2b_realtime_api_manual_v8.md) 的完整接口字段。源码和证据的最终提交 SHA 由主代理在提交后填写；本文件不把工作树状态写成已发布版本。

## 1. `GET /api/operation/agent/status`

服务端只探测 `runtime/local_model_config.json` 指定的 loopback `/v1/models`，不会访问公网，不返回模型权重、账号或机器路径。

在线：

```json
{
  "available": true,
  "mode": "local_model",
  "label": "本地大模型",
  "checked_at": "2026-10-08T01:23:45Z",
  "reason": null
}
```

离线、未配置或探测超时：

```json
{
  "available": false,
  "mode": "local_model",
  "label": "本地大模型",
  "checked_at": "2026-10-08T01:23:45Z",
  "reason": "本地模型未启动"
}
```

离线时只能提示用户改用确定性结构化表单/接口；不能把规划结果朗读为 Agent 已完成，也不触发后台计算。

## 2. `POST /api/operation/agent/parse`

请求：

```json
{
  "request": "预算改为60000元，其他条件不变",
  "current_task": {
    "room": {"area_m2": 35, "room_count": 1, "units_per_room": 2,
              "start_hour": 8, "end_hour": 18},
    "hybrid": {"budget_cny": 90000, "pv_capacity_kwp": 1}
  }
}
```

`current_task` 是旧值的唯一来源；模型的 `from` 字段不具权威性。当前允许字段如下：

| 路径 | 类型/范围 |
|---|---|
| `room.units_per_room`、`room.room_count` | 正整数 |
| `room.start_hour`、`room.end_hour` | 开始0–23，结束1–24 |
| `room.area_m2` | 正数 |
| `room.equipment_id` | 当前公开型号目录中的ID |
| `hybrid.budget_cny`、`hybrid.pv_capacity_kwp`、`pv.capacity_kwp`、`hybrid.import_price_cny_per_kwh` | 非负有限数 |
| `hybrid.budget_multiplier` | 非负有限数；只表达相对预算变化 |
| `hybrid.allow_export` | 布尔值 |
| `hybrid.export_price_cny_per_kwh` | 非负有限数或 `null` |

成功：

```json
{
  "status": "ok",
  "changes": [{"field": "hybrid.budget_cny", "from": 90000,
               "to": 60000, "label": "预算"}],
  "unsupported": [], "question": null,
  "model": "local_model", "latency_ms": 182.4
}
```

不支持项不能静默丢弃：

```json
{
  "status": "ok", "changes": [],
  "unsupported": ["把储能每天按峰谷价自动套利并保证回本"],
  "question": null, "model": "local_model", "latency_ms": 205.1
}
```

需要补充信息时：

```json
{
  "status": "needs_clarification", "changes": [], "unsupported": [],
  "question": "请给出晚上使用时段的开始和结束时间，例如18:00到22:00。",
  "model": "local_model", "latency_ms": 190.7
}
```

模型离线时：

```json
{
  "status": "unavailable", "changes": [], "unsupported": [],
  "question": null, "reason": "本地模型未启动",
  "model": "local_model", "latency_ms": 20.1
}
```

空文本、缺少 `current_task`、字段类型错误或模型 JSON 不符合契约时为 `failed`，并返回中文 `reason`。HTTP 外层对这类请求返回400并带 `field`（当前入口统一定位为 `request`，响应 `message` 会说明实际缺失项）；模型理解出的不支持内容属于正常解析响应中的 `unsupported`，不能当作成功计算。

## 3. 六个中文回放样例

下面样例是接口契约的可读任务起点；除“离线”和“输入无效”外，不把模型未运行时的结构示例冒称实测。

| 编号 | 请求文本 | 预期状态 | 需保留的结果 |
|---|---|---|---|
| A1 | `每间改成3台空调` | `ok` | `room.units_per_room=3` |
| A2 | `型号换成midea_gaia12` | `ok` | `room.equipment_id=midea_gaia12` |
| A3 | `预算改为60000元，其他条件不变` | `ok` | `hybrid.budget_cny=60000` |
| A4 | `使用时间改为18:00到22:00` | `ok` | `room.start_hour=18`、`room.end_hour=22` |
| A5 | `不卖电，余电全部弃用` | `ok` | `hybrid.allow_export=false` |
| A6 | `光伏容量改为2kWp` | `ok` | `hybrid.pv_capacity_kwp=2` 或 `pv.capacity_kwp=2` |

边界样例：

| 编号 | 请求文本 | 预期状态 | 需保留的结果 |
|---|---|---|---|
| B1 | `请把储能每天按峰谷价自动套利并保证回本` | `ok`带 `unsupported` | 不生成储能套利/回本保证字段 |
| B2 | `把空调改成晚上使用` | `needs_clarification` | 追问开始与结束时间，不猜测时段 |
| B3 | 任意非空请求且本地模型未启动 | `unavailable` | 提示离线；不以确定性结果冒充 Agent 成功 |
| B4 | `request=""` 或省略 `current_task` | `failed`/HTTP400 | 中文 `reason` 和 `field`，不进入计算 |

`ok` 只表示修改项通过结构化解析与字段校验，不表示候选已计算、推荐已更新或经济结论成立。修改项必须随后交给已有计划接口；后续接口返回的 `failed`、`needs_clarification` 或缺报价状态继续对用户可见。

## 4. v9 储能/余电字段对齐

`operation_planning/protocol/storage_surplus_paths_contract.md` 的 v9 请求示例固定如下口径：

- 储能系统均价 `553.94 元/kWh`，容量线性安装项 `489.88 元/kWh`（CNESA Datalink 2025：2小时 EPC 1043.82 减系统均价），年运维 `300 元/年`，寿命10年。
- 卖电 `0.25 元/kWh` 是用户敏感性，不是广东固定结算价；小档 `connection_cny=0` 只是尚未取得并网/计量报价的粗算假设。
- `storage.quote.source` / `source_url` 指向 CNESA 页面；`export.source`、`reference_url` 和 `policy_source` 分别保留公开行业示例、公开报告和国家发改委市场化结算政策边界。

这些字段只影响附加储能/卖电卡片，不改变 S0–S3、主推荐或物理轨迹。缺少非零储能必要报价或卖电价格时返回 `incomplete`/空经济字段，不静默按0；容量0不产生储能固定成本。来源明细见 `docs/evidence/storage_surplus_quotes.md`，第16节完整比较见 `phase2b_round16_handoff_5090.md`。

## 5. 离线与安全边界

本地模型端点必须是 loopback `/v1`；不存在公网回退。模型不可用时仍可使用确定性接口和仓库缓存天气，但这两种路径的结果必须在记录中分开标记。任何模型返回的价格、设备、容量或时段修改，都要经过同一任务对象的类型/范围校验；未被支持的字段必须显式显示，不能通过正则兜底后标记 Agent 成功。

## 6. 5090 实测记录

在提交 `b14c53ce707d2ea118a672829f2aa1fe7154785a` 的代码上，使用 `python scripts/verify_agent_parse_round18.py` 对 loopback 服务执行六个支持样例和三个边界请求；六个支持样例的模型 `latency_ms` 为 186.98–394.33 ms，状态探测 HTTP 往返为 31.93 ms，所有断言通过。离线状态由 `tests.test_agent_parse_contract` 的补丁配置契约覆盖；不会把确定性结果冒充模型成功。原始响应和哈希见 `operation_planning/results/phase2b_agent_round18/agent_parse_http_results.json`，运行清单见同目录 `run_manifest_round18.json`。该解析请求只返回修改建议，没有调用任何规划计算函数。

## 7. 18.4 精简回放补字段

`scripts/compact_replay_v9.py` 在保留完整回放现金流的前提下，为每个候选 `economics` 保留或恢复 `simple_payback_years` 与 `annual_saving_after_maintenance_cny`；缺报价或年净节省不为正时回本年限仍为 `null`。本次只重生界面精简文件，没有重跑热湿、发电或生命周期模型：`docs/handoff/replay_viewer/replay_cases_ui_v9.json` 共6案、7,849,491 bytes（约7.49 MiB），所有候选均含这两个字段；完整回放未覆盖。
