/* 能见度 · 关于数据与边界
 * 数据来源从计算服务的目录接口读取（/api/operation/options、/api/operation/wind/profiles）；
 * 未连接计算服务时，改用示例回放文件中记录的来源。技术名只在本页和依据抽屉出现。 */
import { $, esc, fmt, icon } from './util.js';
import { app, on } from './state.js';
import * as data from './data.js';
import { BOUNDARIES } from './results.js';
import { tariffList } from './form.js';

let el = null, wind = null;

const GLOSSARY = [
  ['只用电网', 'S0_grid', '不加装发电设备，作为比较基线'],
  ['加装光伏', 'S1_pv', '屋顶光伏，逐时发电由 pvlib 计算'],
  ['加装小风机', 'S2_wind', 'SWCC 认证 SD Wind Energy SD6 功率曲线；轮毂高度风速按 Hellman 幂律（指数 0.14）由 10 米风速换算'],
  ['光伏 + 小风机', 'S3_pv_wind', '两种发电先合并，再与空调负荷按同一时间轴匹配一次'],
  ['10 年总花费', 'total_cost_npv_cny', '研究期内购电费、设备投入、运维、更换减残值的折现成本'],
  ['比只用电网多花 / 省下', 'incremental_npv_vs_s0_cny', '负数 = 比只用电网多花，正数 = 省下；页面保留方向，不取绝对值'],
  ['净现金流现值', 'npv_cny', '通常为负，是花费的现值，不是利润'],
  ['当时用上 / 浪费 / 从电网买', 'self_use_kwh / curtailment_kwh / grid_import_kwh', '逐小时匹配后的三种去向'],
  ['空调用电由自发电覆盖', 'load_coverage_rate', '一年中空调用电有多少由当时的自发电满足'],
  ['空调达标 / 有缺口', 'within_modeled_scope / service_gap', '有缺口时写明冷量不足小时，结果不代表同等舒适度下的最优投资'],
  ['可比较 / 条件不全 / 已排除 / 与其他方案相同', 'eligible / unknown / excluded / equivalent', '条件不全不是排除；排除原因原文显示'],
  ['有条件推荐 / 部分比较 / 暂无推荐', 'conditional / conditional_subset / not_available', '部分比较时，不能说条件不全的方案已被击败'],
  ['粗算（年发电抵年用电）', 'annual_offset_estimate', '只作对照，不参与推荐'],
  ['容量比选', 'pv_capacity_sweep / recommended_pv_capacity_kwp', '有限候选；按 S1 相对 S0 增量现值（NPV）选择，不是全局最优'],
  ['每吨减碳成本', 'cost_per_tco2_cny', '负数表示该成本口径下省钱，不是碳交易收入'],
  ['储能理想上限', 'storage_upper_bound', '理想调度上限，不含电池成本、寿命和替换，不是储能推荐'],
  ['典型周预览', 'hybrid/preview · preview_period_physics_only', '固定选 7 月或 1 月 15–22 日，只做物理匹配，不含费用与推荐，不外推全年'],
  ['冷量不足小时', 'capacity_shortfall_hours', '空调冷量不足以维持目标温度的小时数']
];

function sourcesHtml(s) {
  const o = app.options;
  const c0 = s && s.cases.get('tier_small');
  const wctx = c0 && c0.weather && c0.weather.provenance && c0.weather.provenance.context;
  const cities = o ? o.cities.map((c) => `${c.name}（${c.cached_years.join('、')}）`).join('；') : null;
  const tariffs = o ? tariffList(o) : [];
  const factors = o ? ((o.carbon_factors || {}).factors || []) : [];
  const cc = c0 && c0.carbon_context;
  const notice = factors[0] || (cc && cc.factor) || null;
  return `
  <div class="about-grid">
    <article class="card"><h3>${icon('sun')}天气</h3>
      <p>${esc(wctx ? wctx.source : 'Open-Meteo Historical Weather API')}（${esc(wctx ? wctx.dataset_kind : 'historical_reanalysis')}）逐小时数据，仓库缓存，不在运行时联网。${cities ? `已缓存：${esc(cities)}。` : ''}</p>
      ${wctx ? `<ul class="notes">${(wctx.notes || []).map((n) => `<li>${esc(n)}</li>`).join('')}</ul>` : ''}</article>
    <article class="card"><h3>${icon('bolt')}光伏与小风机</h3>
      <p>光伏逐时发电由 pvlib 按辐照、温度和 10 米风速计算。小风机：${wind ? `${esc(wind.manufacturer)} ${esc(wind.model)}，额定 ${fmt.d(wind.rated_power_kw, 1)} kW，测试轮毂高度 ${fmt.d(wind.tested_hub_height_m, 1)} m，曲线来源 <a href="${esc(wind.source_url)}" target="_blank" rel="noopener noreferrer">SWCC 认证报告</a>（windpowerlib ${esc(wind.windpowerlib_version || '')}）` : 'SWCC 认证的 SD Wind Energy SD6 公开功率曲线'}；使用参考空气密度，没有按当地气压、温度修正。</p></article>
    <article class="card"><h3>${icon('leaf')}电网排放因子</h3>
      <p>${notice ? `${esc(notice.issuer)}《${esc(notice.source_title)}》${esc(notice.notice_no || '')}（${esc(notice.published || '')}）${notice.url ? ` · <a href="${esc(notice.url)}" target="_blank" rel="noopener noreferrer">公告</a>` : ''}${notice.attachment_url ? ` · <a href="${esc(notice.attachment_url)}" target="_blank" rel="noopener noreferrer">附件</a>` : ''}。` : ''}默认按城市所在省份最新年份的电力平均因子，也可切换全国、区域等对照因子。</p>
      ${factors.length ? `<details class="more"><summary>全部 ${factors.length} 个因子</summary><div class="tablewrap"><table class="table"><thead><tr><th>地区</th><th>年份</th><th>口径</th><th class="r">kgCO₂/kWh</th><th>技术名</th></tr></thead><tbody>${factors.map((f) => `<tr><td>${esc(f.region)}</td><td>${esc(String(f.data_year))}</td><td>${esc(f.basis)}</td><td class="r num">${fmt.d(f.value_kgco2_per_kwh, 4)}</td><td class="mono">${esc(f.factor_id)}</td></tr>`).join('')}</tbody></table></div></details>` : ''}
      <p class="hint">情景估算，不是核证减排量；不含设备制造、运输、回收的隐含排放。碳价情景只是“按某价格出售”的假设，资格未核实。</p></article>
    <article class="card"><h3>${icon('doc')}电价档案</h3>
      ${tariffs.length ? `<div class="tablewrap"><table class="table"><thead><tr><th>档案</th><th>有效期</th><th>状态</th><th>来源</th></tr></thead><tbody>${tariffs.map((t) => `<tr><td>${esc(t.area)}<div class="xsmall muted mono">${esc(t.tariff_id)}</div></td><td>${esc(t.effective_start)}–${esc(t.effective_end)}</td><td>${t.verified ? `<span class="tag ok">${icon('check')}已核验</span>` : `<span class="tag warn">${icon('warn')}待核验</span>`}</td><td>${t.source_url ? `<a href="${esc(t.source_url)}" target="_blank" rel="noopener noreferrer">${esc(t.source_title || '来源')}</a>` : '—'}</td></tr>`).join('')}</tbody></table></div>`
        : `<p>${s && s.file.main_tariff ? `示例主电价档案 ${esc(s.file.main_tariff.tariff_id)}${s.file.main_tariff.provisional ? '（待核验）' : ''}，来源 <a href="${esc(s.file.main_tariff.source_url)}" target="_blank" rel="noopener noreferrer">公开抄录页面</a>。` : ''}连接计算服务后显示完整电价档案目录。</p>`}
      <p class="hint">标为“待核验”的档案是公开抄录、原始公告尚未核对；套用到参考天气年时是现行价格结构情景，不是真实账单。</p></article>
    <article class="card"><h3>${icon('layers')}示例回放</h3>
      <p>${s ? `docs/handoff/replay_viewer/${esc(data.SAMPLE_FILE)}（${esc(s.file.format_version)}，${s.order.length} 个案例，源码提交 <span class="mono">${esc(fmt.sha((s.file.source || {}).source_commit, 10))}</span>，由实时接口 HTTP 调用生成的界面精简版；完整证据另存仓库）；典型周预览 replay_previews_v7.json（${esc((s.previewFile || {}).format_version || '')}）。` : '正在读取示例…'}示例只是起点，不代表真实客户、试点或节能收益。</p></article>
  </div>`;
}

export function show(root) {
  el = root;
  if (!el.dataset.ready) {
    el.dataset.ready = '1';
    el.innerHTML = `<section class="page-head"><div class="container"><p class="kicker">关于数据</p><h1 class="h2">每个数字从哪里来，算到哪里为止。</h1>
      <p class="sub">页面上的数字全部来自本机计算服务的实时结果或随仓库保存的回放文件。前端只做字段映射和显示用分组，不复制计算公式。</p></div></section>
      <section class="container samples-body">
        <h2 class="h3 group-title">数据来源</h2><div data-sources></div>
        <h2 class="h3 group-title">怎么算</h2>
        <ol class="method">
          <li><b>空调负荷</b>：按城市逐时天气、房间面积、层高、人数、设备散热、朝向、窗墙比、使用时段和目标温湿度，计算一间房全年每小时的冷量与用电；同类房间数只在项目层聚合一次。</li>
          <li><b>发电</b>：光伏按屋顶容量逐时计算；小风机按公开功率曲线和轮毂高度风速逐时计算。</li>
          <li><b>逐小时匹配</b>：每个小时，发电先供当时的空调；多出来的电如果不卖给电网就算浪费；不够的部分从电网买。浪费的电不算省钱，也不算减碳。</li>
          <li><b>10 年总账</b>：按电价档案或固定电价算购电费，加上设备投入、运维、更换、残值，折现后比较四种供电方式；“只用电网”永远是基线。</li>
          <li><b>容量比选</b>：在屋顶上限内取有限个光伏容量逐一算全年，选比只用电网省下最多的；被预算、屋顶排除或缺报价的容量不参与选择。</li>
          <li><b>碳</b>：只按当时用上的电乘电网平均排放因子；每吨减碳成本 = 比只用电网多花或省下的钱 ÷ 研究期减碳（由计算服务给出）。</li>
          <li><b>粗算对照</b>：把一年发电量直接抵一年用电量，作为常见算法的对照，不参与推荐。</li>
          <li><b>储能上限</b>：理想调度，先用发电供空调，再用原本浪费的电充电，不足时放电；不含电池成本，不是推荐。</li>
        </ol>
        <h2 class="h3 group-title">模型边界</h2>
        <ul class="notes big-notes">${BOUNDARIES.map((b) => `<li>${esc(b)}</li>`).join('')}<li>大档“工业厂房”是厂房空调分区的有界代理：只计厂房空调区，生产工艺、照明、插座等生产用电未计入，结果偏保守，不代表全厂能源方案。</li><li>典型周预览固定选择日期，只做物理匹配，不含费用和推荐，不外推全年。</li><li>页面不包含任何虚构的客户、试点、获奖、节能收益或现场精度。</li></ul>
        <h2 class="h3 group-title">术语对照</h2>
        <div class="tablewrap"><table class="table"><thead><tr><th>页面用语</th><th>技术名 / 字段</th><th>说明</th></tr></thead><tbody>${GLOSSARY.map(([a, b, c]) => `<tr><td>${esc(a)}</td><td class="mono">${esc(b)}</td><td style="white-space:normal">${esc(c)}</td></tr>`).join('')}</tbody></table></div>
        <h2 class="h3 group-title">分工</h2>
        <div class="about-grid two"><article class="card"><h3>后端计算与数值实验</h3><p>天气、热湿负荷、光伏、风机、逐时匹配、生命周期经济、碳与储能上限、实时接口与回放生成、性能与等价性验收。</p></article>
          <article class="card"><h3>前端产品化</h3><p>交互设计、数据适配层（不做数值计算）、图表与 3D 场景、导出与本机方案保存、诚实规则落地。</p></article></div>
        <p class="hint">作品匿名展示，不列个人姓名或账号。</p>
        <h2 class="h3 group-title">早期研究</h2>
        <p>早期的六页签研究工作台保留在 <a href="assets/legacy/index.html">assets/legacy/</a>，只作研究记录，不是当前产品主线。</p>
      </section>`;
  }
  const render = (s) => { $('[data-sources]', el).innerHTML = sourcesHtml(s); };
  render(data.samplesLoaded());
  data.loadSamples().then(render).catch(() => {});
  if (app.mode === 'live' && !wind) fetch('/api/operation/wind/profiles').then((r) => r.ok ? r.json() : null).then((j) => { wind = j && j.profiles && j.profiles[0]; render(data.samplesLoaded()); }).catch(() => {});
}
on('mode', () => { if (el && !el.hidden) show(el); });
