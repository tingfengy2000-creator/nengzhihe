# 阶段二B API 与结果契约

## 接口

`POST /api/operation/hybrid/run` 接收 `site_id`、`year`、`room`、`pv`、`hybrid`、`request` 和 `use_agent`。`pv` 提供屋顶、朝向、电价和PV报价；`hybrid` 是光伏/风机组合的权威任务对象，包含容量、风机、预算、购电/外送政策、研究年限、折现率、共享接入费及两类报价。确定性模式直接计算；`use_agent=true` 先解释修改，再调用真实工具。

成功响应为 HTTP 200：`{status:"success", report}`。`report.candidates[]` 的物理量单位为 kWh、kWp、元；`economics.capex_cny` 为初始投入，`npv_cny` 为净现金流现值，`total_cost_npv_cny` 为成本现值，`incremental_npv_vs_s0_cny` 为相对只购电基线的增量现值。

确定性模式输入错误由HTTP 400返回：`{status:"failed", error:"异常类型:说明"}`。`use_agent=true`时，模型结构化失败或参数冲突由HTTP 422返回：`{status:"failed"|"needs_clarification", agent:{...}, error:"..."}`；`needs_clarification`不能被程序兜底改写成成功。

## 状态

- `admission_status=eligible`：约束满足且经济输入完整，可进入有限推荐。
- `admission_status=excluded`：面积、预算或高度等已知硬约束不满足，保留排除原因。
- `admission_status=unknown`：可能满足约束但报价、外送价或必要条件缺失，不能称被其他方案击败。
- `admission_status=equivalent`：与已列候选配置重复，仅作等价标识。
- 推荐 `conditional` 表示所有可能适用候选已核实；`conditional_subset` 表示只对已核实子集给条件推荐；`not_available` 表示没有可推荐的核实候选。
- 服务 `service_gap` 仍可做当前负荷情景试算，但不能称同等服务水平下的最优投资。

## 重算边界

| 变化 | 影响与当前实现 |
| --- | --- |
| 仅展示字段/排版 | 不应改变请求或结果；静态回放只读展示。 |
| 负荷、使用时段、天气、设备、容量、朝向 | 需要更新受影响的物理计算，并继续更新匹配和经济结果。当前HTTP接口不承诺跨请求缓存，确定性调用会按完整规划链重算。 |
| 报价、预算、电价 | 物理发电不变；预算/报价会改变候选准入和经济结果，电价会改变计费和经济结果。当前接口仍按完整规划函数执行，不要把它描述为已经实现的增量缓存。 |
| 外送开关或外送上限 | 物理发电不变，但需要重新分配外送与弃电，再更新经济结果。 |
| Agent自然语言修改 | `interpret_request`接收经过schema校验的嵌套 `room`/`hybrid` 参数并改变任务；其他工具按当前规范使用空参数，读取同一次完整规划的中间结果。 |

改变展示字段不应重算。Agent只提交经过schema校验的嵌套 `room`/`hybrid` 修改，工具参数为空并不表示任务参数为空；参数在前一轮解释与验证后进入权威任务对象。

阶段二B目前没有独立服务端导出路由；前端导出必须从当前已显示的同一份 `report` 生成，不能为导出再次调用完整计算。固定回放入口见 `docs/handoff/replay_viewer/`，它不导入仿真核心。
