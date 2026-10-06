/* 能智核 · 图表（手写 SVG，无外部依赖）
 *
 * 只做显示：逐月合计、日历格、典型日等都是把已有逐时序列按时间分组显示，
 * 不重新计算年度指标、成本或推荐。年度数字一律直接读取 report。
 */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const nf0 = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 });

  function el(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    for (const k in attrs || {}) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
  }

  /* ---------- 提示浮层 ---------- */
  const tip = {
    node: null,
    show(html, evt) {
      this.node = this.node || document.getElementById('tooltip');
      if (!this.node) return;
      this.node.innerHTML = html;
      this.node.classList.add('is-on');
      this.move(evt);
    },
    move(evt) {
      if (!this.node || !evt) return;
      const pad = 14, w = this.node.offsetWidth, h = this.node.offsetHeight;
      let x = evt.clientX + pad, y = evt.clientY + pad;
      if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
      if (y + h > window.innerHeight - 8) y = evt.clientY - h - pad;
      this.node.style.left = `${Math.max(8, x)}px`;
      this.node.style.top = `${Math.max(8, y)}px`;
    },
    hide() { if (this.node) this.node.classList.remove('is-on'); }
  };

  function bindTip(target, htmlFn) {
    target.addEventListener('pointerenter', (e) => tip.show(htmlFn(), e));
    target.addEventListener('pointermove', (e) => tip.move(e));
    target.addEventListener('pointerleave', () => tip.hide());
  }

  /* ---------- 分组工具（仅显示用途） ---------- */
  function monthOf(ts) { return Number(String(ts).slice(5, 7)); }
  function sumByMonth(timestamps, values) {
    const out = new Array(12).fill(0);
    for (let i = 0; i < timestamps.length; i++) {
      const v = Number(values[i]);
      if (Number.isFinite(v)) out[monthOf(timestamps[i]) - 1] += v;
    }
    return out;
  }
  function niceStep(v) {
    if (!(v > 0)) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    const n = v / p;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
  }
  /** 刻度：返回 { max, step, ticks }，刻度值为整齐的 1/2/5 倍数。 */
  function niceScale(v, count = 4) {
    const step = niceStep((v > 0 ? v : 1) / count);
    const ticks = Math.max(1, Math.ceil((v > 0 ? v : 1) / step));
    return { max: step * ticks, step, ticks };
  }
  const niceMax = (v) => niceScale(v).max;
  /** 让 SVG 的坐标宽度跟随容器宽度，文字保持实际像素大小。 */
  function widthOf(container, fallback) {
    const w = Math.round(container.getBoundingClientRect().width);
    return w > 200 ? w : fallback;
  }

  /* ---------- 逐月柱状图 ---------- */
  function monthlyBars(container, opts) {
    container.innerHTML = '';
    const months = sumByMonth(opts.timestamps, opts.values);
    const W = widthOf(container, 720), H = 260, m = { t: 20, r: 8, b: 28, l: 48 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const sc = niceScale(Math.max(...months)), max = sc.max;
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-label': opts.ariaLabel || '逐月柱状图' }, container);
    const g = el('g', { transform: `translate(${m.l},${m.t})` }, svg);
    const ticks = sc.ticks;
    for (let i = 0; i <= ticks; i++) {
      const y = ih - (ih * i) / ticks;
      el('line', { x1: 0, x2: iw, y1: y, y2: y, class: i === 0 ? 'baseline' : '', stroke: i === 0 ? 'var(--line-strong)' : 'var(--line)' }, g);
      const t = el('text', { x: -8, y: y + 4, 'text-anchor': 'end' }, g); t.textContent = nf0.format((max * i) / ticks);
    }
    const bw = iw / 12, barW = Math.min(36, bw - 10);
    const peak = months.indexOf(Math.max(...months));
    months.forEach((v, i) => {
      const h = (v / max) * ih, x = i * bw + (bw - barW) / 2, y = ih - h;
      const r = Math.min(4, h / 2, barW / 2);
      const d = h <= 0 ? '' : `M${x},${ih} V${y + r} Q${x},${y} ${x + r},${y} H${x + barW - r} Q${x + barW},${y} ${x + barW},${y + r} V${ih} Z`;
      if (d) el('path', { d, fill: opts.color || 'var(--brand)' }, g);
      const hit = el('rect', { x: i * bw, y: 0, width: bw, height: ih, fill: 'transparent' }, g);
      bindTip(hit, () => `<b>${i + 1} 月</b><div class="tt-row"><span>${opts.label || '数值'}</span><span>${nf1.format(v)} ${opts.unit || ''}</span></div>`);
      const lab = el('text', { x: i * bw + bw / 2, y: ih + 18, 'text-anchor': 'middle' }, g); lab.textContent = W < 560 ? `${i + 1}` : `${i + 1}月`;
      if (i === peak && v > 0) {
        const vl = el('text', { x: x + barW / 2, y: y - 6, 'text-anchor': 'middle', style: 'fill:var(--ink-2);font-weight:600' }, g);
        vl.textContent = nf0.format(v);
      }
    });
    return { months };
  }


  /* ---------- 能源日历热力图（canvas，横轴日期、纵轴小时） ---------- */
  const RAMPS = {
    load: ['#EEF6F5', '#0A524E'],
    gen: ['#FFF6E5', '#8A5A00']
  };
  function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
  function mix(a, b, t) { const A = hexToRgb(a), B = hexToRgb(b); return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(',')})`; }
  function cssVar(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  /** 把逐时序列按“日期 × 小时”排成格子；只做位置排列，不改数值。 */
  function gridOf(h) {
    const days = [], index = new Map();
    for (let i = 0; i < h.timestamps.length; i++) {
      const ts = String(h.timestamps[i]); const d = ts.slice(0, 10); const hr = Number(ts.slice(11, 13));
      if (!index.has(d)) { index.set(d, days.length); days.push({ date: d, idx: new Array(24).fill(-1) }); }
      days[index.get(d)].idx[hr] = i;
    }
    return days;
  }

  function heatmap(container, h, view) {
    container.innerHTML = '';
    const days = gridOf(h);
    const cw = widthOf(container, 900);
    const ml = 34, mt = 4, mb = 24, mr = 4;
    const minCell = 2;
    const cellW = Math.max(minCell, Math.floor((cw - ml - mr) / days.length * 100) / 100);
    const cellH = 10;
    const W = Math.ceil(ml + mr + cellW * days.length), H = mt + mb + cellH * 24;
    const wrap = document.createElement('div'); wrap.className = 'chart-scroll';
    const cv = document.createElement('canvas');
    const dpr = window.devicePixelRatio || 1;
    cv.width = W * dpr; cv.height = H * dpr; cv.style.width = `${W}px`; cv.style.height = `${H}px`;
    cv.setAttribute('role', 'img');
    cv.setAttribute('aria-label', view === 'match' ? '逐小时发电去向日历图' : view === 'gen' ? '逐小时发电量日历图' : '逐小时空调用电日历图');
    wrap.appendChild(cv); container.appendChild(wrap);
    const ctx = cv.getContext('2d'); ctx.scale(dpr, dpr);
    const empty = '#F1F3F5';
    const val = (i, key) => (i < 0 ? 0 : Number(h[key][i]) || 0);
    const genAt = (i) => val(i, 'pv') + val(i, 'wind');   // 仅用于着色深浅
    let max = 0;
    for (let i = 0; i < h.timestamps.length; i++) max = Math.max(max, view === 'gen' ? genAt(i) : Number(h.load[i]) || 0);
    const colExp = cssVar('--c-wind', '#2F80C9'), colSelf = cssVar('--c-self', '#0E9384'), colWaste = cssVar('--c-waste', '#D4760A'), colImp = cssVar('--c-import', '#6B5FB5');
    function colorOf(i) {
      if (i < 0) return '#FFFFFF';
      if (view === 'load') { const v = val(i, 'load'); return v > 0 ? mix(RAMPS.load[0], RAMPS.load[1], Math.sqrt(v / max)) : empty; }
      if (view === 'gen') { const v = genAt(i); return v > 0 ? mix(RAMPS.gen[0], RAMPS.gen[1], Math.sqrt(v / max)) : empty; }
      const s = val(i, 'self'), w = val(i, 'curtail'), m = val(i, 'imp');
      if (s <= 0 && w <= 0 && m <= 0) return val(i, 'exp') > 0 ? colExp : empty;
      if (w >= s && w >= m) return colWaste;
      if (s >= m) return colSelf;
      return colImp;
    }
    days.forEach((d, x) => {
      for (let hr = 0; hr < 24; hr++) {
        ctx.fillStyle = colorOf(d.idx[hr]);
        ctx.fillRect(ml + x * cellW, mt + hr * cellH, Math.max(1, cellW - (cellW >= 3 ? 0.5 : 0)), cellH - 1);
      }
    });
    // 坐标
    ctx.fillStyle = '#6B7480'; ctx.font = '11px ' + cssVar('--font', 'sans-serif');
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    [0, 6, 12, 18, 23].forEach((hr) => ctx.fillText(`${hr}时`, ml - 6, mt + hr * cellH + cellH / 2));
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    days.forEach((d, x) => { if (d.date.slice(8, 10) === '01') { ctx.fillText(`${Number(d.date.slice(5, 7))}月`, ml + x * cellW + 1, H - 6); } });

    const fmtV = (v) => `${nf2.format(v)} kWh`;
    cv.addEventListener('pointermove', (e) => {
      const r = cv.getBoundingClientRect();
      const x = Math.floor((e.clientX - r.left - ml) / cellW), hr = Math.floor((e.clientY - r.top - mt) / cellH);
      if (x < 0 || x >= days.length || hr < 0 || hr > 23) { tip.hide(); return; }
      const i = days[x].idx[hr]; if (i < 0) { tip.hide(); return; }
      const row = (c, k, v) => `<div class="tt-row"><span><i style="background:${c}"></i> ${k}</span><span>${fmtV(v)}</span></div>`;
      tip.show(`<b>${days[x].date} ${String(hr).padStart(2, '0')}:00–${String(hr + 1).padStart(2, '0')}:00</b>
        ${row('#1B1F24', '空调用电', val(i, 'load'))}${row(cssVar('--c-pv', '#C98500'), '光伏发电', val(i, 'pv'))}${row(cssVar('--c-wind', '#2F80C9'), '风机发电', val(i, 'wind'))}
        ${row(colSelf, '当时用上', val(i, 'self'))}${row(colWaste, '浪费', val(i, 'curtail'))}${val(i, 'exp') > 0 ? row(colExp, '卖给电网', val(i, 'exp')) : ''}${row(colImp, '从电网买', val(i, 'imp'))}`, e);
    });
    cv.addEventListener('pointerleave', () => tip.hide());
    return { days: days.length };
  }

  /* ---------- 典型日曲线 ---------- */
  function dayList(h) { return gridOf(h).map((d) => d.date); }
  /** 返回空调用电最多的一天（只用于默认选中日期，标注为“用电最多的一天”）。 */
  function peakLoadDay(h) {
    let best = null, bestV = -1;
    for (const d of gridOf(h)) {
      let v = 0; for (const i of d.idx) if (i >= 0) v += Number(h.load[i]) || 0;
      if (v > bestV) { bestV = v; best = d.date; }
    }
    return best;
  }

  function dayCurve(container, h, date) {
    container.innerHTML = '';
    const day = gridOf(h).find((d) => d.date === date);
    if (!day) { container.innerHTML = '<p class="small subtle">该日期没有数据。</p>'; return; }
    const W = widthOf(container, 720), H = 260, m = { t: 16, r: 12, b: 28, l: 48 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const series = [
      { key: 'load', name: '空调用电', color: cssVar('--c-load', '#1B1F24') },
      { key: 'pv', name: '光伏发电', color: cssVar('--c-pv', '#C98500') },
      { key: 'wind', name: '风机发电', color: cssVar('--c-wind', '#2F80C9') }
    ].map((s) => ({ ...s, values: day.idx.map((i) => (i < 0 ? null : Number(h[s.key][i]) || 0)) }));
    const sc = niceScale(Math.max(0.001, ...series.flatMap((s) => s.values.filter((v) => v != null))));
    const x = (hr) => (hr + 0.5) * (iw / 24), y = (v) => ih - (v / sc.max) * ih;
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-label': `${date} 逐小时用电与发电曲线` }, container);
    const g = el('g', { transform: `translate(${m.l},${m.t})` }, svg);
    for (let i = 0; i <= sc.ticks; i++) {
      const yy = ih - (ih * i) / sc.ticks;
      el('line', { x1: 0, x2: iw, y1: yy, y2: yy, stroke: i === 0 ? 'var(--line-strong)' : 'var(--line)' }, g);
      const t = el('text', { x: -8, y: yy + 4, 'text-anchor': 'end' }, g); t.textContent = nf2.format(sc.step * i);
    }
    [0, 6, 12, 18, 23].forEach((hr) => { const t = el('text', { x: x(hr), y: ih + 18, 'text-anchor': 'middle' }, g); t.textContent = `${hr}时`; });
    // 光伏面积（淡色）+ 三条 2px 曲线
    const pv = series[1];
    const area = `M${x(0)},${ih} ` + pv.values.map((v, i) => `L${x(i)},${y(v || 0)}`).join(' ') + ` L${x(23)},${ih} Z`;
    el('path', { d: area, fill: pv.color, opacity: 0.12 }, g);
    series.forEach((s) => {
      const d = s.values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v || 0)}`).join(' ');
      el('path', { d, fill: 'none', stroke: s.color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', 'stroke-dasharray': s.key === 'wind' ? '5 4' : null }, g);
    });
    // 悬停：竖线 + 提示
    const cross = el('line', { y1: 0, y2: ih, stroke: 'var(--ink-3)', 'stroke-width': 1, opacity: 0 }, g);
    const dots = series.map((s) => el('circle', { r: 4, fill: s.color, stroke: '#fff', 'stroke-width': 2, opacity: 0 }, g));
    const hit = el('rect', { x: 0, y: 0, width: iw, height: ih, fill: 'transparent' }, g);
    hit.addEventListener('pointermove', (e) => {
      const r = hit.getBoundingClientRect();
      const hr = Math.max(0, Math.min(23, Math.floor((e.clientX - r.left) / (r.width / 24))));
      cross.setAttribute('x1', x(hr)); cross.setAttribute('x2', x(hr)); cross.setAttribute('opacity', 1);
      series.forEach((s, k) => { dots[k].setAttribute('cx', x(hr)); dots[k].setAttribute('cy', y(s.values[hr] || 0)); dots[k].setAttribute('opacity', 1); });
      tip.show(`<b>${date} ${String(hr).padStart(2, '0')}:00–${String(hr + 1).padStart(2, '0')}:00</b>` + series.map((s) => `<div class="tt-row"><span><i style="background:${s.color}"></i> ${s.name}</span><span>${nf2.format(s.values[hr] || 0)} kWh</span></div>`).join(''), e);
    });
    hit.addEventListener('pointerleave', () => { tip.hide(); cross.setAttribute('opacity', 0); dots.forEach((d) => d.setAttribute('opacity', 0)); });
  }

  /* ---------- 堆叠流向条 ---------- */
  /** parts: [{ name, value, color }]；宽度按各部分占显示合计的比例，数值原样显示。 */
  function flowBar(parts, unit) {
    const shown = parts.filter((p) => Number.isFinite(p.value) && p.value > 0);
    const total = shown.reduce((a, p) => a + p.value, 0);
    const bar = document.createElement('div'); bar.className = 'flow-bar';
    shown.forEach((p) => {
      const seg = document.createElement('div');
      seg.style.width = `${(p.value / total) * 100}%`; seg.style.background = p.color;
      bindTip(seg, () => `<b>${p.name}</b><div class="tt-row"><span>数量</span><span>${nf0.format(p.value)} ${unit}</span></div>`);
      bar.appendChild(seg);
    });
    const keys = document.createElement('div'); keys.className = 'flow-keys';
    keys.innerHTML = parts.map((p) => `<span><i style="background:${p.color}"></i>${p.name} ${Number.isFinite(p.value) ? nf0.format(p.value) + ' ' + unit : '样例未保存'}</span>`).join('');
    const frag = document.createDocumentFragment(); frag.appendChild(bar); frag.appendChild(keys);
    return frag;
  }

  window.NZH = window.NZH || {};
  window.NZH.charts = { el, tip, bindTip, sumByMonth, niceMax, niceScale, widthOf, monthlyBars, heatmap, dayCurve, dayList, peakLoadDay, flowBar, nf0, nf1, nf2 };
})();
