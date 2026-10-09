/* 能见度 · 开始试算（核心工具）
 *
 * 实时计算为主：用户填写条件 → 点击「计算」→ 同时发起典型周预览与全年异步任务；
 * 先显示预览（不含费用和推荐），全年任务进度只来自后端 progress；全年结果返回后切换到完整结果。
 * 示例只是起点：打开示例时显示回放结果（示例数据），同时把示例条件填进表单，改任何条件后可实时重算。
 * 条件一改，旧结果立即置灰并禁用导出与保存，直到重新计算。 */
import { $, $$, esc, fmt, isNum, icon, toast, reduceMotion } from './util.js';
import { app, on, emit } from './state.js';
import * as data from './data.js';
import { api, pollJob, ApiError } from './api.js';
import { applyAgentChanges, agentLabel, agentValueText, agentFromText, prefillCustom } from './form.js';
import * as agent from './agent.js';
import { FIELDS, FIELD, FIELD_PATH, blankForm, buildRequest, buildPreview, formFromRequest, quoteFieldsFrom, storageFieldsFrom, storageMetaFrom, parseAsk, validate, tariffList, tariffsForSite } from './form.js';
import { lineChart, barChart, dayTicks } from './charts.js';
import * as results from './results.js';
import { ADEQUACY_NOTE } from './results.js';

const T = {
  form: null, step: 1, errors: {},
  result: null,         // { vm, kind: 'live'|'sample', previews: {summer, winter}, form, at }
  stale: false,
  run: null,            // { phase, progress, events, status, elapsedMs, error, previews, ctrl }
  size: null,           // { res, formKey, error, loading }
  ask: null,
  pvSeason: 'summer', pvScen: 'S3_pv_wind'
};
export const getState = () => T;
let el = null, built = false;

const STEPS = [
  ['场景', '房间、空调、屋顶、电价'],
  ['空调用电', '一年用多少电、是否达标'],
  ['比较方案', '四种供电方式、碳、储能'],
  ['决策与导出', '推荐理由、边界、导出']
];

/* ------------------------------------------------------------------ */
/* 页面骨架                                                            */
/* ------------------------------------------------------------------ */
function skeleton() {
  return `
  <section class="tool-head"><div class="container">
    <p class="kicker">开始试算</p>
    <h1 class="h2">填上你的条件，实时算出全年每个小时。</h1>
    <p class="sub">城市、房间、空调、屋顶、报价、电价、预算都可以改。点击计算后先看典型周预览，全年结果由本机计算服务算完后自动替换。</p>
  </div></section>
  <nav class="stepper" aria-label="试算步骤"><div class="container">
    ${STEPS.map(([t, d], i) => `<a href="#/tool/${i + 1}" data-step-link="${i + 1}"><span class="n num">${i + 1}</span><span class="t"><b>${t}</b><span>${d}</span></span></a>`).join('')}
  </div></nav>
  <div class="resbar" data-resbar hidden></div>
  <div class="container tool-body">
    <div data-step-panel="1"></div>
    <div class="result-zone" data-result-zone>
      <div class="result-content">
        <div data-step-panel="2"></div><div data-step-panel="3"></div><div data-step-panel="4"></div>
      </div>
      <div class="stale-mask" role="alert">
        <div class="stale-card">
          ${icon('refresh')}
          <h3>条件已修改，结果已失效</h3>
          <p>下方结果对应修改前的条件，已停止导出和保存。请重新计算。</p>
          <div class="row" style="justify-content:center">
            <button class="btn primary" type="button" data-action="compute" data-needs-live>${icon('calc')}重新计算</button>
            <a class="btn" href="#/tool/1">查看条件</a>
          </div>
          <p class="xsmall muted" data-stale-note></p>
        </div>
      </div>
    </div>
  </div>`;
}

/* ------------------------------------------------------------------ */
/* 第 1 步：表单                                                       */
/* ------------------------------------------------------------------ */
function options(f) {
  const o = app.options;
  if (f.key === 'site_id') { const list = (o && o.cities) || []; const opts = list.map((c) => [c.site_id, c.name]); if (!opts.find((x) => x[0] === T.form.site_id)) opts.push([T.form.site_id, T.form.site_id]); return opts; }
  if (f.key === 'year') { const c = ((o && o.cities) || []).find((x) => x.site_id === T.form.site_id); const ys = c ? c.cached_years.map(String) : []; if (!ys.includes(T.form.year)) ys.push(T.form.year); return ys.map((y) => [y, `${y} 年`]); }
  if (f.key === 'equipment_id') { const list = (o && o.equipment_models) || []; const opts = list.map((e) => [e.equipment_id, `${e.brand} ${e.model} · 额定制冷 ${fmt.d(e.rated_cooling_kw, 2)} kW · 能效比 ${fmt.d(e.cop, 2)}`]); if (!opts.find((x) => x[0] === T.form.equipment_id)) opts.push([T.form.equipment_id, T.form.equipment_id]); return opts; }
  if (f.key === 'tariff_id') { const list = tariffList(o); const opts = list.map((t) => [t.tariff_id, `${t.area}（${t.effective_start}–${t.effective_end}）${t.verified ? '' : ' · 待核验'}`]); if (list.length) opts.push(['custom_user', '自定义分时电价（时段沿用所选官方档案，价格自填）']); if (T.form.tariff_id && !opts.find((x) => x[0] === T.form.tariff_id)) opts.push([T.form.tariff_id, T.form.tariff_id]); return opts; }
  if (f.key === 'factor_id') {
    const fs = (((o && o.carbon_factors) || {}).factors) || [];
    return [['', '按城市所在省份（默认，最新年份电力平均）']].concat(fs.map((x) => [x.factor_id, `${x.region} ${x.data_year} · ${x.basis} · ${fmt.d(x.value_kgco2_per_kwh, 4)} kgCO₂/kWh`]));
  }
  return f.options || [];
}

function fieldHtml(key, extraCls = '') {
  const f = FIELD[key], v = T.form[key], id = `f_${key}`, err = T.errors[key];
  const hint = f.hint ? `<span class="hint" id="${id}_h">${esc(f.hint)}</span>` : '';
  const errHtml = err ? `<span class="err" id="${id}_e">${icon('warn')}${esc(err)}</span>` : '';
  const desc = [f.hint ? `${id}_h` : '', err ? `${id}_e` : ''].filter(Boolean).join(' ');
  const aria = `${desc ? ` aria-describedby="${desc}"` : ''}${err ? ' aria-invalid="true"' : ''}`;
  let control;
  if (f.type === 'select') control = `<div class="control"><select id="${id}" data-field="${key}"${aria}>${options(f).map(([k, l]) => `<option value="${esc(k)}"${String(k) === String(v) ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></div>`;
  else if (f.type === 'seg') return `<div class="field ${extraCls}${err ? ' has-error' : ''}" data-wrap="${key}"><span class="label">${esc(f.label)}</span><div class="seg" role="radiogroup" aria-label="${esc(f.label)}">${f.options.map(([k, l]) => `<button type="button" role="radio" aria-checked="${k === v}" aria-pressed="${k === v}" data-seg="${key}" data-val="${k}">${esc(l)}</button>`).join('')}</div>${hint}${errHtml}</div>`;
  else if (f.type === 'check') return `<div class="field ${extraCls}" data-wrap="${key}"><label class="check"><input type="checkbox" id="${id}" data-field="${key}"${v ? ' checked' : ''}>${esc(f.label)}</label>${hint}</div>`;
  else control = `<div class="control${f.unit ? ' has-unit' : ''}"><input id="${id}" data-field="${key}" ${f.type === 'text' ? 'type="text"' : `type="text" inputmode="decimal"`} value="${esc(v)}" placeholder="${f.opt || f.q ? '使用默认' : ''}" autocomplete="off"${aria}>${f.unit ? `<span class="unit">${esc(f.unit)}</span>` : ''}</div>`;
  return `<div class="field ${extraCls}${err ? ' has-error' : ''}" data-wrap="${key}"><label for="${id}">${esc(f.label)}</label>${control}${hint}${errHtml}</div>`;
}
const fields = (keys) => keys.map((k) => fieldHtml(k)).join('');

function equipmentNote() {
  const e = ((app.options && app.options.equipment_models) || []).find((x) => x.equipment_id === T.form.equipment_id);
  if (!e) return '';
  return `<p class="hint">来源：${esc(e.source_type === 'public_energy_label' ? '公开能效标识' : '厂家公开页面')}（额定工况，不是逐时性能曲线；价格需用户报价）。</p>`;
}
/** 自定义分时电价：四个价格输入 + 只读的时段说明（读基准官方档案的 periods）。 */
function periodText(base) {
  if (!base) return '';
  const NAME = { valley: '谷', flat: '平', peak: '峰', super_peak: '尖峰' };
  const by = {};
  for (const p of base.periods || []) { (by[p.name] = by[p.name] || []).push(p); }
  const seg = (ps) => ps.map((p) => `${p.start}–${p.end}`).join('、');
  const parts = [];
  if (by.valley) parts.push(`谷 ${seg(by.valley)}`);
  if (by.peak) parts.push(`峰 ${seg(by.peak)}`);
  if (by.super_peak) { const p0 = by.super_peak[0]; parts.push(`尖峰 ${seg(by.super_peak)}（${p0.months ? p0.months.join('、') + ' 月' : ''}${p0.high_temp_outside_months ? `，以及其他月份日最高气温≥${p0.high_temp_threshold_c}℃的高温日` : ''}）`); }
  if (by.flat) parts.push('其余时段为平段');
  return parts.join('；');
}
function customTariffHtml() {
  const base = tariffList(app.options).find((t) => t.tariff_id === T.form.tou_base);
  return `<div class="custom-tou">
    <div class="grid-form">${fields(['tou_valley', 'tou_flat', 'tou_peak', 'tou_super'])}</div>
    <p class="hint">时段沿用${base ? `「${esc(base.area)}」` : '所选官方档案'}：${esc(periodText(base))}。时段不可改；四个价格默认填入该官方档案的价格，可按你的实际电价修改。结果中标注“用户自定义电价（未经官方核验）”。</p></div>`;
}

function tariffNote() {
  if (T.form.price_mode !== 'tariff') return '<p class="hint">固定电价是你输入的情景，不是当地官方电价。</p>';
  if (T.form.tariff_id === 'custom_user') return `<div class="tariff-note"><span class="tag warn">${icon('warn')}用户自定义电价（未经官方核验）</span></div>`;
  const t = tariffList(app.options).find((x) => x.tariff_id === T.form.tariff_id);
  if (!t) return '';
  return `<div class="tariff-note">${t.verified ? `<span class="tag ok">${icon('check')}已核验</span>` : `<span class="tag warn">${icon('warn')}待核验</span>`}
    <span>${esc(t.source_title || t.area)}${t.source_url ? ` · <a href="${esc(t.source_url)}" target="_blank" rel="noopener noreferrer">来源${icon('external')}</a>` : ''}</span>
    ${(t.notes || []).slice(0, 2).map((x) => `<span class="hint">${esc(x)}</span>`).join('')}</div>`;
}
function quotesFilled() { return FIELDS.filter((f) => f.q).some((f) => T.form[f.key] !== ''); }

function step1Html() {
  const live = app.mode === 'live';
  return `
  <div class="step1">
    <div class="quick card soft">
      <div class="quick-row">
        <span class="label">从示例开始</span>
        <div class="row" data-quick>${quickButtons()}</div>
      </div>
      <p class="hint">只把示例的条件填进表单，数字仍由你点击计算后实时算出。要直接看示例的完整结果，请到「示例」页打开。</p>
    </div>

    <div class="card ask" data-ask>${askCardHtml()}</div>

    <form class="formcards" novalidate data-form>
      <fieldset class="card fcard"><legend><span class="fnum">1</span>建筑与房间</legend>
        <div class="grid-form">${fields(['site_id', 'year', 'room_count', 'area_m2', 'weekdays_only', 'start_hour', 'end_hour', 'cooling_setpoint_c', 'rh_setpoint_percent'])}</div>
        <details class="more"><summary>更多房间条件（留空使用计算服务默认值）</summary>
          <div class="grid-form">${fields(['height_m', 'people_count', 'equipment_gain_w', 'orientation', 'window_wall_ratio', 'insulation_u_w_m2k', 'ventilation_lps_person', 'infiltration_ach'])}</div></details>
      </fieldset>

      <fieldset class="card fcard"><legend><span class="fnum">2</span>空调</legend>
        <div class="grid-form ac-grid">${fieldHtml('equipment_id')}${fieldHtml('units_per_room')}</div>
        <details class="tipq"><summary>${icon('help')}<span>“达标”是怎么判断的？</span></summary><p class="hint">${ADEQUACY_NOTE}</p></details>
        ${equipmentNote()}
        <div class="sizing" data-sizing>${sizingHtml()}</div>
      </fieldset>

      <fieldset class="card fcard"><legend><span class="fnum">3</span>屋顶与发电设备</legend>
        <div class="grid-form">${fields(['roof_area_m2', 'usable_fraction'])}${fieldHtml('capacity_mode', 'span2')}</div>
        ${T.form.capacity_mode !== 'auto' ? `<div class="grid-form">${fieldHtml('capacities', 'span2')}</div>` : '<p class="hint">自动比选：计算服务在“屋顶面积 × 可用比例”的容量上限内取 0、25%、50%、100% 四个候选，逐个算全年，再按 10 年总账选最划算的容量。</p>'}
        <div class="grid-form">${fields(['wind_turbine_count', 'hub_height_m'])}</div>
      </fieldset>

      <fieldset class="card fcard"><legend><span class="fnum">4</span>电价与预算</legend>
        <div class="grid-form">${fieldHtml('price_mode', 'span2')}${T.form.price_mode === 'tariff' ? fieldHtml('tariff_id', 'span2') + fieldHtml('tariff_application', 'span2') : fieldHtml('import_price')}</div>
        ${T.form.price_mode === 'tariff' && T.form.tariff_id === 'custom_user' ? customTariffHtml() : ''}
        <div class="grid-form" style="margin-top:16px">${fieldHtml('escalation_pct')}</div>
        ${tariffNote()}
        <div class="grid-form">${fields(['budget_cny', 'study_years'])}${fieldHtml('allow_export')}</div>
      </fieldset>

      <fieldset class="card fcard"><legend><span class="fnum">5</span>报价</legend>
        ${quotesFilled() ? '' : `<div class="callout unknown">${icon('help')}<span>还没有填写报价：光伏、小风机方案会显示“条件不全”，不会被当成排除，也不会自动补默认价。</span></div>`}
        <div class="row" style="margin:12px 0"><button class="btn sm" type="button" data-action="sample-quote">填入示例报价</button><span class="hint">示例报价是 5090 回放使用的用户情景报价，不是采购报价，请按实际询价修改。</span></div>
        <details class="more"${quotesFilled() ? ' open' : ''}><summary>光伏报价（每 kWp）</summary><div class="grid-form">${fields(FIELDS.filter((f) => f.group === 'pvq').map((f) => f.key))}</div></details>
        <details class="more"${quotesFilled() ? ' open' : ''}><summary>小风机报价（每台）</summary><div class="grid-form">${fields(FIELDS.filter((f) => f.group === 'wq').map((f) => f.key))}</div></details>
      </fieldset>

      <fieldset class="card fcard"><legend><span class="fnum">6</span>碳、储能与卖电（可选）</legend>
        <div class="grid-form">${fieldHtml('factor_id', 'span2')}${fieldHtml('carbon_price')}</div>
        ${carbonRefHtml()}
        <p class="sub-legend">多余的电存起来（储能）</p>
        <div class="grid-form">${fieldHtml('storage_caps', 'span2')}${fields(['st_price', 'st_install', 'st_maint', 'st_life'])}</div>
        <p class="sub-legend">多余的电卖给电网（粗算）</p>
        <div class="grid-form">${fields(['ex_price', 'ex_conn'])}</div>
        <p class="hint">储能与卖电只是附加估算，不改变四种供电方式的推荐；未填写的报价不补默认值，对应结果显示“条件不全”。“填入示例报价”会一并填入储能示例（CNESA 公开均价，示例拆分，非采购报价）与卖电示例（敏感性情景，不是广东固定上网价）。</p>
      </fieldset>
    </form>

    <div class="actionbar" data-actionbar>
      <div class="actionbar-inner">
        <div class="grow small" data-action-note>${live ? '点击计算：几百毫秒内先出典型周预览，全年结果在后台计算。' : '<b>当前未连接计算服务</b>，只能查看示例。启动本机服务后可实时计算。'}</div>
        <button class="btn primary lg" type="button" data-action="compute" ${live ? '' : 'disabled aria-disabled="true"'}>${icon('calc')}计算</button>
      </div>
    </div>
    <div class="runpanel" data-run aria-live="polite">${runHtml()}</div>
  </div>`;
}

function quickButtons() {
  const s = data.samplesLoaded();
  if (!s) return '<span class="hint">正在读取示例…</span>';
  return s.order.map((id) => { const c = s.cases.get(id); return `<button class="btn sm" type="button" data-quick-case="${id}">${esc((c.label || id).replace('状态变体：', '变体：'))}</button>`; }).join('');
}
/* ---------- 一句话输入：本地大模型理解（可用时）或本地规则识别 ---------- */
const useModel = () => !!(app.agent && app.agent.available);
function askCardHtml() {
  const model = useModel(), busy = T.askBusy;
  return `<div class="row" style="justify-content:space-between"><label class="label" for="askInput">一句话描述（可选）</label>
      <span class="tag ${model ? 'brand' : 'unknown'}" title="${esc(model ? '由本机运行的大模型理解你的话，只提出表单修改' : (app.agent && app.agent.reason ? `本地大模型不可用：${app.agent.reason}` : '本地规则识别'))}">${icon(model ? 'spark' : 'info')}${model ? '本地大模型理解' : '规则识别'}</span></div>
    <div class="ask-row"><input id="askInput" class="askinput" type="text" placeholder="例如：每间改成3台空调，预算加到5万，电价每年涨3%" value="${esc(T.askText || '')}"${busy ? ' disabled' : ''}>
      <button class="btn sm" type="button" data-action="ask"${busy ? ' disabled' : ''}>${busy ? '正在理解…' : model ? '理解' : '识别并填入'}</button></div>
    <p class="hint">${model ? '本地大模型只理解你的话并提出表单修改，你确认后才写入表单；不会自动计算，所有数字仍由计算服务算出。数据只在本机处理。' : '本地规则识别，只处理使用时段、使用日、预算、光伏容量、小风机台数与高度、电价、电价年涨幅、是否卖电；房间数、台数、面积、城市等请在下方表单修改。'}</p>
    <div data-ask-result aria-live="polite">${busy ? '<p class="small muted">本地大模型正在理解这句话…</p>' : askResult()}</div>`;
}
function renderAsk() { const box = $('[data-ask]', el); if (box) box.innerHTML = askCardHtml(); }

function proposalHtml(P) {
  const rows = P.changes.map((c, i) => `<li><span class="pr-label">${esc(agentLabel(c.field, c.label))}</span><span class="pr-from">${esc(agentFromText(c.field, c.from, T.form, app.options))}</span>${icon('arrow')}<b class="pr-to">${esc(agentValueText(c.field, c.to, app.options))}</b></li>`).join('');
  return `<div class="proposal" role="group" aria-label="我理解到的修改">
    <p class="pr-title">${icon('spark')}我理解到的修改</p>
    ${P.changes.length ? `<ul class="pr-list">${rows}</ul>` : '<p class="small muted">没有可以直接写入表单的修改。</p>'}
    ${(P.dropped || []).length ? `<p class="pr-dropped">已忽略：${P.dropped.map((d) => `${esc(agentLabel(d.field, '其他条件'))}（${esc(d.reason || '用户未提及')}）`).join('、')}</p>` : ''}
    ${P.unsupported.length ? `<p class="pr-sub">没能处理：</p><ul class="pr-un">${P.unsupported.map((u) => `<li>${esc(u)}</li>`).join('')}</ul>` : ''}
    <div class="row" style="margin-top:10px">${P.changes.length ? '<button class="btn primary sm" type="button" data-action="agent-apply">采用这些修改</button>' : ''}<button class="btn sm" type="button" data-action="agent-cancel">取消</button></div>
    <p class="hint">采用后只修改表单条件，不会自动计算；请检查后点击「计算」。</p></div>`;
}

function askResult() {
  if (!T.ask) return '';
  const a = T.ask;
  if (a.kind === 'proposal') return proposalHtml(a);
  if (a.kind === 'failed') return `<div class="callout warn">${icon('warn')}<span><b>本地大模型没能可靠理解这句话，请换个说法或直接修改表单。</b>${a.reason ? `<br><span class="small">原因：${esc(a.reason)}</span>` : ''}</span></div>`;
  if (a.kind === 'question') return `<div class="callout info">${icon('help')}<span><b>需要补充：</b>${esc(a.question || '')}</span></div>`;
  if (a.kind === 'applied') return `<div class="ask-tags">${a.keys.length ? `<span class="tag ok">${icon('check')}已写入表单：${esc(a.labels.join('、'))}</span>` : ''}${a.skipped.map((x) => `<span class="tag unknown">${icon('info')}${esc(x.label)}：${esc(x.why)}</span>`).join('')}</div><p class="hint">条件已修改，请检查后点击「计算」。</p>`;
  const fb = a.fallbackReason ? `<p class="small" style="color:var(--warn)">${icon('info')} 本地大模型暂不可用（${esc(a.fallbackReason)}），已改用规则识别。</p>` : '';
  if (!a.applied.length && !a.rejected.length) return fb + '<p class="hint">没有识别到可填入的条件。</p>';
  return fb + `<div class="ask-tags">${a.applied.map(([, , l]) => `<span class="tag ok">${icon('check')}${esc(l)}</span>`).join('')}${a.rejected.map(([t, why]) => `<span class="tag unknown">${icon('info')}${esc(t)}：${esc(why)}</span>`).join('')}</div>`;
}

/* ---------- 台数比选 ---------- */
const sizeKey = () => JSON.stringify([T.form.site_id, T.form.year, T.form.area_m2, T.form.equipment_id, T.form.weekdays_only, T.form.start_hour, T.form.end_hour, T.form.cooling_setpoint_c, T.form.rh_setpoint_percent, T.form.height_m, T.form.people_count, T.form.equipment_gain_w, T.form.orientation, T.form.window_wall_ratio, T.form.insulation_u_w_m2k, T.form.ventilation_lps_person, T.form.infiltration_ach, T.form.max_units]);
function sizingHtml() {
  const live = app.mode === 'live';
  const S = T.size;
  let body = '';
  if (S && S.loading) body = `<p class="small muted">${icon('clock')} 正在逐台计算全年热湿负荷…</p>`;
  else if (S && S.error) body = `<div class="callout bad">${icon('warn')}<span>${esc(S.error)}</span></div>`;
  else if (S && S.res) {
    const r = S.res, min = r.minimum_adequate_units_per_room, stale = S.formKey !== sizeKey();
    body = `<div class="sizing-res${stale ? ' is-stale' : ''}">
      ${stale ? `<p class="small" style="color:var(--warn)">${icon('warn')} 条件已修改，下面的比选对应修改前的条件，请重新比选。</p>` : ''}
      <p class="sizing-head">${isNum(min) ? `每间至少 <b class="num">${min}</b> 台，全年在模型范围内没有冷量或除湿缺口。` : `试到 ${esc(r.max_units)} 台仍有缺口，可提高“最多试到”或换型号。`}</p>
      <div class="chart" data-size-chart></div>
      <div class="tablewrap"><table class="table size-table"><caption class="sr-only">每间台数比选</caption><thead><tr><th>每间台数</th><th>服务状态</th><th class="r">全年空调用电（单房间，kWh）</th><th class="r">冷量不足小时</th></tr></thead><tbody>
      ${r.candidates.map((c) => `<tr class="${c.units_per_room === min ? 'is-best' : ''}"><td><b class="num">${c.units_per_room}</b> 台${c.units_per_room === min ? ' <span class="tag brand">最少达标</span>' : ''}</td><td>${c.service_status === 'within_modeled_scope' ? `<span class="tag ok">${icon('check')}达标</span>` : `<span class="tag warn">${icon('warn')}有缺口</span>`}</td><td class="r num">${fmt.kwh(c.annual_electric_kwh)}</td><td class="r num">${fmt.int(c.capacity_shortfall_hours)}</td></tr>`).join('')}
      </tbody></table></div>
      <p class="hint">每一行都是同一房间按所选台数单独算的全年热湿回放，没有乘房间数；额定点适配，不等于现场选型。</p>
      ${isNum(min) && !stale ? `<button class="btn primary sm" type="button" data-action="adopt-units" data-units="${min}">一键采用每间 ${min} 台</button>` : ''}
    </div>`;
  }
  return `<div class="sizing-top"><div><b>空调配几台才够用？</b><p class="hint">在当前房间条件下，逐个试 1 到 N 台，看哪一台数起全年没有缺口。</p></div>
    <div class="row">${fieldHtml('max_units', 'compact')}<button class="btn sm" type="button" data-action="size" ${live ? '' : 'disabled aria-disabled="true" title="需要连接计算服务"'}>帮我算配几台</button></div></div>${body}`;
}
function drawSizeChart() {
  const box = $('[data-size-chart]', el); if (!box || !T.size || !T.size.res) return;
  const c = T.size.res.candidates;
  barChart(box, { cats: c.map((x) => `${x.units_per_room}台`), series: [{ label: '冷量不足小时', color: 'var(--warn)', values: c.map((x) => x.capacity_shortfall_hours) }], unit: '小时/年', height: 150, label: '每间台数与全年冷量不足小时' });
}

/* ---------- 计算进度与预览 ---------- */
function runHtml() {
  const R = T.run;
  if (!R) return '';
  const events = (R.events || []).filter((e) => e.type === 'capacity_completed');
  const lastCap = events[events.length - 1];
  let status;
  if (R.error) status = `<div class="callout bad">${icon('warn')}<span><b>计算没有完成：</b>${esc(R.error)}${R.field ? `（已定位到表单：${esc((FIELD[FIELD_PATH[R.field]] || {}).label || R.field)}）` : ''}</span></div>`;
  else if (R.status === 'done') status = `<div class="callout info">${icon('check')}<span><b>全年结果已就绪。</b>后端计算用时 ${fmt.d((R.elapsedMs || 0) / 1000, 1)} 秒。</span></div>`;
  else {
    const pct = isNum(R.progress) ? R.progress : 0;
    const text = R.status === 'queued' || !R.status ? '已提交全年计算，等待开始…'
      : lastCap ? (pct >= 1 ? `全部 ${lastCap.total} 个容量已算完，正在生成选中容量的逐时结果…` : `已完成 ${lastCap.completed}/${lastCap.total} 个光伏容量（刚算完 ${fmt.d(lastCap.capacity_kwp, 2)} kWp）`)
        : '全年计算进行中：天气、空调负荷、发电和逐时匹配…';
    status = `<div class="progress-card"><div class="row" style="justify-content:space-between"><b>全年计算</b><span class="small muted">进度来自计算服务（${({ queued: '排队中', running: '计算中', submitting: '提交中' })[R.status] || '计算中'}）${isNum(R.elapsedMs) ? ` · 已用时 ${fmt.d(R.elapsedMs / 1000, 0)} 秒` : ''}</span></div>
      <div class="pbar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(pct * 100)}" aria-label="全年计算进度"><span style="width:${(pct * 100).toFixed(0)}%"></span></div>
      <p class="small">${esc(text)}</p><button class="btn ghost sm" type="button" data-action="stop-wait">停止等待（计算服务会继续算完）</button></div>`;
  }
  return `<div class="runbox">${status}${previewHtml()}</div>`;
}

function previewHtml() {
  const P = (T.run && T.run.previews) || (T.result && T.result.previews);
  if (!P) return T.run && !T.run.error ? '<p class="small muted">正在生成典型周预览…</p>' : '';
  const pv = P[T.pvSeason] || P.summer || P.winter;
  if (!pv) return P.error ? `<div class="callout bad">${icon('warn')}<span>典型周预览失败：${esc(P.error)}</span></div>` : '';
  const c = pv.candidates[T.pvScen] || pv.candidates.S3_pv_wind;
  const s = c.summary;
  return `<section class="preview" aria-labelledby="pvTitle">
    <div class="preview-head"><div><span class="tag warn">${icon('info')}预览：典型周物理匹配，不含费用和推荐</span>
      <h3 id="pvTitle">${pv.season === 'winter' ? '冬季' : '夏季'}典型周 · ${esc(fmt.ts(pv.start).slice(0, 10))} 至 ${esc(fmt.ts(pv.end).slice(5, 10))}（不含）</h3>
      <p class="hint">${esc(pv.scopeNote || '')} ${esc(pv.rule || '')}。预览光伏容量 ${fmt.d(pv.pvInput && pv.pvInput.capacity_kwp, 2)} kWp${pv.pvInput && pv.pvInput.capacity_defaulted ? '（未指定，由计算服务在屋顶上限内取默认值）' : ''}，计算用时 ${fmt.int(pv.elapsedMs)} 毫秒。</p></div>
      <div class="stack"><div class="seg" role="group" aria-label="季节">${['summer', 'winter'].filter((k) => P[k]).map((k) => `<button type="button" data-pv-season="${k}" aria-pressed="${k === T.pvSeason}">${k === 'summer' ? '夏季周' : '冬季周'}</button>`).join('')}</div>
      <div class="seg" role="group" aria-label="方案">${['S1_pv', 'S2_wind', 'S3_pv_wind'].filter((k) => pv.candidates[k]).map((k) => `<button type="button" data-pv-scen="${k}" aria-pressed="${k === T.pvScen}">${data.SCEN[k].name}</button>`).join('')}</div></div>
    </div>
    <div class="preview-sum">
      ${[['空调用电', s.load], ['光伏发电', s.pv], ['风机发电', s.wind], ['当时用上', s.self], ['浪费', s.curt], ['从电网买', s.imp]].map(([l, v]) => `<div><span>${l}</span><b class="num">${fmt.kwh(v)}</b><small>kWh / 这一周</small></div>`).join('')}
    </div>
    <div class="preview-charts">
      <div><p class="chart-title">用电与发电（逐小时）</p><div class="legend"><span><i class="line" style="background:var(--c-load)"></i>空调用电</span><span><i class="line" style="background:var(--c-pv)"></i>光伏发电</span><span><i class="line" style="background:var(--c-wind)"></i>风机发电</span></div><div class="chart" data-pv-chart="src"></div></div>
      <div><p class="chart-title">发的电去哪了（逐小时）</p><div class="legend"><span><i style="background:var(--c-self)"></i>当时用上</span><span><i style="background:var(--c-waste)"></i>浪费</span></div><div class="chart" data-pv-chart="fate"></div></div>
    </div>
    <p class="chart-note">单位 kWh。预览只截取这一周，不外推到全年；全年金额、碳和推荐以全年结果为准。</p>
  </section>`;
}
function drawPreview() {
  const P = (T.run && T.run.previews) || (T.result && T.result.previews);
  if (!P) return;
  const pv = P[T.pvSeason] || P.summer || P.winter; if (!pv) return;
  const c = pv.candidates[T.pvScen] || pv.candidates.S3_pv_wind, s = c.series;
  const x = s.ts.map((t) => fmt.ts(t));
  const a = $('[data-pv-chart="src"]', el), b = $('[data-pv-chart="fate"]', el);
  if (a) lineChart(a, { x, xTicks: dayTicks(s.ts), unit: 'kWh', height: 220, label: '典型周逐小时用电与发电', series: [{ label: '空调用电', color: 'var(--c-load)', values: s.load }, { label: '光伏发电', color: 'var(--c-pv)', values: s.pv, area: true }, { label: '风机发电', color: 'var(--c-wind)', values: s.wind }] });
  if (b) lineChart(b, { x, xTicks: dayTicks(s.ts), unit: 'kWh', height: 220, label: '典型周逐小时发电去向', series: [{ label: '当时用上', color: 'var(--c-self)', values: s.self, area: true }, { label: '浪费', color: 'var(--c-waste)', values: s.curt, area: true }] });
}

/* ------------------------------------------------------------------ */
/* 计算流程                                                            */
/* ------------------------------------------------------------------ */
function focusField(key) {
  const node = $(`[data-field="${key}"]`, el) || $(`[data-wrap="${key}"] button`, el);
  if (!node) return;
  const det = node.closest('details'); if (det) det.open = true;
  node.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'center' });
  setTimeout(() => node.focus({ preventScroll: true }), reduceMotion() ? 0 : 350);
}

async function compute() {
  if (app.mode !== 'live') { toast('当前未连接计算服务，只能查看示例'); return; }
  T.errors = validate(T.form);
  if (Object.keys(T.errors).length) { if (T.step !== 1) location.hash = '#/tool/1'; renderStep(); focusField(Object.keys(T.errors)[0]); toast('有条件需要修改'); return; }
  if (T.run && T.run.ctrl) T.run.ctrl.abort();
  const ctrl = new AbortController();
  const form = JSON.parse(JSON.stringify(T.form));
  const request = buildRequest(form);
  T.run = { status: 'submitting', progress: 0, events: [], previews: null, ctrl, form, request, startedAt: Date.now() };
  if (T.step !== 1) location.hash = '#/tool/1';
  renderStep();
  const runEl = $('[data-run]', el); if (runEl) runEl.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' });

  // 1) 典型周预览：先算夏季周（几百毫秒），返回后立刻提交全年任务并算冬季周。
  //    实测三个请求同时到达时，单进程计算服务互相争用，预览会被拖到 3–4 秒；
  //    让夏季预览先行，全年任务只晚几百毫秒提交，换来 1 秒内出现预览。
  const previews = {};
  const one = (season) => api.preview(buildPreview(form, season), { signal: ctrl.signal })
    .then((res) => { previews[season] = data.fromPreview(res, { kind: 'live', season }); })
    .catch((e) => { if (e.name !== 'AbortError') previews.error = e.message; })
    .then(() => { if (T.run && T.run.ctrl === ctrl) { T.run.previews = Object.assign({}, previews); updateRun(); } });
  await one('summer');
  if (ctrl.signal.aborted) return;
  const pvPromise = one('winter');

  // 2) 全年异步任务（进度只来自后端）
  try {
    const job = await api.submit(request, { signal: ctrl.signal });
    T.run.jobId = job.job_id; T.run.status = job.status; updateRun();
    const report = await pollJob(job.job_id, (p) => { if (T.run && T.run.ctrl === ctrl) { Object.assign(T.run, p); updateRun(); } }, { signal: ctrl.signal });
    await pvPromise;
    const vm = data.fromLive(report, request, { jobId: job.job_id });
    T.run.status = 'done'; T.run.elapsedMs = (report.calculation_timing || {}).elapsed_ms;
    T.result = { vm, kind: 'live', previews, form, at: Date.now(), raw: report };
    T.stale = false;
    app.lastLive = { vm, previews, request, at: Date.now() };
    emit('live-result', app.lastLive);
    toast('全年结果已就绪');
    location.hash = '#/tool/2';
    renderAll();
  } catch (e) {
    if (e.name === 'AbortError') return;
    T.run.error = e.message || String(e); T.run.field = e.field || null;
    const key = e.field && FIELD_PATH[e.field];
    if (key) { T.errors = { [key]: e.message }; renderStep(); focusField(key); }
    else updateRun();
  }
}

function updateRun() {
  const box = $('[data-run]', el);
  if (!box) return;
  const busy = !!(T.run && !T.run.error && T.run.status !== 'done');
  const btn = $('.actionbar [data-action="compute"]', el), note = $('[data-action-note]', el);
  if (btn && app.mode === 'live') btn.innerHTML = `${icon(busy ? 'clock' : 'calc')}${busy ? '计算中…' : '计算'}`;
  if (note && app.mode === 'live') note.textContent = busy ? '正在计算。再次点击会用当前条件重新开始。' : '点击计算：几百毫秒内先出典型周预览，全年结果在后台计算。';
  box.innerHTML = runHtml();
  drawPreview();
}

async function sizeUnits() {
  if (app.mode !== 'live') return;
  const errs = validate(T.form);
  const need = ['area_m2', 'start_hour', 'end_hour', 'cooling_setpoint_c', 'rh_setpoint_percent', 'max_units'];
  const mu = Number(T.form.max_units);
  if (!Number.isInteger(mu) || mu < 1 || mu > 50) errs.max_units = '请输入 1 到 50 的整数';
  const bad = need.filter((k) => errs[k]);
  if (bad.length) { T.errors = Object.fromEntries(bad.map((k) => [k, errs[k]])); renderStep(); focusField(bad[0]); return; }
  const req = buildRequest(T.form);
  T.size = { loading: true, formKey: sizeKey() };
  $('[data-sizing]', el).innerHTML = sizingHtml();
  try {
    const res = await api.thermalSize({ site_id: req.site_id, year: req.year, max_units: mu, room: req.room });
    T.size = { res, formKey: sizeKey() };
  } catch (e) {
    T.size = { error: e.message, formKey: sizeKey() };
    const key = e.field && FIELD_PATH[e.field]; if (key) { T.errors = { [key]: e.message }; }
  }
  $('[data-sizing]', el).innerHTML = sizingHtml(); drawSizeChart();
}

/* ------------------------------------------------------------------ */
/* 结果失效                                                            */
/* ------------------------------------------------------------------ */
function markChanged() {
  if (T.result && !T.stale) { T.stale = true; renderResbar(); applyStale(); }
}
function applyStale() {
  const z = $('[data-result-zone]', el); if (!z) return;
  z.classList.toggle('is-stale', !!T.stale);
  $$('[data-export], [data-action="save-plan"]', el).forEach((b) => { b.disabled = !!T.stale; b.setAttribute('aria-disabled', String(!!T.stale)); });
  const note = $('[data-stale-note]', el);
  if (note) note.textContent = app.mode === 'live' ? '' : '当前未连接计算服务，无法重新计算；可回到原示例查看。';
  $$('[data-needs-live]', el).forEach((b) => { b.disabled = app.mode !== 'live'; });
}

function renderResbar() {
  const bar = $('[data-resbar]', el);
  if (!T.result) { bar.hidden = true; return; }
  const v = T.result.vm;
  bar.hidden = false;
  bar.innerHTML = `<div class="container">
    <span class="tag ${T.stale ? 'warn' : v.kind === 'live' ? 'ok' : 'brand'}">${icon(T.stale ? 'warn' : v.kind === 'live' ? 'bolt' : 'doc')}${T.stale ? '条件已修改，结果已失效' : v.kind === 'live' ? '实时计算结果' : '示例数据'}</span>
    <span class="small">${esc(v.kind === 'live' ? `本机实时计算 · ${fmt.date(v.computedAt)}` : `${v.label} · 来自 ${data.sampleSourceText(data.samplesLoaded())}`)}</span>
    ${v.kind === 'sample' && !T.stale ? '<span class="xsmall muted">改任何条件后可点击「实时重算」</span>' : ''}
    ${T.stale ? `<button class="btn primary sm" type="button" data-action="compute" data-needs-live ${app.mode === 'live' ? '' : 'disabled'}>${icon('calc')}实时重算</button>` : ''}
  </div>`;
}

/* ------------------------------------------------------------------ */
/* 渲染                                                                */
/* ------------------------------------------------------------------ */
function renderStep() {
  $$('[data-step-link]', el).forEach((a) => {
    const n = +a.dataset.stepLink;
    if (n === T.step) a.setAttribute('aria-current', 'step'); else a.removeAttribute('aria-current');
    a.classList.toggle('is-done', !!T.result && n !== T.step);
    a.classList.toggle('is-locked', n > 1 && !T.result);
  });
  $$('[data-step-panel]', el).forEach((p) => { p.hidden = +p.dataset.stepPanel !== T.step; });
  $('[data-result-zone]', el).hidden = T.step === 1;
  if (T.step === 1) { $('[data-step-panel="1"]', el).innerHTML = step1Html(); drawSizeChart(); drawPreview(); }
  else {
    const panel = $(`[data-step-panel="${T.step}"]`, el);
    if (!T.result) panel.innerHTML = `<div class="empty-state big">${icon('calc')}<p>还没有结果。请先在第 1 步填写条件并点击「计算」，或到「示例」页打开一个示例。</p><a class="btn primary" href="#/tool/1">去填写条件</a></div>`;
    else results.render(panel, T.step, T);
  }
  renderResbar(); applyStale();
}
function renderAll() { renderStep(); }

/* ------------------------------------------------------------------ */
/* 事件                                                                */
/* ------------------------------------------------------------------ */
function setField(key, value, { rerender = false } = {}) {
  T.form[key] = value; T.touched = true;
  if (T.errors[key]) { delete T.errors[key]; const w = $(`[data-wrap="${key}"]`, el); if (w) { w.classList.remove('has-error'); const e = $('.err', w); if (e) e.remove(); } }
  markChanged();
  if (rerender) { const y = window.scrollY; renderStep(); window.scrollTo(0, y); }
}

function bind() {
  el.addEventListener('input', (e) => {
    const f = e.target.closest('[data-field]'); if (!f) return;
    const key = f.dataset.field, fd = FIELD[key];
    if (fd.type === 'check' || f.tagName === 'SELECT') return;
    setField(key, f.value);
    if (T.size && T.size.res && FIELD[key].group !== 'price') { const r = $('.sizing-res', el); if (r && T.size.formKey !== sizeKey()) { $('[data-sizing]', el).innerHTML = sizingHtml(); drawSizeChart(); } }
  });
  el.addEventListener('change', (e) => {
    const f = e.target.closest('[data-field]'); if (!f) return;
    const key = f.dataset.field;
    if (FIELD[key].type === 'check') setField(key, f.checked);
    else if (f.tagName === 'SELECT') {
      const prev = T.form[key];
      T.form[key] = f.value;
      if (key === 'tariff_id' && f.value === 'custom_user' && prev && prev !== 'custom_user') prefillCustom(T.form, app.options, prev);
      if (key === 'site_id') {
        const c = ((app.options || {}).cities || []).find((x) => x.site_id === T.form.site_id); if (c && !c.cached_years.includes(T.form.year)) T.form.year = c.cached_years[c.cached_years.length - 1];
        // 换城市：电价档案跟随该城市所在供电区域；没有可用档案时改为固定电价（需用户填写）
        const st = tariffsForSite(app.options, T.form.site_id);
        if (st.length) { if (!st.includes(T.form.tariff_id)) { T.form.tariff_id = st[0]; T.form.price_mode = 'tariff'; } }
        else if (T.form.price_mode === 'tariff') { T.form.price_mode = 'fixed'; toast('这个城市暂无已登记的电价档案，请填写固定电价'); }
      }
      setField(key, f.value, { rerender: ['site_id', 'tariff_id', 'equipment_id', 'price_mode', 'tariff_application'].includes(key) });
      if (['site_id', 'tariff_id', 'equipment_id'].includes(key)) { const n = $(`[data-field="${key}"]`, el); if (n) n.focus({ preventScroll: true }); }
    }
  });
  el.addEventListener('click', (e) => {
    const t = e.target;
    const seg = t.closest('[data-seg]'); if (seg) { setField(seg.dataset.seg, seg.dataset.val, { rerender: true }); return; }
    const lk = t.closest('[data-step-link]'); if (lk && lk.classList.contains('is-locked')) { e.preventDefault(); toast('请先计算，或打开一个示例'); return; }
    const act = t.closest('[data-action]'); const a = act && act.dataset.action;
    if (a === 'compute') { compute(); return; }
    if (a === 'size') { sizeUnits(); return; }
    if (a === 'adopt-units') { setField('units_per_room', act.dataset.units, { rerender: true }); toast(`已采用每间 ${act.dataset.units} 台`); return; }
    if (a === 'stop-wait') { if (T.run && T.run.ctrl) T.run.ctrl.abort(); T.run = null; updateRun(); toast('已停止等待；计算服务会在后台算完本次任务'); return; }
    if (a === 'ask') { askSubmit(); return; }
    if (a === 'agent-cancel') { T.ask = null; renderAsk(); return; }
    if (a === 'agent-apply') { agentApply(); return; }
    if (a === 'sample-quote') {
      const s = data.samplesLoaded(); const c = s && s.cases.get('tier_small');
      if (!c) { toast('示例还没读取完，请稍候'); return; }
      Object.assign(T.form, quoteFieldsFrom(c.request), storageFieldsFrom(c.request)); if ((c.request.storage || {}).capacities_kwh) T.form.storage_caps = c.request.storage.capacities_kwh.join(', '); T.form._extras.storageMeta = storageMetaFrom(c.request); T.touched = true; markChanged(); renderStep(); toast('已填入示例报价（光伏、风机、储能、卖电；示例情景，非采购报价）'); return;
    }
    if (a === 'carbon-ref') { carbonRef(); return; }
    const q = t.closest('[data-quick-case]'); if (q) { startFromSample(q.dataset.quickCase); return; }
    const ps = t.closest('[data-pv-season]'); if (ps) { T.pvSeason = ps.dataset.pvSeason; updateRun(); if (T.step !== 1) renderStep(); return; }
    const pc = t.closest('[data-pv-scen]'); if (pc) { T.pvScen = pc.dataset.pvScen; updateRun(); if (T.step !== 1) renderStep(); return; }
  });
  el.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.id === 'askInput') { e.preventDefault(); $('[data-action="ask"]', el).click(); } });
}

/* ---------- 一句话输入的处理 ---------- */
function ruleAsk(text, fallbackReason) {
  const r = parseAsk(text);
  T.ask = Object.assign({ kind: 'rule', text, fallbackReason: fallbackReason || null }, r);
  for (const [k, v] of r.applied) T.form[k] = v;
  if (r.applied.length) { T.touched = true; markChanged(); }
  const y = scrollY; renderStep(); scrollTo(0, y);
  if (r.applied.length) flashFields(r.applied.map(([k]) => k));
}
async function askSubmit() {
  const text = ($('#askInput', el).value || '').trim();
  T.askText = text;
  if (!text) { toast('请先输入一句话'); return; }
  if (!useModel()) { ruleAsk(text); return; }
  T.askBusy = true; T.ask = null; renderAsk();
  const res = await agent.parse(text, buildRequest(T.form));
  T.askBusy = false;
  if (res.status === 'ok') T.ask = { kind: 'proposal', text, changes: res.changes, dropped: res.dropped || [], unsupported: res.unsupported };
  else if (res.status === 'needs_clarification') T.ask = { kind: 'question', text, question: res.question || res.reason || '请补充更具体的条件。' };
  else if (res.status === 'failed') T.ask = { kind: 'failed', text, reason: res.reason || null };
  else { ruleAsk(text, res.reason || '不可用'); toast('本地大模型暂不可用，已改用规则识别'); return; }
  renderAsk();
}
function agentApply() {
  if (!T.ask || T.ask.kind !== 'proposal') return;
  const { form, keys, skipped } = applyAgentChanges(T.form, T.ask.changes);
  T.form = form;
  const labels = [...new Set(T.ask.changes.filter((c) => !skipped.find((x) => x.label === agentLabel(c.field, c.label))).map((c) => agentLabel(c.field, c.label)))];
  T.ask = { kind: 'applied', text: T.ask.text, keys, labels, skipped: skipped.concat(T.ask.unsupported.map((u) => ({ label: '没能处理', why: u }))) };
  if (keys.length) { T.touched = true; markChanged(); }
  const y = scrollY; renderStep(); scrollTo(0, y);
  flashFields(keys);
  toast(keys.length ? '已写入表单，请检查后点击「计算」' : '没有可写入的修改');
}
/** 被改动的字段高亮 3 秒 */
function flashFields(keys) {
  for (const k of keys) {
    const w = $(`[data-wrap="${k}"]`, el); if (!w) continue;
    const det = w.closest('details'); if (det) det.open = true;
    w.classList.remove('flash'); void w.offsetWidth; w.classList.add('flash');
    setTimeout(() => w.classList.remove('flash'), 3000);
  }
}

/** 公开参考碳价：读计算服务 options.carbon_price_scenarios（数值、来源、“仅情景”说明），只作为输入情景填入。 */
const carbonScenario = () => (((app.options || {}).carbon_price_scenarios) || [])[0] || null;
function carbonRefHtml() {
  const c = carbonScenario();
  if (!c) return '<p class="hint" style="margin:6px 0 10px">连接计算服务后可选用公开参考碳价情景。</p>';
  const v = c.carbon_price_cny_per_t ?? c.value_cny_per_t;
  return `<div class="row" style="margin:6px 0 10px"><button class="btn sm" type="button" data-action="carbon-ref">使用公开参考碳价（${fmt.d(v, 2)} 元/吨）</button><span class="hint">来源：${esc(c.source_title || c.source || '')}${c.date ? `（${esc(c.date)}）` : ''}${c.source_url ? ` · <a href="${esc(c.source_url)}" target="_blank" rel="noopener noreferrer">原文</a>` : ''}。${esc(c.note || '仅为情景')}</span></div>`;
}
function carbonRef() {
  const c = carbonScenario(); if (!c) return;
  setField('carbon_price', String(c.carbon_price_cny_per_t ?? c.value_cny_per_t), { rerender: true }); toast('已填入公开参考碳价情景');
}

function startFromSample(caseId) {
  const s = data.samplesLoaded(); const c = s && s.cases.get(caseId); if (!c) return;
  T.form = formFromRequest(c.request, app.options); T.errors = {}; T.ask = null; T.size = null; T.touched = true;
  markChanged(); renderStep();
  toast(`已填入「${c.label}」的条件，点击计算后实时算出`);
}

/** 打开示例：显示回放的完整结果（示例数据），同时把示例条件填进表单。 */
export async function openSample(caseId, step = 3) {
  const s = await data.loadSamples();
  const c = s.cases.get(caseId); if (!c) { toast('没有这个示例'); return; }
  T.form = formFromRequest(c.request, app.options); T.errors = {}; T.ask = null; T.size = null; T.touched = true;
  const vm = data.fromSample(c, s.file);
  const tier = data.previewTierOf(caseId);
  const previews = tier ? { summer: data.samplePreview(s, tier, 'summer'), winter: data.samplePreview(s, tier, 'winter') } : null;
  T.result = { vm, kind: 'sample', previews, form: JSON.parse(JSON.stringify(T.form)), at: Date.now(), raw: c };
  T.stale = false; T.run = null;
  if (location.hash !== `#/tool/${step}`) location.hash = `#/tool/${step}`; else if (built) renderAll();
}

export function show(root, args = []) {
  el = root;
  if (!built) {
    if (!T.form) T.form = blankForm(app.options);
    el.innerHTML = skeleton(); bind(); built = true;
    data.loadSamples().then(() => { const q = $('[data-quick]', el); if (q) q.innerHTML = quickButtons(); }).catch(() => {});
  }
  const n = Math.min(4, Math.max(1, parseInt(args[0], 10) || 1));
  T.step = n;
  renderAll();
}

on('agent', () => { if (built && !el.hidden && T.step === 1) renderAsk(); });
on('mode', () => {
  // 选项到达后：用户还没动过表单就按选项重建空白条件；否则只补齐缺失的型号与电价档案
  if (!T.form) return;
  if (!T.touched) T.form = blankForm(app.options);
  else if (app.options) { const b = blankForm(app.options); if (!T.form.equipment_id) T.form.equipment_id = b.equipment_id; if (!T.form.tariff_id && b.tariff_id) T.form.tariff_id = b.tariff_id; }
  if (built && !el.hidden) renderAll();
});

/** 我的方案：载入保存的条件（结果若存在则立即失效）。 */
export function loadForm(form) {
  const b = blankForm(app.options);
  T.form = Object.assign(b, JSON.parse(JSON.stringify(form || {})));
  if (!T.form._extras) T.form._extras = { room: {}, wind: {} };
  T.errors = {}; T.ask = null; T.size = null; T.touched = true;
  markChanged();
}
