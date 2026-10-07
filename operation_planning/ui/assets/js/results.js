/* 能见度 · 试算第 2–4 步（第 5 批完整实现；本批只显示结果概要）。 */
import { esc, fmt } from './util.js';
export function render(panel, step, T) {
  const v = T.result.vm;
  panel.innerHTML = `<div class="card"><h3>结果概要</h3><p>${esc(v.sourceLabel)} · 空调一年用电 ${fmt.kwh(v.load.annualKwh)} kWh · 推荐 ${esc((v.byId[(v.rec || {}).scenarioId] || {}).name || '—')}</p><p class="hint">第 ${step} 步的完整图表在下一批实现。</p></div>`;
}
