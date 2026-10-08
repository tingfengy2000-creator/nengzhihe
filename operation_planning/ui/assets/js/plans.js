/* 能见度 · 我的方案
 * 只保存在本机浏览器 localStorage（键 njd.plans.v1）：条件、结论摘要、来源、时间；不保存逐时数据。
 * 可“载入条件重新计算”，可勾选两份方案对比条件与结论。 */
import { $, $$, esc, fmt, icon, toast, store } from './util.js';
import { FIELDS, FIELD } from './form.js';
import { loadPlans, PLAN_KEY } from './export.js';
import * as tool from './tool.js';

let el = null, picked = [];

function planCard(p) {
  const s = p.summary || {};
  return `<article class="plan-card${picked.includes(p.id) ? ' picked' : ''}">
    <div class="row" style="justify-content:space-between"><label class="check"><input type="checkbox" data-pick="${p.id}"${picked.includes(p.id) ? ' checked' : ''}>选来对比</label><span class="tag ${p.kind === 'live' ? 'ok' : 'brand'}">${icon(p.kind === 'live' ? 'bolt' : 'doc')}${p.kind === 'live' ? '实时计算' : '示例数据'}</span></div>
    <h3>${esc(s.headline || p.label)}。</h3>
    <p class="tier-meta">${esc([s.place, s.room, s.schedule].filter(Boolean).join(' · '))}</p>
    <dl class="sample-kv">
      <div><dt>空调一年用电</dt><dd>${s.annualKwh != null ? `<b class="num">${fmt.kwh(s.annualKwh)}</b> kWh${s.service ? ` · ${esc(s.service)}` : ''}` : '—'}</dd></div>
      <div><dt>${esc(s.recName || '推荐')}</dt><dd>${s.recTotal != null ? `<b class="num">${fmt.money(s.recTotal)}</b> 元` : '—'}${s.recName && s.recName !== '只用电网' ? ` · ${esc(fmt.delta(s.recIncremental).short)}` : ''}</dd></div>
      <div><dt>推荐状态</dt><dd>${esc(s.recStatus || '—')}</dd></div>
      ${s.tariff ? `<div><dt>电价</dt><dd>${esc(s.tariff)}</dd></div>` : ''}
    </dl>
    <p class="xsmall muted">来源：${esc(p.source)} · 保存于 ${esc(fmt.date(p.savedAt))}</p>
    <div class="row"><button class="btn primary sm" type="button" data-load="${p.id}">${icon('refresh')}载入条件重新计算</button><button class="btn ghost sm" type="button" data-del="${p.id}">删除</button></div>
  </article>`;
}

function compareHtml(plans) {
  if (plans.length !== 2) return `<p class="muted small">勾选两份方案，可在这里对比条件差异与结论。</p>`;
  const [a, b] = plans;
  const rows = FIELDS.filter((f) => f.key !== 'max_units').map((f) => [f, (a.form || {})[f.key], (b.form || {})[f.key]]).filter(([, x, y]) => String(x ?? '') !== String(y ?? ''));
  const show = (f, v) => { if (v === '' || v == null) return '<span class="muted">未填写</span>'; if (f.type === 'check') return v ? '是' : '否'; if (f.options) { const o = f.options.find((x) => String(x[0]) === String(v)); if (o) return esc(o[1]); } return esc(`${v}${f.unit ? ' ' + f.unit : ''}`); };
  const sa = a.summary || {}, sb = b.summary || {};
  return `<div class="tablewrap"><table class="table"><caption class="sr-only">两份方案对比</caption><thead><tr><th>项目</th><th>${esc(fmt.date(a.savedAt))}</th><th>${esc(fmt.date(b.savedAt))}</th></tr></thead><tbody>
    <tr><td><b>结论</b></td><td>${esc(sa.headline || '')}</td><td>${esc(sb.headline || '')}</td></tr>
    <tr><td>空调一年用电</td><td class="num">${fmt.kwh(sa.annualKwh)} kWh</td><td class="num">${fmt.kwh(sb.annualKwh)} kWh</td></tr>
    <tr><td>推荐方案总花费</td><td class="num">${fmt.money(sa.recTotal)} 元</td><td class="num">${fmt.money(sb.recTotal)} 元</td></tr>
    <tr><td>来源</td><td>${esc(a.source)}</td><td>${esc(b.source)}</td></tr>
    ${rows.length ? rows.map(([f, x, y]) => `<tr><td>${esc(f.label)}</td><td>${show(f, x)}</td><td>${show(f, y)}</td></tr>`).join('') : '<tr><td colspan="3" class="muted">两份方案的条件完全相同。</td></tr>'}
  </tbody></table></div><p class="hint">只列出不同的条件；数字为保存时结果中的原值。</p>`;
}

function render() {
  const plans = loadPlans();
  picked = picked.filter((id) => plans.find((p) => p.id === id));
  $('[data-plans]', el).innerHTML = plans.length
    ? `<div class="sample-grid">${plans.map(planCard).join('')}</div>`
    : `<div class="empty-state big">${icon('save')}<p>还没有保存的方案。在试算第 4 步点击「保存到我的方案」，结论和条件会保存在这台电脑的浏览器里。</p><a class="btn primary" href="#/tool">开始试算</a></div>`;
  $('[data-compare-plans]', el).innerHTML = plans.length >= 2 ? `<h2 class="h3 group-title">两份方案对比</h2>${compareHtml(plans.filter((p) => picked.includes(p.id)))}` : '';
}

export function show(root) {
  el = root;
  if (!el.dataset.ready) {
    el.dataset.ready = '1';
    el.innerHTML = `<section class="page-head"><div class="container"><p class="kicker">我的方案</p><h1 class="h2">保存过的方案，只在这台电脑上。</h1>
      <p class="sub">“我的方案”只保存在本机浏览器（不上传、不同步）。每份保存条件与结论摘要，可载入条件重新计算，也可以挑两份对比。</p></div></section>
      <section class="container samples-body"><div data-plans></div><div data-compare-plans style="margin-top:40px"></div></section>`;
    el.addEventListener('click', (e) => {
      const ld = e.target.closest('[data-load]');
      if (ld) { const p = loadPlans().find((x) => x.id === ld.dataset.load); if (p && p.form) { tool.loadForm(p.form); location.hash = '#/tool/1'; toast('已载入条件，点击计算后实时算出'); } return; }
      const dl = e.target.closest('[data-del]');
      if (dl) { const list = loadPlans().filter((x) => x.id !== dl.dataset.del); store.set(PLAN_KEY, list); render(); toast('已删除'); }
    });
    el.addEventListener('change', (e) => {
      const pk = e.target.closest('[data-pick]'); if (!pk) return;
      const id = pk.dataset.pick;
      picked = pk.checked ? picked.concat(id).slice(-2) : picked.filter((x) => x !== id);
      render();
    });
  }
  render();
}
