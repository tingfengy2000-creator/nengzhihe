# 第23节截图：冻结产品与实测资料分别取证

2026-10-09，5090，本机冻结页面：`http://127.0.0.1:18770/`。
产品源码SHA：`e7f0cf1d0eed5464835897c1d51db84040cb16a0`。
启动命令：`C:\Python314\python.exe -X utf8 -c "from operation_planning.app import serve; serve(port=18770)"`。
截图方式：Codex浏览器真实打开页面、点击和滚动，未修改页面HTML或注入结果。

| 文件 | 实际页面操作 | 证明范围 |
|---|---|---|
| `01_frozen_home.jpg` | 打开冻结首页 | 现有产品与3D场景确实可显示；未重新测帧率或模型速度 |
| `02_frozen_scenario_comparison.jpg` | 示例→小档“打开”→四方案结果 | 已保存v9回放小档参考情景：35㎡、1间、每间2台；589 kWh、推荐1kWp、条件性10年省803元。不是本轮现场实测或重新计算 |
| `03_tariff_layout_observation.jpg` | 关于数据→滚动电价表 | 记录1265×720视口下右侧来源列狭窄、换行较多的排版现象；只记录，不修改前端 |
| `04_frozen_model_boundary.jpg` | 继续滚动至模型边界 | 明确未经现场校准、只计空调、有限容量和成本条件 |

页面显示“本机服务”仅代表后端连接；本次结果页同时显示“示例数据 / replay_cases_ui_v9.json”来源。本轮没有点计算或运行新的模型实验，不把浏览器渲染时间计作数值计算耗时，也没有重跑旧14/18句模型任务。

原回放文件、UI源码与各截图的SHA-256保存到 `capture_manifest.json`。原始截图不作后期合成。界面数字不与本轮曼谷/马德里实测记录混合。

真正实测数据的图表另见 `operation_planning/results/round23_case_admission/figures/public_measured_evidence.pdf`及对应PNG：CU分钟空调记录、固定周曲线、马德里12月计量。该PDF已逐页检查，没有缺字、遮挡或空白页；所有图均明确计量范围和未校准限制。它是答辩数据证据草稿，不是更新后的正式申报材料。
