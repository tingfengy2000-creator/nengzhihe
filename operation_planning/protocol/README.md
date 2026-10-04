# 数据与实验边界

本轮用官方 BOPTEST `bestest_air` v0.9.0 的固定 FMU 做本地物理回放。它是公开建筑性能模型，不是运营楼宇数据、现场试点或实测节能结果。工作台不读取故障标签、文件名、注入参数或预置答案。

Windows 机器上先运行 `powershell -ExecutionPolicy Bypass -File operation_planning/protocol/fetch_boptest.ps1`，再按仓库根目录 README 配置 WSL 的 FMPy 与运行时库。Docker 或公共服务不可用时，系统使用同一官方 FMU 的本地回放；公共 API 的连接状态记录在 `boptest_source.json`。

`experiment_freeze.json` 在正式留出评价前冻结了日期块、候选网格、停止条件和比较对象。日期块是同一仿真系统的时间留出，不能写成跨设备或真实建筑验证。结果文件必须同时保留全体候选、拒绝原因、运行时和适用边界。

`external_physical.py` 和 `external_physical_source.json` 对 OEDI/LBNL 的 `MZVAV-2-1.csv` 做有限物理实测适配。当前跟踪的六个完整日期块包含三个加热盘管旁通泄漏实验日和三个无故障日；所有日期、强度和 `Fault Detection Ground Truth` 都只用于事后核对，未进入诊断输入。该导出没有区温、能耗和实际执行器位置，所以准入门只证明来源、时间轴、单位和点位边界，并拒绝反事实方案评分。
