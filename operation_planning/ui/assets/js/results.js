/* 能见度 · 试算第 2–4 步：空调用电、比较方案、决策与导出
 * 所有数字直接读视图模型（后端或回放字段）。允许的显示用分组只有：按月加总画柱状图、
 * 按日期×小时排日历格、取某一天画曲线，均在图旁注明“仅用于显示”。 */
import { $, $$, esc, fmt, isNum, icon, toast } from './util.js';
import { app } from './state.js';
import { SCEN, sampleSourceText, samplesLoaded } from './data.js';
import { barChart, lineChart, sweepChart, ring, signedBarChart } from './charts.js';
import { createCalendar } from './calendar.js';
import { priceTable, scenIcon } from './home.js';
import * as story from './story.js';
import * as exp from './export.js';

let calInst = null, ui = { ringId: null, calSet: 'recommended', day: null, storeScen: null, storeCap: null, carbonPrice: true };
let lastVM = null;

/* 适用边界（随结果可见） */
export const ADEQUACY_NOTE = '达标判据：允许上班前预冷 1 小时（预冷用电已计入），只在使用时段检查冷量是否够用。冷量够用后再加台数，模型里年用电基本不变（未计入低负荷时的效率变化）。';
export const BOUNDARIES = [
  '空调负荷是城市级天气驱动的单房间模型情景，未经现场校准；只计空调用电，不含照明、插座、生产工艺和建筑总表负荷。',
  '小风机采用公开认证功率曲线和参考空气密度，没有按当地气压、温度修正，也没有现场测风。',
  '报价、寿命、电价为用户情景或公开档案，不是已核实的采购报价或真实账单；屋顶面积、承重、消防间距和并网需现场确认。',
  '碳是电网平均排放因子情景估算，不是核证减排量，不含设备隐含排放；碳收益资格未核实。',
  '没有证明现场节能、真实回本、采购适配或跨楼宇精度；容量比选是有限候选，不是全局最优。'
];

const yrs = (vm) => story.yearsText(vm.studyYears);
/* 后端说明文字里夹带的英文字段名，在主界面换成中文（依据抽屉保留技术名） */
const plain = (t) => String(t || '').replace(/avoided_kgco2/g, '自用减碳量');
const PRICE_BASIS = { 'baseline annual import bill / annual load; load-weighted mean for TOU': '只用电网时的年购电费 ÷ 年用电量（分时电价按负荷加权平均）' };
const genCands = (vm) => vm.candidates.filter(story.hasGen);
const srcText = (vm) => vm.kind === 'live' ? `本机实时计算 · ${fmt.date(vm.computedAt)}` : `示例回放 ${sampleSourceText(samplesLoaded())} · ${vm.label}`;

function hourlySets(vm) {
  const H = vm.hourly || {}, sets = [];
  if (vm.kind === 'live' && H.byScenario) {
    for (const c of genCands(vm)) if (H.byScenario[c.id]) sets.push([c.id, `${c.isRec ? '推荐 · ' : ''}${c.name}：${story.scenLabel(c)}`, H.byScenario[c.id]]);
    if (!sets.length && H.byScenario.S0_grid) sets.push(['S0_grid', '只用电网', H.byScenario.S0_grid]);
  } else {
    if (H.recommended) { const c = vm.byId[H.recommended.scenarioId]; sets.push(['recommended', `推荐 · ${c ? c.name : ''}${c && story.hasGen(c) ? '：' + story.scenLabel(c) : ''}`, H.recommended]); }
    if (H.combo) { const c = vm.byId.S3_pv_wind; sets.push(['combo', `光伏 + 小风机${c ? '：' + story.scenLabel(c) : ''}`, H.combo]); }
  }
  return sets;
}
const anyHourly = (vm) => { const s = hourlySets(vm); return s.length ? s[0][2] : null; };

/* ------------------------------------------------------------------ */
/* 第 2 步：空调用电                                                    */
/* ------------------------------------------------------------------ */
function step2(vm, T) {
  const sv = vm.service || {};
  return `
  <section class="rsec">
    <div class="decision">
      <p class="kicker">空调用电</p>
      <h2 class="h3">${esc(story.roomText(vm) || '你的房间')}${story.scheduleText(vm.request) ? ` · ${esc(story.scheduleText(vm.request))}` : ''}</h2>
      <div class="bigline"><span class="num big">${fmt.kwh(vm.load.annualKwh)}</span><span class="unit">kWh / 年</span></div>
      <p class="muted">项目合计空调用电（${esc(story.placeText(vm))}）。读自结果字段，页面不做乘除。</p>
      <div class="row" style="margin-top:12px">
        <span class="tag ${sv.tone || 'unknown'}">${icon(sv.icon || 'help')}${esc(sv.label || '服务状态未知')}</span>
        ${sv.status === 'service_gap' ? `<span class="small">冷量不足 <b class="num">${fmt.int(sv.shortfallHours)}</b> 小时 · 温度缺口 <b class="num">${fmt.d(sv.unmetTempDegH, 1)}</b> ℃·h · 湿度缺口 <b class="num">${fmt.d(sv.unmetRhPctH, 1)}</b> %·h</span>` : ''}
      </div>
      ${sv.status === 'service_gap' ? `<div class="callout warn" style="margin-top:14px">${icon('warn')}<span><b>空调有缺口，不是达标。</b>全年有 ${fmt.int(sv.shortfallHours)} 小时冷量不足。结果不代表同等舒适度下的最优投资；可回到第 1 步用「帮我算配几台」找最少达标台数。</span></div>` : ''}
      <p class="hint" style="margin-top:10px">${esc(sv.note || '')}${sv.modelNote ? ' ' + esc(sv.modelNote) : ''}</p>
    </div>
    <div class="grid2">
      <div class="card">
        <div class="card-head"><h3>逐月空调用电</h3><span class="xsmall muted">单位 kWh</span></div>
        <div class="chart" data-monthly></div>
        <p class="chart-note">把逐小时空调用电按月加总画柱，仅用于显示；年度数字以上方结果字段为准。</p>
      </div>
      <div class="card">
        <h3>单间与项目合计</h3>
        <dl class="kv">
          <div><dt>同类房间数</dt><dd class="num">${fmt.int(vm.roomCount)}</dd></div>
          <div><dt>每间空调台数</dt><dd class="num">${fmt.int(vm.unitsPerRoom)}</dd></div>
          <div><dt>项目合计空调用电</dt><dd><b class="num">${fmt.kwh(vm.load.annualKwh)}</b> kWh/年</dd></div>
          <div><dt>单间空调用电</dt><dd>${isNum(vm.load.singleRoomKwh) ? `<b class="num">${fmt.kwh(vm.load.singleRoomKwh)}</b> kWh/年` : '<span class="muted">— 结果未给出单间字段</span>'}</dd></div>
        </dl>
        <p class="hint">热湿模型按一间房计算，项目合计只在计算服务里按同类房间数聚合一次，页面不再相乘。</p>
        <p class="hint">${ADEQUACY_NOTE}</p>
        <div class="callout info" style="margin-top:14px">${icon('info')}<span><b>两本账。</b>这里的空调用电和电费是“用电这本账”；空调设备本身的购置、安装是另一本账，不与后面光伏、风机的 10 年总花费相加。</span></div>
      </div>
    </div>
  </section>`;
}
function drawStep2(panel, vm) {
  const H = anyHourly(vm), box = $('[data-monthly]', panel);
  if (!box) return;
  if (!H) { box.innerHTML = '<div class="empty-state">这份结果没有逐时数据</div>'; return; }
  const months = Array.from({ length: 12 }, () => 0);
  H.ts.forEach((t, i) => { const m = +t.slice(5, 7) - 1; if (m >= 0 && m < 12) months[m] += H.load[i] || 0; }); // 仅用于显示
  barChart(box, { cats: months.map((_, i) => `${i + 1}月`), series: [{ label: '空调用电', color: 'var(--brand)', values: months }], unit: 'kWh', height: 230, note: '按月加总，仅用于显示', label: '逐月空调用电柱状图' });
}

/* ------------------------------------------------------------------ */
/* 第 3 步：比较方案                                                    */
/* ------------------------------------------------------------------ */
function decisionCard(vm) {
  const rec = vm.rec || {}, best = vm.byId[rec.scenarioId];
  const alts = vm.candidates.filter((c) => c.id !== (best && best.id));
  return `<div class="decision big-decision">
    <div class="row"><span class="tag ${rec.tone || 'unknown'}">${icon(rec.tone === 'warn' ? 'warn' : 'star')}${esc(rec.label || '—')}</span><span class="xsmall muted">${esc(rec.note || '')}</span></div>
    <h2 class="h2 decision-title">${esc(story.headline(vm))}。</h2>
    ${best ? `<p class="decision-sub">${yrs(vm)}总花费（折现）约 <b class="num">${fmt.money(best.totalCost)}</b> 元${best.id !== 'S0_grid' ? `，${esc(fmt.delta(best.incremental).text)}` : ''}。</p>` : ''}
    ${numCards(vm)}
    <ul class="decision-alts">${alts.map((c) => `<li>${scenIcon(c.id)}<span>${esc(c.name)}</span><b>${c.id === 'S0_grid' ? `${fmt.money(c.totalCost)} 元（基线）` : c.admission.status === 'unknown' ? '条件不全，暂无法比较' : c.admission.status === 'excluded' ? `已排除：${esc(c.reasons.join('；') || c.constraintText)}` : c.admission.status === 'equivalent' ? `与「${esc(SCEN[c.equivalentTo] ? SCEN[c.equivalentTo].name : c.equivalentTo || '')}」相同` : esc(fmt.delta(c.incremental).text)}</b></li>`).join('')}</ul>
    ${rec.status === 'conditional_subset' ? `<div class="callout warn">${icon('warn')}<span>有方案条件不全（${esc(rec.unknown.map((id) => SCEN[id] ? SCEN[id].name : id).join('、'))}），推荐只在其余方案中比较；不能说它们已被击败。补全报价后重算即可一起比较。</span></div>` : ''}
    ${vm.service && vm.service.status === 'service_gap' ? `<div class="callout warn">${icon('warn')}<span>空调有缺口：结果不代表同等舒适度下的最优投资。</span></div>` : ''}
  </div>`;
}

/** 三个数字卡：读推荐方案的 load_coverage_rate、capex_cny、simple_payback_years；缺失时写原因。 */
function numCards(vm) {
  const best = vm.byId[(vm.rec || {}).scenarioId];
  if (!best) return '';
  const s0 = best.id === 'S0_grid';
  const why = best.economicsStatus && best.economicsStatus !== 'complete' ? '计价不完整' : '结果未给出';
  const cov = isNum(best.coverage) ? `<b class="num">${fmt.pct(best.coverage)}</b>` : `<b>—</b><small>${why}</small>`;
  const capex = s0 ? '<b class="num">0</b><span class="u">元</span><small>只用电网，无需投入</small>' : isNum(best.capex) ? `<b class="num">${fmt.money(best.capex)}</b><span class="u">元</span>` : `<b>—</b><small>${why}</small>`;
  const pay = s0 ? '<b>—</b><small>只用电网，无需投入</small>' : isNum(best.paybackYears) ? `<b class="num">${fmt.d(best.paybackYears, 1)}</b><span class="u">年</span>` : best.economicsStatus === 'complete' ? '<b>不回本</b><small>按当前条件不回本</small>' : `<b>—</b><small>${why}</small>`;
  return `<div class="numcards">
    <div><span>空调用电有多少是自己发的</span>${cov}</div>
    <div><span>一开始要投入多少</span>${capex}</div>
    <div><span>大概几年回本</span>${pay}<small class="fine">简单回本：初始投入 ÷ 每年净节省，不折现，仅供参考</small></div>
  </div>`;
}

/** 电价年涨幅敏感性：读 escalation_sensitivity；推荐只用电网时只写一句。 */
function escalationBlock(vm) {
  const es = vm.escalation;
  if (!es) return '';
  const best = vm.byId[(vm.rec || {}).scenarioId];
  if (!best || best.id === 'S0_grid' || es.recId === 'S0_grid') return `<section class="rsec" data-sec="escalation"><div class="callout info">${icon('info')}<span><b>电价变了，结论还成立吗？</b>推荐只用电网，无需投入。</span></div></section>`;
  const cur = vm.tariffEscalation && isNum(vm.tariffEscalation.rate) ? vm.tariffEscalation.rate : null;
  const pct = (r) => `${r > 0 ? '+' : r < 0 ? '−' : ''}${fmt.d(Math.abs(r) * 100, 1)}%`;
  return `<section class="rsec" data-sec="escalation"><div class="sec-head"><div><p class="kicker">电价年涨幅</p><h3 class="h3">电价变了，结论还成立吗？</h3><p class="muted">按电价每年等比变化重算 ${yrs(vm)}总账（只调整购电价，电价结构不变），等比调整，不是电价预测。${cur != null ? `本次计算按每年 ${pct(cur)}。` : ''}</p></div></div>
    <div class="tablewrap"><table class="table"><caption class="sr-only">电价每年变化时的 ${yrs(vm)}总账</caption><thead><tr><th>电价每年变化</th><th class="r">只用电网 ${yrs(vm)}总花费</th><th class="r">${esc(best.name)} ${yrs(vm)}总花费</th><th class="r">比只用电网</th><th>大约第几年回本（逐年累计）</th></tr></thead><tbody>
    ${es.rows.map((r) => `<tr${cur != null && Math.abs(r.rate - cur) < 1e-9 ? ' class="is-best"' : ''}><td class="num">${pct(r.rate)}${cur != null && Math.abs(r.rate - cur) < 1e-9 ? ' <span class="tag brand">本次</span>' : ''}</td><td class="r num">${fmt.money(r.s0Total)} 元</td><td class="r num">${fmt.money(r.recTotal)} 元</td><td class="r">${esc(fmt.delta(r.incremental).short)}</td><td>${isNum(r.cumulativePayback) ? `第 <b class="num">${fmt.int(r.cumulativePayback)}</b> 年` : `<span class="muted">${esc(r.paybackNote ? r.paybackNote.split('；')[0] : '研究期内未回本')}</span>`}</td></tr>`).join('')}
    </tbody></table></div>
    <p class="chart-note">回本年份按逐年累计净节省（含电价变化、运维与更换）首次达到初始投入的年份；上面数字卡里的“几年回本”是按第 1 年节省的简单回本，不含后续电价变化。</p></section>`;
}

function sweepBlock(vm) {
  const st = story.sweepStory(vm);
  if (!st) return '';
  return `<section class="rsec" data-sec="sweep"><div class="sec-head"><div><p class="kicker">装多大最划算</p><h3 class="h3">${esc(st.title)}</h3><p class="muted">${esc(st.text)}</p></div></div>
    <div class="card"><div class="chart" data-sweep></div>
    <div class="tablewrap" style="margin-top:16px"><table class="table"><caption class="sr-only">光伏容量比选明细</caption><thead><tr><th>光伏容量</th><th>状态</th><th class="r">${yrs(vm)}总花费</th><th class="r">比只用电网</th><th class="r">年发电</th><th class="r">当时用上</th><th class="r">发电当时用上比例</th><th class="r">浪费比例</th><th class="r">研究期减碳</th><th class="r">每吨减碳</th></tr></thead><tbody>
    ${vm.sweep.map((r) => { const sel = isNum(vm.recommendedKwp) && Math.abs(r.kwp - vm.recommendedKwp) < 1e-9; const fixed = vm.req.fixedCapacity != null; const best = sel && !fixed && r.admission.status === 'eligible'; return `<tr class="${best ? 'is-best' : ''}"><td><b class="num">${fmt.d(r.kwp, 2)}</b> kWp${best ? ' <span class="tag brand">最划算</span>' : sel && fixed ? ' <span class="tag unknown">固定容量</span>' : ''}</td><td><span class="tag ${r.admission.tone}">${icon(r.admission.icon)}${esc(r.admission.label)}</span>${r.reasons.length ? `<div class="xsmall muted">${esc(r.reasons.join('；'))}</div>` : ''}</td><td class="r num">${r.totalCost == null ? '—' : fmt.money(r.totalCost) + ' 元'}</td><td class="r">${r.admission.status === 'excluded' || r.admission.status === 'unknown' ? '<span class="muted">不参与比较</span>' : esc(fmt.delta(r.incremental).short)}</td><td class="r num">${fmt.kwh(r.gen)}</td><td class="r num">${fmt.kwh(r.selfUse)}</td><td class="r num">${fmt.pct(r.selfUseRate, 1)}</td><td class="r num">${fmt.pct(r.wasteRate, 1)}</td><td class="r num">${fmt.d(r.avoidedT, 2)} t</td><td class="r">${esc(fmt.perTon(r.costPerT).text)}</td></tr>`; }).join('')}
    </tbody></table></div>
    <p class="chart-note">${esc(story.basisPlain(vm))} 发电量与减碳为第 1 年；“比只用电网”为 ${yrs(vm)}折现差额。</p></div></section>`;
}

function calendarBlock(vm) {
  const sets = hourlySets(vm);
  if (!sets.length) return '';
  if (!sets.find((s) => s[0] === ui.calSet)) ui.calSet = sets[0][0];
  return `<section class="rsec" data-sec="calendar"><div class="sec-head"><div><p class="kicker">全年能源日历</p><h3 class="h3">发电和空调用电，在哪些小时重合。</h3></div></div>
  <div class="stage-card" data-cal>
    <div class="caltools">
      <div class="seg on-stage" role="group" aria-label="日历视图"><button type="button" data-cal-view="load" aria-pressed="false">空调用电</button><button type="button" data-cal-view="gen" aria-pressed="false">光伏与风机发电</button><button type="button" data-cal-view="cat" aria-pressed="true">发电时空调在用吗</button></div>
      <div class="seg on-stage" role="group" aria-label="日历数据">${sets.map(([k, l]) => `<button type="button" data-r-calset="${k}" aria-pressed="${k === ui.calSet}">${esc(l)}</button>`).join('')}</div>
    </div>
    <div class="calkeys" data-cal-keys></div>
    <div class="calscroll" tabindex="0" aria-label="全年逐小时能源日历，可横向滚动"><canvas aria-label="全年逐小时能源日历"></canvas></div>
    <p class="calnote" style="margin-top:12px">颜色深浅按全年第 99 百分位归一、分类色只表示这一小时哪种去向最多，仅用于显示；悬停查看原始数值（kWh）。完整逐时数值可在第 4 步导出逐时 CSV。</p>
  </div></section>`;
}

function whereBlock(vm) {
  const cands = genCands(vm);
  if (!cands.length) return `<section class="rsec"><div class="empty-state">这份结果没有发电方案，无法展示发电去向。</div></section>`;
  if (!cands.find((c) => c.id === ui.ringId)) ui.ringId = (story.focusScenario(vm) || cands[0]).id;
  const c = vm.byId[ui.ringId];
  return `<section class="rsec" data-sec="where"><div class="sec-head"><div><p class="kicker">电去哪了</p><h3 class="h3">只有当时用上的电，才真正替代了电网。</h3></div>
    <div class="seg" role="group" aria-label="选择方案">${cands.map((x) => `<button type="button" data-r-ring="${x.id}" aria-pressed="${x.id === ui.ringId}">${esc(x.name)}</button>`).join('')}</div></div>
    <div class="card where-card"><div class="ringbox small-ring" data-ring><div class="center"><span class="num">${fmt.pct(c.carbon && c.carbon.curtailedShare)}</span><span>的${esc(story.scenLabel(c))}发电，发出来时没人用</span></div></div>
    <div class="legendlist">
      <div class="li"><i style="background:var(--c-self)"></i><span class="t">当时给空调用上</span><b class="num">${fmt.kwh(c.selfUse)}</b></div>
      <div class="li"><i style="background:var(--c-waste)"></i><span class="t">发了没人用（浪费）</span><b class="num">${fmt.kwh(c.curtail)}</b></div>
      ${isNum(c.gridExport) && c.gridExport > 0 ? `<div class="li"><i style="background:var(--ink-3)"></i><span class="t">卖给电网</span><b class="num">${fmt.kwh(c.gridExport)}</b></div>` : ''}
      <div class="li"><i style="background:var(--c-import)"></i><span class="t">空调仍需从电网买</span><b class="num">${fmt.kwh(c.gridImport)}</b></div>
      <p class="chart-note">单位 kWh / 年（第 1 年）。环形图角度按发电量比例绘制，仅用于显示。</p>
    </div></div></section>`;
}

function dayBlock(vm, T) {
  const sets = hourlySets(vm); if (!sets.length) return '';
  const H = (sets.find((s) => s[0] === ui.calSet) || sets[0])[2];
  const days = H.ts.filter((t) => t.slice(11, 13) === '00').map((t) => t.slice(0, 10));
  const pv = T.result.previews && T.result.previews.summer;
  if (!ui.day || !days.includes(ui.day)) ui.day = pv && pv.start && days.includes(pv.start.slice(0, 10)) ? pv.start.slice(0, 10) : days[Math.min(days.length - 1, 196)] || days[0];
  return `<section class="rsec" data-sec="day"><div class="sec-head"><div><p class="kicker">典型日曲线</p><h3 class="h3">选一天，看用电和发电怎么错开。</h3></div>
    <label class="field compact-date"><span class="label">日期</span><div class="control"><input type="date" data-r-day value="${esc(ui.day)}" min="${esc(days[0])}" max="${esc(days[days.length - 1])}"></div></label></div>
    <div class="card"><div class="legend"><span><i class="line" style="background:var(--c-load)"></i>空调用电</span><span><i class="line" style="background:var(--c-pv)"></i>光伏发电</span><span><i class="line" style="background:var(--c-wind)"></i>风机发电</span></div><div class="chart" data-day></div>
    <p class="chart-note">取所选日期的 24 个逐时数值画线，仅用于显示；数据为日历当前所选方案。默认日期为夏季典型周首日（固定规则，不按结果挑选）。</p></div></section>`;
}

function carbonBlock(vm) {
  const cc = vm.carbonContext || {}, f = cc.factor || {};
  const priced = isNum(cc.price);
  return `<section class="rsec" data-sec="carbon"><div class="sec-head"><div><p class="kicker">真实减碳</p><h3 class="h3">只按当时用上的电算减碳，再看每吨减碳多花还是省下。</h3></div>
    <label class="check"><input type="checkbox" data-r-carbonprice ${ui.carbonPrice ? 'checked' : ''}>显示碳价情景</label></div>
    <div class="card">
      <div class="tablewrap"><table class="table"><caption class="sr-only">各方案减碳</caption><thead><tr><th>方案</th><th class="r">第 1 年电网排放</th><th class="r">第 1 年减碳</th><th class="r">研究期累计减碳</th><th class="r">每吨减碳</th>${ui.carbonPrice ? '<th class="r">碳收益（情景，总额）</th><th class="r">计入碳收益后比只用电网</th>' : ''}</tr></thead><tbody>
      ${vm.candidates.map((c) => { const k = c.carbon || {}; const pt = fmt.perTon(k.costPerT); return `<tr${c.isRec ? ' class="is-best"' : ''}><td>${esc(c.name)}${c.isRec ? ' <span class="tag brand">推荐</span>' : ''}</td><td class="r num">${fmt.kwh(k.gridEmissionsKgY1)} kg</td><td class="r num">${fmt.kwh(k.avoidedKgY1)} kg</td><td class="r num">${fmt.d(k.avoidedTStudy, 2)} t</td><td class="r">${k.costPerTStatus === 'zero_avoided' ? '<span class="muted">无减碳</span>' : esc(pt.text)}</td>${ui.carbonPrice ? `<td class="r num">${priced ? `${fmt.money(k.revenueStudy)} 元` : '—'}</td><td class="r">${priced ? esc(fmt.delta(k.incrementalWithCarbon).short) : '—'}</td>` : ''}</tr>`; }).join('')}
      </tbody></table></div>
      ${ui.carbonPrice && !priced ? `<div class="callout unknown" style="margin-top:14px">${icon('info')}<span>${esc(cc.priceNote || '本次没有设置碳价情景。')}可在第 1 步「碳与储能」填写碳价情景后重新计算。</span></div>` : ''}
      ${ui.carbonPrice && priced ? `<div class="callout info" style="margin-top:14px">${icon('info')}<span>碳价情景 ${fmt.d(cc.price, 2)} 元/吨${cc.priceSource ? `：${esc(cc.priceSource.title || cc.priceSource.basis || '')}` : '（用户输入）'}。碳收益只是“按这个价格出售”的情景，资格未核实（${esc((vm.candidates.find((c) => c.carbon && c.carbon.eligibilityNote) || {}).carbon?.eligibilityNote || '未核实')}），不改变原费用推荐。${esc(cc.cashflowNote || '')}</span></div>` : ''}
      <dl class="kv" style="margin-top:16px">
        <div><dt>排放因子</dt><dd>${esc(f.region || '')} ${esc(String(f.data_year || ''))} · ${esc(f.basis || '')} · <b class="num">${fmt.d(f.value_kgco2_per_kwh, 4)}</b> kgCO₂/kWh</dd></div>
        <div><dt>来源</dt><dd>${esc(f.issuer || '')}《${esc(f.source_title || '')}》${esc(f.notice_no || '')}${f.url ? ` · <a href="${esc(f.url)}" target="_blank" rel="noopener noreferrer">公告</a>` : ''}${f.attachment_url ? ` · <a href="${esc(f.attachment_url)}" target="_blank" rel="noopener noreferrer">附件</a>` : ''}</dd></div>
        ${cc.comparison ? `<div><dt>对照因子</dt><dd>${esc(cc.comparison.region)} ${esc(String(cc.comparison.data_year))} · ${fmt.d(cc.comparison.value_kgco2_per_kwh, 4)} kgCO₂/kWh（推荐方案第 1 年减碳按对照因子为 ${fmt.kwh(((vm.byId[(vm.rec || {}).scenarioId] || {}).carbon || {}).national ? vm.byId[vm.rec.scenarioId].carbon.national.avoided_kgco2_year1 : null)} kg）</dd></div>` : ''}
      </dl>
      <ul class="notes">${(cc.scopeNotes || []).map((n) => `<li>${esc(plain(n))}</li>`).join('')}<li>每吨减碳为负数时表示在该成本口径下省钱，不是碳交易收入。</li></ul>
    </div></section>`;
}

function roughBlock(vm) {
  const rows = vm.candidates.filter((c) => c.id !== 'S0_grid' && c.rough);
  if (!rows.length) return '';
  const anyOpp = rows.some((c) => { const r = story.roughCompare(c); return r && r.opposite; });
  return `<section class="rsec" data-sec="rough"><div class="sec-head"><div><p class="kicker">粗算对照</p><h3 class="h3">${anyOpp ? '常见的年度粗算，结论和逐小时结果相反。' : '常见的年度粗算，把浪费的电也算成了省钱。'}</h3><p class="muted">粗算把一年发电量直接抵一年用电量，不看发电时有没有人用电；只作对照，不参与推荐。</p></div></div>
    <div class="card"><div class="tablewrap"><table class="table"><caption class="sr-only">粗算与逐小时对照</caption><thead><tr><th>方案</th><th class="r">粗算：空调用电被抵掉</th><th class="r">逐小时：空调用电由自发电覆盖</th><th class="r">粗算：第 1 年减碳</th><th class="r">逐小时：第 1 年减碳</th><th class="r">粗算：比只用电网</th><th class="r">逐小时：比只用电网</th><th>结论</th></tr></thead><tbody>
    ${rows.map((c) => { const r = story.roughCompare(c); return `<tr${r && r.opposite ? ' class="is-warn"' : ''}><td>${esc(c.name)}</td><td class="r num">${fmt.pct(c.rough.coverageRate)}</td><td class="r num">${fmt.pct(c.coverage)}</td><td class="r num">${fmt.kwh(c.rough.avoidedKg)} kg</td><td class="r num">${fmt.kwh(c.carbon && c.carbon.avoidedKgY1)} kg</td><td class="r">${esc(fmt.delta(c.rough.incremental).short)}</td><td class="r">${c.admission.status === 'eligible' || c.admission.status === 'equivalent' ? esc(fmt.delta(c.incremental).short) : `<span class="muted">${esc(c.admission.label)}</span>`}</td><td>${r && r.comparable ? (r.opposite ? `<span class="tag warn">${icon('warn')}结论相反</span>` : `<span class="tag unknown">${icon('info')}${r.roughHigher ? '粗算偏乐观' : '粗算偏保守'}</span>`) : '<span class="muted">—</span>'}</td></tr>`; }).join('')}
    </tbody></table></div>
    <p class="chart-note">粗算电价口径：${esc(PRICE_BASIS[(rows[0].rough || {}).priceBasis] || '计算服务给出的年度平均电价')}（有效电价 ${fmt.d((rows[0].rough || {}).effectivePrice, 3)} 元/kWh）。</p></div></section>`;
}

/* ------------------------------------------------------------------ */
/* 多余的电去哪儿：储能（为主）与卖给电网（粗算），读 surplus_paths      */
/* ------------------------------------------------------------------ */
export const SURPLUS_NOTES = {
  storage: '简单规则：多余电先充进电池、缺电时放出；不含电池衰减和温度影响，不做峰谷套利；净收益不折现。',
  load: '只计算空调用电：下班后和周末楼里不用电，电池晚上没处放，所以容量越大不一定越划算。',
  export: '粗算：能否并网、上网电价和结算方式以当地电网批复为准。',
  both: '两条路从同一份多余电量分别估算，不叠加，也不改变上面的推荐方案。'
};
export function surplusCands(vm) { return vm.candidates.filter((c) => story.hasGen(c) && c.surplus); }
function surplusBlock(vm) {
  const cands = surplusCands(vm);
  if (!cands.length) return `<section class="rsec" data-sec="surplus"><div class="sec-head"><div><p class="kicker">多余的电</p><h3 class="h3">多余的电去哪儿？</h3></div></div><div class="callout unknown">${icon('info')}<span>这份结果没有发电方案的多余电量数据。</span></div></section>`;
  if (!cands.find((c) => c.id === ui.storeScen)) ui.storeScen = ((story.hasGen(vm.byId[(vm.rec || {}).scenarioId]) && vm.byId[vm.rec.scenarioId].surplus) ? vm.rec.scenarioId : (story.focusScenario(vm) || cands[0]).id);
  const c = vm.byId[ui.storeScen], sp = c.surplus, st = sp.storage, ex = sp.export;
  const years = (st && st.studyYears) || vm.studyYears;
  const yt = story.yearsText(years);
  const money = (v) => (isNum(v) ? `${fmt.money(v)} 元` : '—');
  const signed = (v) => (isNum(v) ? `${Math.round(v) < 0 ? '−' : ''}${fmt.money(Math.abs(v))} 元` : '—');
  let left;
  if (!st) left = `<div class="callout unknown">${icon('info')}<span>这个方案没有储能估算数据。</span></div>`;
  else {
    const rec = st.recommendedKwh;
    left = `<div class="tablewrap"><table class="table st-table"><caption class="sr-only">各储能容量的投入与收益</caption><thead><tr><th>电池容量</th><th class="r">初始投入</th><th class="r">每年少交电费</th><th class="r">每年净收益（扣运维）</th><th class="r">几年回本</th><th class="r">${yt}净收益</th><th>自用比例</th></tr></thead><tbody>
      ${st.candidates.map((x) => {
        const best = isNum(rec) && x.capacityKwh === rec && rec > 0;
        const cap = `<b class="num">${fmt.d(x.capacityKwh, 1)}</b> kWh${x.capacityKwh === 0 ? ' 不装' : ''}${best ? ' <span class="tag brand">最划算</span>' : ''}`;
        if (x.status !== 'complete') return `<tr><td>${cap}</td><td colspan="5"><span class="tag unknown">${icon('help')}条件不全：请填写储能报价</span></td><td class="num">${fmt.pct(x.scBefore)} → ${fmt.pct(x.scAfter)}</td></tr>`;
        return `<tr class="${best ? 'is-best' : ''}"><td>${cap}</td><td class="r num">${money(x.investment)}</td><td class="r num">${money(x.annualBillSaving)}</td><td class="r num">${signed(x.annualNet)}</td><td class="r">${isNum(x.payback) ? `<span class="num">${fmt.d(x.payback, 1)}</span> 年` : `<span class="muted">${esc(x.paybackStatus || '—')}</span>`}</td><td class="r num ${isNum(x.studyNet) ? (x.studyNet < 0 ? 'neg' : 'pos') : ''}">${signed(x.studyNet)}</td><td class="num">${fmt.pct(x.scBefore)} → ${fmt.pct(x.scAfter)}</td></tr>`;
      }).join('')}
      </tbody></table></div>
      ${isNum(rec) && rec > 0 ? (st.recommendationNote ? `<p class="hint">${esc(st.recommendationNote)}</p>` : '') : `<div class="callout ${rec === 0 ? 'info' : 'unknown'}">${icon(rec === 0 ? 'info' : 'help')}<span><b>${esc(st.recommendationNote || (rec === 0 ? '按当前报价不建议装储能' : '条件不全，暂不能判断'))}</b></span></div>`}
      <p class="chart-title" style="margin-top:14px">${yt}净收益（不折现）</p><div class="chart" data-st-chart></div>
      <ul class="notes"><li>${SURPLUS_NOTES.storage}</li><li>${SURPLUS_NOTES.load}</li>${(st.candidates.find((x) => x.quoteSource) || {}).quoteSource ? `<li>储能报价来源：${esc(st.candidates.find((x) => x.quoteSource).quoteSource)}${st.candidates.find((x) => x.quoteSourceNote) ? `（${esc(st.candidates.find((x) => x.quoteSourceNote).quoteSourceNote)}）` : '。示例拆分，非采购报价'}。</li>` : ''}</ul>`;
  }
  let right;
  if (!ex) right = `<div class="callout unknown">${icon('info')}<span>这个方案没有卖电估算数据。</span></div>`;
  else {
    const priced = isNum(ex.price) && ex.status === 'complete';
    right = `<dl class="kv">
      <div><dt>每年卖出电量</dt><dd><b class="num">${fmt.kwh(ex.soldKwh ?? ex.surplusKwh)}</b> kWh</dd></div>
      ${priced ? `<div><dt>上网电价</dt><dd><b class="num">${fmt.d(ex.price, 3)}</b> 元/kWh</dd></div>
      <div><dt>每年收入</dt><dd><b class="num">${money(ex.annualRevenue)}</b></dd></div>
      <div><dt>${yt}收入</dt><dd><b class="num">${money(ex.studyRevenue)}</b></dd></div>
      <div><dt>并网投入</dt><dd>${ex.connectionAssumedZero ? '未填写，按 0 粗算' : money(ex.connection)}</dd></div>
      <div><dt>回本</dt><dd>${isNum(ex.payback) ? `<b class="num">${fmt.d(ex.payback, 1)}</b> 年` : esc(ex.paybackStatus || (!isNum(ex.connection) || ex.connection === 0 ? '无额外投入' : '—'))}</dd></div>` : ''}
    </dl>
    ${priced ? '' : `<div class="callout unknown">${icon('help')}<span>填写上网电价后可估算收入。</span></div>`}
    <ul class="notes"><li>${SURPLUS_NOTES.export}</li>${priced ? `<li>电价来源：${esc(ex.source || '用户填写')}${ex.sourceNote ? `。${esc(ex.sourceNote)}` : ''}${vm.kind === 'sample' ? '。示例价为敏感性情景，不是广东固定上网价。' : ''}</li>` : ''}</ul>`;
  }
  return `<section class="rsec" data-sec="surplus"><div class="sec-head"><div><p class="kicker">多余的电</p><h3 class="h3">多余的电去哪儿？</h3><p class="muted">这个方案每年约有 <b class="num">${fmt.kwh(sp.surplusKwh)}</b> 度电自己用不完（${esc(story.scenLabel(c))}，第 1 年）。</p></div>
    <div class="seg" role="group" aria-label="选择方案">${cands.map((x) => `<button type="button" data-r-store="${x.id}" aria-pressed="${x.id === ui.storeScen}">${esc(x.name)}${x.isRec ? '（推荐）' : ''}</button>`).join('')}</div></div>
    <div class="surplus-grid">
      <div class="card"><h3>${icon('battery')}存起来（储能）</h3>${left}</div>
      <div class="card soft"><h3>${icon('bolt')}卖给电网（粗算）</h3>${right}</div>
    </div>
    <p class="chart-note">${SURPLUS_NOTES.both}</p></section>`;
}
function drawSurplus(panel, vm) {
  const box = $('[data-st-chart]', panel); if (!box || !ui.storeScen) return;
  const st = vm.byId[ui.storeScen].surplus.storage;
  const rows = st.candidates.filter((x) => x.status === 'complete' && isNum(x.studyNet));
  if (!rows.some((x) => x.capacityKwh > 0)) { box.innerHTML = '<div class="empty-state">填写储能报价后显示各容量的净收益</div>'; return; }
  signedBarChart(box, { cats: rows.map((x) => `${fmt.d(x.capacityKwh, 1)} kWh`), values: rows.map((x) => x.studyNet), unit: '元', height: 200, label: '各储能容量的研究期净收益', highlight: rows.findIndex((x) => x.capacityKwh === st.recommendedKwh && st.recommendedKwh > 0) });
}

function step3(vm, T) {
  return `${decisionCard(vm)}
  <section class="rsec" data-sec="options"><div class="sec-head"><div><p class="kicker">${yrs(vm)}总账</p><h3 class="h3">四种供电方式，“只用电网”永远是第一列基线。</h3></div></div>
    <div class="compare animate">${priceTable(vm)}</div>
    <p class="chart-note">总花费为空调用电购电费加发电设备投入与运维的折现成本，不含空调设备本身。负的“比只用电网”= 多花，正的 = 省下；“条件不全”不是排除。${vm.tariff ? ` 电价：${esc(vm.tariff.title || vm.tariff.id)}${vm.tariff.provisional ? '（待核验）' : ''}。` : ''}</p>
    ${vm.tariff && vm.tariff.provisional ? `<span class="pending">${icon('warn')}电价档案待核验</span>` : ''}${vm.tariff && vm.tariff.custom ? `<span class="pending">${icon('warn')}用户自定义电价（未经官方核验）</span>` : ''}
  </section>
  ${escalationBlock(vm)}
  ${sweepBlock(vm)}${calendarBlock(vm)}${whereBlock(vm)}${dayBlock(vm, T)}${carbonBlock(vm)}${roughBlock(vm)}${surplusBlock(vm)}`;
}
function drawStep3(panel, vm, T) {
  const sw = $('[data-sweep]', panel);
  if (sw) {
    if (vm.sweep.filter((r) => isNum(r.incremental)).length >= 1 && vm.sweep.length > 1) sweepChart(sw, vm.sweep, vm.req.fixedCapacity != null ? null : vm.recommendedKwp, { yTitle: `${yrs(vm)}比只用电网省下` });
    else sw.innerHTML = `<div class="empty-state">本次只计算了一个光伏容量${vm.req.fixedCapacity != null ? '（固定容量，用来查看该容量的状态）' : ''}，没有容量比选曲线；在第 1 步选择“自动比选”或填写多个候选容量后重算即可看到。</div>`;
  }
  const calRoot = $('[data-cal]', panel);
  if (calRoot) { calInst = createCalendar(calRoot); const s = hourlySets(vm).find((x) => x[0] === ui.calSet); if (s) calInst.set(s[2]); }
  const rb = $('[data-ring]', panel); if (rb && ui.ringId) { const c = vm.byId[ui.ringId]; ring(rb, { self: c.selfUse, waste: c.curtail, total: c.gen }); }
  drawDay(panel, vm);
  drawSurplus(panel, vm);
}
function drawDay(panel, vm) {
  const box = $('[data-day]', panel); if (!box) return;
  const sets = hourlySets(vm); const H = (sets.find((s) => s[0] === ui.calSet) || sets[0])[2];
  const i0 = H.ts.findIndex((t) => t.startsWith(ui.day));
  if (i0 < 0) { box.innerHTML = '<div class="empty-state">这一天不在数据范围内</div>'; return; }
  const sl = (a) => a.slice(i0, i0 + 24);   // 取某一天（仅用于显示）
  lineChart(box, { x: sl(H.ts).map((t) => `${ui.day} ${t.slice(11, 16)}`), xTicks: [0, 6, 12, 18, 23].map((i) => ({ i, label: `${i}时` })), unit: 'kWh', height: 240, label: `${ui.day} 逐时用电与发电`,
    series: [{ label: '空调用电', color: 'var(--c-load)', values: sl(H.load) }, { label: '光伏发电', color: 'var(--c-pv)', values: sl(H.pv), area: true }, { label: '风机发电', color: 'var(--c-wind)', values: sl(H.wind) }] });
}

/* ------------------------------------------------------------------ */
/* 第 4 步：决策与导出                                                  */
/* ------------------------------------------------------------------ */
export function reasonsOf(vm) {
  const rec = vm.rec || {}, best = vm.byId[rec.scenarioId], out = [];
  if (best) out.push(`在可以比较的方案中，「${best.name}」${yrs(vm)}总花费最低，约 ${fmt.money(best.totalCost)} 元（折现）${best.id !== 'S0_grid' ? `，${fmt.delta(best.incremental).text}` : ''}。`);
  if (best && story.hasGen(best)) out.push(`它一年发电 ${fmt.kwh(best.gen)} kWh，其中 ${fmt.kwh(best.selfUse)} kWh 当时被空调用上、${fmt.kwh(best.curtail)} kWh 发出来时没人用；第 1 年减碳约 ${fmt.kwh(best.carbon && best.carbon.avoidedKgY1)} kg。`);
  const st = story.sweepStory(vm); if (st && st.best && st.best.kwp > 0 && st.best.admission.status === 'eligible' && vm.req.fixedCapacity == null && vm.sweep.length > 1) out.push(st.text);
  const alts = vm.candidates.filter((c) => c.id !== 'S0_grid' && c.id !== (best && best.id) && c.admission.status === 'eligible' && isNum(c.incremental));
  if (alts.length) out.push(`其他方案：${alts.map((c) => `${c.name}${fmt.delta(c.incremental).short}`).join('；')}。`);
  const ex = vm.candidates.filter((c) => c.admission.status === 'excluded');
  if (ex.length) out.push(`已排除：${ex.map((c) => `${c.name}（${c.reasons.join('；') || c.constraintText}）`).join('、')}。`);
  const un = vm.candidates.filter((c) => c.admission.status === 'unknown');
  if (un.length) out.push(`条件不全、暂未比较（不是淘汰）：${un.map((c) => c.name).join('、')}。`);
  if (vm.service && vm.service.status === 'service_gap') out.push(`注意：空调全年有 ${fmt.int(vm.service.shortfallHours)} 小时冷量不足，结论不代表同等舒适度下的最优投资。`);
  return out;
}
export function boundariesOf(vm) {
  const list = BOUNDARIES.slice();
  if (vm.feasibility) list.unshift(`${vm.feasibility.conclusion || ''}：${(vm.feasibility.not_modelled || []).join('、')}未计入，只计厂房空调区，结果偏保守。`);
  if (vm.tariff && vm.tariff.provisional) list.push(`电价档案「${vm.tariff.title || vm.tariff.id}」待核验（公开抄录，原始公告未核对）。`);
  for (const n of vm.notProvided || []) if (!list.includes(n)) list.push(n);
  return list;
}

function step4(vm, T) {
  const dis = T.stale ? 'disabled aria-disabled="true"' : '';
  return `
  <div class="decision"><p class="kicker">决策与导出</p><h2 class="h2 decision-title">${esc(story.headline(vm))}。</h2></div>
  <div class="grid2">
    <section class="card"><h3>推荐理由</h3><ol class="reasons">${reasonsOf(vm).map((r) => `<li>${esc(r)}</li>`).join('')}</ol>
      <p class="hint">理由只引用结果中的数值。推荐规则：${esc((vm.rec || {}).note || '')}；计算服务的原文说明见“查看依据”。</p></section>
    <section class="card"><h3>适用边界</h3><ul class="notes">${boundariesOf(vm).map((b) => `<li>${esc(b)}</li>`).join('')}</ul>
      <button class="btn sm" type="button" data-r-basis style="margin-top:12px">${icon('doc')}查看依据（来源、版本、哈希）</button></section>
  </div>
  <section class="card export-card">
    <div class="card-head"><div><h3>导出</h3><p class="hint">全部从当前显示的结果生成，不再调用计算。${T.stale ? '<b style="color:var(--warn)">条件已修改，导出与保存已禁用。</b>' : ''}</p></div></div>
    <div class="export-grid">
      <button class="btn" type="button" data-export="brief" ${dis}>${icon('doc')}决策简报（可打印 HTML）</button>
      <button class="btn" type="button" data-export="print" ${dis}>${icon('doc')}打印 / 另存为 PDF</button>
      <button class="btn" type="button" data-export="summary" ${dis}>${icon('download')}方案汇总 CSV</button>
      <button class="btn" type="button" data-export="hourly" ${dis}>${icon('download')}逐时 CSV</button>
      <button class="btn" type="button" data-export="json" ${dis}>${icon('download')}完整 JSON</button>
      <button class="btn primary" type="button" data-action="save-plan" ${dis}>${icon('save')}保存到我的方案</button>
    </div>
    <p class="hint">“我的方案”只保存在本机浏览器，保存条件与结论摘要（不保存逐时数据），可随时载入条件重新计算。</p>
  </section>`;
}

export function basisHtml(vm) {
  const p = vm.provenance || {};
  const rows = [['数据来源', p.kind], ['文件', p.file], ['格式版本', p.formatVersion], ['源码提交', p.sourceCommit], ['计算版本', p.calculationVersion], ['接口', p.endpoint], ['案例哈希', p.caseHash], ['任务编号', p.jobId],
    ['天气来源', p.weatherSource], ['天气文件', p.weatherFile], ['天气哈希', p.weatherHash], ['计算服务用时', isNum(p.elapsedMs) ? `${fmt.d(p.elapsedMs / 1000, 2)} 秒${p.timingScope ? '（' + p.timingScope + '）' : ''}` : null]].filter((r) => r[1] != null && r[1] !== '');
  const t = vm.tariff;
  return `<h3>推荐依据（计算服务原文）</h3><p>${esc((vm.rec || {}).reason || '—')}</p>${vm.recommendationBasis ? `<p>${esc(vm.recommendationBasis)}</p>` : ''}
    <h3>本次结果</h3><dl>${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono">${esc(v)}</dd>`).join('')}</dl>
    ${t ? `<h3>电价</h3><dl><dt>档案</dt><dd>${esc(t.id)}</dd><dt>名称</dt><dd>${esc(t.title || '')}</dd><dt>状态</dt><dd>${t.provisional ? '待核验（provisional）' : t.verified ? '已核验' : '—'}</dd><dt>用法</dt><dd>${esc(vm.tariffApplication || '')}</dd>${t.sourceUrl ? `<dt>来源</dt><dd><a href="${esc(t.sourceUrl)}" target="_blank" rel="noopener noreferrer">${esc(t.sourceUrl)}</a></dd>` : ''}</dl>` : ''}
    <h3>术语对照</h3><dl><dt>只用电网</dt><dd>S0_grid</dd><dt>加装光伏</dt><dd>S1_pv（pvlib）</dd><dt>加装小风机</dt><dd>S2_wind（SWCC 认证 SD6 曲线，Hellman 幂律换算轮毂高度风速）</dd><dt>光伏 + 小风机</dt><dd>S3_pv_wind</dd><dt>10 年总花费</dt><dd>total_cost_npv_cny（折现）</dd><dt>比只用电网多花/省下</dt><dd>incremental_npv_vs_s0_cny（负=多花，正=省下）</dd><dt>净现金流现值</dt><dd>npv_cny（不是利润）</dd><dt>浪费的电</dt><dd>curtailment_kwh</dd><dt>空调用电由自发电覆盖</dt><dd>load_coverage_rate</dd><dt>冷量不足小时</dt><dd>capacity_shortfall_hours</dd><dt>粗算</dt><dd>annual_offset_estimate</dd><dt>储能上限</dt><dd>storage_upper_bound</dd></dl>
    <h3>适用边界</h3><ul>${boundariesOf(vm).map((b) => `<li>${esc(b)}</li>`).join('')}</ul>`;
}

/* ------------------------------------------------------------------ */
/* 入口                                                                */
/* ------------------------------------------------------------------ */
let bound = new WeakSet();
export function render(panel, step, T) {
  const vm = T.result.vm;
  if (vm !== lastVM) { ui = { ringId: null, calSet: 'recommended', day: null, storeScen: null, storeCap: null, carbonPrice: true }; lastVM = vm; }
  if (step === 2) { panel.innerHTML = step2(vm, T); drawStep2(panel, vm); }
  if (step === 3) { panel.innerHTML = step3(vm, T); drawStep3(panel, vm, T); }
  if (step === 4) panel.innerHTML = step4(vm, T);
  if (!bound.has(panel)) {
    bound.add(panel);
    panel.addEventListener('click', (e) => {
      const t = e.target, V = T.result && T.result.vm; if (!V) return;
      const rerender = () => { const y = scrollY; render(panel, step, T); scrollTo(0, y); };
      const r = t.closest('[data-r-ring]'); if (r) { ui.ringId = r.dataset.rRing; rerender(); return; }
      const cs = t.closest('[data-r-calset]'); if (cs) { ui.calSet = cs.dataset.rCalset; rerender(); return; }
      const st = t.closest('[data-r-store]'); if (st) { ui.storeScen = st.dataset.rStore; ui.storeCap = null; rerender(); return; }
      if (t.closest('[data-r-basis]')) { import('./state.js').then((m) => m.emit('drawer', { title: '依据', html: basisHtml(V) })); return; }
      const ex = t.closest('[data-export]'); if (ex && !ex.disabled) { if (T.stale) { toast('条件已修改，请先重新计算'); return; } exp.run(ex.dataset.export, T); return; }
      const sv = t.closest('[data-action="save-plan"]'); if (sv && !sv.disabled) { if (T.stale) return; exp.savePlan(T); return; }
    });
    panel.addEventListener('change', (e) => {
      if (e.target.matches('[data-r-day]')) { ui.day = e.target.value; drawDay(panel, T.result.vm); }
      if (e.target.matches('[data-r-carbonprice]')) { ui.carbonPrice = e.target.checked; const y = scrollY; render(panel, step, T); scrollTo(0, y); }
    });
  }
}
