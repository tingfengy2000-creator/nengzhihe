/* 能见度 · 导出与“我的方案”
 * 导出只从当前显示的结果生成（视图模型与已读取的原始结果），不为导出再次调用计算。
 * 条件已修改（结果失效）时，导出与保存全部禁用（由调用方和这里双重检查）。
 * “我的方案”只保存在本机浏览器 localStorage（键 njd.plans.v1），读写失败时页面照常可用。 */
import { esc, fmt, isNum, download, toast, store } from './util.js';
import { SCEN } from './data.js';
import * as story from './story.js';
import { reasonsOf, boundariesOf } from './results.js';

export const PLAN_KEY = 'njd.plans.v1';
const stamp = () => new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '');
const csvCell = (v) => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
const csv = (rows) => '﻿' + rows.map((r) => r.map(csvCell).join(',')).join('\n');
const base = (vm) => `能见度_${vm.kind === 'live' ? '实时' : vm.caseId}_${stamp()}`;

function summaryRows(vm) {
  const head = ['方案', '技术名', '状态', '状态说明/排除原因', '计价状态', '光伏容量_kWp', '风机台数', '10年总花费_折现_元', '比只用电网_元(负=多花,正=省下)', '净现金流现值_元(非利润)', '年发电_kWh', '当时用上_kWh', '浪费_kWh', '从电网买_kWh', '卖给电网_kWh', '空调用电自发电覆盖率', '第1年减碳_kgCO2', '研究期累计减碳_tCO2', '每吨减碳成本_元(负=省钱)', '粗算_比只用电网_元', '是否推荐'];
  return [head].concat(vm.candidates.map((c) => [c.name, c.id, c.admission.label, c.admission.status === 'equivalent' && c.equivalentTo ? `与${SCEN[c.equivalentTo] ? SCEN[c.equivalentTo].name : c.equivalentTo}相同` : c.reasons.join('；'), c.economicsStatus, c.pvKwp, c.windCount, c.totalCost, c.incremental, c.npv, c.gen, c.selfUse, c.curtail, c.gridImport, c.gridExport, c.coverage, c.carbon && c.carbon.avoidedKgY1, c.carbon && c.carbon.avoidedTStudy, c.carbon && c.carbon.costPerT, c.rough && c.rough.incremental, c.isRec ? '推荐' : '']));
}

function hourlyCsv(vm) {
  const H = vm.hourly || {};
  const sets = vm.kind === 'live' && H.byScenario ? Object.entries(H.byScenario) : [['recommended', H.recommended], ['combo', H.combo]].filter((x) => x[1]);
  if (!sets.length) return null;
  const ts = sets[0][1].ts;
  const head = ['时间', '空调用电_kWh'];
  const cols = [ts, sets[0][1].load];
  for (const [, h] of sets) {
    const n = SCEN[h.scenarioId] ? SCEN[h.scenarioId].name : h.scenarioId;
    head.push(`${n}_光伏发电_kWh`, `${n}_风机发电_kWh`, `${n}_当时用上_kWh`, `${n}_从电网买_kWh`, `${n}_浪费_kWh`);
    cols.push(h.pv, h.wind, h.self, h.imp, h.curt);
  }
  return csv([head].concat(ts.map((_, i) => cols.map((c) => c[i]))));
}

export function briefHtml(T) {
  const vm = T.result.vm, rec = vm.byId[(vm.rec || {}).scenarioId];
  const y = story.yearsText(vm.studyYears);
  const conds = [['地点与天气', story.placeText(vm)], ['房间', story.roomText(vm)], ['使用时段', story.scheduleText(vm.request)], ['屋顶面积', isNum(vm.req.roofM2) ? `${vm.req.roofM2} ㎡` : null],
    ['光伏容量', vm.req.autoCapacity ? '自动比选' : vm.req.fixedCapacity != null ? `固定 ${vm.req.fixedCapacity} kWp` : vm.req.capacities ? vm.req.capacities.join('、') + ' kWp' : null],
    ['小风机', vm.req.windCount != null ? `${vm.req.windCount} 台` : null], ['电价', vm.tariff ? `${vm.tariff.title || vm.tariff.id}${vm.tariff.provisional ? '（待核验）' : ''}` : isNum(vm.req.importPrice) ? `固定 ${vm.req.importPrice} 元/kWh` : null],
    ['预算', isNum(vm.req.budget) ? `${fmt.money(vm.req.budget)} 元` : '未设上限'], ['是否卖电', vm.req.allowExport ? '允许' : '不卖电']].filter((r) => r[1]);
  const opt = vm.candidates.map((c) => `<tr${c.isRec ? ' class="rec"' : ''}><td>${esc(c.name)}${c.isRec ? '（推荐）' : ''}</td><td>${esc(c.admission.label)}${c.reasons.length ? '：' + esc(c.reasons.join('；')) : ''}</td><td class="r">${c.totalCost == null ? '—' : fmt.money(c.totalCost)}</td><td class="r">${c.id === 'S0_grid' ? '基线' : esc(fmt.delta(c.incremental).short)}</td><td class="r">${fmt.kwh(c.gen)}</td><td class="r">${fmt.kwh(c.selfUse)}</td><td class="r">${fmt.kwh(c.curtail)}</td><td class="r">${fmt.kwh(c.carbon && c.carbon.avoidedKgY1)}</td></tr>`).join('');
  const sweep = vm.sweep.map((r) => `<tr${isNum(vm.recommendedKwp) && Math.abs(r.kwp - vm.recommendedKwp) < 1e-9 ? ' class="rec"' : ''}><td>${fmt.d(r.kwp, 2)} kWp</td><td>${esc(r.admission.label)}</td><td class="r">${r.admission.status === 'excluded' || r.admission.status === 'unknown' ? '不参与比较' : esc(fmt.delta(r.incremental).short)}</td><td class="r">${fmt.pct(r.selfUseRate, 1)}</td><td class="r">${esc(fmt.perTon(r.costPerT).text)}</td></tr>`).join('');
  const p = vm.provenance || {};
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>能见度决策简报</title><style>
  body{font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif;color:#111716;max-width:880px;margin:32px auto;padding:0 20px}
  h1{font-size:24px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 8px;border-bottom:1px solid #ddd;padding-bottom:4px}
  .k{color:#0E7C73;font-weight:700;letter-spacing:.1em;font-size:12px}.big{font-size:20px;font-weight:800;margin:10px 0}
  table{border-collapse:collapse;width:100%;font-size:12.5px}td,th{border-bottom:1px solid #e3e7e6;padding:5px 6px;text-align:left}th{background:#f2f4f3}.r{text-align:right}tr.rec td{background:#e6f3f1;font-weight:600}
  .note{color:#5F6B69;font-size:12px}.warn{background:#FFF3DC;padding:8px 10px;border-radius:6px}ul{padding-left:18px}
  @media print{body{margin:0;max-width:none}h2{break-after:avoid}table{break-inside:auto}tr{break-inside:avoid}}
  </style></head><body>
  <p class="k">能见度 · 低碳改造决策简报</p>
  <h1>${esc(story.headline(vm))}</h1>
  <p class="note">来源：${esc(vm.kind === 'live' ? `本机实时计算（${fmt.date(vm.computedAt)}）` : `示例回放 replay_cases_v6.json · ${vm.label}`)}；生成时间 ${esc(fmt.date(Date.now()))}。简报只引用结果中的数值。</p>
  ${rec ? `<p class="big">${y}总花费约 ${fmt.money(rec.totalCost)} 元（折现）${rec.id !== 'S0_grid' ? `，${esc(fmt.delta(rec.incremental).text)}` : ''}</p>` : ''}
  <p>推荐状态：${esc((vm.rec || {}).label || '')}——${esc((vm.rec || {}).note || '')}</p>
  ${vm.service && vm.service.status === 'service_gap' ? `<p class="warn">空调有缺口：全年 ${fmt.int(vm.service.shortfallHours)} 小时冷量不足，结论不代表同等舒适度下的最优投资。</p>` : `<p>空调服务状态：${esc((vm.service || {}).label || '')}（${esc((vm.service || {}).note || '')}）</p>`}
  <h2>条件</h2><table>${conds.map(([k, v]) => `<tr><th style="width:28%">${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')}<tr><th>空调一年用电（项目合计）</th><td>${fmt.kwh(vm.load.annualKwh)} kWh</td></tr></table>
  <h2>推荐理由</h2><ol>${reasonsOf(vm).map((r) => `<li>${esc(r)}</li>`).join('')}</ol>
  <h2>四种供电方式（${y}总账）</h2><table><tr><th>方案</th><th>状态</th><th class="r">总花费（元）</th><th class="r">比只用电网</th><th class="r">年发电 kWh</th><th class="r">当时用上 kWh</th><th class="r">浪费 kWh</th><th class="r">第1年减碳 kg</th></tr>${opt}</table>
  <p class="note">负的“比只用电网”= 多花，正 = 省下；“条件不全”不是排除；总花费不含空调设备本身。</p>
  ${sweep ? `<h2>光伏容量比选</h2><table><tr><th>容量</th><th>状态</th><th class="r">比只用电网</th><th class="r">发电当时用上</th><th class="r">每吨减碳</th></tr>${sweep}</table><p class="note">${esc(story.basisPlain(vm))}</p>` : ''}
  <h2>减碳口径</h2><ul>${((vm.carbonContext || {}).scopeNotes || []).map((n) => `<li>${esc(n)}</li>`).join('')}</ul>
  <h2>适用边界</h2><ul>${boundariesOf(vm).map((b) => `<li>${esc(b)}</li>`).join('')}</ul>
  <h2>依据</h2><p class="note">${esc([p.kind, p.file, p.sourceCommit && `源码 ${p.sourceCommit}`, p.calculationVersion, p.weatherHash && `天气哈希 ${p.weatherHash}`].filter(Boolean).join(' · '))}</p>
  </body></html>`;
}

export function run(kind, T) {
  if (!T.result || T.stale) { toast('条件已修改，请先重新计算'); return; }
  const vm = T.result.vm;
  if (kind === 'brief') { download(`${base(vm)}_决策简报.html`, 'text/html;charset=utf-8', briefHtml(T)); toast('已生成决策简报'); return; }
  if (kind === 'print') {
    const f = document.createElement('iframe'); f.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0'; document.body.appendChild(f);
    f.srcdoc = briefHtml(T); f.onload = () => { try { f.contentWindow.focus(); f.contentWindow.print(); } catch (e) { toast('浏览器阻止了打印，请改用“决策简报”下载后打印'); } setTimeout(() => f.remove(), 60000); };
    return;
  }
  if (kind === 'summary') { download(`${base(vm)}_方案汇总.csv`, 'text/csv;charset=utf-8', csv(summaryRows(vm))); return; }
  if (kind === 'hourly') { const t = hourlyCsv(vm); if (!t) { toast('这份结果没有逐时数据'); return; } download(`${base(vm)}_逐时.csv`, 'text/csv;charset=utf-8', t); return; }
  if (kind === 'json') {
    const body = vm.kind === 'live'
      ? { exported_from: '能见度 前端（当前显示的实时结果）', computed_at: new Date(vm.computedAt).toISOString(), request: vm.request, report: T.result.raw || null }
      : { exported_from: '能见度 前端（当前显示的示例）', sample_file: 'docs/handoff/replay_viewer/replay_cases_v6.json', ui_note: '界面读取时省略了 weather.provenance.normalization 审计数组与 candidates[].hourly；完整原件见 sample_file。', case: T.result.raw || null };
    download(`${base(vm)}_完整结果.json`, 'application/json;charset=utf-8', JSON.stringify(body, null, 2)); return;
  }
}

/* ------------------------------------------------------------------ */
/* 我的方案                                                            */
/* ------------------------------------------------------------------ */
export const loadPlans = () => { const v = store.get(PLAN_KEY, []); return Array.isArray(v) ? v : []; };
export function savePlan(T) {
  if (!T.result || T.stale) { toast('条件已修改，请先重新计算'); return; }
  const vm = T.result.vm, rec = vm.byId[(vm.rec || {}).scenarioId];
  const plan = {
    id: `p${Date.now().toString(36)}`, savedAt: Date.now(), kind: vm.kind, caseId: vm.caseId, label: vm.label,
    source: vm.kind === 'live' ? `本机实时计算 · ${fmt.date(vm.computedAt)}` : `示例回放 replay_cases_v6.json · ${vm.label}`,
    form: T.result.form, request: vm.request,
    summary: {
      place: story.placeText(vm), room: story.roomText(vm), schedule: story.scheduleText(vm.request),
      annualKwh: vm.load.annualKwh, service: vm.service ? vm.service.label : null, serviceStatus: vm.service ? vm.service.status : null,
      headline: story.headline(vm), recStatus: (vm.rec || {}).label, recName: rec ? rec.name : null,
      recTotal: rec ? rec.totalCost : null, recIncremental: rec ? rec.incremental : null, recommendedKwp: vm.recommendedKwp, studyYears: vm.studyYears,
      options: vm.candidates.map((c) => ({ id: c.id, name: c.name, status: c.admission.label, total: c.totalCost, incremental: c.incremental, reasons: c.reasons })),
      tariff: vm.tariff ? `${vm.tariff.title || vm.tariff.id}${vm.tariff.provisional ? '（待核验）' : ''}` : null
    }
  };
  const list = loadPlans(); list.unshift(plan);
  if (!store.set(PLAN_KEY, list.slice(0, 50))) { toast('浏览器不允许本机保存（可能是隐私模式）'); return; }
  toast('已保存到“我的方案”（仅本机浏览器）');
}
