/* 能见度 · 数据适配层
 *
 * 职责：把“本机实时接口响应”和“5090 回放文件”映射成同一个视图模型（view model）。
 * 约束（任务书第 1、6.2、7 节）：
 *   - 本层不做任何数值计算：不聚合电量、不算费用/现值/碳、不推断房间配置、不外推全年；
 *     只做字段映射、状态翻译。所有数字原样来自后端或回放文件。
 *   - 契约里没有的字段返回 null，由界面显示“—”或“示例未记录”，不猜。
 *   - 计价不完整（economics_status ≠ complete）的方案不显示金额（回放里此类方案的
 *     total_cost_npv_cny 记为 0，0 不是真实花费）。
 */
import { app, emit } from './state.js';

/* ------------------------------------------------------------------ */
/* 术语映射：主界面用中文；技术名只进依据抽屉和关于页                    */
/* ------------------------------------------------------------------ */
export const SCEN = {
  S0_grid:    { name: '只用电网',    short: '电网',      verb: '暂不加装，只用电网', order: 0, color: 'var(--c-grid)' },
  S1_pv:      { name: '加装光伏',    short: '光伏',      verb: '加装光伏',           order: 1, color: 'var(--c-pv)' },
  S2_wind:    { name: '加装小风机',  short: '小风机',    verb: '加装小风机',         order: 2, color: 'var(--c-wind)' },
  S3_pv_wind: { name: '光伏 + 小风机', short: '光伏+风机', verb: '光伏和小风机都装',   order: 3, color: 'var(--c-pv)' }
};
export const SCEN_IDS = ['S0_grid', 'S1_pv', 'S2_wind', 'S3_pv_wind'];

export const ADMISSION = {
  eligible:   { label: '可比较',   tone: 'ok',      icon: 'check', note: '条件齐全，参与比较' },
  unknown:    { label: '条件不全', tone: 'unknown', icon: 'help',  note: '报价或必要条件缺失，暂无法比较——不是淘汰' },
  excluded:   { label: '已排除',   tone: 'bad',     icon: 'x',     note: '不满足预算、屋顶或高度等硬性条件' },
  equivalent: { label: '与其他方案相同', tone: 'unknown', icon: 'equal', note: '结果与另一方案相同' }
};
export const RECOMMENDATION = {
  conditional:        { label: '有条件推荐', tone: 'brand',   note: '在条件齐全、可比较的方案中 10 年总花费最低' },
  conditional_subset: { label: '部分比较',   tone: 'warn',    note: '部分方案条件不全，只在其余方案中比较；不能说它们已被击败' },
  not_available:      { label: '暂无推荐',   tone: 'unknown', note: '可比较的方案不足' }
};
export const SERVICE = {
  within_modeled_scope: { label: '空调达标', tone: 'ok',   icon: 'check', note: '在模型范围内满足设定温湿度（未经现场校准）。' },
  service_gap:          { label: '空调有缺口', tone: 'warn', icon: 'warn',  note: '模型中有冷量或除湿不足的时段。结果不代表同等舒适度下的最优投资。' }
};
export const CONSTRAINT_TEXT = {
  feasible: '满足限制条件', over_budget: '超出预算', not_applicable: '场地条件不满足',
  incomplete_quote: '缺少报价', height_limit: '超出高度限制'
};
export const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

/* ------------------------------------------------------------------ */
/* 后端探测                                                            */
/* ------------------------------------------------------------------ */
/* 本机计算服务把页面挂在根路径（/ 或 /index.html）。若页面是从仓库目录的静态服务器
 * 打开的（路径形如 /operation_planning/ui/index.html），不存在计算服务，直接进入示例模式，
 * 避免无意义的 404 请求。 */
const servedByBackend = () => /^\/(index\.html)?$/.test(location.pathname);

export async function probe() {
  if (!servedByBackend()) { app.options = null; app.mode = 'sample'; emit('mode', app.mode); return app.mode; }
  try {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 3500);
    const res = await fetch('/api/operation/options', { cache: 'no-store', signal: ctl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error(String(res.status));
    const body = await res.json();
    if (!body || !Array.isArray(body.cities)) throw new Error('options 响应格式不符');
    app.options = body; app.mode = 'live';
  } catch (e) {
    app.options = null; app.mode = 'sample';
  }
  emit('mode', app.mode);
  return app.mode;
}

/* ------------------------------------------------------------------ */
/* 示例回放读取（后台线程）                                              */
/* ------------------------------------------------------------------ */
const sampleBases = () => servedByBackend()
  ? [new URL('/samples/', location.href).href]                               // 本机计算服务的只读路由
  : [new URL('../../docs/handoff/replay_viewer/', location.href).href];      // 仓库根目录静态服务
const pending = {};
function loadInWorker(which) {
  if (pending[which]) return pending[which];
  pending[which] = new Promise((resolve, reject) => {
    let worker;
    try { worker = new Worker(new URL('./sample-worker.js', import.meta.url)); } catch (e) { worker = null; }
    if (!worker) { reject(new Error('浏览器不支持后台读取')); return; }
    worker.onmessage = (e) => { worker.terminate(); if (e.data.ok) resolve(e.data); else reject(new Error(e.data.error)); };
    worker.onerror = (e) => { worker.terminate(); reject(new Error(e.message || '后台读取失败')); };
    worker.postMessage({ which, bases: sampleBases() });
  }).catch((err) => { delete pending[which]; throw err; });
  return pending[which];
}

let samplesCache = null;
/** 读取示例：{ file, cases: Map(caseId → case), order: [caseId], previews: Map('tier_small_summer' → case), url } */
export async function loadSamples() {
  if (samplesCache) return samplesCache;
  const [cs, pv] = await Promise.all([loadInWorker('cases'), loadInWorker('previews').catch(() => null)]);
  const file = cs.data;
  const cases = new Map((file.cases || []).map((c) => [c.case_id, c]));
  const previews = new Map();
  if (pv && pv.data) for (const p of pv.data.cases || []) previews.set(`${p.tier}_${p.season}`, p);
  samplesCache = { file, cases, order: (file.cases || []).map((c) => c.case_id), previews, url: cs.url, previewFile: pv ? pv.data : null, previewUrl: pv ? pv.url : null };
  emit('samples', samplesCache);
  return samplesCache;
}
export const samplesLoaded = () => samplesCache;

/* ------------------------------------------------------------------ */
/* 映射工具                                                            */
/* ------------------------------------------------------------------ */
const pick = (...vals) => { for (const v of vals) if (v !== undefined) return v; return undefined; };
const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

function mapAdmission(status) {
  return Object.assign({ status }, ADMISSION[status] || { label: status || '未知状态', tone: 'unknown', icon: 'help', note: '' });
}

function mapCarbon(c) {
  if (!c) return null;
  return {
    gridEmissionsKgY1: num(c.grid_emissions_kgco2_year1),
    avoidedKgY1: num(c.avoided_kgco2_year1),
    avoidedTStudy: num(c.avoided_tco2_study_period),
    curtailedKwhY1: num(c.curtailed_kwh_year1),
    curtailedShare: num(c.curtailed_share),
    exportedKwhY1: num(c.exported_kwh_year1),
    exportAvoidedKgY1: num(c.export_avoided_kgco2_year1),
    costPerT: num(c.cost_per_tco2_cny),
    costPerTStatus: c.cost_per_tco2_status || null,
    revenueStudy: num(c.carbon_revenue_cny_study_period),
    revenuePV: num(c.carbon_revenue_present_value_cny),
    incrementalWithCarbon: num(c.incremental_npv_with_carbon_cny),
    national: c.national_comparison || null,
    eligibility: c.eligibility || null,
    eligibilityNote: c.eligibility_note || null,
    yearly: Array.isArray(c.yearly) ? c.yearly : []
  };
}

function mapRough(r) {
  if (!r) return null;
  return {
    coveredKwh: num(r.covered_kwh),
    coverageRate: num(r.claimed_coverage_rate),
    avoidedKg: num(r.claimed_avoided_kgco2),
    billSavingY1: num(r.claimed_bill_saving_cny_year1),
    incremental: num(r.claimed_incremental_npv_vs_s0_cny),
    effectivePrice: num(r.effective_price_cny_per_kwh),
    priceBasis: r.electricity_price_basis || null,
    method: r.method || null,
    participates: r.participates_in_recommendation === true
  };
}

function mapStorage(s) {
  if (!s) return null;
  return {
    status: s.status || null,
    note: s.note || null,
    allowExport: s.allow_export,
    candidates: (s.candidates || []).map((x) => ({
      capacityKwh: num(x.capacity_kwh), powerKw: num(x.power_limit_kw), eta: num(x.round_trip_efficiency),
      recoveredKwh: num(x.recovered_kwh_year1), remainingCurtailKwh: num(x.remaining_curtailment_kwh_year1),
      gridImportKwh: num(x.grid_import_kwh_year1), extraAvoidedKg: num(x.additional_avoided_kgco2_year1),
      conservationPassed: x.conservation ? x.conservation.passed === true : null
    }))
  };
}

function mapCandidate(c, recId) {
  const econ = c.economics || {};
  const economicsStatus = pick(c.economics_status, econ.status) || null;
  const complete = economicsStatus === 'complete';
  const meta = SCEN[c.scenario_id] || { name: c.scenario_id, short: c.scenario_id, verb: c.scenario_id, order: 9 };
  return {
    id: c.scenario_id, name: meta.name, short: meta.short, verb: meta.verb, order: meta.order,
    admission: mapAdmission(c.admission_status),
    constraintStatus: c.constraint_status || null,
    constraintText: CONSTRAINT_TEXT[c.constraint_status] || c.constraint_status || null,
    reasons: Array.isArray(c.constraint_reasons) ? c.constraint_reasons.slice() : [],
    equivalentTo: c.equivalent_to || null,
    economicsStatus,
    totalCost: complete ? num(pick(c.total_cost_npv_cny, econ.total_cost_npv_cny)) : null,
    incremental: complete ? num(pick(c.incremental_npv_vs_s0_cny, econ.incremental_npv_vs_s0_cny)) : null,
    npv: complete ? num(pick(c.npv_cny, econ.npv_cny)) : null,
    capex: num(pick(c.capex_cny, econ.capex_cny)),
    yearly: Array.isArray(econ.yearly) ? econ.yearly : [],
    pvKwp: num(c.pv_capacity_kwp), windCount: num(c.wind_turbine_count),
    gen: num(c.generation_kwh), pvGen: num(c.pv_generation_kwh), windGen: num(c.wind_generation_kwh),
    selfUse: num(c.self_use_kwh), gridImport: num(c.grid_import_kwh), gridExport: num(c.grid_export_kwh),
    curtail: num(c.curtailment_kwh), coverage: num(c.load_coverage_rate),
    carbon: mapCarbon(c.carbon),
    rough: mapRough(c.annual_offset_estimate),
    storage: mapStorage(c.storage_upper_bound),
    isRec: c.scenario_id === recId,
    hourly: c.hourly ? mapHourly(c.hourly, c.scenario_id) : null
  };
}

export function mapHourly(h, scenarioId) {
  if (!h || !Array.isArray(h.timestamps)) return null;
  return {
    scenarioId: h.scenario_id || scenarioId || null,
    ts: h.timestamps,
    load: h.load_kwh || [], pv: h.pv_generation_kwh || [], wind: h.wind_generation_kwh || [],
    self: h.self_use_kwh || [], imp: h.grid_import_kwh || [], exp: h.grid_export_kwh || null, curt: h.curtailment_kwh || []
  };
}

function mapSweep(rows) {
  return (rows || []).map((r) => {
    const complete = (r.economics_status || null) === 'complete';
    return {
      kwp: num(r.requested_capacity_kwp),
      admission: mapAdmission(r.admission_status),
      constraintStatus: r.constraint_status || r.status || null,
      reasons: Array.isArray(r.constraint_reasons) ? r.constraint_reasons : [],
      economicsStatus: r.economics_status || null,
      totalCost: complete ? num(r.total_cost_npv_cny) : null,
      incremental: complete ? num(r.incremental_npv_vs_s0_cny) : null,
      gen: num(r.generation_kwh), selfUse: num(r.self_use_kwh), curtail: num(r.curtailment_kwh), gridImport: num(r.grid_import_kwh),
      selfUseRate: num(pick(r.self_use_rate, r.self_consumption_rate)), wasteRate: num(r.waste_rate),
      avoidedT: num(pick(r.avoided_tco2_study_period, r.carbon && r.carbon.avoided_tco2_study_period)),
      costPerT: num(pick(r.cost_per_tco2_cny, r.carbon && r.carbon.cost_per_tco2_cny))
    };
  });
}

function mapRecommendation(r) {
  if (!r) return null;
  const meta = RECOMMENDATION[r.status] || { label: r.status || '—', tone: 'unknown', note: '' };
  return {
    status: r.status, label: meta.label, tone: meta.tone, note: meta.note,
    scenarioId: r.scenario_id || null, reason: r.reason || '',
    eligible: r.eligible_scenario_ids || [], excluded: r.excluded_scenario_ids || [], unknown: r.unknown_scenario_ids || [],
    conclusion: r.all_candidates_conclusion || null
  };
}

function mapService(sq) {
  if (!sq) return null;
  const meta = SERVICE[sq.status] || { label: sq.status || '—', tone: 'unknown', icon: 'help', note: '' };
  const g = sq.gaps || {};
  return {
    status: sq.status, label: meta.label, tone: meta.tone, icon: meta.icon, note: meta.note, modelNote: sq.note || null,
    shortfallHours: num(g.capacity_shortfall_hours), unmetTempDegH: num(g.unmet_temp_degree_hours), unmetRhPctH: num(g.unmet_rh_percent_hours)
  };
}

function mapCarbonContext(cc) {
  if (!cc) return null;
  return {
    factor: cc.factor || null, comparison: cc.comparison_factor || null,
    price: num(cc.carbon_price_cny_per_t), priceNote: cc.carbon_price_note || null, priceSource: cc.carbon_price_source || null,
    cashflowNote: cc.cashflow_note || null, scopeNotes: cc.scope_notes || []
  };
}

/** 把请求体里的房间、屋顶、报价、电价等条件整理成显示用摘要（只搬运字段）。 */
function mapRequest(req) {
  req = req || {};
  const room = req.room || {}, pv = req.pv || {}, hy = req.hybrid || {};
  return {
    siteId: req.site_id || null, year: req.year ?? null,
    room,
    roomCount: room.room_count ?? null, unitsPerRoom: room.units_per_room ?? null, areaM2: room.area_m2 ?? null,
    equipmentId: room.equipment_id || null,
    weekdaysOnly: room.weekdays_only ?? null, startHour: room.start_hour ?? null, endHour: room.end_hour ?? null,
    roofM2: pv.roof_area_m2 ?? null, usableFraction: pv.usable_fraction ?? null,
    capacities: pv.requested_capacities_kwp || null, autoCapacity: !!pv.auto_capacity, fixedCapacity: pv.fixed_capacity_kwp ?? null,
    tariffId: pv.tariff_id || null, tariffApplication: pv.tariff_application || null,
    importPrice: hy.import_price_cny_per_kwh ?? pv.import_price_cny_per_kwh ?? null,
    budget: hy.budget_cny ?? null, allowExport: hy.allow_export ?? pv.allow_export ?? null, studyYears: hy.study_years ?? pv.study_years ?? null,
    pvQuote: hy.pv_quote || pv.quote || null, windQuote: hy.wind_quote || null,
    windCount: (hy.wind || {}).turbine_count ?? null, hubHeight: (hy.wind || {}).hub_height_m ?? null,
    carbon: req.carbon || null, storage: req.storage || null
  };
}

function siteName(id) {
  const c = app.options && (app.options.cities || []).find((x) => x.site_id === id);
  return c ? c.name : ({ guangzhou: '广州', beijing: '北京', harbin: '哈尔滨' }[id] || id);
}

function tariffInfo(id, reportTariff, sampleMain) {
  if (reportTariff && reportTariff.tariff_id) {
    return { id: reportTariff.tariff_id, title: reportTariff.source_title || reportTariff.area || reportTariff.tariff_id, area: reportTariff.area || null,
      provisional: reportTariff.verified === false, verified: reportTariff.verified === true, sourceUrl: reportTariff.source_url || null,
      effective: [reportTariff.effective_start, reportTariff.effective_end], priceType: reportTariff.price_type || null, notes: reportTariff.notes || [] };
  }
  const opt = app.options && ((app.options.tariffs || {}).tariffs || []).find((t) => t.tariff_id === id);
  if (opt) return { id, title: opt.source_title || opt.area, area: opt.area, provisional: opt.verified === false, verified: opt.verified === true, sourceUrl: opt.source_url, effective: [opt.effective_start, opt.effective_end], priceType: opt.price_type, notes: opt.notes || [] };
  if (sampleMain && sampleMain.tariff_id === id) return { id, title: id, area: null, provisional: sampleMain.provisional === true, verified: sampleMain.provisional === false, sourceUrl: sampleMain.source_url || null, effective: null, priceType: null, notes: [] };
  return id ? { id, title: id, provisional: null, verified: null, sourceUrl: null, notes: [] } : null;
}

/* ------------------------------------------------------------------ */
/* 结果 → 视图模型（实时与示例共用）                                     */
/* ------------------------------------------------------------------ */
function buildVM(src, ctx) {
  const rec = mapRecommendation(src.recommendation);
  const candidates = (src.candidates || []).map((c) => mapCandidate(c, rec && rec.scenarioId)).sort((a, b) => a.order - b.order);
  const lc = src.load_context || {};
  const plc = src.project_load_contract || lc.project_load_context || {};
  const request = ctx.request || {};
  const r = mapRequest(request);
  const tariff = tariffInfo(r.tariffId, ctx.reportTariff, ctx.sampleMain);
  const byId = Object.fromEntries(candidates.map((c) => [c.id, c]));
  return {
    kind: ctx.kind, caseId: ctx.caseId || null, label: ctx.label, sourceLabel: ctx.sourceLabel,
    computedAt: ctx.computedAt || null, request, req: r,
    site: { id: r.siteId, name: siteName(r.siteId) }, year: r.year,
    roomCount: num(pick(plc.room_count, lc.room_count, src.room_count)), unitsPerRoom: num(pick(plc.units_per_room, lc.units_per_room, src.units_per_room)),
    load: { annualKwh: num(pick(plc.electric_load_kwh, lc.electric_load_kwh)), scope: plc.scope || null, source: plc.source || null },
    service: mapService(lc.service_quality || src.service_quality),
    rec, candidates, byId,
    sweep: mapSweep(src.pv_capacity_sweep),
    recommendedKwp: num(pick(src.recommended_pv_capacity_kwp, (src.pv_recommendation || {}).recommended_capacity_kwp)),
    recommendationBasis: src.recommendation_basis || (src.pv_recommendation || {}).basis || null,
    hourly: ctx.hourly,
    carbonContext: mapCarbonContext(src.carbon_context),
    tariff,
    tariffApplication: r.tariffApplication,
    studyYears: num(pick(r.studyYears, (src.scenario || {}).study_years)),
    feasibility: src.feasibility || null,
    variantReason: src.variant_reason || null,
    notProvided: src.not_provided || [],
    storageContext: src.storage_context || null,
    timing: src.calculation_timing || null,
    provenance: ctx.provenance
  };
}

/** 实时接口：hybrid/run 或异步任务完成后的 result.report。逐时数据用各方案 hourly。 */
export function fromLive(report, request, extra = {}) {
  const byScenario = {};
  for (const c of report.candidates || []) if (c.hourly) byScenario[c.scenario_id] = mapHourly(c.hourly, c.scenario_id);
  const recId = (report.recommendation || {}).scenario_id;
  const wp = report.weather_provenance || {};
  return buildVM(report, {
    kind: 'live', label: '实时计算', sourceLabel: '本机实时计算', computedAt: extra.computedAt || Date.now(), request,
    reportTariff: report.tariff,
    hourly: { recommended: byScenario[recId] || null, combo: byScenario.S3_pv_wind || null, byScenario },
    provenance: {
      kind: '本机实时计算', calculationVersion: report.calculation_version || null,
      weatherHash: wp.hash || null, weatherSource: ((wp.context || {}).source) || null,
      weatherFile: wp.source_file ? String(wp.source_file).split(/[\\/]/).pop() : null,
      elapsedMs: (report.calculation_timing || {}).elapsed_ms ?? null, timingScope: (report.calculation_timing || {}).timing_scope || null,
      jobId: extra.jobId || null
    }
  });
}

/** 示例回放：replay_cases_v6.json 中的一个 case。逐时数据用 chart_recommended 与 chart（S3）。 */
export function fromSample(c, file) {
  const prov = (c.weather || {}).provenance || {};
  return buildVM(c, {
    kind: 'sample', caseId: c.case_id, label: c.label || c.case_id, sourceLabel: `示例 · ${c.label || c.case_id}`, request: c.request,
    sampleMain: file && file.main_tariff,
    hourly: { recommended: mapHourly(c.chart_recommended, (c.chart_recommended || {}).scenario_id), combo: mapHourly(c.chart, (c.chart || {}).scenario_id), byScenario: null },
    provenance: {
      kind: '5090 回放文件', file: 'docs/handoff/replay_viewer/replay_cases_v6.json', formatVersion: file ? file.format_version : null,
      sourceCommit: (c.source || {}).source_commit || null, calculationVersion: (c.source || {}).calculation_version || null,
      endpoint: (c.source || {}).endpoint || null, caseHash: c.case_hash || null,
      weatherHash: prov.hash || null, weatherSource: ((prov.context || {}).source) || null,
      weatherFile: (c.weather || {}).source ? String(c.weather.source).split(/[\\/]/).pop() : null,
      elapsedMs: ((c.http_trace || [])[0] || {}).elapsed_ms ?? null
    }
  });
}

/* ------------------------------------------------------------------ */
/* 典型周预览 → 视图模型                                                */
/* ------------------------------------------------------------------ */
const COLS = [['ts', 'timestamp'], ['load', 'load_kwh'], ['pv', 'pv_generation_kwh'], ['wind', 'wind_generation_kwh'], ['self', 'self_use_kwh'], ['imp', 'grid_import_kwh'], ['exp', 'grid_export_kwh'], ['curt', 'curtailment_kwh']];
export function fromPreview(resp, meta = {}) {
  if (!resp || resp.scope !== 'preview_period_physics_only') return null;
  const cands = {};
  for (const c of resp.candidates || []) {
    const series = {};
    for (const [k, f] of COLS) series[k] = (c.intervals || []).map((row) => row[f]);
    const s = c.summary || {};
    cands[c.scenario_id] = {
      id: c.scenario_id, pvKwp: num(c.pv_capacity_kwp), windCount: num(c.wind_turbine_count), series,
      summary: { load: num(s.load_kwh), pv: num(s.pv_generation_kwh), wind: num(s.wind_generation_kwh), gen: num(s.total_generation_kwh),
        self: num(s.self_use_kwh), imp: num(s.grid_import_kwh), exp: num(s.grid_export_kwh), curt: num(s.curtailment_kwh),
        selfRate: num(s.self_consumption_rate), coverage: num(s.load_coverage_rate) }
    };
  }
  const p = resp.preview || {};
  return {
    kind: meta.kind || 'live', label: meta.label || null,
    scope: resp.scope, scopeNote: resp.scope_note,
    season: p.season || meta.season || null, month: p.month ?? null, start: p.start || null, end: p.end_exclusive || null,
    rule: p.selection_rule || null, rows: p.row_count ?? null,
    pvInput: resp.pv_input || null, windInput: resp.wind_input || null,
    elapsedMs: (resp.calculation_timing || {}).elapsed_ms ?? meta.elapsedMs ?? null,
    candidates: cands
  };
}

/** 示例的典型周预览（replay_previews_v7.json）。tier 为 tier_small 等，season 为 summer/winter。 */
export function samplePreview(samples, tier, season) {
  const p = samples && samples.previews.get(`${tier}_${season}`);
  if (!p) return null;
  return fromPreview(p.response, { kind: 'sample', season, label: p.case_id, elapsedMs: p.http_elapsed_ms });
}

/** 示例 case 对应的典型周档位（状态变体与小档同一房间口径，但没有单独的预览回放）。 */
export function previewTierOf(caseId) {
  return ['tier_small', 'tier_medium', 'tier_large'].includes(caseId) ? caseId : null;
}
