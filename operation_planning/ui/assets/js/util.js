/* 能见度 · 通用工具：DOM、转义、图标、格式化、提示。
 * 格式化只做显示（千分位、取整、正负方向文字），不做任何业务计算。 */

export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
export const reduceMotion = () => !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);

/* ---------- 图标（线性，24 网格） ---------- */
const ICONS = {
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M7 7l10 10M17 7 7 17"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.3a2.5 2.5 0 1 1 3.4 2.4c-.7.3-1 .8-1 1.5v.4M12 17h.01"/>',
  equal: '<path d="M6 9.5h12M6 14.5h12"/>',
  warn: '<path d="M12 3.5 2.8 19.5h18.4L12 3.5z"/><path d="M12 10v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  star: '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9L12 3.5z"/>',
  play: '<path d="M8 5v14l11-7z" fill="currentColor" stroke="none"/>',
  pause: '<path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor" stroke="none"/>',
  prev: '<path d="M15 6l-6 6 6 6"/>',
  next: '<path d="M9 6l6 6-6 6"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  back: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
  auto: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17" /><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor" stroke="none"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  doc: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  save: '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4M8 20v-6h8v6"/>',
  calc: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h2M12 11h2M16 11h0M8 15h2M12 15h2M8 18h2M12 18h2M16 14v4"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/>',
  leaf: '<path d="M5 19c0-9 6-14 15-14 0 9-5 15-14 15"/><path d="M5 19c3-4 6-7 10-9"/>',
  battery: '<rect x="3" y="7" width="16" height="10" rx="2"/><path d="M21 10.5v3"/><path d="M7 10v4M10.5 10v4"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5z"/><path d="m3 13 9 5 9-5"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>'
};
export function icon(name, cls = '') {
  return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
}
export const LOGO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';

/* ---------- 格式化（仅显示） ---------- */
const nf0 = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });
const nfd = (d) => new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: d });
export const fmt = {
  int(v) { return isNum(v) ? nf0.format(Math.round(v)) : '—'; },
  money(v) { return isNum(v) ? nf0.format(Math.round(v)) : '—'; },
  kwh(v) { return isNum(v) ? (Math.abs(v) < 10 && v !== 0 ? nfd(1).format(v) : nf0.format(Math.round(v))) : '—'; },
  d(v, digits = 1) { return isNum(v) ? nfd(digits).format(v) : '—'; },
  fixed(v, digits = 2) { return isNum(v) ? v.toFixed(digits) : '—'; },
  /** 比率字段（0–1，由后端给出）显示为百分比。 */
  pct(v, digits = 0) { return isNum(v) ? `${nfd(digits).format(v * 100)}%` : '—'; },
  kwp(v) { return isNum(v) ? `${nfd(2).format(v)} kWp` : '—'; },
  /** 相对“只用电网”的增量现值：负数＝多花，正数＝省下。保留方向，不取绝对值后丢符号。 */
  delta(incr) {
    if (!isNum(incr)) return { dir: 'na', text: '暂无法比较', short: '暂无法比较' };
    const r = Math.round(incr);
    if (r === 0) return { dir: 'base', text: '与只用电网相同', short: '与基线相同' };
    if (r < 0) return { dir: 'more', text: `比只用电网多花 ${nf0.format(-r)} 元`, short: `多花 ${nf0.format(-r)} 元`, amount: nf0.format(-r) };
    return { dir: 'less', text: `比只用电网省下 ${nf0.format(r)} 元`, short: `省下 ${nf0.format(r)} 元`, amount: nf0.format(r) };
  },
  /** 每吨减碳成本：后端字段 cost_per_tco2_cny；负数表示该口径下省钱，不是碳交易收入。 */
  perTon(v) {
    if (!isNum(v)) return { text: '—', dir: 'na' };
    const r = Math.round(v);
    if (r < 0) return { text: `每减 1 吨省 ${nf0.format(-r)} 元`, dir: 'less' };
    if (r === 0) return { text: '每减 1 吨不多花', dir: 'base' };
    return { text: `每减 1 吨多花 ${nf0.format(r)} 元`, dir: 'more' };
  },
  ts(t) { return String(t || '').replace('T', ' '); },
  date(ms) { try { return new Date(ms).toLocaleString('zh-CN', { hour12: false }); } catch (e) { return String(ms); } },
  sha(s, n = 7) { return typeof s === 'string' && s ? s.slice(0, n) : '—'; }
};

/* ---------- 本机存储：读写失败时照常可用 ---------- */
export const store = {
  get(key, fallback = null) { try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch (e) { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch (e) { return false; } }
};

/* ---------- 提示 ---------- */
export function toast(msg) {
  const t = $('#toast'); if (!t) return;
  t.textContent = msg; t.classList.add('on');
  clearTimeout(toast._h); toast._h = setTimeout(() => t.classList.remove('on'), 2800);
}
export const tip = {
  show(html, x, y) {
    const t = $('#tooltip'); if (!t) return;
    t.innerHTML = html; t.classList.add('on');
    const w = t.offsetWidth, h = t.offsetHeight;
    let left = x + 14, top = y + 14;
    if (left + w > innerWidth - 8) left = Math.max(8, x - w - 14);
    if (top + h > innerHeight - 8) top = Math.max(8, y - h - 14);
    t.style.left = left + 'px'; t.style.top = top + 'px';
  },
  hide() { const t = $('#tooltip'); if (t) t.classList.remove('on'); }
};

/** 数字滚动到真实值（≤0.9 秒），只对已读取的结果做；减少动态效果时直接显示。 */
export function countUp(el, to, format) {
  if (!el || !isNum(to)) return;
  const show = (v) => { el.textContent = format(v); };
  if (reduceMotion()) { show(to); return; }
  const t0 = performance.now(), dur = 900;
  const step = (n) => {
    const p = Math.min(1, (n - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    show(p < 1 ? to * e : to);
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/** 进入视野时触发一次（不支持 IntersectionObserver 时立即触发）。 */
export function onVisible(el, fn, threshold = 0.2) {
  if (!el) return;
  if (!('IntersectionObserver' in window)) { fn(); return; }
  const io = new IntersectionObserver((es) => { es.forEach((e) => { if (e.isIntersecting) { io.disconnect(); fn(); } }); }, { threshold });
  io.observe(el);
}

/** 位移出现：只给视口以下的元素加 .pre，静止状态始终完整可读。 */
export function reveal(root = document) {
  if (reduceMotion() || !('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver((es) => {
    es.forEach((e) => { if (e.isIntersecting) { e.target.classList.remove('pre'); io.unobserve(e.target); } });
  }, { threshold: 0.12 });
  $$('.reveal', root).forEach((el) => {
    if (el.getBoundingClientRect().top > innerHeight) { el.classList.add('pre'); io.observe(el); }
  });
}

export function download(name, mime, text) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1500);
}

export function cssVar(name, el = document.documentElement) {
  return getComputedStyle(el).getPropertyValue(name).trim();
}
