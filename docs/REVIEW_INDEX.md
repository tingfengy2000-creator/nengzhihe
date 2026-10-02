# 阶段评审索引

当前固定评审版本：**`round3-review-v1`**。在 GitHub 分支选择器中切换到该标签即可固定全部源文件；后续 `main` 更新不会改变此版本。

| 阶段 | 说明与原始记录 | 可运行版本 / 交付 |
| --- | --- | --- |
| 首轮历史 | [完整说明](archive/round1_README.md)、[成绩](../output/benchmark.json)、[逐例评测](../output/evaluation_v1) | [源码目录](../)、[评审包](../delivery) |
| 第二轮历史 | [说明](../round2/README.txt)、[协议](../round2/PROTOCOL.txt)、[逐例结果](../round2/output/evaluation_final)、[独立审核原包](archive/能智核_第二轮独立审核.zip) | [源码](../round2)、[原交付包](../round2/delivery) |
| 第三轮当前 | [修复报告](../round3/REPORT.txt)、[修复前](../round3/output/audit_before.json)、[修复后](../round3/output/audit_after.json)、[分组与失败分析](../round3/output/regression/analysis.json) | [启动说明](../round3/README.txt)、[完整评审包](../round3/delivery)、[本次隔离复查](reviews/round3-github-2026-10-02) |

## 建议评审顺序

1. [当前版本报告](../round3/REPORT.txt)：先看能力与限制。
2. [操作演示](DEMO.md)：完成公开 CSV 到核查卡的实际任务。
3. [可靠性检查](../round3/output/reliability_tests.json)、[隔离 HTTP 检查](../round3/output/standalone_tests.json)、[界面核验](../round3/output/ui_checks.json)。
4. [历史回归分解](../round3/output/regression/summary.json)：保留全部类别；112 条不是新留出。
5. [三份 Word](../round3/materials/final) 与以下 PDF / 逐页 PNG 对照阅读。

| 材料 | 可编辑原件 | 已视觉复检的 PDF / 页面 |
| --- | --- | --- |
| 项目简表（3 页） | [DOCX](../round3/materials/final/附件1_能智核_项目简表.docx) | [PDF](../round3/materials/working/render_final_1/附件1_能智核_项目简表.pdf) · [页面](../round3/materials/working/render_final_1) |
| 项目说明书（4 页） | [DOCX](../round3/materials/final/附件2_能智核_项目说明书.docx) | [PDF](../round3/materials/working/render_final_2/附件2_能智核_项目说明书.pdf) · [页面](../round3/materials/working/render_final_2) |
| 商业计划书（3 页） | [DOCX](../round3/materials/final/附件3_能智核_商业计划书.docx) | [PDF](../round3/materials/working/render_final_3/附件3_能智核_商业计划书.pdf) · [页面](../round3/materials/working/render_final_3) |

字体与页数见 [QA JSON](../round3/materials/working/qa.json)，赛事四份原文件见 [references](../round3/materials/references)。这是已视觉复检的匿名底稿，不能视为手续完备的正式提交文件。

历史回执中的本机绝对路径和时间是原始记录，不代表在新机器仍存在。用各轮相对路径复现。ZIP、原始结果及 Word 保持原字节；Git 禁用行尾转换以保护 SHA256 清单。
