/* 能见度 · 全年能源日历（深色舞台）
 *
 * 横轴为日期、纵轴为一天 24 小时，每格一个小时。三种视图：
 *   load  空调用电（青色色阶）
 *   gen   光伏与风机发电（琥珀色阶；格子颜色按该小时光伏+风机发电量着色，仅用于显示）
 *   cat   发电时空调在用吗：比较该小时“用上 / 浪费 / 从电网买”三个后端数值，取最多的一项着色
 * 颜色深浅按全年第 99 百分位归一（仅用于显示），悬停显示该小时的原始数值。
 */
import { $, $$, esc, fmt, tip, reduceMotion, download } from './util.js';
import { WEEKDAYS } from './data.js';

const RAMP = { load: ['#12302C', '#5AD8CA'], gen: ['#2A2108', '#F2B33D'] };
const LEVELS = 8;

function mix(a, b, t) {
  const A = parseInt(a.slice(1), 16), B = parseInt(b.slice(1), 16);
  const r = Math.round((A >> 16) + ((B >> 16) - (A >> 16)) * t), g = Math.round(((A >> 8) & 255) + (((B >> 8) & 255) - ((A >> 8) & 255)) * t), bl = Math.round((A & 255) + ((B & 255) - (A & 255)) * t);
  return `rgb(${r},${g},${bl})`;
}
function p99(arr) {
  const pos = arr.filter((v) => v > 0).sort((a, b) => a - b);
  if (!pos.length) return 0;
  return pos[Math.min(pos.length - 1, Math.floor(pos.length * 0.99))];
}

export const KEYS = {
  load: '<span><i style="background:linear-gradient(90deg,#12302C,#5AD8CA);width:40px"></i>空调用电 少 → 多</span><span><i style="background:rgba(234,242,240,.08)"></i>不用电</span>',
  gen: '<span><i style="background:linear-gradient(90deg,#2A2108,#F2B33D);width:40px"></i>光伏与风机发电 少 → 多</span><span><i style="background:rgba(234,242,240,.08)"></i>不发电</span>',
  cat: '<span><i style="background:var(--stage-self)"></i>发的电当时用上</span><span><i style="background:var(--stage-waste)"></i>发了没人用（浪费）</span><span><i style="background:var(--stage-import)"></i>主要靠电网</span>'
};

export function createCalendar(root, { onView } = {}) {
  const canvas = $('canvas', root), keys = $('[data-cal-keys]', root);
  let H = null, view = 'cat', geo = {}, anim = null, days = 0, colors = { load: [], gen: [], cat: [] }, timer = null, userPicked = false, visible = false;
  const css = getComputedStyle(document.documentElement);
  const C = () => ({ empty: 'rgba(234,242,240,0.06)', self: css.getPropertyValue('--stage-self').trim() || '#1E9E8E', waste: css.getPropertyValue('--stage-waste').trim() || '#D17C26', imp: css.getPropertyValue('--stage-import').trim() || '#8A7FDB', ink: '#A3B4B0' });

  function prepare() {
    const n = H.ts.length; days = Math.ceil(n / 24);
    const c = C();
    const genArr = H.pv.map((v, i) => (v || 0) + (H.wind[i] || 0));      // 仅用于显示着色
    const mx = { load: p99(H.load), gen: p99(genArr) };
    const lv = (v, m) => (v > 1e-9 && m > 0 ? Math.min(LEVELS - 1, Math.floor((Math.min(v, m) / m) * (LEVELS - 1) + 0.5)) : -1);
    const rampLoad = Array.from({ length: LEVELS }, (_, k) => mix(RAMP.load[0], RAMP.load[1], k / (LEVELS - 1)));
    const rampGen = Array.from({ length: LEVELS }, (_, k) => mix(RAMP.gen[0], RAMP.gen[1], k / (LEVELS - 1)));
    colors = { load: new Array(n), gen: new Array(n), cat: new Array(n) };
    for (let i = 0; i < n; i++) {
      const a = lv(H.load[i] || 0, mx.load); colors.load[i] = a < 0 ? c.empty : rampLoad[Math.max(1, a)];
      const g = lv(genArr[i], mx.gen); colors.gen[i] = g < 0 ? c.empty : rampGen[Math.max(1, g)];
      const s = H.self[i] || 0, w = H.curt[i] || 0, m = H.imp[i] || 0;
      colors.cat[i] = (s <= 1e-9 && w <= 1e-9 && m <= 1e-9) ? c.empty : (s >= w && s >= m ? c.self : w >= m ? c.waste : c.imp);
    }
  }
  function layout() {
    const wrap = canvas.parentElement;
    const w = Math.max(720, wrap.clientWidth - 36), ml = 36, mb = 22, ch = 11;
    geo = { w, h: ch * 24 + mb, ml, cw: (w - ml) / Math.max(1, days), ch };
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(geo.h * dpr);
    canvas.style.width = w + 'px'; canvas.style.height = geo.h + 'px';
    canvas.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function draw(upto) {
    if (!H) return;
    const ctx = canvas.getContext('2d'), c = C(), col = colors[view];
    ctx.clearRect(0, 0, geo.w, geo.h);
    for (let d = 0; d < days; d++) {
      for (let h = 0; h < 24; h++) {
        const i = d * 24 + h; if (i >= H.ts.length) break;
        ctx.fillStyle = d < upto ? col[i] : c.empty;
        ctx.fillRect(geo.ml + d * geo.cw, h * geo.ch, Math.max(1, geo.cw - 0.6), geo.ch - 1.5);
      }
    }
    ctx.fillStyle = c.ink; ctx.font = '11px ' + getComputedStyle(document.body).fontFamily;
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    [0, 6, 12, 18, 23].forEach((h) => ctx.fillText(h + '时', geo.ml - 6, h * geo.ch + geo.ch / 2));
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    for (let d = 0; d < days; d++) { const t = H.ts[d * 24]; if (t && t.slice(8, 10) === '01') ctx.fillText(`${+t.slice(5, 7)}月`, geo.ml + d * geo.cw, geo.h - 6); }
  }
  function setView(v, animate) {
    view = v;
    keys.innerHTML = KEYS[v];
    $$('[data-cal-view]', root).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.calView === v)));
    if (onView) onView(v);
    if (anim) cancelAnimationFrame(anim);
    if (!animate || reduceMotion()) { draw(days); return; }
    const t0 = performance.now();
    const f = (n) => { const p = Math.min(1, (n - t0) / 1100), e = 1 - Math.pow(1 - p, 3); draw(Math.ceil(days * e)); if (p < 1) anim = requestAnimationFrame(f); };
    anim = requestAnimationFrame(f);
  }
  function startCycle() {
    if (reduceMotion() || timer || userPicked || !visible) return;
    const order = ['cat', 'load', 'gen'];
    timer = setInterval(() => { if (userPicked) { stopCycle(); return; } setView(order[(order.indexOf(view) + 1) % 3], true); }, 5200);
  }
  function stopCycle() { clearInterval(timer); timer = null; }

  $$('[data-cal-view]', root).forEach((b) => b.addEventListener('click', () => { userPicked = true; stopCycle(); setView(b.dataset.calView, true); }));
  canvas.addEventListener('pointermove', (ev) => {
    if (!H) return;
    const r = canvas.getBoundingClientRect();
    const d = Math.floor((ev.clientX - r.left - geo.ml) / geo.cw), h = Math.floor((ev.clientY - r.top) / geo.ch);
    if (d < 0 || d >= days || h < 0 || h > 23) { tip.hide(); return; }
    const i = d * 24 + h; if (i >= H.ts.length) { tip.hide(); return; }
    const t = H.ts[i]; const wd = WEEKDAYS[new Date(t.slice(0, 10) + 'T12:00:00').getDay()];
    tip.show(`<b>${esc(t.slice(0, 10))} ${wd} ${esc(t.slice(11, 16))}</b>
      <div class="tt-row"><span>空调用电</span><b class="num">${fmt.d(H.load[i], 3)}</b></div>
      <div class="tt-row"><span>光伏发电</span><b class="num">${fmt.d(H.pv[i], 3)}</b></div>
      <div class="tt-row"><span>风机发电</span><b class="num">${fmt.d(H.wind[i], 3)}</b></div>
      <div class="tt-row"><span><i style="background:var(--stage-self)"></i>当时用上</span><b class="num">${fmt.d(H.self[i], 3)}</b></div>
      <div class="tt-row"><span><i style="background:var(--stage-waste)"></i>浪费</span><b class="num">${fmt.d(H.curt[i], 3)}</b></div>
      <div class="tt-row"><span><i style="background:var(--stage-import)"></i>从电网买</span><b class="num">${fmt.d(H.imp[i], 3)}</b></div>
      <div class="tt-note">单位 kWh</div>`, ev.clientX, ev.clientY);
  });
  canvas.addEventListener('pointerleave', () => tip.hide());
  const io = 'IntersectionObserver' in window ? new IntersectionObserver((es) => {
    es.forEach((e) => { visible = e.isIntersecting; if (visible) { if (!userPicked && !timer) { setView(view, true); startCycle(); } } else stopCycle(); });
  }, { threshold: 0.35 }) : null;
  if (io) io.observe(canvas);
  let rz = null;
  window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (H) { layout(); draw(days); } }, 150); });

  return {
    set(hourly) { H = hourly; if (!H) return; prepare(); layout(); setView(view, false); },
    view: () => view,
    stop: stopCycle,
    exportCsv(name) {
      if (!H) return;
      const head = ['时间', '空调用电_kWh', '光伏发电_kWh', '风机发电_kWh', '当时用上_kWh', '从电网买_kWh', '浪费_kWh'];
      const rows = H.ts.map((t, i) => [t, H.load[i], H.pv[i], H.wind[i], H.self[i], H.imp[i], H.curt[i]].join(','));
      download(name, 'text/csv;charset=utf-8', '﻿' + head.join(',') + '\n' + rows.join('\n'));
    }
  };
}
