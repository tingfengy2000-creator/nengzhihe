/* 能见度 · 入口：路由、主题、数据模式标识、依据抽屉。 */
import { $, $$, icon, store, toast } from './util.js';
import { app, on, emit } from './state.js';
import * as data from './data.js';
import * as home from './home.js';
import * as tool from './tool.js';
import * as samples from './samples.js';
import * as plans from './plans.js';
import * as about from './about.js';
import * as demo from './demo.js';

const VIEWS = { home, tool, samples, plans, about };

/* ---------- 主题：自动 → 浅色 → 深色 ---------- */
const THEMES = ['auto', 'light', 'dark'];
const THEME_LABEL = { auto: '主题：跟随系统', light: '主题：浅色', dark: '主题：深色' };
function applyTheme(t) {
  if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
  else document.documentElement.removeAttribute('data-theme');
  const b = $('#themeBtn');
  b.innerHTML = icon(t === 'dark' ? 'moon' : t === 'light' ? 'sun' : 'auto');
  b.setAttribute('aria-label', `${THEME_LABEL[t]}，点击切换`);
  b.title = THEME_LABEL[t];
  emit('theme', t);
}
let theme = store.get('njd.theme', 'auto');
if (!THEMES.includes(theme)) theme = 'auto';
applyTheme(theme);
$('#themeBtn').addEventListener('click', () => {
  theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
  store.set('njd.theme', theme); applyTheme(theme); toast(THEME_LABEL[theme]);
});
if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => emit('theme', theme));

/* ---------- 移动端菜单 ---------- */
const menuBtn = $('#menuBtn'), mobileMenu = $('#mobileMenu');
menuBtn.innerHTML = icon('menu');
menuBtn.addEventListener('click', () => {
  const on = !mobileMenu.classList.contains('on');
  mobileMenu.classList.toggle('on', on); menuBtn.setAttribute('aria-expanded', String(on));
});
mobileMenu.addEventListener('click', (e) => { if (e.target.closest('a')) { mobileMenu.classList.remove('on'); menuBtn.setAttribute('aria-expanded', 'false'); } });

/* ---------- 依据抽屉 ---------- */
export function openDrawer(title, html) {
  $('#drawerTitle').textContent = title;
  $('#drawerBody').innerHTML = html;
  $('#drawer').classList.add('on'); $('#drawer').setAttribute('aria-hidden', 'false');
  $('#scrim').classList.add('on');
  openDrawer.last = document.activeElement;
  setTimeout(() => $('#drawer [data-action="close-drawer"]').focus(), 50);
}
function closeDrawer() {
  $('#drawer').classList.remove('on'); $('#drawer').setAttribute('aria-hidden', 'true'); $('#scrim').classList.remove('on');
  if (openDrawer.last && openDrawer.last.focus) openDrawer.last.focus();
}
$('#drawer [data-action="close-drawer"]').innerHTML = icon('close');
$('#scrim').addEventListener('click', closeDrawer);
document.addEventListener('click', (e) => { if (e.target.closest('[data-action="close-drawer"]')) closeDrawer(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && $('#drawer').classList.contains('on')) closeDrawer(); });
on('drawer', ({ title, html }) => openDrawer(title, html));

/* ---------- 数据模式标识 ---------- */
function renderMode() {
  const badge = $('#modeBadge'), text = $('#modeText'), banner = $('#modeBanner');
  badge.dataset.mode = app.mode;
  if (app.mode === 'live') { text.innerHTML = '实时计算<span class="long"> · 本机服务</span>'; badge.title = '已连接本机计算服务：结果由后端实时计算'; banner.hidden = true; }
  else if (app.mode === 'sample') {
    text.innerHTML = '示例数据<span class="long"> · 未连接计算服务</span>'; badge.title = '未连接计算服务，只能查看示例回放';
    banner.hidden = false;
    banner.innerHTML = `<div class="container">${icon('info')}<span><b>当前未连接计算服务，只能查看示例。</b>页面数字来自随仓库保存的回放文件。要实时计算，请在仓库根目录运行 <code>python -m operation_planning.run_server</code> 后打开 <code>http://127.0.0.1:18765/</code>。</span><button class="btn sm" type="button" data-action="reprobe">重新连接</button></div>`;
  } else { text.textContent = '正在连接计算服务'; banner.hidden = true; }
}
on('mode', renderMode);
document.addEventListener('click', async (e) => {
  if (e.target.closest('[data-action="reprobe"]')) { await data.probe(); toast(app.mode === 'live' ? '已连接本机计算服务' : '仍未连接计算服务'); }
  if (e.target.closest('[data-action="demo"]')) demo.start();
});

/* ---------- 路由 ---------- */
let current = null;
function parse() {
  const h = (location.hash || '#/').replace(/^#\/?/, '');
  const [name, ...rest] = h.split('/');
  return { name: VIEWS[name] ? name : (name === '' ? 'home' : 'home'), args: rest };
}
function route() {
  const { name, args } = parse();
  $$('[data-view]').forEach((v) => { v.hidden = v.dataset.view !== name; });
  $$('[data-nav]').forEach((a) => { if (a.dataset.nav === name) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  const changed = current !== name;
  if (current && current !== name && VIEWS[current].leave) VIEWS[current].leave();
  current = name;
  const el = $(`#view-${name}`);
  if (changed) { el.classList.remove('view'); void el.offsetWidth; el.classList.add('view'); }
  VIEWS[name].show(el, args, { changed });
  if (changed) window.scrollTo({ top: 0, behavior: 'auto' });
}
window.addEventListener('hashchange', route);
export function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }
on('go', go);

renderMode();
route();
data.probe();
