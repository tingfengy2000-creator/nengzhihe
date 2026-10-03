# 数据与实验边界

本轮用官方 BOPTEST `bestest_air` v0.9.0 的固定 FMU 做本地物理回放。它是公开建筑性能模型，不是运营楼宇数据、现场试点或实测节能结果。工作台不读取故障标签、文件名、注入参数或预置答案。

Windows 机器上先运行 `powershell -ExecutionPolicy Bypass -File operation_planning/protocol/fetch_boptest.ps1`，再按仓库根目录 README 配置 WSL 的 FMPy 与运行时库。Docker 或公共服务不可用时，系统使用同一官方 FMU 的本地回放；公共 API 的连接状态记录在 `boptest_source.json`。

`experiment_freeze.json` 在正式留出评价前冻结了日期块、候选网格、停止条件和比较对象。日期块是同一仿真系统的时间留出，不能写成跨设备或真实建筑验证。结果文件必须同时保留全体候选、拒绝原因、运行时和适用边界。
