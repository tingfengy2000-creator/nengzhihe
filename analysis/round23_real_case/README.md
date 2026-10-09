# 第23节：公开真实案例准入与实测证据

后端基线固定为 `feat/5060-product-ui@e7f0cf1d0eed5464835897c1d51db84040cb16a0`。
本目录只有独立数据审查脚本，不改变后端、接口、前端或既有回放。团队确认暂时没有私人建筑电费单，本轮先核查公开来源。

**当前状态：公开实测资料已取得，真实案例校准尚未成立（CALIBRATION_NOT_ESTABLISHED）。**
不能把总表电量与任意参考房间拟合，把缺测补零，或用已有广州情景冒充这两栋建筑。模型运行/拟合次数均为0。

## 已取得的资料

| 来源 | 实际取得 | 可做什么 | 当前不能做什么 |
|---|---|---|---|
| CU-BEMS v6，曼谷朱拉隆功大学 Chamchuri 5 | `2019Floor2.csv`，525,600分钟，36个测量通道，其中16个空调通道；论文、设备与字段说明、许可元数据 | 绘制实际空调用电及缺测分布，检查完整时段与设备范围 | 二层不是整栋楼；没有完全覆盖一年的空调通道；缺分区面积、对应型号/容量/COP、控制与设定点。不能直接套用目录小空调或宣称账单校准 |
| 马德里市政月度能耗数据 | 原始CSV、3页数据字典；确定性选择2024年 Casa Consistorial - Casa de la Villa 的12个月一般有功电量 | 核对一个真实建筑计量点的月度、年度电量 | 不提供发票金额、空调分项和房间/设备配置；传感器实际范围未独立核实。不能与只算制冷除湿的模型直接比较精度 |
| SHIFDR（有限替代核查） | 原始发布入口/ORNL官方目录核查；本机未取得数据 | 记录为未接入候选 | 入口访问受限、未读原始设备与计量说明；不声称已验证或已适配，不继续无限收集 |

原始第三方大文件保存在不入库的 `working/round23/sources/`。公开下载脚本、源URL、许可、SHA-256和CU发布方MD5均保存；仅上传小型派生表与图片，不上传模型权重、私人账单或完整逐时模型响应。

## 实际观察

- CU时间轴完整，步长60秒，没有重复时间戳。16个空调同时有效495,619分钟，占94.295852%；每个空调通道都存在缺测。共同有效分钟的电量积分为186,741.808667 kWh，**这是不完整时段的积分，不是全年账单电量**。
- CU各月共同有效率从58.42%到100%。10月共同通道完整；其他月份保留完整月电量为未知。不能用较低的1、2月柱状值解释真实节能或季节变化。
- 数据中的大型压缩机通道最大观测55.33 kW，不凭“AC”名称就当成现有3个公开参考小空调。`z2_AC11(kW)`所有有限值均为0，只记录现象，不推断真实全年停机原因。
- 固定展示2019年7月1–7日 `z2_AC2(kW)`，168小时中2小时不完整，曲线断开显示；该设备与同区其他空调共同作用，单机服务范围和设定点未知。
- 马德里选中计量点的12个月合计214,828.03516 kWh。选取只用年份、用途、计量类/单位、完整性和名称排序，不用模型误差或投资结果。
- 马德里2024年行政建筑范围305行的ID全部缺失，13行用文本标记“无数据/资料不完整”；保留原始值并排除不完整计量点，没有补0或伪造ID。

## 复查入口

- [中文交接和可用主张](../../operation_planning/protocol/round23_public_case_handoff.md)
- [来源与准入结果](../../operation_planning/results/round23_case_admission/admission_summary.json)
- [12个月实测明细](../../operation_planning/results/round23_case_admission/madrid_selected_12_months.csv)
- [空调通道质量](../../operation_planning/results/round23_case_admission/cu_channel_quality.csv)
- [实际空调周记录](../../operation_planning/results/round23_case_admission/cu_measured_week_hourly.csv)
- [实测图表PDF（3页）](../../operation_planning/results/round23_case_admission/figures/public_measured_evidence.pdf)
- [冻结工作台实际截图与边界](../../docs/handoff/screenshots/round23_public_case/acceptance.md)
- [逐步分析Notebook](./public_case_admission.ipynb)

## 复现

以下均在本台5090完成，第一步仅下载/复用一个CU楼层年文件以及两份说明、马德里CSV。可以保留缓存，不做清理。

```powershell
Set-Location E:\比赛\nengzhihe
& C:\Python314\python.exe -X utf8 -m analysis.round23_real_case.fetch_sources
& C:\Python314\python.exe -X utf8 -m analysis.round23_real_case.inspect_sources
& C:\Python314\python.exe -X utf8 -m analysis.round23_real_case.verify_outputs
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 -m analysis.round23_real_case.render_evidence
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe' -png -r 110 operation_planning/results/round23_case_admission/figures/public_measured_evidence.pdf operation_planning/results/round23_case_admission/figures/measured_page
```

运行环境与实际命令、源码提交、输入输出哈希见 `analysis_run_manifest.json`、`verification.json`、`figures/render_manifest.json`。CSV审查使用已有Python3.14/pandas/numpy，PDF使用现有桌面依赖Python3.12/ReportLab；同一5090机器，没有借用其他机器或云端执行。Notebook仅封装上述真实审查和保存的输出，不调用模型。

再次下载时，若远端字节变化，需要将新哈希另存为版本，不与本轮快照成绩混用。下载失败记录保留；公开跳转的临时签名参数已从可提交清单剔除。

## 来源和署名

CU-BEMS：Pipattanasomporn等，Scientific Data 7, 241 (2020)，[论文](https://www.nature.com/articles/s41597-020-00582-3)、[原始数据](https://doi.org/10.6084/m9.figshare.11726517)、[作者说明](https://sgrudata.github.io/)。数据许可CC BY 4.0；派生分析包括时段过滤、质量计数、功率积分和图表，均由本项目生成，没有重写原始测量值。

马德里：Ayuntamiento de Madrid，[官方数据目录及许可](https://datos.gob.es/en/catalogo/l01280796-consumo-de-energia-en-edificios-municipales-datos-mensuales)、[CSV](https://datos.madrid.es/dataset/300430-0-consumo-energia-edificios/resource/300430-0-consumo-energia-edificios-csv/download/datos-abiertos_consumo-energia-edificios.csv)。CC BY 4.0；派生分析为2024年一个计量点的筛选、十进制解析和月度求和。字典版本2024年5月；远端CSV会更新，以本轮SHA-256固定快照。

电费口径依据：[美国能源部FEMP](https://www.energy.gov/cmei/femp/evaluating-your-utility-rate-options)。电量费、需量费、固定费分开，不用账单金额直接除一个单价倒推kWh。
