# 阶段二B API 与结果契约

## 接口

`POST /api/operation/hybrid/run` 接收 `site_id`、`year`、`room`、`pv`、`hybrid`、`request` 和 `use_agent`。`pv` 提供屋顶、朝向、电价和PV报价；`hybrid` 是光伏/风机组合的权威任务对象，包含容量、风机、预算、购电/外送政策、研究年限、折现率、共享接入费及两类报价。确定性模式直接计算；`use_agent=true` 先解释修改，再调用真实工具。

成功响应为 `{status:"success", report}`。`report.candidates[]` 的物理量单位为 kWh、kWp、元；`economics.capex_cny` 为初始投入，`npv_cny` 为净现金流现值，`total_cost_npv_cny` 为成本现值，`incremental_npv_vs_s0_cny` 为相对只购电基线的增量现值。

## 状态

- `admission_status=eligible`：约束满足且经济输入完整，可进入有限推荐。
- `admission_status=excluded`：面积、预算或高度等已知硬约束不满足，保留排除原因。
- `admission_status=unknown`：可能满足约束但报价、外送价或必要条件缺失，不能称被其他方案击败。
- `admission_status=equivalent`：与已列候选配置重复，仅作等价标识。
- 推荐 `conditional` 表示所有可能适用候选已核实；`conditional_subset` 表示只对已核实子集给条件推荐；`not_available` 表示没有可推荐的核实候选。
- 服务 `service_gap` 仍可做当前负荷情景试算，但不能称同等服务水平下的最优投资。

## 重算边界

改变负荷时重算负荷、发电匹配和经济；改变天气、容量、朝向时重算受影响的发电、匹配和经济；改变报价、预算、电价或外送条件只重算约束/经济层（物理发电不变）。改变展示字段不应重算。Agent只提交经过schema校验的嵌套 `room`/`hybrid` 修改，工具参数为空。

错误响应使用 HTTP 400；模型任务无法结构化或参数冲突时为 `failed` 或 `needs_clarification`，不使用确定性兜底冒充成功。
