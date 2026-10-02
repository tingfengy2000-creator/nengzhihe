能智核｜公共建筑用能异常核验工作台（第二轮）
智慧能源与环境方向。产品展示版本与可复现证据包；DOCX为待视觉复检底稿。

快速打开
1. 在本目录执行 PowerShell：.\scripts\start.ps1
2. 浏览器打开 http://127.0.0.1:18192
3. 停止仅本轮服务：.\scripts\stop.ps1
脚本绑定本轮路径、端口18192和进程创建身份，后台隐藏启动；不会操作首轮18190/18191或其他项目。
若移到另一台机器，安装Python3.12与numpy2.3.5后，在本目录运行：python server.py --port 18192
仅监听127.0.0.1；没有付费API、本轮不调用模型。材料重建另外需要python-docx1.2.0/lxml6.1.1；数据重新准备需要pandas3.0.1。

三段实际交互演示
A 实测回放：http://127.0.0.1:18192/?demo=1
  BDG2表计与天气、历史参考；观测差异不等于节能量，也不能定位设备故障。
B 合格工况：http://127.0.0.1:18192/?demo=2
  原正常演示中核对工况、两条正向一致证据；关闭风路或关阀证据可重算为未决。
  这是开发演示，最终时间留出正常召回为0，不能用演示替代泛化结果。
C 数据与设备双维：http://127.0.0.1:18192/?demo=3
  原300记录、12重复；预算1未决，预算4核验；关闭风路证据会变未决。
  执行修正删除12条完全重复后剩288条，再实际核验，数据通过但风阀疑点仍在。
每次修改预算、证据开关、时间窗或修复状态均重新调用数值程序；运行编号与证据JSON可导出。完整信息参照取得全部允许证据，不受滑块截断。具体实际运行记录、截图见output/ui_review。

本轮已做与结果
先看output/最终结果与建议.txt与output/benchmark.json：旧新完整信息6→24/112正确，均无已判错误，但新版本仍88未决；正常/泄漏召回0。固定和自适应同样24/112、同样3.3571查询，未发现主动策略增益。
定位并修复了全天波动门槛与工况未使用的瓶颈，采用稳定窗口、正常参考及重叠拒判。不是原创算法，工程修复不能写成原创算法贡献。
output/root_cause_summary.txt与root_cause_old_audit.json记录首轮420次逐例审计；旧42仅开发回归。
output/architecture.svg是可编辑架构，architecture.png已渲染查看。
materials/包含按三份原模板填好的可编辑DOCX、四份原始指南/模板、字数/结构/匿名检查及渲染失败记录。无正式提交、无真实收益/合作/试点虚构。

复现已有最终评价（不重新选阈值）
在本目录运行：
  python scripts/test_integration.py
  python scripts/evaluate.py --reproduction --output-dir output/reproduction_01
第二条校验frozen文件与最终案例哈希，重用冻结阈值；输出单独目录，不覆盖首次最终成绩。耗时因硬件和负载会变化，预测应相同。后续复现目录请换新名字。
output/frozen.json记录规则/校准/策略/口径/分组哈希；data/final_seal.json封存112案例及标签。最终日期标签仅评分；网页只能打开3演示与开发案例。
output/evaluation_final/receipt.json记录先448预测、再开标签的时间，predictions/保存全部逐次证据，scored_rows.json与metrics.csv为逐例及汇总结果。

从原始数据重新准备/重新校准
首轮原始缓存、源码和交付包完整保留在上级nengzhihe目录。本轮的prepare_round2_data.py与test_diagnostics.py/audit_old.py依赖上级原始缓存/开发样本/首轮逐例记录。
本交付包已带冻结案例与配置，可以独立运行产品和最终复现。原始重建应在另一个工作副本中按PROTOCOL.txt的已声明日期分组执行prepare_round2_data.py --split dev、--split final，再test_diagnostics.py、select_policy.py、freeze.py、evaluate.py；不能在已冻结交付目录重建或清除freeze来继续调最终集。
原始重建脚本需要同目录层级的首轮包与data/raw/lbnl_sdahu.zip（保留原缓存）；不得从本次最终结果反向挑选日期或改规则。模型权重与大原始压缩包不重复装入本轮ZIP。

保留与未完成项
首轮源码、结果、原交付ZIP不覆盖；output/baseline_preservation.json复核原572个文件。未操作“乡艺有据”。没有删除缓存。
本轮27项数值/集成检查通过；UI桌面与手机显示及实际交互另有截图/运行记录。
独立时间留出属于同一仿真系统；实际阀位未接入。尚欠真实建筑点位/运维验证与正常、泄漏的新日期覆盖。节能机会只能列为后续筛查线索。
材料缺安全可用的Word渲染器，DOCX标“待视觉复检”，提交前需逐页视觉检查与填写必要个人信息/匿名性复核；不以此阻塞产品。
