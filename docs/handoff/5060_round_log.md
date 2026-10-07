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

---

## [5060回交] 第1轮补充：接入 5090 房间口径回放（2026-10-07）

```text
起始SHA：e734cac（第1轮回交）
本次提交SHA：adde7cd（合并 fix/5090-room-contract-replay@5b955c0，无冲突）、c0a0a68（界面读取新回放）
分支：feat/5060-product-ui
```

- `app.py` 样例白名单加入 `replay_cases_room_contract.json`（仍只读，不复制）。
- 主演示改为新回放的 4 个案例；页面显示真实房间配置（如“1 间 × 6 台”），不再显示“待5090确认”。
- 旧回放的预算60000 / 缺PV报价 / 屋顶1㎡ 三个变体保留为“旧版本状态示例”，旧默认样例不再列出。
- 是否影响数值：否。

### 需要5090确认或补充

1. **同一场景的费用在新旧回放中不一致。** 新回放 `comparison_undersized_one_unit`（源码 `bc90c8a`，1 间 × 1 台，年用电 1251.284 kWh，与旧默认样例相同）与旧回放 `default_four_scenarios`（源码 `a4d4bd1`）对比：只用电网 8258.47 元相同；加装光伏 10487.25 vs 10117.25（+370.00）；加装小风机 101106.41 vs 97006.41（+4100.00）；光伏+小风机 104064.10 vs 99594.10（+4470.00）。年发电、年购电完全相同，差额都是整数，推测是报价/运维/替换假设变化。请说明原因，并在回放 `input` 中记录完整报价假设（光伏与风机报价、轮毂高度）。说明前，页面不会把两份费用放在一起比较。
2. **新回放 `chart` 没有 `scenario_id`。** 页面现在写“未注明对应方案”。请补上（推测是光伏+小风机）。
3. **请按新源码重新生成三个状态变体**（预算60000、缺光伏报价、屋顶1㎡），基于主演示场景，并保留完整 `input`、`total_cost_npv_cny` 和逐时数据，以便演示“已排除 / 条件不全”时与主演示口径一致。
4. **新回放 `input` 未记录 `hub_height_m`。**

---

## [5060回交] 前端重构：能见度（2026-10-07）

按 `docs/handoff/frontend_redesign/PROMPT.md` 一次性任务书执行，在 claude.ai/code 云端会话中完成并直接推送（本次云端会话有推送权限，未经用户本地中转）。

```text
起始SHA：f7dbd1a（feat/5060-product-ui 最新提交，含任务书 1507f52；代码与 29fc660 相同）
本次提交SHA：见下表（第 7 批为本记录所在提交，以远程分支最新 SHA 为准）
分支：feat/frontend-redesign（普通推送；未改 main，未强推，未建 Release/Tag，未开 PR）
```

### 提交拆分（远程 SHA）

| 批次 | SHA | 内容 |
| --- | --- | --- |
| 1 | `4e6bc9e` | 设计系统与外壳：浅/深主题令牌（深色单独调色）、排版、组件、顶栏导航、哈希路由、ES modules；离线 vendored three.js r128（MIT 许可证与版本/哈希说明）；第一轮 `assets/*.js`、`styles.css` 由 `assets/js/`、`assets/css/` 取代，`assets/legacy/` 保留 |
| 2 | `73f1920` | 数据适配层（实时响应与回放映射为同一视图模型，不做数值计算）、后端探测与示例模式、Web Worker 读取 76 MB 回放、`/samples/` 白名单加入 v6/v7 |
| 3 | `4deeeb4` | 首页叙事：3D 场景、事实大数字、能源日历、电去哪了、两种算法、容量曲线、10 年总账、三档入口、演示入口 |
| 4 | `fd43f75` | 试算第 1 步与计算流程：表单与选项、台数比选、预览 + 全年任务真实进度、错误定位、失效 |
| 5 | `71e329a` | 试算第 2–4 步：结果、碳面板、粗算对照、储能上限、导出、失效禁用 |
| 6 | `9183c03` | 示例页、我的方案、关于数据、一键演示 |
| 7 | 本记录所在提交 | 自动验收脚本 `scripts/check_frontend_redesign.cjs`、容量比选表中“已排除/条件不全”行不再显示差额、截图与本记录 |

### 修改文件

- `operation_planning/app.py`：**唯一的后端改动**，`REPLAY_SAMPLES` 白名单加入 `replay_cases_v6.json`、`replay_previews_v7.json`（仍按完整文件名精确匹配、只读，`../` 与编码路径照旧 404，已用 curl 验证）。静态资源路由原本已支持子目录，`.js` MIME 已有，未改。
- `operation_planning/ui/index.html`：重写为外壳（相对路径引用资源，可从本机服务或仓库静态服务器打开）。
- 新增 `operation_planning/ui/assets/css/`（tokens、base、home、tool、pages）与 `assets/js/`（main、state、util、data、sample-worker、api、charts、calendar、scene3d、story、home、form、tool、results、export、samples、plans、about、demo）。
- 新增 `operation_planning/ui/assets/vendor/three/`（`three.min.js` r128、`LICENSE`、`VERSION.txt`）。来源 npm `three@0.128.0` 官方包，下载后核对 npm shasum。
- 删除第一轮 `operation_planning/ui/assets/{app,charts,data,deliver,stage}.js`、`styles.css`（历史在 git 中可查）；`assets/legacy/` 与 `index.v1-baseline.html` 未动。
- 新增 `scripts/check_frontend_redesign.cjs`（只读验收脚本）、`docs/handoff/screenshots/frontend_redesign/`（截图）、本记录。
- 未改动：任何算法文件、天气/曲线/报价/电价/排放因子数据、回放文件、`operation_planning/results/**`、`main`。

### 接口使用清单

| 接口 | 用途 |
| --- | --- |
| `GET /api/operation/options` | 启动探测（成功 = 实时模式）；城市与缓存年份、空调型号（额定制冷量、能效比、来源）、电价档案（verified/provisional、来源）、排放因子目录 |
| `POST /api/operation/thermal/size` | 「帮我算配几台」：1..N 台服务状态、单房间年用电、冷量不足小时、`minimum_adequate_units_per_room`（一键采用） |
| `POST /api/operation/hybrid/preview` | 夏季、冬季典型周预览（`preview.period=typical_week`、`season`） |
| `POST /api/operation/hybrid/jobs` + `GET /api/operation/hybrid/jobs/{id}` | 全年计算；进度只用 `progress` 与 `capacity_completed` 事件；失败时读 `message`/`field` 定位表单 |
| `GET /api/operation/wind/profiles` | 关于页的风机曲线来源 |
| `GET /samples/replay_cases_v6.json`、`/samples/replay_previews_v7.json` | 示例模式与首页示例（未连接计算服务时，从仓库静态服务器的相对路径读取同一文件） |
| 未使用 | `POST /hybrid/run`（同步接口；为统一显示真实进度只用异步任务）、`/carbon/factors` 与 `/tariffs`（内容已含在 options 中） |

请求字段：房间参数全部在 `room`（`room_count`、`units_per_room`，不发送 `equipment_count`/`quantity`）；光伏 `pv.auto_capacity` / `pv.requested_capacities_kwp` / `pv.fixed_capacity_kwp` 三选一；电价档案走 `pv.tariff_id` + `pv.tariff_application`，固定电价走 `hybrid.import_price_cny_per_kwh`；报价只发送用户填写的字段（未填写不补默认值，对应方案由后端判为 `unknown`）；可选 `carbon.factor_id`、`carbon.carbon_price_cny_per_t`、`storage.capacities_kwh`。

是否影响数值：**否**。前端只做字段映射和显示；显示用分组只有：逐月柱（按月加总逐时空调用电）、能源日历（日期×小时排格，颜色按第 99 百分位归一或按三种去向取最大）、典型日曲线（取一天 24 个逐时值），图旁均注明“仅用于显示”。年度数字、金额、碳、比率全部读结果字段。

### 关键实现决定（任务书未覆盖处）

1. **预览先行**：实测预览、两个季节和全年任务同时提交时，单进程计算服务互相争用，预览被拖到约 3.9 秒。改为夏季预览先发（本机约 0.6–0.9 秒返回），返回后立即提交全年任务和冬季预览；全年任务只晚几百毫秒。实测点击后 0.88 秒出现预览，全年约 13–14 秒完成。
2. **计价不完整不显示金额**：回放中 `economics_status=incomplete` 的方案 `total_cost_npv_cny` 记为 0，页面显示“—”和“条件不全，暂无法比较（不是淘汰）”。
3. **示例回放瘦身只在内存**：Worker 读取后删去界面用不到的 `weather.provenance.normalization` 审计数组和 `candidates[].hourly`（示例模式按任务书用 `chart` / `chart_recommended`）；不生成任何新文件。完整 JSON 导出里写明省略了哪些字段及原件路径。
4. **默认条件**：空白表单预填的是输入（城市第一项、2024、1 间 35㎡、工作日 8–18 点、26℃/60%、第一种型号、每间 1 台、屋顶 35㎡、自动比选、1 台风机、所在城市的电价档案），不是结果；报价留空。默认电价档案按 options 里供电区域城市名匹配所选城市；无匹配时切换为固定电价并要求填写。
5. **公开参考碳价**：options 未提供碳价情景，前端在“使用公开参考碳价”按钮里保留与 `carbon.py` 相同的 97.49 元/吨作为**输入**预设（注明来源与“只是情景”），结果中由后端回显来源；见下方 5090 第 5 条。
6. **一键演示 7 幕**：任务书写“5–6 幕”，同时给出 7 项建议分幕；按建议分幕做了 7 幕，每幕 8 秒。
7. **单房间用电**：hybrid 结果只给项目合计；第 2 步的单房间数只在「帮我算配几台」同条件结果存在时显示，并注明来源，不在前端除以房间数。
8. **大档称呼**：带 `feasibility` 的示例按“空调分区”称呼（6 个空调分区 × 每区 14 台），并显示“只计厂房空调区、生产用电未计入、结果偏保守”。

### 截图

`docs/handoff/screenshots/frontend_redesign/`，云端无头 Chromium（SwiftShader 软件 WebGL，3D 场景可渲染），1440（1 倍）与 390（2 倍）× 浅色/深色：

| 前缀 | 内容 |
| --- | --- |
| `01_home` | 首页全长（3D 场景、事实、日历、电去哪了、两种算法、容量曲线、10 年总账、三档、演示入口） |
| `02_tool_step1_sizing` | 第 1 步（从小档示例填入条件）+ 台数比选结果 |
| `03_preview_and_progress` | 点击计算后：典型周预览 + 全年任务真实进度（截图时“已完成 1/4 个光伏容量”） |
| `04_live_step2` / `05_live_step3` / `06_live_step4` | 实时计算结果第 2/3/4 步 |
| `07_stale` | 修改预算后：结果置灰、“条件已修改，结果已失效”、导出与保存禁用 |
| `08_samples` | 示例页（三档与三个状态变体） |
| `09_variant_*_step3` | 三个状态变体打开后的第 3 步（1440 浅色、390 深色） |
| `10_my_plans` | 我的方案（两份方案对比） |
| `11_about` | 关于数据 |
| `12_demo_scene4` | 一键演示第 4 幕“装多大最划算” |

1024 宽度没有截图，由验收脚本检查无横向滚动。本机预览：仓库根目录 `python -m operation_planning.run_server`，打开 <http://127.0.0.1:18765/>；只看示例可用 `python -m http.server 18799 --bind 127.0.0.1` 后打开 <http://127.0.0.1:18799/operation_planning/ui/index.html>。

### 第 9 节验收自查

自动脚本 `node scripts/check_frontend_redesign.cjs`（需两个本机服务与 playwright）：**334 项检查，0 项不通过**（最后一次运行于第 7 批提交前）。逐条：

| # | 标准 | 结果 | 依据 |
| --- | --- | --- | --- |
| 1 | 30 秒内说出“帮我决定什么、结论是什么” | **未验证** | 首屏主标题 + 四个问题，试算第 3 步首行是一句话结论；没有真人测试。 |
| 2 | 不打开示例也能从默认条件完成实时计算并看到全部图表 | 通过（有条件） | 默认条件可直接计算（已在云端实测）。默认不填报价，所以光伏/风机方案为“条件不全”、容量曲线没有金额；点“填入示例报价”或自己填报价后所有图表齐全。这是按任务书“不自动补默认报价”的结果。 |
| 3 | 改型号或台数后重算，年用电和服务状态变化；配几台给出最少达标台数并一键采用 | 通过 | 实测默认房间 1 台“有缺口”、比选得出每间至少 13 台，一键采用后重算为达标；小档条件比选为 6 台。 |
| 4 | 1 秒内出现预览；全年进度来自后端；全年结果替换预览 | 通过（本机） | 云端实测 0.88 秒；进度只取 `progress`/事件；完成后自动进入第 2 步。普通笔记本未测。 |
| 5 | 三档与三个变体的数字、状态、排除原因、推荐与回放一致 | 通过 | 验收脚本逐项比较四方案总花费、差额、状态标签、排除原因原文、推荐高亮与推荐状态、年用电、服务状态、容量比选行与最划算标注、碳、粗算、储能。 |
| 6 | 容量曲线与 `pv_capacity_sweep` 一致，最划算标注正确 | 通过 | 最划算取 `recommended_pv_capacity_kwp` 且该行可比较；固定容量的变体标“固定容量”不标最划算；已排除行用虚线空心点并写原因。 |
| 7 | 碳、粗算、储能数字一致，边界文字可见 | 通过 | 脚本核对第 1 年减碳、研究期减碳、粗算差额、各档挽回电量；各面板写明情景估算/不参与推荐/不含电池成本。 |
| 8 | 第 7 节 13 条 | 通过（见下） | 1 只用电网永远第一列（脚本核对）；2 unknown 不显示为排除、excluded 原文、equivalent 写明同哪个方案；3 service_gap 显示缺口小时与“结果不代表同等舒适度下的最优投资”；4 差额保留方向、npv 只在 CSV/依据中且注明非利润；5 碳情景/不含隐含排放/资格未核实；6 储能“理想上限，不含电池成本、寿命、替换，不是储能推荐”；7 预览标“不含费用和推荐，不外推全年”；8 provisional 档案在选择处、价格表、简报处标“待核验”；9 改任一条件即置灰并禁用导出与保存；10 导出只用当前视图模型与已读取原始结果；11 进度只来自后端；12 边界随结果可见；13 页面无写死结果数字（示例数字均从回放读取）。 |
| 9 | 主界面不出现 pvlib、SD6、Hellman、NPV、S0–S3 与英文字段名 | 通过 | 脚本对首页、示例、我的方案、试算 1–4 步的可见文字做正则检查（依据抽屉、关于页、文件名除外）。后端返回的说明文字中夹带的字段名/英文（如 `avoided_kgco2`、“PV-only”“S0增量NPV”、变体说明里的 unknown/excluded）已在主界面换成中文，原文放在依据抽屉。 |
| 10 | 浅/深色 × 1440/1024/390 无横向滚动；减少动态效果下无动画 | 通过 | 脚本检查 8 个页面 × 6 种组合；`reducedMotion: reduce` 下无动画、无过渡、无待显现元素；3D 只渲染一帧，演示不自动播放。 |
| 11 | 后端不可用自动进入示例模式并提示 | 通过 | 静态服务器打开：模式标识“示例数据”、顶部提示“当前未连接计算服务，只能查看示例”，首页示例数据正常加载。 |
| 12 | 无控制台错误；离线可用 | 通过（有说明） | 脚本全程 0 个页面错误；页面不请求任何外部地址（字体用系统字体栈，three.js 本地）。无头 SwiftShader 下 Chrome 会打印“软件 WebGL 已弃用”“GPU stall due to ReadPixels”等**浏览器/驱动警告**（截图读像素导致），不是页面错误；真机 GPU 未测。断网条件按“无外部请求”验证，没有拔网线实测。 |

### 需要5090处理的问题

1. **典型周预览的服务缺口与全年不一致**：小档条件（6 台/间，全年 `capacity_shortfall_hours=0`）的夏季典型周预览返回 `service_quality.capacity_shortfall_hours=118`（`replay_previews_v7.json` 与实时接口一致）。一周 168 小时里 118 小时缺口与全年 0 矛盾，疑似 `_slice_project_load` 的汇总口径问题。前端暂不显示预览的服务状态。
2. **计价不完整方案的金额字段**：`replay_cases_v6.json` 缺报价变体中 `unknown` 方案的 `total_cost_npv_cny` 为 `0`（`economics_status=incomplete`），建议改为 `null`，避免其他使用者把 0 当花费。
3. **变体的 `chart_recommended` 不是推荐方案**：缺报价、屋顶不足两个变体推荐为 `S0_grid`，但 `chart_recommended.scenario_id` 为 `S1_pv`。前端按实际 `scenario_id` 标注（“加装光伏”，不写“推荐”）；请确认字段语义或改名。
4. **hybrid 结果没有单房间汇总**：`project_load.py` 有 `single_room_summary`，但 `hybrid/run` 与任务结果的 `load_context` 只给项目合计，第 2 步无法直接并列单房间与项目合计。请在 `load_context` 增加单房间年用电字段。
5. **碳价情景未在 options 中提供**：请在 `options`（或 `carbon/factors`）给出 `carbon_price_scenarios`（数值、来源、说明），前端就能去掉 97.49 的输入预设副本。
6. **计算服务并发**：预览与全年任务同时到达时互相拖慢（见实现决定 1）。如果普通笔记本更慢，可考虑任务进程隔离或在接口手册中写明建议的调用顺序。
7. **进度到 1.0 后仍在计算**：`progress` 在全部容量算完后即为 1.0，但选中容量还要带逐时数据重算一次（本机约 2 秒）。前端写“正在生成选中容量的逐时结果”；如能把这一步计入进度或单独发事件更清楚。
8. **后端说明文字含英文/技术名**：`carbon_context.scope_notes`（avoided_kgco2）、`recommendation.reason`（S0、NPV）、`recommendation_basis`（PV-only、S0、NPV）、回放 `variant_reason`（unknown、excluded）、`annual_offset_estimate.electricity_price_basis`（英文）。前端已在主界面替换；建议后端另给面向用户的中文字段。
9. **电价档案与城市的对应**：`tariffs.regions` 只有城市名文本，没有 `site_id`；前端按城市名包含关系匹配。建议增加 `site_ids`。
10. **默认房间的台数比选结果**：只填面积/时段/温湿度、其余用模型默认值时，35㎡ 房间要 13 台/间才无缺口（缺口集中在开机首小时的降温），请确认这是预期的模型行为，以免用户误读为选型建议。
11. **示例回放体积**：`replay_cases_v6.json` 76 MB（每案约 12.7 MB，多为天气审计数组与各方案逐时）；前端在后台线程读取后丢弃，但仍需传输 76 MB。可考虑提供面向界面的精简文件（或按 case 读取）。
12. **回放中含机器绝对路径**：`weather.provenance.source_file` 等字段含 `E:\比赛\...`，实时响应含 `/home/...`。前端只显示文件名；正式匿名提交前建议改为仓库相对路径。
13. **小档的 `not_provided` 含“车间大档为有界空调分区代理”**：每个案例共用同一列表，前端照原文列出。
14. **品牌**：`/api/operation/health` 的 `product` 仍为“能智核——…”。前端不读取该字段，仅提示。

### 已知问题与下一步

- 30 秒理解度没有真人测试；普通笔记本的计算等待时间、真机 GPU 下的 3D 帧率、Firefox/Safari 未测（只测了 Chromium）。
- 打印/另存 PDF 只生成了简报 HTML 并调用浏览器打印，没有在各浏览器实际检查分页。
- 一句话输入仍是本地规则识别，不是模型解析；房间数、台数、面积等提示“请在表单修改”。
- 能源日历用 canvas 绘制，读屏只能读到图名；替代方式是“下载逐时数据（文字替代）”与第 4 步逐时 CSV。键盘可达、焦点环已做，未做完整读屏审计。
- 第一轮“我的方案”键 `nzh.plans.v1` 未迁移到新键 `njd.plans.v1`。
- 停止等待只停止轮询，计算服务没有取消接口，后台任务会继续算完。
- 根目录 `AGENTS.md`（round4 合约，要求更新 CHANGELOG/REVIEW_INDEX 并推送 main）与本任务书冲突（第 11.2 节 A9 已提出）；本轮按任务书只在功能分支提交，未改 `CHANGELOG.md`、`docs/REVIEW_INDEX.md`。
- 品牌“能见度”为暂定名，正式申报前需商标检索（任务书第 3 节）。
