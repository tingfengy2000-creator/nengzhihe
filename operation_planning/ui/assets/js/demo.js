/* 能见度 · 一键演示
 * 页内播放器：基于示例数据自动走 8 幕，每幕约 8 秒；底部字幕，画面自动滚动到对应区域并高亮（“多余的电去哪儿”一幕打开中档示例的试算第 3 步）。
 * 可暂停、上一幕、下一幕，键盘 ←/→ 切换、空格暂停、Esc 退出。字幕数字全部从示例回放读取。
 * 减少动态效果时不自动播放、不平滑滚动。 */
import { $, $$, esc, fmt, icon, reduceMotion, toast } from './util.js';
import * as data from './data.js';
import * as story from './story.js';

const DUR = 8000;
let scenes = [], cur = 0, playing = false, t0 = 0, raf = null, active = false, lastFocus = null;

function buildScenes(s) {
  const v = data.fromSample(s.cases.get('tier_small'), s.file);
  const mid = s.cases.get('tier_medium') ? data.fromSample(s.cases.get('tier_medium'), s.file) : null;
  const big = s.cases.get('tier_large') ? data.fromSample(s.cases.get('tier_large'), s.file) : null;
  const s3 = v.byId.S3_pv_wind, rec = v.byId[(v.rec || {}).scenarioId];
  const st = story.sweepStory(v);
  const hrs = v.hourly && v.hourly.combo ? v.hourly.combo.ts.length : null;
  const pt = rec && rec.carbon ? fmt.perTon(rec.carbon.costPerT).text : '—';
  const tierLine = (x) => { if (!x) return ''; const r = x.byId[(x.rec || {}).scenarioId]; return `${x.label.replace(/^[^：]*：/, '')}：最划算光伏 ${fmt.d(x.recommendedKwp, 2)} kWp，${r ? fmt.delta(r.incremental).text : ''}`; };
  return [
    { t: '场景', target: '.hero', cap: `${story.placeText(v)}，${story.roomText(v)}，${story.scheduleText(v.request) || ''}。空调一年用电 ${fmt.kwh(v.load.annualKwh)} kWh，${v.service ? v.service.label : ''}。` },
    { t: '有人建议装光伏和风机', target: '[aria-labelledby="h-facts"]', cap: s3 ? `有人建议装${story.scenLabel(s3)}：一年能发 ${fmt.kwh(s3.gen)} kWh${s3.gen > v.load.annualKwh ? '，比空调一年的用电还多' : ''}。装了就一定省钱、减碳吗？` : '有人建议装光伏和小风机。' },
    { t: '能源日历', target: '#home-cal', cap: s3 ? `把全年 ${fmt.int(hrs)} 个小时铺开：中午光伏发电、夜里风机在转，房间却常常没人用电。光伏+小风机的发电有 ${fmt.pct(s3.carbon && s3.carbon.curtailedShare)} 在发出来时没人用。` : '把全年每个小时铺开看用电和发电。', cal: 'cat', calset: 'combo' },
    { t: '装多大最划算', target: '[aria-labelledby="h-sweep"]', cap: st ? st.text : '比较不同光伏容量。' },
    { t: '10 年总账与每吨减碳成本', target: '[aria-labelledby="h-price"]', cap: rec ? `${story.headline(v)}：${story.yearsText(v.studyYears)}总花费约 ${fmt.money(rec.totalCost)} 元${rec.id !== 'S0_grid' ? `，${fmt.delta(rec.incremental).text}` : ''}；按当时用上的电算，${pt}。加装小风机${fmt.delta((v.byId.S2_wind || {}).incremental).text}。` : '' },
    { t: '多余的电去哪儿', route: 'tool', caseId: 'tier_medium', target: '[data-sec="surplus"]', cap: surplusCap(mid) },
    { t: '换成图书馆或厂房再看', target: '[aria-labelledby="h-tiers"]', cap: [tierLine(mid), tierLine(big)].filter(Boolean).join('；') + '。厂房只计空调区，生产用电未计入。' },
    { t: '导出决策简报', target: '[aria-labelledby="h-demo"]', cap: '打开示例或用自己的条件实时计算后，在第 4 步一键导出决策简报、方案汇总表和逐时数据，导出内容只来自当前显示的结果。' }
  ];
}

/** “多余的电去哪儿”一幕的字幕：读中档示例推荐方案的 surplus_paths。 */
function surplusCap(x) {
  if (!x) return '多余的电可以存起来，也可以卖给电网；两条路分别估算，不改变推荐。';
  const r = x.byId[(x.rec || {}).scenarioId];
  const sp = r && r.surplus; if (!sp) return '多余的电可以存起来，也可以卖给电网；两条路分别估算，不改变推荐。';
  const st = sp.storage, ex = sp.export;
  const best = st && st.candidates.find((c) => c.capacityKwh === st.recommendedKwh);
  const yt = story.yearsText((st && st.studyYears) || x.studyYears);
  const stTxt = best && best.capacityKwh > 0 && best.status === 'complete'
    ? `装 ${fmt.d(best.capacityKwh, 1)} kWh 储能约 ${fmt.d(best.payback, 1)} 年回本，${yt}净收益约 ${fmt.money(best.studyNet)} 元`
    : (st && st.recommendationNote) || '储能按当前报价不划算';
  const exTxt = ex && ex.status === 'complete' && ex.price != null ? `按 ${fmt.d(ex.price, 2)} 元/kWh 粗算卖给电网，每年约 ${fmt.money(ex.annualRevenue)} 元` : '';
  return `${x.label.replace(/^[^：]*：/, '')}推荐的${story.scenLabel(r)}，每年约有 ${fmt.kwh(sp.surplusKwh)} 度电用不完：${stTxt}${exTxt ? '；' + exTxt : ''}。两条路分别估算，不叠加，也不改变推荐。`;
}

function render() {
  const box = $('#demo');
  box.innerHTML = `<div class="demo-bar container">
    <div class="demo-top"><span class="demo-scene num">第 ${cur + 1} 幕 / ${scenes.length} · ${esc(scenes[cur].t)}</span><span class="xsmall demo-src">数据：示例回放 ${esc(data.sampleSourceText(data.samplesLoaded()))}（小档、中档、大档）</span></div>
    <p class="demo-cap" aria-live="polite">${esc(scenes[cur].cap)}</p>
    <div class="demo-ctrls">
      <button class="iconbtn" type="button" data-demo="prev" aria-label="上一幕">${icon('prev')}</button>
      <button class="iconbtn" type="button" data-demo="play" aria-label="${playing ? '暂停' : '播放'}">${icon(playing ? 'pause' : 'play')}</button>
      <button class="iconbtn" type="button" data-demo="next" aria-label="下一幕">${icon('next')}</button>
      <div class="demo-dots">${scenes.map((_, i) => `<button type="button" data-demo-go="${i}" aria-label="第 ${i + 1} 幕"><i style="width:${i < cur ? 100 : 0}%"></i></button>`).join('')}</div>
      <button class="btn sm on-stage" type="button" data-demo="exit">退出（Esc）</button>
    </div></div>`;
}

let navUntil = 0;   // 演示自己切换页面时，短时间内的 hashchange 不视为用户离开
const waitFor = (sel, ms = 8000) => new Promise((resolve) => { const t0 = performance.now(); const f = () => { const n = $(sel); if (n || performance.now() - t0 > ms) resolve(n); else setTimeout(f, 60); }; f(); });
async function focusScene() {
  $$('.demo-focus').forEach((n) => n.classList.remove('demo-focus'));
  const sc = scenes[cur], idx = cur;
  let target;
  if (sc.route === 'tool') {
    navUntil = performance.now() + 2500;
    const tool = await import('./tool.js'); await tool.openSample(sc.caseId, 3);
    target = await waitFor(`#view-tool:not([hidden]) ${sc.target}`);
  } else {
    if (location.hash !== '#/' && location.hash !== '') { navUntil = performance.now() + 2500; location.hash = '#/'; }
    target = await waitFor(`#view-home:not([hidden]) ${sc.target}`);
  }
  if (idx !== cur) return;
  if (target) {
    target.classList.add('demo-focus');
    target.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' });
  }
  if (sc.calset) { const b = $(`#view-home [data-calset-btn="${sc.calset}"]`); if (b) b.click(); }
  if (sc.cal) { const b = $(`#view-home [data-cal-view="${sc.cal}"]`); if (b) b.click(); }
}

function go(i) {
  cur = (i + scenes.length) % scenes.length; t0 = performance.now();
  render(); focusScene();
}
function tick(n) {
  if (!active) return;
  if (playing) {
    const p = (n - t0) / DUR;
    const dot = $(`#demo [data-demo-go="${cur}"] i`); if (dot) dot.style.width = `${Math.min(100, p * 100)}%`;
    if (p >= 1) { if (cur === scenes.length - 1) { playing = false; render(); } else go(cur + 1); }
  }
  raf = requestAnimationFrame(tick);
}

function onKey(e) {
  if (!active) return;
  if (e.key === 'Escape') { e.preventDefault(); stop(); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); go(cur + 1); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); go(cur - 1); }
  else if (e.key === ' ' && !e.target.closest('input,textarea,select,button')) { e.preventDefault(); toggle(); }
}
function toggle() { playing = !playing; t0 = performance.now() - (parseFloat(($(`#demo [data-demo-go="${cur}"] i`) || {}).style?.width || 0) / 100) * DUR; render(); }

export async function start() {
  let s;
  try { s = await data.loadSamples(); } catch (e) { toast(`示例数据读取失败：${e.message}`); return; }
  scenes = buildScenes(s);
  lastFocus = document.activeElement;
  if (location.hash !== '#/' && location.hash !== '') location.hash = '#/';
  const home = await import('./home.js'); home.useSample('tier_small');
  active = true; playing = !reduceMotion(); cur = 0;
  const box = $('#demo'); box.hidden = false; document.body.classList.add('demo-on');
  setTimeout(() => { go(0); $('#demo [data-demo="play"]').focus(); }, 120);
  cancelAnimationFrame(raf); raf = requestAnimationFrame(tick);
  if (reduceMotion()) toast('已关闭自动播放（减少动态效果），请用左右键切换');
}
export function stop() {
  active = false; playing = false; cancelAnimationFrame(raf);
  $('#demo').hidden = true; document.body.classList.remove('demo-on');
  $$('.demo-focus').forEach((n) => n.classList.remove('demo-focus'));
  if (lastFocus && lastFocus.focus) lastFocus.focus();
}

document.addEventListener('keydown', onKey);
document.addEventListener('click', (e) => {
  if (!active) return;
  const b = e.target.closest('[data-demo]');
  if (b) { const a = b.dataset.demo; if (a === 'prev') go(cur - 1); if (a === 'next') go(cur + 1); if (a === 'play') toggle(); if (a === 'exit') stop(); return; }
  const d = e.target.closest('[data-demo-go]'); if (d) go(+d.dataset.demoGo);
});
window.addEventListener('hashchange', () => { if (active && performance.now() > navUntil && location.hash !== '#/' && location.hash !== '') stop(); });
