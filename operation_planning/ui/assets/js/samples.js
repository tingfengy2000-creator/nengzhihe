/* 能见度 · 示例
 * 三档（小：35㎡办公室；中：每天开放的图书馆阅读区；大：工业厂房空调分区代理）+ 三个状态变体。
 * 卡片上的结论与关键数字全部从 replay_cases_v6.json 读取；点「打开」显示完整结果（示例数据），
 * 同时把示例条件填进表单，用户改任何条件后可实时重算。 */
import { $, esc, fmt, icon } from './util.js';
import * as data from './data.js';
import * as tool from './tool.js';
import * as story from './story.js';

const TIER_TAG = { tier_small: '小档', tier_medium: '中档', tier_large: '大档' };
let el = null;
/* 回放里变体说明夹带的英文状态词换成页面用语 */
const plainReason = (t) => String(t).replace(/\bunknown\b/g, '“条件不全”').replace(/\bexcluded\b/g, '“已排除”');

function card(v, id) {
  const rec = v.byId[(v.rec || {}).scenarioId];
  const variant = !TIER_TAG[id];
  const fe = v.feasibility;
  return `<article class="sample-card${variant ? ' variant' : ''}">
    <div class="row" style="justify-content:space-between"><span class="tier-tag">${variant ? '状态变体' : TIER_TAG[id]}</span><span class="tag ${v.rec.tone}">${esc(v.rec.label)}</span></div>
    <h3>${esc(v.label.replace(/^[^：]*：/, ''))}</h3>
    <p class="tier-meta">${esc(story.placeText(v))} · ${esc(story.roomText(v))}${story.scheduleText(v.request) ? ' · ' + esc(story.scheduleText(v.request)) : ''}</p>
    ${v.variantReason ? `<p class="small">${icon('info')}<span>${esc(plainReason(v.variantReason))}</span></p>` : ''}
    <p class="tier-say">${esc(story.headline(v))}。</p>
    <dl class="sample-kv">
      <div><dt>空调一年用电</dt><dd><b class="num">${fmt.kwh(v.load.annualKwh)}</b> kWh</dd></div>
      <div><dt>空调服务</dt><dd><span class="tag ${v.service.tone}">${icon(v.service.icon)}${esc(v.service.label)}</span></dd></div>
      <div><dt>${rec ? esc(rec.name) : '推荐'}</dt><dd>${rec ? `<b class="num">${fmt.money(rec.totalCost)}</b> 元 · ${rec.id === 'S0_grid' ? '基线' : esc(fmt.delta(rec.incremental).short)}` : '—'}</dd></div>
      <div><dt>${variant ? '光伏容量' : '最划算光伏容量'}</dt><dd><b class="num">${fmt.d(v.recommendedKwp, 2)}</b> kWp${v.req.fixedCapacity != null ? '（固定）' : ''}</dd></div>
    </dl>
    <ul class="opt-mini">${v.candidates.map((c) => `<li><span>${esc(c.name)}</span><span class="tag ${c.admission.tone}">${icon(c.admission.icon)}${esc(c.admission.label)}</span>${c.reasons.length ? `<small>${esc(c.reasons.join('；'))}</small>` : ''}</li>`).join('')}</ul>
    ${fe ? `<p class="tier-bound">${icon('info')}<span>${esc(fe.conclusion || '')}。只计厂房空调区，${esc((fe.not_modelled || []).join('、'))}等生产用电未计入，结果偏保守。</span></p>` : ''}
    <div class="row sample-actions"><a class="btn primary sm" href="#/samples/${id}">打开${icon('arrow')}</a><button class="btn sm" type="button" data-home-sample="${id}"${variant ? ' hidden' : ''}>在首页看这一档</button></div>
  </article>`;
}

export function show(root, args = []) {
  el = root;
  if (args[0]) { tool.openSample(args[0], 3); return; }
  if (!el.dataset.ready) {
    el.dataset.ready = '1';
    el.innerHTML = `<section class="page-head"><div class="container">
      <p class="kicker">示例</p><h1 class="h2">三档示例与三个状态变体。</h1>
      <p class="sub">示例只是起点：数字来自 5090 用本机计算服务实时接口生成并保存的回放文件。打开后会显示完整结果，同时把示例条件填进试算表单，改任何条件都可以实时重算。</p>
    </div></section>
    <section class="container samples-body"><div data-samples><div class="empty-state">正在读取示例数据…</div></div>
      <p class="source-note" data-samples-src></p></section>`;
    el.addEventListener('click', async (e) => {
      const b = e.target.closest('[data-home-sample]'); if (!b) return;
      const home = await import('./home.js'); home.useSample(b.dataset.homeSample); location.hash = '#/';
    });
  }
  data.loadSamples().then((s) => {
    const tiers = s.order.filter((id) => TIER_TAG[id]), vars = s.order.filter((id) => !TIER_TAG[id]);
    $('[data-samples]', el).innerHTML = `<h2 class="h3 group-title">三档示例</h2><div class="sample-grid">${tiers.map((id) => card(data.fromSample(s.cases.get(id), s.file), id)).join('')}</div>
      <h2 class="h3 group-title">状态变体</h2><p class="muted small">与小档同一房间口径，固定 1 kWp 光伏，用来展示“已排除”“条件不全”等状态如何显示。</p><div class="sample-grid">${vars.map((id) => card(data.fromSample(s.cases.get(id), s.file), id)).join('')}</div>`;
    $('[data-samples-src]', el).textContent = `来源：docs/handoff/replay_viewer/replay_cases_v6.json（${s.file.format_version}，源码提交 ${fmt.sha(((s.file.source || {}).source_commit), 10)}）。主电价档案 ${(s.file.main_tariff || {}).tariff_id || ''}${(s.file.main_tariff || {}).provisional ? '（待核验）' : ''}。示例不代表真实客户、试点或节能收益。`;
  }).catch((err) => { $('[data-samples]', el).innerHTML = `<div class="callout bad">${icon('warn')}<span>示例数据读取失败：${esc(err.message)}</span></div>`; });
}
