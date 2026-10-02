# 能智核

公共建筑用能异常核验工作台，参赛方向为“智慧能源与环境”。首轮重点是验证补证策略是否有实际价值；节能机会筛查是附属能力。项目独立运行，所有脚本仅管理本目录的工作台与模型，不涉及“乡艺有据”。

## 首轮实际结果与取舍

冻结留出评测已经完成。预算 4 的主比较中，固定流程、自适应规则、本地模型和完整信息均为 **10/42 正确、0 错误、32 未决**；整体正确率为 **23.8%**，未决记录计入分母，不能把“零错判”表述为高准确率或全场景可靠。

本地模型与自适应规则相比没有增加正确数，也没有减少平均查询：分别为 3.238 与 3.190 查询单位；平均运行耗时分别约 641.6 与 1.7 毫秒。这是本轮实际运行记录，不是稳定时延承诺。预算 2、3 为次要分析，不替代预设的预算 4 主比较。

**继续保留核验工作台、来源区分、数据修正后复核和证据记录；收缩“大模型主动补证带来增益”的创新表述。** 本地模型保留为实验选项，不追加复杂架构。结果仅涉及一套仿真机组的 21 个基础日工况及其重复记录扰动，共 7 个日期块；42 条记录不是 42 栋独立楼宇。完整指标见 `output/benchmark.json`、`output/benchmark_report.txt` 和 `output/evaluation_v1/metrics.csv`。

## 打开已有工作台

在本项目根目录执行 PowerShell：

```powershell
& .\scripts\start.ps1
```

浏览器打开 [核验工作台](http://127.0.0.1:18190)。启动脚本使用 Codex bundled Python，后台隐藏窗口；本地模型使用项目内的 llama.cpp 与 Qwen3-4B-Q4_K_M。两个服务只监听本机：

| 服务 | 地址 | 进程记录 | 日志 |
|---|---|---|---|
| 工作台 | `127.0.0.1:18190` | `runtime/workbench_process.json` | `runtime/workbench.stdout.log`、`runtime/workbench.stderr.log` |
| 本地免费模型 | `127.0.0.1:18191` | `runtime/server.pid` | `runtime/server.stdout.log`、`runtime/server.stderr.log` |

模型文件尚未准备时，可用 `& .\scripts\start.ps1 -SkipModel` 打开确定性策略。界面读取真实模型健康状态；连接或动作格式错误不会用规则结果冒充模型结果。下载需要联网，下载后的模型推理通过本机接口完成，不使用付费 API。

启动脚本不会占用、停止或重配现有未知服务。如果早期工作台通过相对路径 `server.py` 启动，脚本无法仅凭命令行证明其工作目录，会拒绝认领。请从原启动终端结束那次启动，再使用本项目脚本；不要按端口或进程名批量结束进程。

停止前可先核对计划：

```powershell
& .\scripts\stop.ps1 -WhatIf
& .\scripts\stop.ps1
# 只停止工作台、保留本项目模型：
& .\scripts\stop.ps1 -KeepModel
```

停止脚本核对 PID、完整可执行路径、项目脚本路径与端口参数，并检查工作台进程创建时间；身份不一致时拒绝停止。源码或模型变更后需要重新启动相应服务，但冻结评测后不应变更算法、提示词或运行配置。

## 三个演示入口

界面默认展示三个独立演示，开发案例可通过“展开开发案例”查看。来源、扰动与修正状态均有明确标记。

1. **真实建筑 · 用能回放**：BDG2 实测电表与历史参考曲线，单位为 `kWh`。采用固定统计回放，不调用模型、不参加设备故障策略比较。相对参考的差额是筛查线索，不是已实现或保证可实现的节能量。
2. **空调机组 · 证据核验**：LBNL 单风道空调机组仿真；在相同证据池内选择固定流程、自适应规则、本地模型或完整信息。所有数值与最终判断由共同程序计算。
3. **记录修正 · 持续核查**：在仿真记录中明确插入完全重复行。先查看数据问题与设备疑点，再点击“修正数据问题”，重新执行核验。修正仅去重，不消除原有设备过程；质量通过不等于设备正常。

“开始核验”实际完成后，右侧逐步回放已经返回的真实证据。每次记录注明执行策略、预算、查询成本、耗时及警告，可导出 JSON。诊断展示规则证据与适用边界，不显示未经校准的故障概率。

LBNL 的第一个查询固定为记录质量检查，成本为 1；另外 3 组是混风过程、盘管响应和运行工况。预算 1 只能完成质量检查。完整信息强制使用预算 4，只在同为预算 4 时作公平比较；它是信息充分参照，不保证性能上界。现场补采次数在本次离线回放中为 0，真实现场补采成本尚未测量，不等于现场取证免费。

## 数据与证据边界

- **BDG2 实测轨道**：仅少量真实公共建筑历史回放，没有设备故障真值。原始项目见 [Building Data Genome 2](https://github.com/buds-lab/building-data-genome-project-2)。
- **LBNL 仿真轨道**：一套单风道空调机组的正常及指定故障工况。数据与点位说明见 [LBNL 官方说明](https://fdddata.lbl.gov/data/Simulated_LBNL_FDD_Data_Sets_SDAHU/LBNL_FDD_Data_Sets_SDAHU.pdf)。不将仿真结果推广为已验证的真实楼宇故障定位能力。
- **人为扰动**：记录重复等扰动与原始工况分开标记，同源扰动属于成对记录，不能作为新增独立建筑或独立场景计数。
- 实际阀位、故障注入标记、源文件故障名称等不作为策略输入。开发标签与留出标签分开保存，网页不暴露留出案例及标签。
- 数据查询、现场补采、算法耗时分别记账。不存在已验证的试点、客户合作或实际节能收益声明。

下载来源与摘要见 `data/source_manifest.json`；处理约定见 `data/data_contract.json`。数据许可与来源要求以原始说明及 `data/raw/` 保留的许可文件为准。模型和运行器的固定版本、许可、摘要及下载说明见 [runtime/README.txt](runtime/README.txt)。不要把 CUDA 第三方组件统一标成 llama.cpp 的 MIT 许可。

## 复现顺序

以下“准备与冻结”用于尚未冻结的新实验。**已有 `output/protocol_frozen.json` 时，不要重跑 `prepare_data.py`、`prepare_engine.py` 或 `freeze.py`，即使认为输出确定性相同。** 已冻结实验的复现直接使用末尾的评测命令和新输出目录。

先从项目根目录确定 bundled Python：

```powershell
$NzhPython = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $NzhPython -X utf8 .\scripts\prepare_data.py --download
& $NzhPython -X utf8 .\scripts\prepare_data.py --prepare
```

默认准备命令只公开开发与演示案例。按固定模型版本完成下载、摘要核验与一次接口检查；模型接口检查不属于诊断性能实验：

```powershell
& $NzhPython -X utf8 .\runtime\download_runtime.py
& $NzhPython -X utf8 .\runtime\verify_downloads.py
& .\scripts\start.ps1
```

慢连接的分段下载命令见 `runtime/README.txt`。然后只用开发数据准备共同规则与策略配置：

```powershell
& $NzhPython -X utf8 .\scripts\prepare_engine.py
```

开发与演示检查用于排错、确定方案，不是留出成绩。开发参数确定后，由**数据准备方**按固定划分构建封存案例；开发和评测操作者不能通过查看这些载荷或标签调整方法：

```powershell
# 仅用于尚未冻结的新实验，由数据准备方执行封存构建。
& $NzhPython -X utf8 .\scripts\prepare_data.py --prepare --include-holdout
& $NzhPython -X utf8 .\scripts\freeze.py
```

封存构建会读取原始源记录，不等于方法开发端已查看留出案例。冻结文件记录规则、策略、提示词/客户端、模型配置、数据约定和封存清单的摘要；这是可审核流程记录，不是分析者盲态的密码学证明。冻结后不得根据结果调规则、改提示词或更换案例。

第一次正式评测：

```powershell
& $NzhPython -X utf8 .\scripts\run_benchmark.py --output-dir output/evaluation_v1
```

再次复现已有冻结实验，只启动所需服务并指定新目录，不重新准备或冻结：

```powershell
& .\scripts\start.ps1
& $NzhPython -X utf8 .\scripts\run_benchmark.py --output-dir output/evaluation_reproduction_01
```

评测脚本在运行前后校验冻结摘要，保存所有预测后才打开留出标签计分。新目录保留该次预测、执行回执、逐条结果与 `metrics.csv`；原目录中的记录不被覆盖。工作台使用的 `output/benchmark.json` 与 `output/benchmark_report.txt` 会刷新为最近一次汇总。时延受模型缓存与机器负载影响，固定种子不构成时延逐位一致承诺。

“对照实验”页面只读取实际评测输出。主比较须同时审查正确/错误/未决、查询次数、模型调用及耗时；如果主动策略没有增益，就收缩创新表述，不追加复杂架构来掩盖结果。

## 文件与比赛材料

| 位置 | 用途 |
|---|---|
| `web/` | 无构建依赖的中文交互工作台 |
| `engine.py`、`policies.py` | 共同数值/证据规则与四种取证策略 |
| `model_client.py` | 仅允许本地模型选择白名单动作 |
| `scripts/` | 数据准备、开发准备、冻结、评测、安全启停 |
| `runtime/` | 本地模型、运行器、许可、运行配置与日志 |
| `output/` | 运行记录、冻结协议、实际评测结果 |
| `materials/` | 依照比赛模板准备的受控申报底稿 |

比赛材料按上传的指南、项目简表、项目说明书与商业计划书的章节、字数、格式和匿名要求准备。**当前材料是受控底稿，不能仅凭文件存在就视为可提交终稿。** 正式提交前需核对实际实验数字、报名字段与匿名口径，完成所有页面渲染检查；不得填造试点、合作、性能、营收或节能收益。

源码打包保留复现脚本、许可与来源说明，不默认打包原始大数据、模型二进制、下载分块、`.part` 临时文件及私有留出标签。是否提供数据须按比赛要求和各来源许可核定。
