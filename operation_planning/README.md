# 能智核——公共建筑空调运行方案试算与优化智能体

展示主张：**先试算，再决策。**

本目录是独立增强分支上的产品链，不改动前四轮源码和发布包。它把一个公共办公单元的用户约束转成可审核的候选运行方案，调用固定的官方 BOPTEST `bestest_air` v0.9.0 FMU 做离线回放，再返回温度带、用电、动态电价费用、恢复窗口和拒绝原因。它不接管 BMS，也不把仿真结果写成现场节能或人工提效。

## 启动

先准备官方模型：

```powershell
powershell -ExecutionPolicy Bypass -File operation_planning/protocol/fetch_boptest.ps1
```

本机验证过的执行链是 Windows → WSL Ubuntu-24.04 → FMPy 0.3.22 → FMI 2.0 co-simulation FMU。`runtime/boptest_linux/lib4` 是为官方 Linux FMU 提供 `libgfortran.so.4` 的运行时补充。Docker 未安装时不影响本地 FMU 回放；公共服务连接状态记录于 `protocol/boptest_source.json`。

```powershell
# 可选：先启动已配置的本地 Qwen3-4B llama.cpp 服务
powershell -ExecutionPolicy Bypass -File runtime/start_model.ps1

# 启动免安装工作台（仅监听本机）
python operation_planning/run_server.py
# 浏览器打开 http://127.0.0.1:18765
```

命令行最小真实回放：

```powershell
python scripts/operation_planning_demo.py --day 153 --max-candidates 2 --step-seconds 1800
```

## 产品边界

`schemas.py` 的 `TaskSpec`、`PlanSpec`、`SimulationResult` 和 `DecisionReport` 是前后端共享合同。业务营业时段与模型占用/内部得热分开保存；缺少模拟日期不会静默猜测。`search.py` 只使用预注册的候选网格，最多 36 个方案，按可行性优先、再按目标值排序，并保留全部方案和原因。价格、功率和温度全部由程序从模型输出计算。

`agent.py` 是一个真实的本地模型工具反馈循环，允许工具为 `get_case_context`、`validate_task`、`evaluate_plan`、`search_plans`、`get_violation_details`、`compare_results`、`prepare_report`，最多 8 轮。模型不能直接写数值结论；模型不可用、输出截断或工具调用不合规时明确失败，不伪装成表单成功。

## 实验与证据

`protocol/experiment_freeze.json` 预先冻结开发日期、6 个时间留出日期块、方案网格、比较组和评价分母。A0/A1/A2 比较物理回放；B0/B1/B2 比较结构化输入、单轮模型和完整工具反馈；C2 是去掉新增反馈机制的必要消融。旧风阀 56 个基础工况与 112 条扰动记录仍只作历史回归，不作为本轮新结果。

公开模型属于物理实验模型回放来源，不是实际运营楼宇。只有在本地实跑并保存逐例 JSON 后，才能在申报中写入对应数值；无真实参与者时不写用户提效；无优势时保留无增益结果。
