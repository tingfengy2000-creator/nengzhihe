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

  window.NZH = window.NZH || {};
  window.NZH.charts = { el, tip, bindTip, sumByMonth, niceMax, niceScale, widthOf, monthlyBars, nf0, nf1, nf2 };
})();
