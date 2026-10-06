# 5060交接：审查结论与界面重构方向

- 适用对象：在 claude.ai/code 中接手 5060 工作的 Claude Code 会话，以及 5090 和用户。
- 基线：`fix/5090-project-load-handoff` @ `64c58ebf0a330537dcb851771c0d595b55f3c66a`
- 撰写日期：2026-10-06（由 5060 侧聊天会话完成静态审查后整理）
- 本文件放入仓库路径：`docs/handoff/5060_review_and_ui_direction.md`。之后三方（5060聊天、Claude Code、5090）以本文件为准；结论变化时更新本文件，不在聊天里口头改。

---

## 0. 给 Claude Code 的开工说明

你是项目里的“5060”角色：负责前端界面重构、业务产品化、导出和文档。数值实验由 5090 机器负责，你不运行任何热湿、光伏、风电、生命周期或 LLM 计算。

开工顺序：

1. 只在 `tingfengy2000-creator/nengzhihe` 仓库工作。**不得访问、读取或修改该账号下任何其他仓库，尤其是“乡艺有据 / xiangyi-youju”。**
2. 从 `fix/5090-project-load-handoff` 创建工作分支 `feat/5060-product-ui`（若平台强制使用 `claude/...` 前缀，用平台分支名，并在回交里写明）。
3. 第一个提交：把本文件原样放到 `docs/handoff/5060_review_and_ui_direction.md`。
4. 按第 3 节顺序阅读仓库文档，再按第 8 节的任务清单开工。
5. 每次停下来推送前，按第 9 节模板写回交说明（放在提交信息或 `docs/handoff/5060_round_log.md`）。

硬性规则：

- 不改 `main`，不强推，不创建 Release/Tag，不开 PR 合并到 main（可以开 PR 供审查，但不合并）。
- 不改天气数据、SD6 功率曲线、报价原始证据、核心算法（`thermal_model.py`、`pv.py`、`wind.py`、`hybrid.py`、`lifecycle.py`、`economics.py`、`project_load.py`）。发现算法问题写进回交说明交给 5090。
- 不改已有结果目录 `operation_planning/results/**` 和历史证据字节。
- 前端不重新聚合电量、不自行计算 NPV/成本；所有数字直接读 API 返回或固定回放 JSON。
- 用户改条件后，旧结果必须标记“已失效”，禁止导出旧结果。导出不得再次调用完整计算。
- 不用动画伪造计算进度；不提交密钥、模型权重、缓存。
- 不引入构建工具链（React/Vite/npm 打包）。保持“Python 原生 HTTP + 原生 HTML/CSS/JS”架构；图表用手写 SVG，不依赖外部 CDN（本地服务也要能离线运行）。

---

## 1. 作品理解

品牌“能智核”，参赛第十二届中国研究生智慧城市技术与创意设计大赛“智慧能源与环境”方向，目标冲击一等奖（对外不写成已获奖或保证）。记忆点“先试算，再决策”。

产品回答管理者（学校后勤、物业、园区、节能服务人员——目前是待验证的场景假设）的一个具体问题：

> 这些房间在当地气候下，空调一年要用多少电、花多少钱？如果再装光伏或小风机，10 年下来到底划不划算？

四种供能方案在同一逐时负荷上比较：S0 只用电网 / S1 加光伏 / S2 加小风机 / S3 风光组合。

**核心卖点（必须在界面上被看见）**：不是“年发电量抵年用电量”，而是逐小时匹配——发电时如果空调没在用电，那部分电就浪费了。默认样例里 2 kWp 光伏年发电 2214 kWh，超过空调年用电，但真正能抵用的只是一部分；风机 10 年多花约 8.9 万元；结论是“暂不加装、只用电网”最省钱。**能在花钱之前拦住一笔不划算的投资，就是作品的实用价值。** 推荐 S0 不是失败结果，界面要理直气壮地展示它。

架构：`operation_planning/app.py`（Python 原生 HTTP，API + 静态资源）+ `operation_planning/ui/`（原生 HTML/CSS/JS）。LLM 只做需求解释和受约束的工具调用，数值全部由代码计算。

---

## 2. 协作方式

- 5090：维护计算与数据基线，跑所有数值实验，审查 5060 的具体 SHA，验收后的集成 SHA 才是下一基线。
- 5060（Claude Code）：独立分支提交前端与业务修改，用固定真实样例开发；需要数值验证的新条件写成少量具体请求交给 5090。
- 5060 聊天会话：审查、设计方向、文档撰写；与 Claude Code 通过本仓库文件同步。
- 用户：最终决定品牌副标题、默认演示场景、正式提交内容。

仓库目前为公开状态。参赛指南要求作品匿名：正式材料中不要出现仓库链接或账号名；提交前由用户决定是否改回私有或另建匿名展示仓库。

---

## 3. 必读顺序

1. `START_HERE_5060.md`
2. `operation_planning/protocol/phase2b_project_load_handoff_5090.md`（本轮项目负荷契约）
3. `operation_planning/protocol/phase2b_api_result_contract.md`
4. `operation_planning/protocol/phase2b_5090_collaboration.md`、`phase2b_5090_acceptance.md`
5. `docs/handoff/replay_viewer/README.md`、`replay_cases.json`、`aircost_cases.json`
6. `operation_planning/ui/index.html`、`operation_planning/ui/assets/app.js`、`styles.css`
7. `operation_planning/app.py`（只读，理解请求/响应结构）

本地预览固定回放：

```bash
python -m http.server 8060 --directory docs/handoff/replay_viewer
```

---

## 4. 审查结论（已核对代码，2026-10-06）

### 4.1 交给 5090 的问题

| 编号 | 级别 | 问题 | 证据 | 请求 |
| --- | --- | --- | --- | --- |
| A1 | P0 | 演示基线不一致：固定回放/`START_HERE`锚点单房间年用电 1251.284 kWh（源码 `a4d4bd1`）；本轮完整年证据单房间（每间2台）1359.664 kWh。回放的 `load_context` 不含 `room_count`/`units_per_room`，无法判断各自对应的房间配置。 | `replay_cases.json` cases[0].load_context；`project_load_full_year.json` room_contract | 明确正式演示场景及完整 `room` 参数；按新契约重新导出回放（含 `project_load_contract`、`room_count`、`units_per_room`，至少 1 间/3 间两个 case）。 |
| A2 | P0 | 默认样例空调存在服务缺口：容量不足 1014 h，湿度超标 5186.6 %RH·h。首屏展示“空调本身不达标”会削弱作品。 | `replay_cases.json` cases[0].load_context.service_quality | 提供服务达标或缺口很小的配置作主演示；原场景保留为“设备选小了会怎样”的对照案例。 |
| A3 | P1 | `/api/operation/pv/run` 与 `/hybrid/run` 的非 Agent 路径只读 `payload["room"]`，忽略顶层 `room_count`/`units_per_room`/`quantity`；而 `/thermal/run` 经 `_thermal_inputs` 接受顶层字段。顶层写法会**静默按一间房**计算。 | `app.py` 约 122–135 行 vs 281、301 行 | 三个接口统一复用 `_thermal_inputs` 的房间归一化，或顶层出现这些字段时拒绝；补“顶层 room_count=3”契约探针。5060 前端会统一发送 `room.room_count`。 |
| A4 | P1 | 单房间轨迹 `scope` 文案过时：“room_count applied only in cost aggregation”，与新契约（`aggregate_project_load` 也使用）矛盾；完整年证据 `source_scope` 带着这句。 | `thermal_model.py` 176 行 | 改为 “room_count applied once by project_load / lifecycle”，下次出证据时更新。纯文案。 |
| A5 | P1 | 结果与证据中写死本机绝对路径 `E:\比赛\...`（约 205 个文件），换机器无法复查。 | `git grep "E:\\比赛"` | 新证据改用仓库相对路径；旧证据不改字节，可在说明中注明。 |
| A6 | P2 | CI 只校验 round3/round4，`operation_planning` 与 `tests/test_project_load_adapter.py` 不在 CI；5090 用 Python 3.14，README/CI 写 3.12。 | `.github/workflows/review.yml` | 加不依赖 GPU/LLM 的轻量契约测试 job；环境清单写明兼容范围。 |
| A7 | P2 | `docs/handoff/5060_start_prompt.txt` 残留 PowerShell 转义字符 `` `r`n``。 | 文件中部 | 清理。 |

### 4.2 仓库与参赛层面

- 根目录 `README.md`、`AGENTS.md` 仍是 round4“公共建筑风阀疑点核验与补证工作台”，并写着“私有仓库”。仓库公开后访客看到的是旧产品。**建议**：主线确定后由 5090 集成到新的 review 分支，重写根 README，旧风阀内容移到 `docs/archive/`。在此之前 5060 文档以 `START_HERE_5060.md` 和本文件为准。5060 可起草新 README 放在 `docs/handoff/README_draft.md`，不直接覆盖根 README。
- 两本账口径必须在界面上讲清：空调成本（设备+安装+运维+电费，按 `quote_scope`）与 S0–S3 比较（空调用电购电成本+风光设备生命周期）不是同一口径；S0 的 8258.47 元不含空调设备投资。
- 内部文档目标措辞统一为“冲击一等奖”。

### 4.3 当前前端（5060 负责修复）

- 主 UI 完全不发送 `room_count`、`units_per_room`、`quote_scope`（`app.js` 中出现 0 次），回放页也没有项目负荷 case。
- 6 个按研发阶段划分的页签：空调选型 / 光伏配置 / 风光联算 / 方案工作台 / 地区与电价 / 历史方案。用户必须先懂研发结构才知道从哪开始。
- “方案工作台”是旧 BOPTEST 研究线（标语“告警之后，先安排什么”），与当前主线冲突。
- 每页开头 15–20 个输入框；pvlib、SD6、windpowerlib、Hellman 指数、ACH、S0–S3、NPV 直接暴露在主界面；结果在页面最底部，原始 JSON 与结论混排。
- 结论：这是“给开发者看的调试界面”，不是给评委和管理者用的产品。

---

## 5. 设计目标

用户（项目负责人）的要求：**突出实用性和创新点，界面要高级，参考微软、谷歌、苹果、沃尔玛的成熟产品前端。** 参考的是它们的层级、留白、控件一致性和价格表达方式；不复制商标、专有字体或整页构图。

三条原则：

1. **答案先行**：先给一句管理者听得懂的结论和关键金额，再给图表，最后才是依据和原始数据。
2. **一条任务流**：用户不需要知道项目分几个研发阶段。
3. **专业藏在第二层**：术语、模型名、曲线来源进“查看依据”抽屉，不出现在主界面文案里。

明确不做：深色霓虹大屏、把开发日志当高级感、为了好看隐藏 S0、把费用取绝对值、动画伪造进度。

---

## 6. 信息架构

### 6.1 导航

顶栏：品牌 + 一级导航只有两项：**新建试算**、**我的方案**。右侧一个“关于数据与边界”入口。

旧页面处理：

- “空调选型 / 光伏配置 / 风光联算”合并进一条任务流。
- “地区与电价”变成任务流第 1 步里的“电价”选择器和一个弹层，不再独立成页。
- “方案工作台”（BOPTEST 旧线）从主导航移除。代码和 `index.v1-baseline.html` 保留不删，可在“关于数据与边界”里以“早期研究”链接进入，或仅保留在仓库中。
- “历史方案”成为“我的方案”。

### 6.2 任务流（单页分步，顶部步骤条）

**第 1 步：描述场景**

- 顶部一句话输入框（自然语言），示例占位：“广州，3 间 35㎡ 办公室，每间 2 台空调，工作日 8 点到 18 点，预算 6 万”。模型只负责把话解析成下方条件，解析结果以“条件标签”显示，用户可逐个点改。**Agent 不可用时输入框退化为提示，表单照常可用。**
- 基本条件卡（默认展示，不超过 8 项）：城市、天气参考年、房间面积、同类房间数、每间空调台数、使用时段、目标温度/湿度、研究期。
- “更多条件”折叠：窗墙比、新风、渗透、朝向、报价（设备/安装/运维、`quote_scope`）、寿命/保修、电价档案、屋顶面积、轮毂高度、外送设置、上传天气 CSV。

**第 2 步：空调需求与费用**

- 决策卡：“这 3 间办公室每年空调用电约 X kWh，10 年空调总花费约 Y 元（设备+安装+运维+电费）”。
- 服务状态横幅：达标（绿）/ 有缺口（琥珀，写明缺口小时数和含义，“设备偏小或目标偏严”）。
- 逐月用电/电费柱状图；单房间与项目合计并列（直接读 `single_room_summary` 与 `project_load_context`，不在前端乘）。

**第 3 步：比较供能方案（主舞台）**

- 决策卡（最大字号）：“建议：暂不加装，只用电网。10 年约 8,258 元。加装 2 kWp 光伏多花约 1,859 元；加装小风机多花约 8.9 万元。”金额与正负来自 `total_cost_npv_cny`、`incremental_npv_vs_s0_cny`。
- 四方案对比卡（横排 4 张，手机竖排）：每张卡显示状态标签、10 年总成本、相对只用电网多花/省下、年发电、年购电、负荷覆盖率。**S0 永远显示，作为基线放在第一位。**
- 创新可视化（见 7.4）：能源日历热力图、电去哪了流向条、典型日曲线。
- 预算/屋顶/报价造成的排除或缺失直接写在卡上，例如“超出预算 6 万元，已排除”“缺少光伏报价，暂无法比较”。

**第 4 步：决策与导出**

- 推荐理由（3 句以内）+ 适用边界（现场测风、并网审批、采购报价、同等服务水平未验证）。
- 导出：一页“决策简报”（打印/PDF 友好 HTML）、CSV（逐时或逐月）、JSON（完整 report）。全部从当前显示的 report 生成。
- 条件改变后，结果区整体置灰并显示“条件已修改，结果已失效——重新计算”，导出按钮禁用。

**我的方案**：卡片列表，每张显示条件摘要、结论、计算时间、数据来源（实时计算 / 固定回放），可对比两次方案的条件差异。

### 6.3 数据模式

界面右上角固定显示当前数据模式：

- **固定样例**：读取 `docs/handoff/replay_viewer/*.json`，标签“5090 已验算样例”。
- **实时计算**：调用本地 API（需要 5090 环境或完整依赖）。
- 未列入样例、又无法实时计算的条件：显示“待计算 / 待 5090 验算”，**绝不返回旧样例冒充新结果**。

---

## 7. 视觉与交互系统

### 7.1 设计取向

- Apple：克制的排版层级、大号数字、大量留白、一屏一个重点。
- Google Material 3：状态标签（chips）、表单控件一致性、清晰的焦点和错误状态。
- Microsoft Fluent：数据密集的对比表和依据面板的对齐与层级。
- Walmart：价格表达——总价大字、“多花 / 省下”明确带方向，用户不用自己算差价。

### 7.2 设计令牌（CSS 变量，起点，可调）

```css
:root{
  /* 中性色 */
  --bg:#F6F7F9; --surface:#FFFFFF; --surface-2:#F1F3F5;
  --ink:#1B1F24; --ink-2:#4A5260; --ink-3:#7A8391; --line:#E3E7EC;
  /* 品牌：深青绿，代表能源/环境 */
  --brand:#0F6E68; --brand-weak:#E6F3F1; --brand-strong:#0A524E;
  /* 方案配色（图表固定，不靠颜色单独传达含义） */
  --c-grid:#5B6573; --c-pv:#E3A008; --c-wind:#2F80C9; --c-load:#1B1F24;
  /* 状态 */
  --ok:#1E7F4F; --ok-weak:#E7F5EE;
  --warn:#9A5B00; --warn-weak:#FFF4E0;
  --bad:#B42318; --bad-weak:#FDECEA;
  --unknown:#5B6573; --unknown-weak:#EEF0F3;
  /* 形状与阴影 */
  --r-sm:8px; --r:12px; --r-lg:16px;
  --shadow-1:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.08);
  --shadow-2:0 8px 24px rgba(16,24,40,.08);
  /* 字体：系统中文字体栈，不嵌入专有字体 */
  --font:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC","Segoe UI",sans-serif;
  --mono:ui-monospace,SFMono-Regular,Consolas,monospace;
}
```

- 8px 栅格；正文 15–16px；决策卡数字 40–48px，`font-variant-numeric: tabular-nums`。
- 浅色为主；可选支持 `prefers-color-scheme: dark`，但不做霓虹。
- 桌面最大内容宽 1200px；断点 1024 / 768 / 480；手机上四方案卡竖排，热力图横向滚动。
- 可访问性：对比度 ≥ 4.5:1；所有状态同时用文字+图标+颜色；键盘可达；焦点环清晰。

### 7.3 状态语义（与契约一一对应，不得混用）

| 契约值 | 界面标签 | 颜色 | 说明文案示例 |
| --- | --- | --- | --- |
| `eligible` | 可比较 | ok | 条件齐全，参与比较 |
| `unknown` | 条件不全 | unknown（灰） | 缺少光伏报价，暂无法比较——**不是淘汰** |
| `excluded` | 已排除 | bad | 超出预算 / 屋顶面积不足 / 高度超限 |
| `equivalent` | 与某方案相同 | unknown | 例：0 kWp 光伏等同只用电网 |
| `service_gap` | 空调有缺口 | warn | 有 X 小时冷量不足，结果不代表同等舒适度下的最优投资 |
| 推荐 `conditional` | 有条件推荐 | brand | 在已核实条件齐全的方案中最省 |
| 推荐 `conditional_subset` | 部分比较 | warn | 部分方案条件不全，仅在其余方案中比较 |
| 推荐 `not_available` | 暂无推荐 | unknown | 说明缺什么 |

费用字段：`npv_cny` 是净现金流现值（通常为负），`total_cost_npv_cny` 是成本现值，`incremental_npv_vs_s0_cny` 是相对只用电网的增量现值（负数 = 比只用电网多花）。界面写“多花 / 省下 X 元”，方向由符号决定，**不得取绝对值后丢掉方向，不得把成本现值标成收益或利润。**

### 7.4 创新点可视化（作品记忆点）

1. **能源日历热力图**：横轴 365（366）天，纵轴 24 小时，三种视图切换——空调用电、发电、“发电时空调在用吗”（自用 / 浪费 / 购电三色）。一眼看出白天发电高峰与空调使用时段的重合与错位，这是“逐时匹配”区别于“年度抵扣”的核心证据。数据直接用 report 的逐时序列（回放默认样例保留了完整 8784 小时），浏览器只做显示聚合，不重算年度指标。
2. **电去哪了**：一条堆叠横条（或简洁桑基）：发电 → 自用 / 弃电 / 外送；用电 → 自发自用 / 电网购入。
3. **典型日曲线**：选一天（默认夏季典型日），负荷、光伏、风电三条曲线叠加。
4. **10 年成本瀑布或分组柱**：设备投资、运维、购电，S0 作基线。

图表全部手写 SVG，配图例和数值提示（hover/tap），配色用 7.2 的方案色。

### 7.5 文案与术语映射（主界面用左列，依据抽屉可出现右列）

| 主界面 | 技术名 |
| --- | --- |
| 只用电网 | S0_grid |
| 加装光伏 | S1_pv |
| 加装小风机 | S2_wind（SWCC SD6） |
| 光伏+小风机 | S3_pv_wind |
| 10 年总花费 | total_cost_npv_cny（折现后） |
| 比只用电网多花 / 省下 | incremental_npv_vs_s0_cny |
| 发的电当时就用上的比例 | 自用率 |
| 空调用电中由自发电覆盖的比例 | load_coverage_rate |
| 浪费掉的电 | curtailment |
| 风速随高度换算 | Hellman 幂律 0.14 |
| 光伏发电计算 | pvlib |
| 空调冷量不足的小时数 | capacity_shortfall_hours |

依据抽屉里保留完整来源：天气文件与哈希、模型版本、曲线来源、源码提交 SHA、计算版本。

### 7.6 品牌与副标题

用户已授权暂用更贴切的副标题，正式申报前由用户确认。候选（不改仓库名、包名、API、字段 ID、历史证据目录）：

- 能智核｜气候驱动的建筑空调用能与风光投资决策
- 能智核｜先试算，再决策——建筑空调与风光投资一站式测算

---

## 8. 第一轮任务清单（Claude Code 执行）

按顺序，每完成一项可单独提交：

1. **提交本文件**到 `docs/handoff/5060_review_and_ui_direction.md`。
2. **设计令牌与基础组件**：重写 `operation_planning/ui/assets/styles.css`（可读、分区注释，不再单行压缩），实现按钮、输入、选择器、条件标签、状态标签、卡片、决策卡、抽屉、步骤条、空状态、失效遮罩。
3. **固定样例数据适配层**：新建 `operation_planning/ui/assets/data.js`（或同等模块），统一读取实时 API 响应与回放 JSON，输出同一视图模型；不在此层做任何数值计算，只做字段映射与格式化。回放 JSON 可复制到 `operation_planning/ui/assets/samples/`，或让本地服务直接读取 `docs/handoff/replay_viewer/`，二选一并在回交里说明。
4. **任务流页面**：重写 `index.html` 与 `app.js`（可拆成多个模块文件），实现第 6 节四步与“我的方案”。请求体统一使用 `room.room_count`、`room.units_per_room`、`quote_scope`，不再发送旧字段 `quantity`。
5. **第 3 步主舞台**：四方案对比卡 + 决策卡 + 能源日历热力图 + 电去哪了 + 典型日曲线。先用“默认四方案”样例完成，再接其余 3 个回放 case（预算 6 万、PV 报价缺失、屋顶 1㎡）验证状态标签。
6. **结果失效与导出**：条件变化即失效；决策简报（打印样式 `@media print`）、CSV、JSON 从当前视图模型导出。
7. **空调成本页**：接 `aircost_cases.json`，展示两本账口径说明。
8. **响应式与可访问性**：1440 / 1024 / 390 宽度检查。
9. **截图**：桌面与手机各一组，存 `docs/handoff/screenshots/5060_round1/`。
10. **README 草稿**：`docs/handoff/README_draft.md`，面向评委和新协作者介绍当前主线（不覆盖根 README）。

基线数字处理：A1 未解决前，界面所有数字从数据读取，不在 HTML/JS 写死任何年用电量或金额；文档中引用数字时注明来源文件和源码 SHA。

### 第一轮验收标准

- 第一次打开的人 30 秒内能看懂“这个工具帮我决定什么、结论是什么”。
- 默认样例在固定回放模式下完整走通四步，数字与 `replay_cases.json` 逐项一致。
- 4 个回放 case 的状态标签、排除原因、推荐类型显示正确；`unknown` 没有被显示成排除。
- S0 在任何情况下可见。
- 改任一条件后结果失效、导出禁用。
- 主界面不出现 pvlib、SD6、Hellman、NPV、S0–S3 等术语（依据抽屉除外）。
- 桌面和手机截图齐全；页面无横向滚动（热力图容器内滚动除外）。

---

## 9. 回交模板

```text
[5060回交] 第N轮
起始SHA：
本次提交SHA：
分支：
修改文件：
业务/接口变化：（请求字段、默认值、单位、校验、推荐状态、计算触发、结果失效、导出）
是否影响数值：否 / 是（说明）
截图：docs/handoff/screenshots/...
需要5090验证的具体请求：（逐条写出请求体或条件）
已知问题与下一步：
```

---

## 10. 待用户决定

1. 正式演示主场景（依赖 5090 对 A1、A2 的回复）。
2. 品牌副标题（7.6 候选或其他）。
3. 仓库公开/私有与匿名展示方式（正式提交前）。

---

## 11. 5060（Claude）复核补充（2026-10-07）

基线：`fix/5090-project-load-handoff` @ `64c58eb`。在云端克隆仓库只读复核，未运行任何年度试算。

### 11.1 5090本轮证据核对：通过

- `project_load_full_year.json`：1间×2台 1359.664 kWh；3间 4078.992 kWh，比例 3.0；2 kWp 光伏 2213.987 kWh、S3 发电 3123.984 kWh 不随房间数变化；3间 S0 购电 = 项目负荷；空调成本页年负荷 = 4078.992 kWh。与5090回复一致。
- `run_manifest.json` 的 `output_sha256 = bae2c00b…` 与结果文件按 `sort_keys + 紧凑分隔符` 重算一致（不是文件字节哈希，回交说明里写清楚即可）。
- 短契约测试 `tests.test_project_load_adapter` + `tests.test_aircost_handoff` 共6项在云端 Python 3.13 通过（仅3行契约样例，不是年度结果）。
- 第4节 A1、A3、A5（205个文件含 `E:\比赛`）、A6、A7 已逐项在代码中确认属实。

### 11.2 新增问题（交5090）

| 编号 | 级别 | 问题 | 证据 | 请求 |
| --- | --- | --- | --- | --- |
| A8 | P1 | 自然语言修改 schema 的 `room` 只允许 `start_hour/end_hour`，不能改 `room_count`、`units_per_room`、面积。用户说“3间、每间2台”时 Agent 无法应用。 | `task_changes.py` 17–18 行 | 二选一：扩展 schema（含校验与冲突规则），或明确“房间数量只能在表单改”。5060 暂按后者做：这些条件由表单发送，解析结果里不出现可点改的房间数标签。 |
| A9 | P1 | 根目录 `AGENTS.md` 仍是 round4 风阀合约，并写“每次更新推送到 main”，与 `START_HERE_5060.md`“不改 main”冲突；编码代理会自动读取 `AGENTS.md`。 | `AGENTS.md` | 在根 `AGENTS.md` 顶部加一行“当前主线以 START_HERE_5060.md 为准；round4 段落为历史”，或移入 `docs/archive/`。 |
| A10 | P2 | `requirements-phase2b.txt` 只有 windpowerlib，缺 pvlib/numpy/pandas/scipy（在 phase2 文件里）；单装 2b 无法导入 `pv.py`。 | 两个 requirements 文件 | 2b 文件首行加 `-r requirements-phase2.txt`。 |
| A11 | P2 | `/thermal/run` 同时返回单房间 `result.load_series` 和 `project_load.load_series`，全年两份 8784 行序列，响应体翻倍。 | `app.py` 254 行 | 非阻塞；前端只读 `project_load`。如需瘦身由5090决定。 |
| A12 | P2 | 仓库可匿名 `git ls-remote`，确认为公开；`AGENTS.md` 写“private”。 | — | 与第2节匿名问题一起由用户决定。 |

### 11.3 5060 推送通道（已解决，2026-10-07）

5060 通过用户电脑上的本地工作区、使用仅限本仓库的细粒度令牌推送；令牌不在仓库内。分支 `feat/5060-product-ui` 自 `fix/5090-project-load-handoff` @ `64c58eb` 创建，本文件为该分支第一个提交。

**请 5090 优先回复第 4.1 节 A1、A2、A3 与第 11.2 节 A8、A9**；前端在 A1/A2 有结论前使用现有固定回放，多房间风光比较显示“待5090验算”。
