/* 能见度 · 首页（叙事页，按已批准的设计确认稿）
 * 首页所有数字来自当前选中的示例（replay_cases_ui_v9.json / replay_previews_v7.json）
 * 或用户最近一次实时计算的结果，并在每段标明来源。 */
import { $, $$, esc, fmt, isNum, icon, countUp, onVisible, reveal, reduceMotion } from './util.js';
import { app, on, emit } from './state.js';
import * as data from './data.js';
import { SCEN, SCEN_IDS } from './data.js';
import { lineChart, sweepChart, ring } from './charts.js';
import { createCalendar } from './calendar.js';
import { createScene } from './scene3d.js';
import * as story from './story.js';

let el = null, samples = null, scene = null, cal = null, built = false;
let source = { kind: 'sample', caseId: 'tier_small' };
let vm = null, week = null, ringId = null, calSet = 'recommended';

const TIER_IDS = ['tier_small', 'tier_medium', 'tier_large'];
const TIER_TAG = { tier_small: '小档', tier_medium: '中档', tier_large: '大档' };
const DEMO_SCENES = ['场景', '有人建议装光伏和风机', '能源日历', '装多大最划算', '10 年总账与每吨减碳成本', '多余的电去哪儿', '换成图书馆或厂房再看', '导出决策简报'];

const SCEN_ICON = {
  S0_grid: '<svg class="icon" viewBox="0 0 48 48" fill="none" stroke="var(--c-grid)" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M24 4 14 44M24 4l10 40M17 30h14M15 38h18M19 20h10M8 14h32M12 14l12-10 12 10"/></svg>',
  S1_pv: '<svg class="icon" viewBox="0 0 48 48" fill="none" stroke="var(--c-pv)" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M6 36 14 20h28l-8 16z"/><path d="M10 28h28M20 20l-4 16M30 20l-4 16"/><circle cx="36" cy="9" r="4"/></svg>',
  S2_wind: '<svg class="icon" viewBox="0 0 48 48" fill="none" stroke="var(--c-wind)" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M24 22v24M20 46h8"/><circle cx="24" cy="20" r="2.5"/><path d="M24 17.5 22 4c4 1 5 8 2 13.5zM26 21.5l12 7c-3 3-10 0-12-7zM21.8 21.3 10 28c-1-4 5-8 11.8-6.7z"/></svg>',
  S3_pv_wind: '<svg class="icon" viewBox="0 0 48 48" fill="none" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M4 40 10 28h18l-6 12z" stroke="var(--c-pv)"/><path d="M36 22v24" stroke="var(--c-wind)"/><circle cx="36" cy="20" r="2.5" stroke="var(--c-wind)"/><path d="M36 17.5 34 6c3.5 1 4.5 7 2 11.5zM38 21.5l10 6c-3 2.5-8.5 0-10-6z" stroke="var(--c-wind)"/></svg>'
};
export const scenIcon = (id) => SCEN_ICON[id] || '';

/* ------------------------------------------------------------------ */
/* 骨架（静止状态完整可读：数据未到时显示“正在读取”）                     */
/* ------------------------------------------------------------------ */
function skeleton() {
  return `
  <header class="hero">
    <div class="sky" aria-hidden="true"></div>
    <div class="container">
      <div class="hero-copy">
        <p class="eyebrow">低碳改造决策助手</p>
        <h1 class="h1">看见每一小时的电。<span class="soft">再决定花不花这笔钱。</span></h1>
        <p class="lead">装光伏、装小风机之前，用当地全年<span data-k="hours">逐小时</span>的天气，把空调什么时候用电、设备什么时候发电一一对齐，算清 10 年总账和真实减碳。</p>
        <div class="btns">
          <button class="btn primary lg" type="button" data-action="demo">${icon('play')}一键演示</button>
          <a class="btn lg" href="#/tool">开始试算${icon('arrow')}</a>
        </div>
        <ul class="hero-q" aria-label="系统回答的四个问题">
          <li><b>空调配几台才够用？</b></li><li><b>发的电当时用得上吗？</b></li><li><b>装不装、装多大最划算？</b></li><li><b>真实减了多少碳？</b></li>
        </ul>
      </div>
      <div class="stage3d" data-stage role="img" aria-label="三维微缩场景：一栋楼、屋顶光伏和一台小风机，按真实逐小时数据播放一周的用电与发电">
        <canvas></canvas>
        <div class="scene-fallback" data-scene-fallback hidden></div>
        <div class="hud">
          <div class="chip" style="flex:1 1 230px">
            <span data-hud="date">正在读取典型周数据…</span>
            <div class="chip-row"><span><i style="background:var(--ink)"></i>空调 <b class="num" data-hud="load">—</b></span><span><i style="background:var(--c-pv)"></i>光伏 <b class="num" data-hud="pv">—</b></span><span><i style="background:var(--c-wind)"></i>风机 <b class="num" data-hud="wind">—</b></span></div>
            <div class="timeline"><span data-hud="bar"></span></div>
          </div>
          <div class="chip">
            <span>这一小时发的电</span>
            <div class="chip-row"><span><i style="background:var(--c-self)"></i>用上 <b class="num" data-hud="self">—</b></span><span><i style="background:var(--c-waste)"></i>浪费 <b class="num" data-hud="waste">—</b></span></div>
            <span class="chip-note" data-hud="meta">单位 kWh</span>
          </div>
        </div>
      </div>
    </div>
  </header>

  <div class="srcbar" role="region" aria-label="首页数据来源">
    <div class="container">
      <span class="srcbar-label">首页数据</span>
      <div class="seg" role="group" aria-label="选择首页数据来源" data-src-seg></div>
      <span class="srcbar-note" data-k="srcnote">正在读取示例数据…</span>
    </div>
  </div>

  <section class="section tight" aria-labelledby="h-facts"><div class="container">
    <p class="kicker reveal">一个被忽略的事实</p>
    <h2 class="h2 reveal" id="h-facts">发电多，不等于省钱，也不等于减碳多。</h2>
    <p class="sub reveal" data-k="factsSub">正在读取示例数据…</p>
    <div class="statement">
      <div class="stat reveal"><div class="bar"><span></span></div><div class="v"><span class="num" data-k="genV">—</span><small>kWh</small></div><p data-k="genL">一年发电</p></div>
      <div class="stat reveal"><div class="bar"><span></span></div><div class="v"><span class="num" data-k="loadV">—</span><small>kWh</small></div><p>空调一年用电</p></div>
      <div class="stat reveal waste"><div class="bar"><span></span></div><div class="v"><span class="num" data-k="wasteV">—</span><small>kWh</small></div><p data-k="wasteL">发了没人用的电</p></div>
    </div>
    <p class="source-note" data-k="factsSrc"></p>
  </div></section>

  <section class="section dark" id="home-cal" aria-labelledby="h-cal"><div class="container">
    <p class="kicker reveal">全年能源日历</p>
    <h2 class="h2 reveal" id="h-cal"><span data-k="calHours">全年每个小时</span>，一格一格摊开看。</h2>
    <p class="sub reveal" data-k="calSub">横轴是日期，纵轴是一天 24 小时。切换三种视图，看用电和发电在哪里重合、在哪里错开。</p>
    <div class="calwrap" data-cal>
      <div class="caltools">
        <div class="seg on-stage" role="group" aria-label="日历视图">
          <button type="button" data-cal-view="load" aria-pressed="false">空调用电</button>
          <button type="button" data-cal-view="gen" aria-pressed="false">光伏与风机发电</button>
          <button type="button" data-cal-view="cat" aria-pressed="true">发电时空调在用吗</button>
        </div>
        <div class="seg on-stage" role="group" aria-label="日历数据" data-calset></div>
      </div>
      <div class="calkeys" data-cal-keys></div>
      <div class="calscroll" tabindex="0" aria-label="全年逐小时能源日历，可横向滚动"><canvas aria-label="全年逐小时能源日历：横轴日期，纵轴小时"></canvas></div>
      <div class="calfoot"><p class="calnote" data-k="calNote">正在读取示例数据…</p><button class="btn sm on-stage" type="button" data-action="cal-csv">${icon('download')}下载逐时数据（文字替代）</button></div>
    </div>
    <div class="calcaption">
      <div class="reveal"><b>青色格</b><p>这一小时发的电，大部分当时就被空调用上，真正替代了电网购电。</p></div>
      <div class="reveal"><b>橙色格</b><p>这一小时发了电，但房间里没人开空调，电浪费了，不算省钱也不算减碳。</p></div>
      <div class="reveal"><b>紫色格</b><p>这一小时空调主要靠电网供电，发电不够或不在发电时段。</p></div>
    </div>
  </div></section>

  <section class="section" aria-labelledby="h-where"><div class="container">
    <p class="kicker reveal">电去哪了</p>
    <h2 class="h2 reveal" id="h-where">只有当时用上的电，才真正替代了电网。</h2>
    <div class="where">
      <div class="ringbox reveal" data-ring>
        <div class="center"><span class="num" data-k="ringPct">—</span><span data-k="ringLab">的发电，发出来时没人用</span></div>
      </div>
      <div>
        <div class="legendlist">
          <div class="li"><i style="background:var(--c-self)"></i><span class="t">当时给空调用上</span><b class="num" data-k="lSelf">—</b></div>
          <div class="li"><i style="background:var(--c-waste)"></i><span class="t">发了没人用（浪费）</span><b class="num" data-k="lWaste">—</b></div>
          <div class="li"><i style="background:var(--c-import)"></i><span class="t">空调仍需从电网买</span><b class="num" data-k="lImp">—</b></div>
        </div>
        <div class="seg" role="group" aria-label="选择方案" data-ringseg style="margin-top:24px"></div>
        <p class="source-note" data-k="ringNote">单位 kWh / 年。</p>
      </div>
    </div>
  </div></section>

  <section class="section alt" aria-labelledby="h-vs"><div class="container">
    <p class="kicker reveal">两种算法</p>
    <h2 class="h2 reveal" id="h-vs" data-k="vsTitle">同一栋楼，两种算法。</h2>
    <div class="versus reveal" data-vs>
      <div class="old"><span class="lab">常见粗算 · 年发电抵年用电</span><p class="say" data-k="vsOld">—</p><p class="how" data-k="vsOldHow"></p></div>
      <div class="new"><span class="lab">能见度 · 逐小时匹配</span><p class="say" data-k="vsNew">—</p><p class="how" data-k="vsNewHow"></p></div>
    </div>
    <div class="vs-table" data-vs-table></div>
    <p class="source-note">粗算只作对照：它把一年发电量直接抵一年用电量，不看发电时有没有人用电，不参与推荐。两列数字都由计算服务给出，粗算口径见“关于数据”。</p>
  </div></section>

  <section class="section" aria-labelledby="h-sweep"><div class="container">
    <p class="kicker reveal">装多大最划算</p>
    <h2 class="h2 reveal" id="h-sweep" data-k="sweepTitle">装多大，比装不装更关键。</h2>
    <p class="sub reveal" data-k="sweepSub">正在读取示例数据…</p>
    <div class="sweepbox reveal"><div class="chart" data-sweep></div></div>
    <p class="source-note" data-k="sweepNote">候选容量是有限个，不是全局最优；最划算容量由计算服务在计价完整、满足屋顶与预算约束的候选中选出。</p>
  </div></section>

  <section class="section alt" aria-labelledby="h-price"><div class="container">
    <p class="kicker reveal" data-k="priceKicker">10 年总账</p>
    <h2 class="h2 reveal" id="h-price" data-k="priceTitle">四种供电方式，一张表比清楚。</h2>
    <p class="sub reveal">“只用电网”永远作为基线放在第一列。每个方案都写明比基线多花还是省下，不需要自己算差价。</p>
    <div class="compare" data-compare></div>
    <p class="source-note" data-k="priceNote"></p>
  </div></section>

  <section class="section" aria-labelledby="h-tiers"><div class="container">
    <p class="kicker reveal">三档示例</p>
    <h2 class="h2 reveal" id="h-tiers">办公室、图书馆、厂房，结论各不一样。</h2>
    <p class="sub reveal">示例只是起点。打开后可以改任何条件，再实时计算。</p>
    <div class="tiers" data-tiers><div class="empty-state">正在读取示例数据…</div></div>
  </div></section>

  <section class="section dark" aria-labelledby="h-demo"><div class="container">
    <p class="kicker reveal">一键演示</p>
    <h2 class="h2 reveal" id="h-demo">点一下，自动讲完一个示例。</h2>
    <div class="demo-entry">
      <div class="demo-steps">${DEMO_SCENES.map((t, i) => `<div><span class="n num">${String(i + 1).padStart(2, '0')}</span><span>${t}</span></div>`).join('')}</div>
      <div class="demo-cta">
        <p>页面会自动滚动到对应区域并高亮，底部字幕的数字全部从示例数据读取。可以暂停、上一幕、下一幕，键盘左右键切换，Esc 退出。</p>
        <button class="btn primary lg" type="button" data-action="demo">${icon('play')}开始演示</button>
      </div>
    </div>
  </div></section>`;
}

/* ------------------------------------------------------------------ */
/* 数据来源                                                            */
/* ------------------------------------------------------------------ */
function currentVM() {
  if (source.kind === 'live' && app.lastLive) return app.lastLive.vm;
  if (!samples) return null;
  const c = samples.cases.get(source.caseId) || samples.cases.get('tier_small');
  return c ? data.fromSample(c, samples.file) : null;
}
function currentWeek() {
  let pv = null;
  if (source.kind === 'live' && app.lastLive) pv = app.lastLive.previews && app.lastLive.previews.summer;
  else if (samples) pv = data.samplePreview(samples, data.previewTierOf(source.caseId) || 'tier_small', 'summer');
  if (!pv) return null;
  const s3 = pv.candidates.S3_pv_wind, s1 = pv.candidates.S1_pv;
  const pick = s3 && isNum(s3.windCount) && s3.windCount > 0 ? s3 : (s1 || s3);
  return pick ? { pv, cand: pick } : null;
}

function renderSrcSeg() {
  const seg = $('[data-src-seg]', el);
  const items = TIER_IDS.filter((id) => !samples || samples.cases.has(id)).map((id) => [`sample:${id}`, `${TIER_TAG[id]}示例`]);
  if (app.lastLive) items.push(['live', '我的最近一次计算']);
  const cur = source.kind === 'live' ? 'live' : `sample:${source.caseId}`;
  seg.innerHTML = items.map(([k, l]) => `<button type="button" data-src="${k}" aria-pressed="${k === cur}">${esc(l)}</button>`).join('');
}

/* ------------------------------------------------------------------ */
/* 渲染各段                                                            */
/* ------------------------------------------------------------------ */
const k = (name) => $(`[data-k="${name}"]`, el);
function setText(name, text) { const n = k(name); if (n) n.textContent = text; }
function setHtml(name, html) { const n = k(name); if (n) n.innerHTML = html; }

function srcLine(v) {
  if (!v) return '';
  if (v.kind === 'live') return `来源：本机实时计算（${fmt.date(v.computedAt)}）· ${story.placeText(v)}`;
  return `来源：示例回放 ${data.sampleSourceText(samples)} · ${v.label} · ${story.placeText(v)}`;
}

function renderHero() {
  const wk = currentWeek();
  if (!wk || !scene) return;
  const c = wk.cand, s = c.series;
  scene.set({ ts: s.ts, load: s.load, pv: s.pv, wind: s.wind, self: s.self, curt: s.curt }, { windCount: c.windCount || 0 });
  const season = wk.pv.season === 'winter' ? '冬季' : '夏季';
  $('[data-hud="meta"]', el).textContent = `单位 kWh · ${source.kind === 'live' ? '我的计算' : TIER_TAG[data.previewTierOf(source.caseId)] + '示例'} · ${season}典型周 ${String(wk.pv.start || '').slice(5, 10)} 起 · ${story.scenLabel(c)}`;
}

function renderFacts() {
  const f = story.focusScenario(vm);
  const place = `${story.placeText(vm)}，${vm.label === '实时计算' ? '你的条件' : vm.label.replace(/^[^：]*：/, '')}`;
  if (!f) {
    setText('factsSub', `${place}：这次结果里没有发电方案，无法展示发电去向。`);
    ['genV', 'loadV', 'wasteV'].forEach((n) => setText(n, '—'));
    return;
  }
  setText('factsSub', `${place}。${story.scenLabel(f)} 一年发电 ${fmt.kwh(f.gen)} kWh，空调一年用电 ${fmt.kwh(vm.load.annualKwh)} kWh；其中 ${fmt.pct(f.carbon && f.carbon.curtailedShare)} 的发电在发出来时没人用。`);
  setText('genL', `${story.scenLabel(f)} 一年发电`);
  setText('wasteL', `发了没人用的电，占这部分发电的 ${fmt.pct(f.carbon && f.carbon.curtailedShare)}`);
  const vals = { genV: f.gen, loadV: vm.load.annualKwh, wasteV: f.curtail };
  for (const [n, v] of Object.entries(vals)) { const node = k(n); node.textContent = fmt.kwh(v); node.dataset.to = String(v); }
  setText('factsSrc', `${srcLine(vm)}。年发电、年用电、浪费电量与占比均为计算服务给出的字段原值，页面只做取整显示。`);
  const st = $('.statement', el);
  if (!st.dataset.counted) {
    onVisible(st, () => { st.dataset.counted = '1'; ['genV', 'loadV', 'wasteV'].forEach((n) => { const node = k(n); countUp(node, +node.dataset.to, (x) => fmt.kwh(x)); }); });
  }
}

function renderCalendar() {
  const H = vm.hourly || {};
  const sets = [];
  if (H.recommended) { const c = vm.byId[H.recommended.scenarioId]; sets.push(['recommended', `推荐方案：${c ? (story.hasGen(c) ? story.scenLabel(c) : c.name) : ''}`]); }
  if (H.combo) sets.push(['combo', `光伏 + 小风机${vm.byId.S3_pv_wind ? '：' + story.scenLabel(vm.byId.S3_pv_wind) : ''}`]);
  if (!sets.find((s) => s[0] === calSet)) calSet = sets.length ? sets[0][0] : null;
  $('[data-calset]', el).innerHTML = sets.map(([key, label]) => `<button type="button" data-calset-btn="${key}" aria-pressed="${key === calSet}">${esc(label)}</button>`).join('');
  const series = calSet ? H[calSet] : null;
  if (!series) { setText('calNote', '这份结果没有逐时数据。'); return; }
  cal.set(series);
  setText('calHours', `${fmt.int(series.ts.length)} 个小时`);
  const sch = story.scheduleText(vm.request);
  setText('calSub', `横轴是一年的每一天，纵轴是一天 24 小时。${sch ? `这里的空调使用时段是 ${sch}。` : ''}切换三种视图，看用电和发电在哪里重合、在哪里错开。`);
  setText('calNote', `${srcLine(vm)} · 当前显示：${(sets.find((s) => s[0] === calSet) || [])[1] || ''}。颜色深浅按全年第 99 百分位归一、分类色只表示这一小时哪种去向最多，仅用于显示；悬停查看该小时原始数值（kWh）。`);
}

function ringCands() { return vm.candidates.filter(story.hasGen); }
function renderRing() {
  const cands = ringCands();
  if (!cands.length) { setText('ringPct', '—'); setText('ringLab', '这份结果没有发电方案'); $('[data-ringseg]', el).innerHTML = ''; return; }
  if (!cands.find((c) => c.id === ringId)) ringId = (story.focusScenario(vm) || cands[0]).id;
  $('[data-ringseg]', el).innerHTML = cands.map((c) => `<button type="button" data-ring-btn="${c.id}" aria-pressed="${c.id === ringId}">${esc(c.name)}</button>`).join('');
  const c = vm.byId[ringId];
  ring($('[data-ring]', el), { self: c.selfUse, waste: c.curtail, total: c.gen });
  setText('ringPct', fmt.pct(c.carbon && c.carbon.curtailedShare));
  setText('ringLab', `的${story.scenLabel(c)}发电，发出来时没人用`);
  setText('lSelf', fmt.kwh(c.selfUse)); setText('lWaste', fmt.kwh(c.curtail)); setText('lImp', fmt.kwh(c.gridImport));
  const cb = c.carbon || {};
  setHtml('ringNote', `单位 kWh / 年（第 1 年）。减碳只按“当时用上”的电计算：第 1 年约 <b class="num">${fmt.kwh(cb.avoidedKgY1)}</b> kg 二氧化碳${vm.carbonContext && vm.carbonContext.factor ? `（${esc(vm.carbonContext.factor.region || '')}电网平均排放因子 ${fmt.d(vm.carbonContext.factor.value_kgco2_per_kwh, 4)} kgCO₂/kWh 情景估算，不是核证减排量）` : ''}。环形图角度按发电量的比例绘制，仅用于显示。`);
}

function renderVersus() {
  const f = story.focusScenario(vm);
  const table = $('[data-vs-table]', el);
  if (!f || !f.rough) { setText('vsOld', '—'); setText('vsNew', '—'); table.innerHTML = ''; return; }
  const cmp = story.roughCompare(f);
  const yrs = vm.studyYears;
  setText('vsTitle', cmp && cmp.opposite ? '同一栋楼，两种算法，两个相反的结论。' : '同一栋楼，两种算法，粗算把浪费的电也算成了省钱。');
  setText('vsOld', `“${story.sayDelta(f.rough.incremental, yrs)}。”`);
  setText('vsOldHow', `${story.scenLabel(f)}：粗算认为空调用电的 ${fmt.pct(f.rough.coverageRate)}（${fmt.kwh(f.rough.coveredKwh)} kWh）都被一年的发电量抵掉，第 1 年少交电费 ${fmt.money(f.rough.billSavingY1)} 元、减碳 ${fmt.kwh(f.rough.avoidedKg)} kg。`);
  setText('vsNew', `${story.sayDelta(f.incremental, yrs)}。`);
  setText('vsNewHow', `${fmt.int(vm.hourly && vm.hourly.recommended ? vm.hourly.recommended.ts.length : null)} 个小时逐一对齐：当时用上 ${fmt.kwh(f.selfUse)} kWh，浪费 ${fmt.kwh(f.curtail)} kWh 不算省钱；第 1 年真实减碳 ${fmt.kwh(f.carbon && f.carbon.avoidedKgY1)} kg。`);
  $('[data-vs]', el).classList.toggle('opposite', !!(cmp && cmp.opposite));
  const rows = vm.candidates.filter((c) => c.id !== 'S0_grid' && c.rough);
  table.innerHTML = `<div class="tablewrap"><table class="table"><caption class="sr-only">各方案粗算与逐小时结果对照</caption>
    <thead><tr><th>方案</th><th class="r">粗算：比只用电网</th><th class="r">逐小时：比只用电网</th><th>结论</th></tr></thead><tbody>
    ${rows.map((c) => { const r = story.roughCompare(c); return `<tr><td>${esc(c.name)}<span class="muted xsmall"> · ${esc(story.scenLabel(c))}</span></td><td class="r">${esc(fmt.delta(c.rough.incremental).short)}</td><td class="r">${c.admission.status === 'eligible' || c.admission.status === 'equivalent' ? esc(fmt.delta(c.incremental).short) : `<span class="muted">${esc(c.admission.label)}</span>`}</td><td>${r && r.comparable ? (r.opposite ? `<span class="tag warn">${icon('warn')}结论相反</span>` : r.roughHigher ? '<span class="tag unknown">' + icon('info') + '粗算偏乐观</span>' : '<span class="tag unknown">' + icon('info') + '粗算偏保守</span>') : '<span class="muted">—</span>'}</td></tr>`; }).join('')}
    </tbody></table></div>`;
}

function renderSweep() {
  const st = story.sweepStory(vm);
  const box = $('[data-sweep]', el);
  if (!st) { setText('sweepSub', '这份结果没有容量比选。'); box.innerHTML = '<div class="empty-state">无容量比选数据</div>'; return; }
  setText('sweepTitle', st.title);
  setText('sweepSub', st.text);
  sweepChart(box, vm.sweep, vm.recommendedKwp, { label: '光伏容量比选曲线：横轴容量，纵轴比只用电网省下的钱', yTitle: `${story.yearsText(vm.studyYears)}比只用电网省下` });
  setText('sweepNote', `${srcLine(vm)} · 每个点是一次完整的全年逐小时计算；虚线空心点为已排除或条件不全的容量。候选容量是有限个，不是全局最优。`);
}

export function priceTable(v, { compact = false } = {}) {
  const yrs = story.yearsText(v.studyYears);
  return v.candidates.map((c) => {
    const adm = c.admission;
    let price, delta;
    if (c.id === 'S0_grid') { price = `${fmt.money(c.totalCost)}<small>元</small>`; delta = '<span class="delta base">比较基线</span>'; }
    else if (adm.status === 'unknown') { price = '<span class="muted">—</span>'; delta = `<span class="delta na">${icon('help')}条件不全，暂无法比较（不是淘汰）</span>`; }
    else if (adm.status === 'excluded') { price = `<span class="muted">${fmt.money(c.totalCost)}<small>元</small></span>`; delta = `<span class="delta bad">${icon('x')}已排除：${esc(c.reasons.join('；') || c.constraintText || '不满足限制条件')}</span>`; }
    else { const d = fmt.delta(c.incremental); price = `${fmt.money(c.totalCost)}<small>元</small>`; delta = `<span class="delta ${d.dir}">${esc(d.short)}</span>`; }
    const eq = adm.status === 'equivalent' && c.equivalentTo ? `<span class="xsmall muted">与「${esc(SCEN[c.equivalentTo] ? SCEN[c.equivalentTo].name : c.equivalentTo)}」相同</span>` : '';
    return `<div class="opt reveal${c.isRec ? ' rec' : ''}${adm.status === 'excluded' || adm.status === 'unknown' ? ' dim' : ''}" data-scen="${c.id}">
      ${c.isRec ? `<span class="rec-badge">${esc((v.rec || {}).label || '推荐')}</span>` : ''}
      ${scenIcon(c.id)}
      <span class="name">${esc(c.name)}</span>
      <span class="sub-name">${c.id === 'S0_grid' ? '不加装发电设备' : esc(story.scenLabel(c))}</span>
      <span class="price-cap">${yrs}总花费（折现）</span>
      <span class="price num">${price}</span>
      ${delta}${eq}
      <div class="meta">
        <span><span class="tag ${adm.tone}">${icon(adm.icon)}${esc(adm.label)}</span></span>
        <span>年发电 <b class="num">${fmt.kwh(c.gen)}</b> kWh</span>
        <span>空调用电由自发电覆盖 <b class="num">${fmt.pct(c.coverage)}</b></span>
        ${compact ? '' : `<span>第 1 年减碳 <b class="num">${fmt.kwh(c.carbon && c.carbon.avoidedKgY1)}</b> kg</span>`}
      </div>
    </div>`;
  }).join('');
}

function renderPrice() {
  const rec = vm.byId[(vm.rec || {}).scenarioId];
  setText('priceKicker', `${story.yearsText(vm.studyYears)}总账`);
  setText('priceTitle', rec ? `在可比较的方案里，「${rec.name}」${story.yearsText(vm.studyYears)}总花费最低。` : '四种供电方式，一张表比清楚。');
  $('[data-compare]', el).innerHTML = priceTable(vm);
  const t = vm.tariff;
  setHtml('priceNote', `${esc(srcLine(vm))}。总花费为空调用电购电费加发电设备投入与运维的折现成本，不含空调设备本身；报价为用户情景，未经采购核实。${t ? ` 电价：${esc(t.title || t.id)}${t.provisional ? ' <span class="pending">待核验</span>' : ''}。` : ''} 推荐依据：${esc((vm.rec || {}).note || '')}。`);
}

function renderTiers() {
  if (!samples) return;
  const box = $('[data-tiers]', el);
  box.innerHTML = TIER_IDS.filter((id) => samples.cases.has(id)).map((id) => {
    const v = data.fromSample(samples.cases.get(id), samples.file);
    const rec = v.byId[(v.rec || {}).scenarioId];
    const fe = v.feasibility;
    return `<article class="tier">
      <span class="tier-tag">${TIER_TAG[id]}</span>
      <h3>${esc(v.label.replace(/^[^：]*：/, ''))}</h3>
      <p class="tier-meta">${esc(story.roomText(v))}${story.scheduleText(v.request) ? ' · ' + esc(story.scheduleText(v.request)) : ''}</p>
      <dl>
        <div><dt>空调一年用电</dt><dd><b class="num">${fmt.kwh(v.load.annualKwh)}</b> kWh</dd></div>
        <div><dt>最划算的光伏容量</dt><dd><b class="num">${fmt.d(v.recommendedKwp, 2)}</b> kWp</dd></div>
        <div><dt>${rec ? esc(rec.name) : '推荐方案'}</dt><dd><b>${rec ? esc(fmt.delta(rec.incremental).short) : '—'}</b></dd></div>
      </dl>
      <p class="tier-say">${esc(story.headline(v))}。</p>
      ${fe ? `<p class="tier-bound">${icon('info')}<span>${esc(fe.conclusion || '')}：${esc((fe.not_modelled || []).join('、'))}未计入，结果偏保守。</span></p>` : ''}
      <a class="btn sm" href="#/samples/${id}">打开示例${icon('arrow')}</a>
    </article>`;
  }).join('');
}

function renderAll() {
  vm = currentVM();
  renderSrcSeg();
  if (!vm) return;
  setText('srcnote', srcLine(vm));
  const hrs = vm.hourly && (vm.hourly.recommended || vm.hourly.combo);
  setText('hours', hrs ? ` ${fmt.int(hrs.ts.length)} 个小时` : '逐小时');
  renderHero(); renderFacts(); renderCalendar(); renderRing(); renderVersus(); renderSweep(); renderPrice(); renderTiers();
  reveal(el);
}

/* ------------------------------------------------------------------ */
/* 入口                                                                */
/* ------------------------------------------------------------------ */
function build() {
  el.innerHTML = skeleton();
  scene = createScene($('[data-stage]', el), {
    date: $('[data-hud="date"]', el), load: $('[data-hud="load"]', el), pv: $('[data-hud="pv"]', el), wind: $('[data-hud="wind"]', el),
    self: $('[data-hud="self"]', el), waste: $('[data-hud="waste"]', el), bar: $('[data-hud="bar"]', el)
  });
  cal = createCalendar($('[data-cal]', el));
  el.addEventListener('click', (e) => {
    const s = e.target.closest('[data-src]');
    if (s) { const v = s.dataset.src; source = v === 'live' ? { kind: 'live' } : { kind: 'sample', caseId: v.split(':')[1] }; ringId = null; $('.statement', el).dataset.counted = ''; renderAll(); return; }
    const r = e.target.closest('[data-ring-btn]'); if (r) { ringId = r.dataset.ringBtn; renderRing(); return; }
    const cs = e.target.closest('[data-calset-btn]'); if (cs) { calSet = cs.dataset.calsetBtn; renderCalendar(); return; }
    if (e.target.closest('[data-action="cal-csv"]')) cal.exportCsv(`能见度_逐时_${vm ? (vm.caseId || 'live') : ''}_${calSet}.csv`);
  });
  let rz = null;
  window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (vm && !el.hidden) renderSweep(); }, 180); });
  built = true;
}

export function show(root) {
  el = root;
  if (!built) {
    build();
    data.loadSamples().then((s) => { samples = s; renderAll(); }).catch((err) => {
      $$('[data-k="srcnote"],[data-k="factsSub"],[data-k="sweepSub"],[data-k="calNote"]', el).forEach((n) => { n.textContent = `示例数据读取失败：${err.message}`; });
    });
  } else if (vm) { renderSweep(); }
}

/** 用户完成一次实时计算后，首页改用该结果。 */
on('live-result', () => { source = { kind: 'live' }; ringId = null; if (built) { const st = $('.statement', el); if (st) st.dataset.counted = ''; renderAll(); } });
export function useSample(caseId) { source = { kind: 'sample', caseId }; if (built) renderAll(); }
export const getVM = () => vm;
export { renderAll };
