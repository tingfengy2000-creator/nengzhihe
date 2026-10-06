# 5060 回交记录

按 `docs/handoff/5060_review_and_ui_direction.md` 第 9 节模板逐轮追加。新的一轮写在最下面。

---

## [5060回交] 第1轮（2026-10-07）

```text
起始SHA：64c58ebf0a330537dcb851771c0d595b55f3c66a（fix/5090-project-load-handoff）
本次提交SHA：6be93dd4c9f0caeaf554af527ad5d7b41e122dd0（最后一个代码提交 e；本记录与截图另有一个文档提交，见分支最新 SHA）
分支：feat/5060-product-ui
```

### 提交拆分（远程 SHA）

| 提交 | SHA | 内容 |
| --- | --- | --- |
| 审查文件 | `9ec5b6a` | `docs/handoff/5060_review_and_ui_direction.md` |
| a | `afc82a4` | 设计令牌与基础组件：`styles.css` 重写；旧工作台保留到 `ui/assets/legacy/` |
| b | `5fdb6a2` | 数据适配层 `data.js`；`app.py` 只读样例路由 |
| 11.3 更正 | `be0dad2` | 审查文件第 11.3 节按实际提交、推送方式改写 |
| c | `efa1bdf` | 四步任务流骨架与新导航；旧页面移出主导航 |
| d | `ea00106` | 第 3 步主舞台：决策卡、四方案卡、能源日历、电去哪了、典型日曲线 |
| e | `6be93dd` | 结果失效、第 4 步决策简报、CSV/JSON 导出、我的方案 |

### 修改文件

- `operation_planning/app.py`：**唯一的后端改动**。新增 `GET /samples/<name>`，白名单只有 `replay_cases.json`、`aircost_cases.json`，读取 `docs/handoff/replay_viewer/` 原文件字节；其他文件名、`../`、URL 编码路径一律 404（已在本地用 curl 验证）。样例没有复制到 `ui/` 目录。
- `operation_planning/ui/index.html`：重写。
- `operation_planning/ui/assets/styles.css`：重写为分区注释的设计系统。
- `operation_planning/ui/assets/app.js`：重写（任务流、表单、路由、一句话输入、依据抽屉）。
- 新增 `operation_planning/ui/assets/data.js`、`charts.js`、`stage.js`、`deliver.js`。
- 新增 `operation_planning/ui/assets/legacy/`：旧六页签工作台（`app.js`、`styles.css` 与原文件字节一致；`index.html` 只改了两处资源路径），可从“数据与边界 → 早期研究”进入。
- `docs/handoff/5060_review_and_ui_direction.md`：第 11.3 节更正。
- 新增 `docs/handoff/5060_round_log.md`（本文件）和 `docs/handoff/screenshots/5060_round1/`（22 张截图）。
- 未改动：任何算法文件、天气/曲线/报价原始数据、`operation_planning/results/**`、`main` 分支。

### 业务/接口变化

| 项目 | 变化 |
| --- | --- |
| 请求字段 | 实时模式调用 `POST /api/operation/hybrid/run`，房间参数统一放在 `room` 下：`room.room_count`、`room.units_per_room`（以及面积、时段、温湿度、朝向、窗墙比、人数，未填写则不发送、由后端默认）；不再发送旧字段 `quantity`。`quote_scope` 属于空调成本接口，第 3 步风光比较不发送，留待任务 7。 |
| 默认值 | 前端不设任何结果默认值。固定样例模式下，表单只填样例 `input` 里记录的字段；房间参数显示“待5090确认”，其他未记录字段显示“样例未记录”。 |
| 单位 | 面积 ㎡、电量 kWh、金额 元、电价 元/kWh、光伏 kWp、高度 m，与契约一致；金额显示取整到元。 |
| 校验 | 表单数字输入有 min/max/step；一句话输入只接受修改 schema 内的字段（使用时段、预算、光伏容量、小风机 0/1 台与高度、电价、是否外送）。房间数、台数、面积、城市、人数、温度会显示“请在下方表单修改”，不写入表单。 |
| 推荐状态 | 原样读取 `recommendation.status`、`scenario_id`、`unknown_scenario_ids` 等；`unknown` 显示“条件不全（不是淘汰）”，`excluded` 显示 report 中的 `constraint_reasons`；`service_gap` 显示“空调有缺口”，不显示成达标。 |
| 费用表达 | `total_cost_npv_cny` 显示为“10 年总花费”；`incremental_npv_vs_s0_cny` 按符号显示“多花 / 省下”，不取绝对值；`npv_cny` 只在 CSV/JSON 和术语表出现，未标成利润。 |
| 计算触发 | 固定样例模式：点击“查看结果”只在当前条件与所选已验算样例完全一致时显示样例结果，否则显示“待5090验算”和改动清单，不显示任何数字。实时模式：只有用户在抽屉中切换后才会调用计算接口。 |
| 结果失效 | 结果产生后改动任一表单字段 → 第 2–4 步置灰、显示“条件已修改，结果已失效”、导出按钮全部禁用。 |
| 导出 | 决策简报（A4 HTML，可打印/存 PDF）、方案汇总 CSV、逐时 CSV（8784 行原始值）、完整 JSON（含原始样例对象）。全部从当前视图模型生成，不调用任何计算接口。 |
| 我的方案 | 仅 `localStorage`（键 `nzh.plans.v1`），页面标明“仅保存在本机浏览器”；未使用旧的 `/api/operation/history`。 |

是否影响数值：**否**。前端只做字段映射与显示；唯一的显示聚合是逐月柱图、能源日历着色、典型日曲线（把已有逐时序列按时间分组显示），年度数字一律直接读取结果。

### 截图

`docs/handoff/screenshots/5060_round1/`，1440 与 390 宽度各 11 张（390 为 2 倍像素）：

| 文件后缀 | 内容 |
| --- | --- |
| `01_step1_describe` | 第 1 步：样例选择、一句话输入、表单（房间参数“待5090确认”） |
| `02_step2_ac_energy` | 第 2 步：年用电、服务缺口、逐月用电、两本账说明 |
| `03_step3_compare_default` | 第 3 步默认样例：决策卡、四方案卡、能源日历、电去哪了、典型日 |
| `04_step4_decision_export` | 第 4 步：推荐理由、适用边界、导出、保存 |
| `05_step3_case_*` | 预算 60000 / PV 报价缺失 / 屋顶 1㎡ 三个样例的状态标签 |
| `06_stale_after_edit` | 改预算后结果失效遮罩 |
| `07_pending_5090` | 重新计算后显示“待5090验算”与改动清单 |
| `08_my_plans` | 我的方案 |
| `09_drawer_sources` | 依据抽屉：来源、SHA、天气哈希、边界、术语对照 |

截图在云端无头 Chromium 中生成（系统中文字体，与 Windows 上的“微软雅黑”渲染会略有差别）。本机预览命令（仓库根目录）：

```powershell
python -m operation_planning.run_server
```

打开 <http://127.0.0.1:18765/>。只绑定本机；固定样例模式不运行任何计算。

### 第 8 节验收标准自查

| 标准 | 结果 | 依据 |
| --- | --- | --- |
| 第一次打开 30 秒内看懂工具帮我决定什么、结论是什么 | **未验证** | 首屏加了一句话问题、三个要点和四步条；第 3 步决策卡第一行即结论。没有真人测试，不能声称达到。 |
| 默认样例四步走通，数字与 `replay_cases.json` 逐项一致 | 通过 | 自动检查：四个方案总花费、相对只用电网差额、年发电量均与 JSON 取整后一致；第 2 步年用电 1,251 kWh 与 `load_context` 一致。 |
| 4 个回放 case 的状态标签、排除原因、推荐类型正确；`unknown` 未显示成排除 | 通过 | 自动检查 4 个 case 共 16 个方案卡标签、2 条排除原因原文、推荐标签（3 个“有条件推荐”、1 个“部分比较”）。 |
| S0 在任何情况下可见 | **部分通过** | 有结果时 S0 始终在第一位（4 个 case 均检查）。“待5090验算”状态下整页不显示任何方案和数字（包括 S0），这是为避免旧结果冒充新结果；如需在该状态保留 S0 占位，请用户决定。 |
| 改任一条件后结果失效、导出禁用 | 通过 | 自动检查：改预算后 `is-stale` 生效、5 个导出按钮与保存按钮全部 `disabled`。 |
| 主界面不出现 pvlib、SD6、Hellman、NPV、S0–S3 等术语（抽屉除外） | 通过 | 自动检查四步全部文本，以上术语及 `load_coverage`、`total_cost` 均未出现。 |
| 桌面和手机截图齐全；页面无横向滚动（热力图容器内滚动除外） | 通过（限 1440/390） | 22 张截图；1440 与 390 宽度下各步骤 `scrollWidth` 等于视口宽度。1024 宽度未截图（属任务 8）。 |

### 需要5090验证的具体请求

1. **审查 `app.py` 的 `/samples/` 路由**（本轮唯一后端改动）：确认白名单与路径处理可以接受。
2. **实时模式请求体能否被现有接口正确处理**（5060 未运行任何计算，只按代码构造）。在第 1 步切到“本机实时计算”、填写如下条件后，前端会发送：

   ```json
   {
     "use_agent": false,
     "site_id": "guangzhou",
     "year": 2024,
     "room": { "area_m2": 35, "room_count": 3, "units_per_room": 6, "start_hour": 8, "end_hour": 18,
               "orientation": "north", "window_wall_ratio": 0.1, "people_count": 2 },
     "pv": { "roof_area_m2": 50 },
     "hybrid": { "pv_capacity_kwp": 2, "budget_cny": 90000, "import_price_cny_per_kwh": 0.66,
                 "allow_export": false, "study_years": 10, "wind": { "turbine_count": 1, "hub_height_m": 9 } }
   }
   ```

   请确认：(a) 返回 200 且 `load_context.project_load_context.room_count = 3`；(b) 因表单暂无报价字段，光伏/风机方案应为 `unknown`（条件不全），页面应显示“条件不全”而非淘汰；(c) `candidates[*].hourly` 字段名与 `data.js` 的映射一致（`load_kwh`、`pv_generation_kwh`、`wind_generation_kwh`、`self_use_kwh`、`grid_import_kwh`、`grid_export_kwh`、`curtailment_kwh`）。注意表单没有 U 值字段，这个请求与 5090 的 A2 主演示（U 值 0.3）不完全相同。
3. **新回放文件的接入方式**：5090 已在 `fix/5090-room-contract-replay`（`5b955c0`）提供带房间配置的 `replay_cases_room_contract.json` 和无服务缺口主演示。按本轮用户决定，白名单暂只含两个旧文件，界面仍显示“房间配置：待5090确认”。下一轮需要用户确认：是否把新文件加入白名单（或先由 5090 合并到交接分支）。

### 已知问题与下一步

- 默认样例来自旧回放（每间台数未记录、存在服务缺口 1,014 小时），因此第 2 步首屏显示“空调有缺口”。5090 的无缺口主演示尚未接入（见上条 3）。
- 三个变体样例只保存了方案汇总：没有总花费、年用电和逐时数据，界面显示“样例未保存”，能源日历给出空状态。它们来自与默认样例不同的汇总文件，所以适配层不借用默认样例的数据。
- 样例匹配是严格的：在默认样例上把预算改成 60000，会显示“待5090验算”，不会自动跳到“预算60000元”样例，因为该样例只记录了 3 个条件，无法确认其余条件与默认样例相同。要看该样例，请直接在样例列表中选择。
- 实时模式在 5060 未执行，请求结构待 5090 验证（上条 2）。报价明细、寿命、电价档案、天气 CSV 上传尚未进入表单。
- 空调成本页（两本账中的设备投资一本，任务 7）未做，第 2 步只给出口径说明。
- 一句话输入是本地规则识别，只覆盖少量句式，不是本地大模型；大模型协同仍在 5090 的 `use_agent` 路径。
- 能源日历用 canvas 绘制，读屏软件只能读到图名；逐时数值可从“逐时数据 CSV”获得。键盘可达性、对比度只做了设计层面的处理，没有完整审计（属任务 8）。
- 决策简报只验证了生成的 HTML 内容，没有在各浏览器实际打印成 PDF 检查分页。
- 日期选择器显示格式随浏览器语言变化。
- 本分支根目录 `AGENTS.md` 仍是 round4 内容（5090 已在自己的分支修正，A9），本分支未改。
- 推送使用的补丁暂存在用户本地文件夹 `能智核\_to_delete\patches\`，可手动删除。
- 按用户要求，本轮在 e 之后停止，未做任务 7–10。
