/* 能见度 · 手写 SVG 图表
 *
 * 图表只画传入的数值，不做业务计算。唯一允许的“显示用分组”（按月加总、按日期×小时排格、
 * 取某一天）由调用方完成并在图旁注明“仅用于显示”。
 * 规范：单一纵轴（不用双纵轴）、2px 线、≥8px 标记、整齐刻度、图例、悬停提示、单位清楚。
 */
import { esc, fmt, isNum, tip } from './util.js';

const NS = 'http://www.w3.org/2000/svg';

/** 整齐刻度 */
export function niceTicks(min, max, count = 5) {
  if (!isNum(min) || !isNum(max)) return [0, 1];
  if (min === max) { if (max === 0) return [0, 1]; min = Math.min(0, min); max = Math.max(0, max); }
  const span = max - min;
  const raw = span / Math.max(1, count);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
  const out = [];
  for (let v = lo; v <= hi + step * 1e-6; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : +v.toPrecision(12));
  return out;
}
export function axisLabel(v) {
  const a = Math.abs(v);
  if (a >= 1e8) return `${fmt.d(v / 1e8, 1)}亿`;
  if (a >= 1e4) return `${fmt.d(v / 1e4, a >= 1e5 ? 0 : 1)}万`;
  if (a > 0 && a < 1) return fmt.d(v, 2);
  return fmt.d(v, a < 10 ? 1 : 0);
}

function svg(w, h, label) {
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${esc(label || '')}" preserveAspectRatio="none">`;
}

/* ------------------------------------------------------------------ */
/* 折线/面积图（逐时，带十字准线与悬停提示）                              */
/* opts: { x: [时间文本], series: [{ key, label, color, values, area?, dash? }],
 *         unit, height, xTicks: [{ i, label }], label, stacked?: false }
 * ------------------------------------------------------------------ */
export function lineChart(el, opts) {
  const W = Math.max(320, Math.round(el.clientWidth || 720)), H = opts.height || 260;
  const m = { l: 52, r: 14, t: 12, b: 30 };
  const n = opts.x.length;
  const all = opts.series.flatMap((s) => s.values.filter(isNum));
  const ticks = niceTicks(0, Math.max(0, ...all), 4);
  const yMax = ticks[ticks.length - 1] || 1;
  const X = (i) => m.l + (n <= 1 ? 0 : (i / (n - 1)) * (W - m.l - m.r));
  const Y = (v) => m.t + (1 - v / yMax) * (H - m.t - m.b);
  let s = svg(W, H, opts.label);
  for (const t of ticks) s += `<line class="gridline" x1="${m.l}" x2="${W - m.r}" y1="${Y(t)}" y2="${Y(t)}"/><text class="axis" x="${m.l - 8}" y="${Y(t) + 4}" text-anchor="end">${axisLabel(t)}</text>`;
  for (const xt of opts.xTicks || []) s += `<text class="axis" x="${X(xt.i)}" y="${H - 8}" text-anchor="${xt.anchor || 'middle'}">${esc(xt.label)}</text>`;
  if (opts.unit) s += `<text class="axis-title" x="${m.l - 8}" y="${m.t - 2}" text-anchor="end" dy="-2"></text>`;
  for (const se of opts.series) {
    const pts = se.values.map((v, i) => `${X(i).toFixed(1)},${Y(isNum(v) ? v : 0).toFixed(1)}`);
    if (se.area) s += `<path d="M${X(0)},${Y(0)}L${pts.join('L')}L${X(n - 1)},${Y(0)}Z" fill="${se.color}" fill-opacity=".18" stroke="none"/>`;
    s += `<polyline points="${pts.join(' ')}" fill="none" stroke="${se.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"${se.dash ? ' stroke-dasharray="5 4"' : ''}/>`;
  }
  s += `<line class="xhair" x1="0" x2="0" y1="${m.t}" y2="${H - m.b}" stroke="var(--ink-3)" stroke-width="1" visibility="hidden"/>`;
  s += `<rect class="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/>`;
  s += '</svg>';
  el.innerHTML = s;
  const root = el.querySelector('svg'), hair = root.querySelector('.xhair'), hit = root.querySelector('.hit');
  const move = (ev) => {
    const r = root.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(n - 1, Math.round(((px - m.l) / (W - m.l - m.r)) * (n - 1))));
    hair.setAttribute('x1', X(i)); hair.setAttribute('x2', X(i)); hair.setAttribute('visibility', 'visible');
    const rows = opts.series.map((se) => `<div class="tt-row"><span><i style="background:${se.color}"></i>${esc(se.label)}</span><b class="num">${fmt.d(se.values[i], 2)}</b></div>`).join('');
    tip.show(`<b>${esc(opts.x[i])}</b>${rows}<div class="tt-note">单位 ${esc(opts.unit || '')}</div>`, ev.clientX, ev.clientY);
  };
  hit.addEventListener('pointermove', move);
  hit.addEventListener('pointerleave', () => { hair.setAttribute('visibility', 'hidden'); tip.hide(); });
}

/* ------------------------------------------------------------------ */
/* 柱状图（可堆叠；每类一组）                                            */
/* opts: { cats: [文本], series: [{ label, color, values }], stacked, unit, height, label, note }
 * ------------------------------------------------------------------ */
export function barChart(el, opts) {
  const W = Math.max(320, Math.round(el.clientWidth || 720)), H = opts.height || 240;
  const m = { l: 52, r: 10, t: 12, b: 28 };
  const n = opts.cats.length;
  const tops = opts.cats.map((_, i) => opts.stacked ? opts.series.reduce((a, se) => a + (isNum(se.values[i]) ? se.values[i] : 0), 0) : Math.max(...opts.series.map((se) => se.values[i] || 0)));
  const ticks = niceTicks(0, Math.max(0, ...tops), 4);
  const yMax = ticks[ticks.length - 1] || 1;
  const band = (W - m.l - m.r) / n;
  const groups = opts.stacked ? 1 : opts.series.length;
  const bw = Math.max(3, Math.min(34, band * 0.62 / groups));
  const Y = (v) => m.t + (1 - v / yMax) * (H - m.t - m.b);
  let s = svg(W, H, opts.label);
  for (const t of ticks) s += `<line class="gridline" x1="${m.l}" x2="${W - m.r}" y1="${Y(t)}" y2="${Y(t)}"/><text class="axis" x="${m.l - 8}" y="${Y(t) + 4}" text-anchor="end">${axisLabel(t)}</text>`;
  opts.cats.forEach((c, i) => {
    const cx = m.l + band * i + band / 2;
    s += `<text class="axis" x="${cx}" y="${H - 8}" text-anchor="middle">${esc(c)}</text>`;
    let acc = 0;
    opts.series.forEach((se, k) => {
      const v = isNum(se.values[i]) ? se.values[i] : 0;
      if (v <= 0) return;
      const x = opts.stacked ? cx - bw / 2 : cx - (bw * groups) / 2 + k * bw;
      const y0 = opts.stacked ? Y(acc) : Y(0), y1 = opts.stacked ? Y(acc + v) : Y(v);
      const h = Math.max(1, y0 - y1 - (opts.stacked && acc > 0 ? 2 : 0));
      s += `<rect x="${x + (opts.stacked ? 0 : 1)}" y="${y1}" width="${bw - (opts.stacked ? 0 : 2)}" height="${h}" rx="3" fill="${se.color}"/>`;
      acc += v;
    });
    s += `<rect class="hit" data-i="${i}" x="${m.l + band * i}" y="${m.t}" width="${band}" height="${H - m.t - m.b}" fill="transparent"/>`;
  });
  s += '</svg>';
  el.innerHTML = s;
  el.querySelectorAll('.hit').forEach((r) => {
    r.addEventListener('pointermove', (ev) => {
      const i = +r.dataset.i;
      const rows = opts.series.map((se) => `<div class="tt-row"><span><i style="background:${se.color}"></i>${esc(se.label)}</span><b class="num">${fmt.kwh(se.values[i])}</b></div>`).join('');
      tip.show(`<b>${esc(opts.cats[i])}</b>${rows}<div class="tt-note">单位 ${esc(opts.unit || '')}${opts.note ? ' · ' + esc(opts.note) : ''}</div>`, ev.clientX, ev.clientY);
    });
    r.addEventListener('pointerleave', () => tip.hide());
  });
}

/* ------------------------------------------------------------------ */
/* 光伏容量比选曲线：横轴容量，纵轴“比只用电网省下（正）/多花（负）”      */
/* rows: vm.sweep；bestKwp: 后端 recommended_pv_capacity_kwp            */
/* ------------------------------------------------------------------ */
export function sweepChart(el, rows, bestKwp, opts = {}) {
  const W = Math.max(320, Math.round(el.clientWidth || 720)), H = opts.height || 300;
  const m = { l: 60, r: 24, t: 28, b: 40 };
  const pts = rows.filter((r) => isNum(r.kwp));
  const vals = pts.map((r) => r.incremental).filter(isNum);
  const ticks = niceTicks(Math.min(0, ...vals), Math.max(0, ...vals), 5);
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const xMax = Math.max(...pts.map((r) => r.kwp), 1);
  const xt = niceTicks(0, xMax, 5);
  const xHi = xt[xt.length - 1] || 1;
  const X = (k) => m.l + (k / xHi) * (W - m.l - m.r);
  const Y = (v) => m.t + (1 - (v - lo) / (hi - lo || 1)) * (H - m.t - m.b);
  let s = svg(W, H, opts.label || '光伏容量比选曲线');
  for (const t of ticks) s += `<line class="${t === 0 ? 'baseline' : 'gridline'}" x1="${m.l}" x2="${W - m.r}" y1="${Y(t)}" y2="${Y(t)}"${t === 0 ? ' stroke-width="1.5"' : ''}/><text class="axis" x="${m.l - 8}" y="${Y(t) + 4}" text-anchor="end">${axisLabel(t)}</text>`;
  for (const t of xt) s += `<text class="axis" x="${X(t)}" y="${H - 18}" text-anchor="middle">${axisLabel(t)}</text>`;
  s += `<text class="axis-title" x="${W - m.r}" y="${H - 2}" text-anchor="end">光伏容量（kWp）</text>`;
  s += `<text class="axis-title" x="${m.l}" y="${m.t - 12}" text-anchor="start">${esc(opts.yTitle || '比只用电网省下')}（元；负数为多花）</text>`;
  const line = pts.filter((r) => isNum(r.incremental));
  if (line.length > 1) s += `<polyline points="${line.map((r) => `${X(r.kwp)},${Y(r.incremental)}`).join(' ')}" fill="none" stroke="var(--brand)" stroke-width="2" stroke-linejoin="round"/>`;
  pts.forEach((r, i) => {
    if (!isNum(r.incremental)) return;
    const best = isNum(bestKwp) && Math.abs(r.kwp - bestKwp) < 1e-9;
    const excluded = r.admission.status === 'excluded' || r.admission.status === 'unknown';
    const cx = X(r.kwp), cy = Y(r.incremental);
    s += `<circle cx="${cx}" cy="${cy}" r="${best ? 8 : 5.5}" fill="${excluded ? 'var(--bg)' : best ? 'var(--brand)' : 'var(--surface)'}" stroke="${excluded ? 'var(--bad)' : 'var(--brand)'}" stroke-width="2.5"${excluded ? ' stroke-dasharray="3 2"' : ''}/>`;
    if (best) s += `<text x="${cx}" y="${cy - 16}" text-anchor="middle" font-size="13" font-weight="700" fill="var(--ink)">最划算 ${fmt.d(r.kwp, 2)} kWp</text>`;
    else if (excluded) s += `<text x="${cx}" y="${cy - 13}" text-anchor="middle" font-size="12" fill="var(--bad)">${esc(r.admission.label)}</text>`;
    s += `<circle class="hit" data-i="${i}" cx="${cx}" cy="${cy}" r="16" fill="transparent"/>`;
  });
  s += '</svg>';
  el.innerHTML = s;
  el.querySelectorAll('.hit').forEach((c) => {
    c.addEventListener('pointermove', (ev) => {
      const r = pts[+c.dataset.i]; const d = fmt.delta(r.incremental);
      tip.show(`<b>光伏 ${fmt.d(r.kwp, 2)} kWp</b>
        <div class="tt-row"><span>10 年总花费</span><b class="num">${fmt.money(r.totalCost)} 元</b></div>
        <div class="tt-row"><span>比只用电网</span><b>${esc(d.short)}</b></div>
        <div class="tt-row"><span>发电当时用上</span><b class="num">${fmt.pct(r.selfUseRate)}</b></div>
        <div class="tt-row"><span>状态</span><b>${esc(r.admission.label)}</b></div>
        ${r.reasons.length ? `<div class="tt-note">${esc(r.reasons.join('；'))}</div>` : ''}`, ev.clientX, ev.clientY);
    });
    c.addEventListener('pointerleave', () => tip.hide());
  });
}

/* ------------------------------------------------------------------ */
/* 环形图：用上 / 浪费（占发电量的角度只用于显示）                         */
/* ------------------------------------------------------------------ */
export function ring(el, { self, waste, total }) {
  const R = 92, C = 2 * Math.PI * R;
  const fs = isNum(self) && total > 0 ? (self / total) * C : 0;
  const fw = isNum(waste) && total > 0 ? (waste / total) * C : 0;
  let svgEl = el.querySelector('svg');
  if (!svgEl) {
    el.insertAdjacentHTML('afterbegin', `<svg viewBox="0 0 220 220" aria-hidden="true">
      <circle cx="110" cy="110" r="${R}" fill="none" stroke="var(--line)" stroke-width="16"/>
      <circle class="r-waste" cx="110" cy="110" r="${R}" fill="none" stroke="var(--c-waste)" stroke-width="16" stroke-linecap="butt" stroke-dasharray="0 ${C}"/>
      <circle class="r-self" cx="110" cy="110" r="${R}" fill="none" stroke="var(--c-self)" stroke-width="16" stroke-linecap="butt" stroke-dasharray="0 ${C}"/></svg>`);
    svgEl = el.querySelector('svg');
    void svgEl.getBoundingClientRect();
  }
  const gap = fs > 0 && fw > 0 ? 3 : 0;
  svgEl.querySelector('.r-self').setAttribute('stroke-dasharray', `${Math.max(0, fs - gap)} ${C}`);
  const w = svgEl.querySelector('.r-waste');
  w.setAttribute('stroke-dasharray', `${Math.max(0, fw - gap)} ${C}`);
  w.setAttribute('stroke-dashoffset', String(-fs));
}

/** 典型日/周横轴刻度：每天 0 点一个刻度 */
export function dayTicks(ts) {
  const out = [];
  ts.forEach((t, i) => { if (/T00:00/.test(t)) out.push({ i, label: t.slice(5, 10).replace('-', '/') , anchor: 'start' }); });
  return out;
}

/* ------------------------------------------------------------------ */
/* 正负柱：纵轴正负共用一条 0 线；正值青绿、负值暖红，每根柱标数值（不只靠颜色） */
/* opts: { cats, values, unit, height, label, highlight }                 */
/* ------------------------------------------------------------------ */
export function signedBarChart(el, opts) {
  const W = Math.max(300, Math.round(el.clientWidth || 600)), H = opts.height || 200;
  const m = { l: 56, r: 10, t: 18, b: 26 };
  const vals = opts.values.map((v) => (isNum(v) ? v : 0));
  const ticks = niceTicks(Math.min(0, ...vals), Math.max(0, ...vals), 4);
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const Y = (v) => m.t + (1 - (v - lo) / (hi - lo || 1)) * (H - m.t - m.b);
  const n = opts.cats.length, band = (W - m.l - m.r) / Math.max(1, n), bw = Math.min(46, band * 0.56);
  let s = svg(W, H, opts.label);
  for (const t of ticks) s += `<line class="${t === 0 ? 'baseline' : 'gridline'}" x1="${m.l}" x2="${W - m.r}" y1="${Y(t)}" y2="${Y(t)}"${t === 0 ? ' stroke-width="1.6"' : ''}/><text class="axis" x="${m.l - 8}" y="${Y(t) + 4}" text-anchor="end">${axisLabel(t)}</text>`;
  opts.cats.forEach((c, i) => {
    const v = vals[i], cx = m.l + band * i + band / 2, y0 = Y(0), y1 = Y(v);
    const top = Math.min(y0, y1), h = Math.max(1.5, Math.abs(y1 - y0));
    const col = v < 0 ? 'var(--more)' : 'var(--brand)';
    s += `<rect x="${cx - bw / 2}" y="${top}" width="${bw}" height="${h}" rx="3" fill="${col}"${opts.highlight === i ? ' stroke="var(--ink)" stroke-width="2"' : ''}/>`;
    s += `<text x="${cx}" y="${v < 0 ? top + h + 13 : top - 5}" text-anchor="middle" font-size="11.5" fill="var(--ink-2)" class="num">${v < 0 ? '−' : ''}${axisLabel(Math.abs(v))}</text>`;
    s += `<text class="axis" x="${cx}" y="${H - 6}" text-anchor="middle">${esc(c)}</text>`;
    s += `<rect class="hit" data-i="${i}" x="${m.l + band * i}" y="${m.t}" width="${band}" height="${H - m.t - m.b}" fill="transparent"/>`;
  });
  s += '</svg>';
  el.innerHTML = s;
  el.querySelectorAll('.hit').forEach((r) => {
    r.addEventListener('pointermove', (ev) => { const i = +r.dataset.i; tip.show(`<b>${esc(opts.cats[i])}</b><div class="tt-row"><span>净收益</span><b class="num">${vals[i] < 0 ? '−' : ''}${fmt.money(Math.abs(vals[i]))} ${esc(opts.unit || '')}</b></div>`, ev.clientX, ev.clientY); });
    r.addEventListener('pointerleave', () => tip.hide());
  });
}
