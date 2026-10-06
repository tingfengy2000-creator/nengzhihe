/* 能智核 · 数据适配层
 *
 * 职责：把“5090 固定回放样例”和“本机实时 API 响应”映射成同一个视图模型。
 * 约束（见 docs/handoff/5060_review_and_ui_direction.md）：
 *   - 本层不做任何数值计算：不聚合电量、不算成本/NPV、不推断房间配置；
 *     只做字段映射、状态翻译和显示格式化。
 *   - 样例里没有的字段返回 null，由界面显示“样例未记录”或“待5090确认”。
 *   - 唯一的显示聚合（逐月、典型日）放在 charts.js，并标注为显示用途。
 */
(function () {
  'use strict';

  const SAMPLE_BASE = '/samples/';

  /* ---------- 术语映射：主界面用中文，技术名只进依据抽屉 ---------- */
  const SCENARIOS = {
    S0_grid:    { name: '只用电网',     short: '电网',     desc: '不加装发电设备，作为比较基线', color: 'var(--c-grid)', order: 0 },
    S1_pv:      { name: '加装光伏',     short: '光伏',     desc: '屋顶光伏，发电优先供空调使用', color: 'var(--c-pv)',   order: 1 },
    S2_wind:    { name: '加装小风机',   short: '小风机',   desc: '小型风力发电机',               color: 'var(--c-wind)', order: 2 },
    S3_pv_wind: { name: '光伏+小风机', short: '光伏+风机', desc: '两种发电设备组合',             color: 'var(--c-self)', order: 3 }
  };

  const ADMISSION = {
    eligible:   { label: '可比较',   tone: 'ok',      icon: 'check', note: '条件齐全，参与比较' },
    unknown:    { label: '条件不全', tone: 'unknown', icon: 'help',  note: '报价或必要条件缺失，暂无法比较——不是淘汰' },
    excluded:   { label: '已排除',   tone: 'bad',     icon: 'x',     note: '明确超出预算、屋顶或高度等限制' },
    equivalent: { label: '与其他方案相同', tone: 'unknown', icon: 'equal', note: '结果与另一方案相同' }
  };

  const RECOMMENDATION = {
    conditional:        { label: '有条件推荐', tone: 'brand',   note: '在条件齐全、可比较的方案中最省钱' },
    conditional_subset: { label: '部分比较',   tone: 'warn',    note: '部分方案条件不全，仅在其余方案中比较；不能说它们已被击败' },
    not_available:      { label: '暂无推荐',   tone: 'unknown', note: '可比较的方案不足' }
  };

  const SERVICE = {
    service_gap:          { label: '空调有缺口', tone: 'warn', note: '模型中存在冷量或除湿不足的时段。结果不代表同等舒适度下的最优投资。' },
    within_modeled_scope: { label: '空调达标',   tone: 'ok',   note: '在模型范围内满足设定温湿度（未经现场校准）。' }
  };

  const CONSTRAINT_TEXT = {
    feasible: '满足限制条件',
    over_budget: '超出预算',
    not_applicable: '场地条件不满足',
    incomplete_quote: '缺少报价',
    height_limit: '超出高度限制'
  };

  /* ---------- 格式化 ---------- */
  const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
  const nf0 = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1, minimumFractionDigits: 0 });

  const fmt = {
    money(v) { return isNum(v) ? nf0.format(Math.round(v)) : '—'; },
    kwh(v) { return isNum(v) ? nf0.format(Math.round(v)) : '—'; },
    num(v, digits = 1) { return isNum(v) ? (digits === 0 ? nf0 : nf1).format(v) : '—'; },
    pct(v) { return isNum(v) ? `${nf0.format(Math.round(v * 100))}%` : '—'; },
    /** 相对“只用电网”的增量现值：负数＝多花，正数＝省下；保留方向，不取绝对值后丢符号。 */
    delta(incr) {
      if (!isNum(incr)) return { dir: 'na', text: '暂无法比较', amount: null };
      const r = Math.round(incr);
      if (r === 0) return { dir: 'base', text: '与只用电网相同', amount: 0 };
      if (r < 0) return { dir: 'more', text: `比只用电网多花 ${nf0.format(-r)} 元`, short: `多花 ${nf0.format(-r)} 元`, amount: r };
      return { dir: 'less', text: `比只用电网省下 ${nf0.format(r)} 元`, short: `省下 ${nf0.format(r)} 元`, amount: r };
    },
    sha(s, n = 7) { return typeof s === 'string' && s ? s.slice(0, n) : '—'; },
    datetime(ts) {
      try { return new Date(ts).toLocaleString('zh-CN', { hour12: false }); } catch (e) { return String(ts); }
    }
  };

  /* ---------- 读取样例 ---------- */
  const cache = {};
  async function loadSampleFile(name) {
    if (cache[name]) return cache[name];
    const res = await fetch(SAMPLE_BASE + encodeURIComponent(name), { cache: 'no-store' });
    if (!res.ok) throw new Error(`样例文件读取失败（${res.status}）：${name}。请用 operation_planning.run_server 启动本地服务。`);
    cache[name] = await res.json();
    return cache[name];
  }

  /* ---------- 候选方案映射 ---------- */
  function mapCandidate(c, recommendedId) {
    const meta = SCENARIOS[c.scenario_id] || { name: c.scenario_id, short: c.scenario_id, desc: '', color: 'var(--ink-3)', order: 9 };
    const adm = ADMISSION[c.admission_status] || { label: c.admission_status || '未知状态', tone: 'unknown', icon: 'help', note: '' };
    const pick = (k) => (Object.prototype.hasOwnProperty.call(c, k) ? c[k] : undefined);
    return {
      id: c.scenario_id,
      name: meta.name, short: meta.short, desc: meta.desc, color: meta.color, order: meta.order,
      admission: Object.assign({ status: c.admission_status }, adm),
      constraintStatus: c.constraint_status || null,
      constraintText: CONSTRAINT_TEXT[c.constraint_status] || c.constraint_status || null,
      reasons: Array.isArray(c.constraint_reasons) ? c.constraint_reasons.slice() : [],
      economicsStatus: c.economics_status || null,
      equivalentTo: c.equivalent_to || null,
      // 费用字段：按契约原样读取；undefined 表示样例未保存该字段，null 表示计算上不可得
      totalCost: pick('total_cost_npv_cny'),
      incremental: pick('incremental_npv_vs_s0_cny'),
      npv: pick('npv_cny'),
      capex: pick('capex_cny'),
      pvKwp: pick('pv_capacity_kwp'),
      windCount: pick('wind_turbine_count'),
      gen: pick('generation_kwh'),
      pvGen: pick('pv_generation_kwh'),
      windGen: pick('wind_generation_kwh'),
      selfUse: pick('self_use_kwh'),
      gridImport: pick('grid_import_kwh'),
      gridExport: pick('grid_export_kwh'),
      curtail: pick('curtailment_kwh'),
      coverage: pick('load_coverage_rate'),
      isRecommended: c.scenario_id === recommendedId,
      hourly: c.hourly || null,
      raw: c
    };
  }

  function mapRecommendation(r) {
    if (!r) return null;
    const meta = RECOMMENDATION[r.status] || { label: r.status || '—', tone: 'unknown', note: '' };
    return {
      status: r.status, label: meta.label, tone: meta.tone, note: meta.note,
      scenarioId: r.scenario_id || null,
      reason: r.reason || '',
      conclusion: r.all_candidates_conclusion || null,
      eligible: r.eligible_scenario_ids || [],
      excluded: r.excluded_scenario_ids || [],
      unknown: r.unknown_scenario_ids || [],
      raw: r
    };
  }

  function mapService(sq) {
    if (!sq) return null;
    const meta = SERVICE[sq.status] || { label: sq.status, tone: 'unknown', note: '' };
    return { status: sq.status, label: meta.label, tone: meta.tone, note: sq.note || meta.note, gaps: sq.gaps || {}, scope: sq.scope || null };
  }

  function mapHourly(h, scenarioId, inheritedFrom) {
    if (!h || !Array.isArray(h.timestamps)) return null;
    return {
      scenarioId: h.scenario_id || scenarioId || null,
      timestamps: h.timestamps,
      load: h.load_kwh || [], pv: h.pv_generation_kwh || [], wind: h.wind_generation_kwh || [],
      self: h.self_use_kwh || [], imp: h.grid_import_kwh || [], exp: h.grid_export_kwh || [], curtail: h.curtailment_kwh || [],
      windSpeed: h.wind_speed_hub_m_s || null,
      samplingRule: h.sampling_rule || null,
      inheritedFrom: inheritedFrom || null
    };
  }

  /* ---------- 回放样例 → 视图模型 ---------- */
  function sameSource(a, b) {
    return !!(a && b && a.source_result_sha256 && a.source_result_sha256 === b.source_result_sha256 && a.source_commit === b.source_commit);
  }

  function fromReplay(file, caseId) {
    const cases = file.cases || [];
    const c = cases.find((x) => x.case_id === caseId) || cases[0];
    if (!c) throw new Error('样例文件中没有可用案例');
    const base = cases[0];
    // 变体案例（预算/报价/屋顶）只记录与默认样例不同的条件。仅当源文件与哈希完全相同时，
    // 才把默认样例的负荷与逐时数据作为“同源数据”显示，并在界面注明来源。
    const inherits = c !== base && sameSource(c.source, base.source);
    const loadCtx = c.load_context || (inherits ? base.load_context : null);
    const chart = c.chart || (inherits ? base.chart : null);
    const rec = mapRecommendation(c.recommendation);
    const candidates = (c.candidates || []).map((x) => mapCandidate(x, rec && rec.scenarioId)).sort((a, b) => a.order - b.order);
    const inputs = Object.assign({}, inherits ? base.input : {}, c.input || {});

    return {
      mode: 'replay',
      caseId: c.case_id,
      label: c.label || c.case_id,
      provenance: {
        kind: '5090已验算样例',
        sourceCommit: (c.source || {}).source_commit || (file.source || {}).source_commit || null,
        calculationVersion: (c.source || {}).calculation_version || null,
        sourceFile: (c.source || {}).source_result_file || null,
        sourceSha256: (c.source || {}).source_result_sha256 || null,
        summaryFile: (c.source || {}).summary_result_file || null,
        summarySha256: (c.source || {}).summary_result_sha256 || null,
        sampleFile: 'docs/handoff/replay_viewer/replay_cases.json',
        formatVersion: file.format_version || null,
        inheritsFrom: inherits ? base.case_id : null,
        inheritsLabel: inherits ? (base.label || base.case_id) : null,
        weather: c.weather || (inherits ? base.weather : null)
      },
      inputs,
      recordedInputs: c.input || {},
      // 样例 load_context 没有房间数/台数字段：明确返回 null，界面显示“待5090确认”，不猜。
      roomConfig: (loadCtx && (loadCtx.room_count != null || loadCtx.units_per_room != null))
        ? { roomCount: loadCtx.room_count ?? null, unitsPerRoom: loadCtx.units_per_room ?? null }
        : null,
      load: { annualKwh: loadCtx ? loadCtx.electric_load_kwh ?? null : null, inherited: !c.load_context && !!loadCtx },
      service: mapService((loadCtx && loadCtx.service_quality) || c.service_quality),
      recommendation: rec,
      candidates,
      hourly: chart ? mapHourly(chart, chart.scenario_id, c.chart ? null : base.case_id) : null,
      notProvided: c.not_provided || [],
      studyYears: inputs.study_years ?? null,
      importPrice: inputs.import_price_cny_per_kwh ?? null,
      displayContract: file.display_contract || null,
      computedAt: null
    };
  }

  /** 样例里可比较的条件（用于判断“改过的条件是否正好对应另一个已验算样例”）。 */
  function replayConditions(file, caseId) {
    const vm = fromReplay(file, caseId);
    return vm.inputs;
  }

  /* ---------- 实时 API 响应 → 视图模型 ---------- */
  function fromLive(report, request) {
    const rec = mapRecommendation(report.recommendation);
    const candidates = (report.candidates || []).map((x) => mapCandidate(x, rec && rec.scenarioId)).sort((a, b) => a.order - b.order);
    const lc = report.load_context || {};
    const plc = lc.project_load_context || {};
    const show = candidates.find((x) => x.id === 'S3_pv_wind' && x.hourly) || candidates.find((x) => x.hourly);
    return {
      mode: 'live',
      caseId: null,
      label: '本机实时计算',
      provenance: {
        kind: '本机实时计算',
        sourceCommit: null,
        calculationVersion: report.calculation_version || null,
        weather: report.weather_provenance || null,
        projectLoad: plc
      },
      inputs: request || {},
      recordedInputs: request || {},
      roomConfig: (plc.room_count != null || lc.room_count != null)
        ? { roomCount: plc.room_count ?? lc.room_count ?? null, unitsPerRoom: plc.units_per_room ?? lc.units_per_room ?? null }
        : null,
      load: { annualKwh: lc.electric_load_kwh ?? null, inherited: false },
      service: mapService(lc.service_quality),
      recommendation: rec,
      candidates,
      hourly: show ? mapHourly(show.hourly, show.id, null) : null,
      notProvided: ['现场测风', '并网审批', '已核实采购报价', '同等服务水平保证'],
      studyYears: (report.scenario || {}).study_years ?? null,
      importPrice: (report.scenario || {}).import_price_cny_per_kwh ?? null,
      displayContract: null,
      computedAt: Date.now(),
      raw: report
    };
  }

  window.NZH = window.NZH || {};
  window.NZH.data = {
    SCENARIOS, ADMISSION, RECOMMENDATION, SERVICE, CONSTRAINT_TEXT,
    fmt, isNum, loadSampleFile, fromReplay, fromLive, replayConditions, sameSource
  };
})();
