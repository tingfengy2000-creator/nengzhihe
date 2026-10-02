能智核 第三轮交付
公共建筑用能异常核验工作台 / 智慧能源与环境

一、启动与停止
本目录为独立版本；运行不读取 round2、首轮目录或“乡艺有据”。本机已启动 http://127.0.0.1:18193/?demo=3 。
Windows PowerShell 在本目录执行：
  .\scripts\start.ps1
停止仅此版本：
  .\scripts\stop.ps1
脚本核验进程路径、端口和创建时间，不强占其他程序端口。可用 -PythonPath 指定解释器。
其他已安装 Python 3.11+ 的环境：
  python -m pip install -r requirements.txt
  python -X utf8 server.py --port 18193
验证环境为 Python 3.12.14、numpy 2.3.5、pandas 3.0.1。要求的 Python/依赖不打包成便携可执行文件；独立副本检查采用同一已安装解释器，检验的是目录自包含性，不是新机器安装认证。

二、完整原始 CSV 操作任务
1. 打开工作台，点击“导入公开CSV”，用“选择本地CSV”选择：
   data/public_csv/LBNL_SDAHU_2018-04-10_raw_excerpt.csv
2. 时间列选择 Datetime，原始采样间隔选择 1 分钟。
3. 当前17类允许点位按同名列映射；温度单位为 degF，两个 *_SPD_DM 为 binary，其余控制指令为 fraction。源文件含31列，额外的实际阀位等13列默认不进入诊断。
4. 确认当前 LBNL SDAHU 公开仿真配置，点击导入并核验。得到1440→288行的显式转换记录。原始CSV字节与哈希可检查，不是由JSON反推的伪原始数据。
5. 点击“导出可阅读核查卡”。下载HTML可离线打开、用浏览器打印；同时可导出JSON计算记录。后端保留 output/runs、output/cards 和 data/imports 的原始CSV副本/映射。
6. 反例：将原始间隔选为5分钟再提交。界面应明确拒绝间隔错标，而不是继续计算运行分钟。
7. 选择固定流程，将预算调到1，或取消风路证据，结果须重新计算，不能沿用先前设备结论。完整信息模式始终取得全部允许证据，不被预算滑块截断。
这是已有开发日期的功能演示，不是新留出或真实建筑诊断验证。

输入边界：UTF-8单日CSV，2—3000行、最多80列、8 MiB以内；只支持当前公开仿真配置。原始时钟无时区，不自动推断时区。只允许1或5分钟栅格；时间递增且无重复。1分钟桶须有5个真实时刻，任何点位缺值仍保留缺值，不插值补足证据。缺点位会作为分支状态显示；非支持设备、错单位、非完整桶、实际阀位/标签映射等明确拒绝。
用户仍须如实选择源字段含义和单位。软件不凭数值猜测标签或认证文件的真实设备来源；勾选配置不能证明任意楼宇适用。

三、保留的三个演示
01 http://127.0.0.1:18193/?demo=1
BDG2真实用能回放：查看曲线与天气/历史参考，只给用能变化核查建议，不生成空调设备故障真值。
02 http://127.0.0.1:18193/?demo=2
LBNL仿真工况核验：查看有限已核验时段结论，展开每个分支的具体点位与补证条件。把“参考内响应”与“排除全部故障”区分。
03 http://127.0.0.1:18193/?demo=3
人为重复记录演示：300条含12条完全重复；点击“修正完全重复记录并重算”，变288条且质量通过，风阀卡滞候选仍存在。取消风路证据后退回待补证。
以上均实时调用程序，可操作；没有把预写结论当作重算。演示不是录制视频。实测、仿真与人为扰动来源在界面分别标注。

四、命令行复现与验收证据
  python -X utf8 scripts/demo_import.py
  python -X utf8 scripts/test_reliability.py
  python -X utf8 scripts/test_standalone.py
  python -X utf8 scripts/regression.py
  python -X utf8 audit_input/复现新增问题.py . --output output/audit_recheck_new.json
最后一个输出必须是新文件，审核原脚本拒绝覆盖。原脚本按原样随包保留。
结果：output/audit_before.json、audit_after.json；reliability_tests.json（29项）；standalone_tests.json（11项）；import_demo.json；ui_checks.json；regression/analysis.json（112条明细）。
test_standalone 启动自己的隔离副本18194端口，结束只关闭该子进程，副本不清理。若端口被占用，先人工选择空闲端口修改测试配置，不停止其他进程。
本轮112条只作回归，预测相对上轮零变化。历史24/112结果、025/075组及失败类别全部保留；没有新增性能实验。完整年度原始ZIP不随包重复分发；回归直接使用冻结JSON输入，不能称已在此包离线重建完整年度数据。
如果需要重新提取提供的原始日片段，从 data/public_csv/provenance.json 中的官方URL取得指定SHA256源ZIP后运行：
  python -X utf8 scripts/prepare_public_csv.py --source "下载的官方ZIP绝对路径"
该可选步骤不依赖首轮路径，不参与普通启动。

五、材料与可写入申报的范围
materials/final 下三份可编辑DOCX：简表3页、说明书4页、商业计划书3页，已用完整中文字体逐页渲染复检。正文保留原章节和限字；说明书包含实际截图、代码对应流程图及分组结果表。
materials/QA_视觉复检.txt 和 materials/working/qa.json 记录字体、页码、逐页检查与内容限制。
可写：质量/时间轴两项反例已修复；双维度展示、分支可检验条件；一个真实原始CSV输入至核查卡的软件任务；29项可靠性与11项隔离HTTP检查通过。不能写：算法领先、真实楼宇故障定位已验证、人工提效、节能收益或主动查询增益。
这三份是已视觉复检的匿名底稿；简表身份字段按匿名要求留空，技术成熟度未代填，须按组委会实际口径和可提供证据确认。不能直接称手续完备的正式提交版。

六、交付与保留
REPORT.txt 说明明确修复、未解决能力与证据位置。delivery 下评审ZIP含独立运行源码、数据、报告、三份Word和证据。
runtime 下任务私有渲染器、下载分块、渲染缓存继续保留，但不放进软件评审包；未绕过或执行清理。前两轮文件哈希核验在 output/preservation_check.json。
