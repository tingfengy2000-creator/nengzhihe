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

## [5060回交] 前端第二轮小修：能见度（2026-10-08）

按 `docs/handoff/frontend_redesign/PROMPT_round2.md` 执行（第一轮 `PROMPT.md` 的原则、视觉规范、技术约束和诚实规则继续有效），在 claude.ai/code 云端会话中完成并普通推送。

```text
起始SHA：fc05a6b（feat/5060-product-ui 最新提交，含 PROMPT_round2.md）
分支：feat/frontend-round2（普通推送；未改 main，未强推，未建 Release/Tag，未合并，未开 PR）
```

### 提交拆分（远程 SHA）

| 批次 | SHA | 内容 |
| --- | --- | --- |
| 1 | `1d2a27d` | 白名单加入 `replay_cases_ui_v9.json`；示例、首页、示例页、演示、关于、导出改读 v9（来源写 `format_version` 与源码提交）；删除 76 MB Worker 读取；第 2 步单间/项目合计读 `load_context.single_room_annual_kwh`；碳价按钮读 `options.carbon_price_scenarios`；默认电价按 `tariffs[].site_ids`；计价不完整金额按后端 `null`；`chart_recommended` 标为推荐 |
| 2 | `991f030` | “多余的电去哪儿”卡片（替换原“储能理想上限”）、储能与卖电报价输入、汇总 CSV 与决策简报加入两条去路、演示第 6 幕（共 8 幕） |
| 3 | `b13d364` | 一句话输入接本地大模型（`agent/status`、`agent/parse`，提出修改→用户确认→写入表单，不自动计算）、关于页“大模型在这里做什么”、验收脚本测试桩 |
| 4 | `cf5ba9c` | 第 3 步三个数字卡、台数达标说明、自定义分时电价（`custom_user`）、电价年涨幅与敏感性表、`nzh.plans.v1` 一次性迁移、第 3 步结论句去重 |
| 5 | `8f9e8b1` | 验收脚本补充第 4 节各项；卖电“回本”改用后端 `payback_status` 原文 |
| 5 | `4640fd2` | 电价年涨幅表窄屏在容器内横向滑动（截图复查发现 390 宽表头被压成一字一行） |
| 5 | `2041885` | 截图；验收脚本卖电标签比较忽略空白 |
| 5 | `d1ff8e0` | 迁移方案缺年用电时只显示“—”；推荐只用电网时自发比例卡补“只用电网，不自己发电”（截图复查发现） |
| 5 | 本记录所在提交 | 重拍受影响截图（`08_*`、`13_*`）、本记录 |

### 修改文件

- `operation_planning/app.py`：**唯一的后端改动**，`REPLAY_SAMPLES` 加入 `replay_cases_ui_v9.json`（精确文件名、只读，旧文件名保留）。
- `operation_planning/ui/assets/js/`：`data.js`（v9 字段映射：`surplus_paths`、`simple_payback_years`、`tariff_escalation`、`escalation_sensitivity`、`tariff`）、`results.js`（数字卡、多余的电卡片、电价表、达标说明）、`form.js`（储能/卖电/自定义电价/年涨幅字段与请求、规则识别“电价每年涨3%”、模型修改映射）、`tool.js`（表单第 4、6 组、一句话输入卡）、`agent.js`（新增）、`export.js`（两条去路导出、方案迁移）、`charts.js`（正负柱图）、`demo.js`、`about.js`、`home.js`、`samples.js`、`story.js`、`main.js`、`util.js`；删除 `sample-worker.js`。
- `operation_planning/ui/assets/css/tool.css`、`pages.css`。
- `scripts/check_frontend_redesign.cjs`、`docs/handoff/screenshots/frontend_round2/`、本记录。
- 未改动：算法、数据、回放与结果文件、`docs/handoff/5090_carbon_request.md`、`docs/handoff/frontend_redesign/` 下文件、`main`。

### 接口使用变化

| 接口 / 字段 | 用途 |
| --- | --- |
| `GET /samples/replay_cases_ui_v9.json` | 示例模式与首页示例（不再读取 v6） |
| `GET /api/operation/agent/status`、`POST /api/operation/agent/parse` | 一句话输入；状态 404/超时/不可用时退回本地规则识别；`parse` 的 404、网络错误、超时视为不可用 |
| 请求 `storage.capacities_kwh`、`storage.quote{…}`、`storage.export{…}` | 储能与卖电报价；来源字段只在用户未改示例报价时随请求发送；未填写的不补默认值 |
| 请求 `pv.tariff_id="custom_user"` + `pv.custom_tariff` | 时段从所选官方档案复制（只读）、四个价格用户可改，带 `base_tariff_id` 与生效日期 |
| 请求 `hybrid.tariff_escalation_rate` | 年涨幅（界面填 %，发送小数；为 0 时不发送） |
| 响应 `surplus_paths`、`escalation_sensitivity`、`tariff_escalation`、`load_context.single_room_annual_kwh`、`options.carbon_price_scenarios`、`tariffs[].site_ids` | 只读显示 |

是否影响数值：**否**。前端只做字段映射和显示；大模型只提出表单修改，确认后仍由计算服务算出全部数字，模型返回的内容不作为结果数字显示。

### 截图

`docs/handoff/screenshots/frontend_round2/`，云端无头 Chromium，1440、1024（1 倍）与 390（2 倍）× 浅色/深色，PNG 已量化为 256 色：

| 前缀 | 内容 |
| --- | --- |
| `01_home` | 首页（1024） |
| `02_sample_medium_step3` | 中档示例第 3 步全页 |
| `03_numcards_medium` / `04_surplus_medium` / `05_escalation_medium` | 三个数字卡、多余的电去哪儿、电价变了结论还成立吗 |
| `06_sample_medium_step2` | 第 2 步（单间与项目合计、达标说明） |
| `07_surplus_small_not_recommended` | 小档：按当前报价不建议装储能 |
| `08_variant_missing_pv_quote_step3` | 缺光伏报价变体：推荐只用电网，数字卡写“无需投入” |
| `09_tool_step1_form` / `10_ask_proposal` | 第 1 步表单（自定义分时电价、年涨幅、储能与卖电）与一句话输入的修改提案 |
| `11_samples` | 示例页（1024、390） |
| `12_about` / `13_my_plans_migrated` | 关于页与迁移后的我的方案（1024） |
| `14_live_custom_tariff_step3` / `15_live_escalation` | 实时计算：自定义分时电价 + 年涨幅 3%（1440 浅色、390 深色） |
| `16_demo_scene6` | 演示第 6 幕“多余的电去哪儿” |

`09`/`10` 中一句话输入的“本地大模型理解”提案由截图脚本拦截 `agent` 两个接口返回固定内容（与验收脚本桩服务同一契约），**不是真实模型输出**。

### 第 4 节验收自查

自动脚本 `node scripts/check_frontend_redesign.cjs`（需本机计算服务 18765、静态服务器 18799 与 playwright；脚本自带 18767 端口的大模型测试桩）：**955 项检查，0 项不通过**（第 5 批最后一次代码修改 d1ff8e0 后运行；第一轮为 334 项）。

| # | 标准 | 结果 | 依据 |
| --- | --- | --- | --- |
| 1 | 第一轮 12 条仍通过 | 通过（同第一轮的说明） | 第一轮脚本全部检查保留（“储能理想上限”一项按 2.2 替换为多余的电卡片检查）；第一轮第 1 条“30 秒理解”仍无真人测试，第 4 条普通笔记本未测。 |
| 2 | 示例数字与 v9 一致，含 `surplus_paths`；不再引用 v6 | 通过 | 六个案例逐项比较原有字段及数字卡、电价表、单间年用电、多余的电（每个发电方案）；脚本扫描 `assets/js` 全部文件与 8 个页面 HTML 均无 `replay_cases_v6`。 |
| 3 | 储能卡片 | 通过 | 每个容量的投入、年少交电费、年净收益、回本、研究期净收益、自用比例前后与数据一致；最划算只标 `recommended_capacity_kwh>0` 的行；小档写 `recommendation_note`“按当前报价不建议装储能”；实时清空储能报价后各容量显示“条件不全：请填写储能报价”。 |
| 4 | 卖电卡片 | 通过 | 电量、电价、每年/研究期收入、并网投入（未填写写“按 0 粗算”）、回本（无投入时用后端 `payback_status` 原文）；实时清空上网电价后只显示电量和“填写上网电价后可估算收入”。 |
| 5 | 实时计算储能/卖电 | 通过 | 脚本实算小档 1 kWp：有报价时卡片完整；改储能单价后结果置灰；清空报价重算显示条件不全且无页面错误。 |
| 6 | 一句话输入 | 通过（仅桩服务） | 桩服务覆盖 ok / needs_clarification / unavailable / failed / 404 / 超时与状态接口 404 / 超时 / 未启动；采用修改后计算次数为 0；提案只列字段与新旧值，模型文字不进入结果区。**真实本地模型未接入测试**（本机状态“本地模型未启动”）。 |
| 7 | 三个数字卡 | 通过 | 推荐方案 `load_coverage_rate`、`capex_cny`、`simple_payback_years` 与数据一致；推荐只用电网时写“只用电网，无需投入”；缺失时“—”加原因。 |
| 8 | `nzh.plans.v1` 迁移 | 通过 | 脚本写入一条第一轮格式方案，两次打开我的方案均只有 1 条；旧键保留、写入 `nzh.plans.v1.migrated`；缺少的字段显示“—”。 |
| 9 | 无横向滚动、吸底栏、减少动态 | 通过 | 8 页 × 1440/1024/390 × 浅/深无横向滚动；吸底操作栏只在第 1 步，滚到底时位于最后一组表单之后，不遮挡（三种宽度实测），并加了聚焦时的底部留白；390 宽各表格在自身容器内横向滑动；减少动态效果下无动画/过渡。 |
| 10 | 禁用技术词、机器路径 | 通过 | 主界面正则检查同第一轮；8 个页面 HTML 与示例的汇总 CSV、决策简报、完整 JSON 均不含盘符路径、`/home/`、`/root/`、`/tmp/`、用户名或账号；实时响应的天气 `source_file` 已是仓库相对路径。 |
| 11 | 无控制台错误、离线 | 通过（同第一轮说明） | 全程 0 个页面错误；不请求外部地址。 |
| 12 | 自定义分时电价与年涨幅 | 通过 | 实算请求含 `pv.tariff_id=custom_user`、`pv.custom_tariff`（峰段 1.5）与 `hybrid.tariff_escalation_rate=0.03`；结果写“电价：用户自定义电价（未经官方核验）”与“本次计算按每年 +3%”；示例电价表四行与 `escalation_sensitivity` 一致（总花费、差额方向、逐年累计回本年），推荐只用电网时为一句话，删去该字段后不显示。 |

### 需要5090处理的问题

1. **敏感性表不含用户本次涨幅**：`escalation_sensitivity.rates` 固定为 −2%/0/+2%/+4%；用户填 3% 时表中没有“本次”行，界面只写“本次计算按每年 +3%”。建议在 rates 中加入请求的涨幅（若不在列表内）。
2. **自定义分时电价的生效期**：前端把所选官方档案的 `effective_start/end`（如 `guangzhou_industrial_lt1kv_202610` 为单月）原样带入 `custom_tariff`；请确认自定义档案按 `tariff_application` 用于全年的口径，并在结果 `tariff` 中回显用户的四个价格以便核对。
3. **一句话输入未接真实模型验证**：本次只用测试桩验证契约；请在装有本地模型的机器上跑一次 `agent/status` 与 `agent/parse`，确认字段路径与 `FIELD_RULES` 一致（尤其 `hybrid.tariff_escalation_rate` 用小数、`storage.capacities_kwh` 为数组）。
4. **只用电网方案也带 `surplus_paths`**：S0 的储能各档均为负净收益（无发电），前端不展示 S0；建议后端对无发电方案省略该字段或标 `not_applicable`。
5. **卖电 `payback_status` 文字**：前端原样显示（如“无并网投入”）；如需统一措辞请在后端改。
6. 第一轮第 1、6、7、8、10、13、14 条（预览缺口口径、并发、进度、英文说明字段、默认房间台数、not_provided、品牌）本轮未涉及，状态不变。

### 已知问题与下一步

- 真实本地大模型未测（见上）；模型不可用时的规则识别覆盖范围同第一轮，并新增“电价每年涨/降 x%”。
- 演示第 6 幕会切换到试算视图展示卡片（与第 3、4 幕方式相同）。
- 迁移的第一轮方案只能还原第一轮表单中仍存在的字段；条件对比中缺失项显示“未填写”。
- 30 秒理解度、普通笔记本耗时、Firefox/Safari、读屏审计仍未做（同第一轮）。
- 本轮按任务书只在功能分支提交，未改 `CHANGELOG.md`、`docs/REVIEW_INDEX.md`（与根目录 `AGENTS.md` round4 约定的冲突同第一轮说明）。

## [5060回交] 前端第三轮收尾：能见度（2026-10-09）

按 `docs/handoff/frontend_redesign/PROMPT_round3.md` 执行（前两轮任务书的原则与诚实规则继续有效），在 claude.ai/code 云端会话中完成并普通推送。

```text
起始SHA：e7f0cf1（feat/5060-product-ui 最新提交，含 PROMPT_round3.md）
分支：feat/frontend-round3（普通推送；未改 main，未强推，未建 Release/Tag，未开 PR，未访问其他仓库）
后端：未改动任何文件（含示例白名单）
```

### 提交拆分（远程 SHA）

| 批次 | SHA | 内容 |
| --- | --- | --- |
| 1 | `7ddcd70` | 第 1、2、5 项：`failed` 与“不可用”分开显示；`dropped` 列为“已忽略”；修改清单原值显示“0%（默认）”“自动比选”/候选列表 |
| 2 | `03facbf` | 第 3 项：规则识别列出“没能识别”的片段；预算“改为/改成/调到…”等写法与千分位 |
| 3 | `9162bb1` | 第 4 项：示例条件保留回放的电价档案；第 6 项：打印简报表头重复、行不拆分、2 页 A4；打印证据 |
| 4 | 本记录所在提交 | 验收脚本补充第三轮各项、两处图标尺寸修正、截图、本记录 |

### 提交身份自查

开工前在仓库内设置 `user.name=tingfengy2000-creator`、`user.email=tingfengy2000-creator@users.noreply.github.com`。推送前 `git log --format='%h %an %ae %cn %ce' e7f0cf1..HEAD`：本轮全部提交的作者与提交者均为 `tingfengy2000-creator <tingfengy2000-creator@users.noreply.github.com>`；提交信息不含 AI 署名或 Co-Authored-By 行。

### 修改文件

- `operation_planning/ui/assets/js/agent.js`：传出 `dropped`；404、其他 HTTP 错误、网络错误、超时归为“不可用”，只有接口正常返回 `status=failed` 才是“没理解”。
- `operation_planning/ui/assets/js/tool.js`：`failed` 提示与原因、不再触发规则识别；“已忽略”；“没能识别”；两处无尺寸的提示图标改为固定尺寸。
- `operation_planning/ui/assets/js/form.js`：`agentFromText`（原值说明）；`parseAsk` 记录命中位置、列出未识别片段、预算写法；`formFromRequest` 电价分支修正。
- `operation_planning/ui/assets/js/export.js`：简报表格 `thead/tbody`、打印样式、碳口径说明去字段名。
- `operation_planning/ui/assets/css/tool.css`：`.pr-dropped`、`.ask-unrec`。
- `scripts/check_frontend_redesign.cjs`、`docs/handoff/screenshots/frontend_round3/`、本记录。

### 逐项说明与验收

自动脚本 `node scripts/check_frontend_redesign.cjs`：**999 项检查，0 项不通过**（第 4 批最后一次代码修改后运行；第二轮为 955 项）。开工时在新后端上先跑了第二轮脚本：955 项中 1 项不通过，正是本轮要改的“failed 也改用规则识别”旧期望，其余（含实时储能/卖电/自定义电价/年涨幅）全部通过。

| # | 验收标准 | 结果 | 依据 |
| --- | --- | --- | --- |
| 1 | 第一、二轮验收全部仍通过 | 通过 | 同一脚本，旧检查全部保留；只把“failed → 规则识别”的旧期望改为本轮要求。 |
| 2 | 桩服务 `failed`（含 reason）、`ok + dropped`、`unavailable` 三种显示；`failed` 不触发规则识别 | 通过 | `failed`：显示“本地大模型没能可靠理解这句话，请换个说法或直接修改表单”和原因，表单不变、只调用一次理解接口；`ok + dropped`：“已忽略：空调型号（用户未提及）”，响应没有 `dropped` 时不显示；`unavailable`/404/超时/HTTP 500：“本地大模型暂不可用（…），已改用规则识别”并按规则写入。修改清单原值：年涨幅“0%（默认）”，自动比选时光伏“自动比选”（候选列表模式写“候选 0、1、2 kWp”）。 |
| 3 | 规则识别三项写入；无法识别片段列出 | 通过 | 模型未启动时“预算改为60000元，使用时段改为18点到22点，电价每年涨3%”写入 60000 / 18 / 22 / 3%；“预算改成6万”“预算调到6万元，其他条件不变”“预算60,000元”均为 60000；“预算改为50000元，换成格力空调和朝南的窗户”列出“没能识别：‘换成格力空调’、‘朝南的窗户’”。 |
| 4 | 三档示例条件重算与回放一致（≤1 元） | 通过（差 0 元） | 见下表；脚本对三档 12 个方案逐一比较导出 JSON 中的 `total_cost_npv_cny`，并核对请求的 `tariff_id`、`tariff_application` 与回放相同。 |
| 5 | 打印 PDF 跨页表格有表头，无空白页 | 通过 | Chromium 打印 A4：三档均 2 页（修改前 3 页、第 3 页大半空白）。A4 下表格恰好没有跨页，另用 A5 压力打印：容量比选表跨第 2/3 页，第 3 页首行为重复表头（修改前第 3 页直接从数据行开始）。脚本检查 thead、打印样式、无强制分页、A4 页数 ≤2。 |
| 6 | 提交作者/提交者为 tingfengy2000-creator | 通过 | 见“提交身份自查”。 |

#### 第 4 项：三档示例条件载入后重算的 10 年总花费（元）

原因：第二轮第 4 批把“年涨幅”一行插在“有电价档案”分支与它的 `else` 之间，使请求没有年涨幅时总是落到固定价 0.66 元/kWh。修正后按回放请求原样使用 `guangzhou_industrial_lt1kv_202610` + `current_tariff_on_reference_weather`。

| 示例 | 方案 | 回放 | 修正前重算（固定 0.66） | 修正后重算 | 差值 |
| --- | --- | ---: | ---: | ---: | ---: |
| 小档 | 只用电网 | 6,617.25 | 3,887.21 | 6,617.25 | 0 |
| 小档 | 加装光伏 | 5,813.85 | 3,887.21 | 5,813.85 | 0 |
| 小档 | 加装小风机 | 95,201.89 | 93,050.26 | 95,201.89 | 0 |
| 小档 | 光伏 + 小风机 | 95,193.98 | 93,050.26 | 95,193.98 | 0 |
| 中档 | 只用电网 | 700,362.53 | 397,570.37 | 700,362.53 | 0 |
| 中档 | 加装光伏 | 572,549.36 | 390,566.22 | 572,549.36 | 0 |
| 中档 | 加装小风机 | 786,602.53 | 485,393.61 | 786,602.53 | 0 |
| 中档 | 光伏 + 小风机 | 659,651.08 | 478,544.74 | 659,651.08 | 0 |
| 大档 | 只用电网 | 802,256.14 | 460,298.08 | 802,256.14 | 0 |
| 大档 | 加装光伏 | 622,520.58 | 438,101.41 | 622,520.58 | 0 |
| 大档 | 加装小风机 | 888,168.55 | 547,946.95 | 888,168.55 | 0 |
| 大档 | 光伏 + 小风机 | 709,725.20 | 526,513.64 | 709,725.20 | 0 |

修正后差值在双精度下为 0（不只是 ≤1 元）。回放请求另含 `room.equipment_count`、`pv.pv_capacity_kwp`、`hybrid.import_price_cny_per_kwh=0.66`、`hybrid.wind.site_id/year`、`carbon.carbon_price_cny_per_t=null`、`storage.round_trip_efficiency=0.9` 等回显/别名字段，表单请求不发送它们；这些都等于后端默认值或同义字段，上表结果相同即为证明。

### 任务书未覆盖、按原则直接处理的小问题

1. **理解接口 HTTP 5xx 归为“不可用”**：任务书只列 `unavailable`/404/超时走规则；服务出错不是“模型没理解”，按“不可用”处理（显示“理解接口出错（HTTP 500）”并改用规则）。
2. **两处提示图标没有尺寸**：“已改用规则识别”提示和“台数比选已过期”提示里的图标会按容器宽度放大（390 宽时约 270 px），第二轮截图没有覆盖这两个状态。改为与其他小提示相同的 16 px，并用脚本扫描主要页面与状态，没有其他超大图标。
3. **“预算60,000元”被读成 60**：千分位逗号截断数字，一并修正。
4. **简报“减碳口径”出现后端字段名 `avoided_kgco2`**（5090 打印的 PDF 可见）：改为与结果页相同的“自用减碳量”。
5. **`dropped` 中不在表单映射里的字段**显示为“其他条件”，不显示英文字段名。
6. 规则识别的“没能识别”忽略“其他条件不变”“请”“谢谢”等无内容片段；按“和”切分可能把一个短语拆成两段列出，宁可多提醒。

### 截图

`docs/handoff/screenshots/frontend_round3/`，1440（1 倍）与 390（2 倍）× 浅色/深色：

| 前缀 | 内容 |
| --- | --- |
| `01_model_ok_dropped_defaults` | 模型提案：原值“0%（默认）”“自动比选”，下方“已忽略：空调型号（用户未提及）” |
| `02_model_failed_reason` | `failed`：没能可靠理解 + 原因，未改用规则 |
| `03_model_unavailable_rules` | `unavailable`：暂不可用，已改用规则识别（三项写入） |
| `04_rules_unrecognized` | 规则识别：“没能识别：…” |
| `05_sample_conditions_tariff` | “从小档示例开始”后电价为官方分时档案（不再是 0.66 固定价） |
| `print/` | 三档 A4 简报 PDF 与逐页图；A5 压力打印第 3 页修改前后对比 |

`01`–`03` 的模型返回由截图脚本拦截两个 agent 接口给出固定内容（与验收脚本桩服务同一契约），**不是真实模型输出**。

### 需要5090处理的问题

无。本轮没有发现会导致结果数字错误的后端缺陷。第 4 项的费用差异来自前端表单分支错误，已在前端修正。

### 已知问题

- `failed`/`dropped` 的新显示只用测试桩验证；真实模型下的 `dropped` 内容以 5090 第 22 节记录为准，未在本机复现（云端没有本地模型）。
- 打印只用 Chromium 检查（A4 与 A5 压力打印）；Edge/Firefox/Safari 的原生打印对话框未测。
- 规则识别仍是有限规则；“没能识别”只是提醒，不判断语义。
