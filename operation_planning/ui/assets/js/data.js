/* 能见度 · 数据层（第 1 批外壳：只做后端探测；数据适配在第 2 批补齐）。 */
import { app, emit } from './state.js';

export async function probe() {
  try {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 3000);
    const res = await fetch('/api/operation/options', { cache: 'no-store', signal: ctl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error(String(res.status));
    app.options = await res.json(); app.mode = 'live';
  } catch (e) { app.mode = 'sample'; }
  emit('mode', app.mode);
  return app.mode;
}
