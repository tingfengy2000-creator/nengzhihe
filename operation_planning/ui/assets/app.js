/* 能智核 · 主程序（任务流、表单、路由、依据抽屉）
 *
 * 数字规则：页面上的年用电量、金额、发电量全部来自视图模型（data.js），
 * 本文件不写死任何结果数值，也不在前端做聚合或经济计算。
 */
(function () {
  'use strict';
  const D = window.NZH.data;
  const C = window.NZH.charts;
  const fmt = D.fmt;

  /* ------------------------------------------------------------------ */
  /* 小工具                                                              */
  /* ------------------------------------------------------------------ */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const ICONS = {
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    x: '<path d="M7 7l10 10M17 7 7 17"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.3a2.5 2.5 0 1 1 3.4 2.4c-.7.3-1 .8-1 1.5v.4M12 17h.01"/>',
    equal: '<path d="M6 9.5h12M6 14.5h12"/>',
    warn: '<path d="M12 3.5 2.8 19.5h18.4L12 3.5z"/><path d="M12 10v4M12 17h.01"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    star: '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9L12 3.5z"/>',
    spark: '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
    doc: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    back: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'
  };
  const icon = (name, cls = '') => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
  const tag = (tone, text, ic) => `<span class="tag tag-${tone}">${ic ? icon(ic) : ''}${esc(text)}</span>`;

  function toast(msg) {
    const t = $('#toast'); t.textContent = msg; t.classList.add('is-on');
    clearTimeout(toast._h); toast._h = setTimeout(() => t.classList.remove('is-on'), 2600);
  }

  /* ------------------------------------------------------------------ */
  /* 表单定义                                                            */
  /* ------------------------------------------------------------------ */
  // room: true 表示房间参数；回放样例的 load_context 未记录房间配置 → 显示“待5090确认”
  const FIELDS = [
    { key: 'site_id', group: 'basic', label: '城市', type: 'select', options: [['guangzhou', '广州'], ['beijing', '北京'], ['harbin', '哈尔滨']] },
    { key: 'year', group: 'basic', label: '天气参考年', type: 'select', num: true, options: [[2023, '2023 年'], [2024, '2024 年'], [2025, '2025 年']] },
    { key: 'area_m2', group: 'basic', label: '单间面积', unit: '㎡', type: 'number', room: true, min: 1, step: 1 },
    { key: 'room_count', group: 'basic', label: '同类房间数', unit: '间', type: 'number', room: true, min: 1, step: 1, hint: '朝向、使用时段、设备都相同的房间' },
    { key: 'units_per_room', group: 'basic', label: '每间空调台数', unit: '台', type: 'number', room: true, min: 1, step: 1 },
    { key: 'start_hour', group: 'basic', label: '使用开始', unit: '点', type: 'number', room: true, min: 0, max: 23, step: 1, nl: true },
    { key: 'end_hour', group: 'basic', label: '使用结束', unit: '点', type: 'number', room: true, min: 1, max: 24, step: 1, nl: true },
    { key: 'cooling_setpoint_c', group: 'basic', label: '目标温度', unit: '℃', type: 'number', room: true, step: 0.5 },
    { key: 'rh_setpoint_percent', group: 'basic', label: '目标湿度', unit: '%', type: 'number', room: true, step: 1 },
    { key: 'study_years', group: 'basic', label: '比较年限', unit: '年', type: 'number', min: 1, step: 1 },

    { key: 'pv_capacity_kwp', group: 'supply', label: '光伏容量', unit: 'kWp', type: 'number', min: 0, step: 0.5, nl: true },
    { key: 'roof_area_m2', group: 'supply', label: '可装光伏屋顶面积', unit: '㎡', type: 'number', min: 0, step: 1 },
    { key: 'wind_turbine_count', group: 'supply', label: '小风机台数', type: 'select', num: true, options: [[0, '不装'], [1, '1 台']], nl: true },
    { key: 'hub_height_m', group: 'supply', label: '风机安装高度', unit: 'm', type: 'number', min: 1, step: 0.5, nl: true },
    { key: 'budget_cny', group: 'supply', label: '初始投入预算', unit: '元', type: 'number', min: 0, step: 1000, nl: true },
    { key: 'import_price_cny_per_kwh', group: 'supply', label: '购电价格', unit: '元/kWh', type: 'number', min: 0, step: 0.01, nl: true },
    { key: 'pv_quote_complete', group: 'supply', label: '光伏报价', type: 'select', bool: true, options: [[true, '已提供'], [false, '缺少报价']] },
    { key: 'allow_export', group: 'supply', label: '多余电量卖给电网', type: 'switch', nl: true },

    { key: 'orientation', group: 'more', label: '朝向', type: 'select', room: true, options: [['south', '南'], ['north', '北'], ['east', '东'], ['west', '西']] },
    { key: 'window_wall_ratio', group: 'more', label: '窗墙比', type: 'number', room: true, min: 0, max: 0.9, step: 0.05 },
    { key: 'people_count', group: 'more', label: '每间人数', unit: '人', type: 'number', room: true, min: 0, step: 1 }
  ];
  const FIELD = Object.fromEntries(FIELDS.map((f) => [f.key, f]));
  const blankForm = () => Object.fromEntries(FIELDS.map((f) => [f.key, null]));

  /** 从视图模型的输入条件填表：样例未记录的字段保持 null。 */
  function formFromInputs(inputs) {
    const f = blankForm();
    const map = {
      site_id: 'site_id', year: 'year', study_years: 'study_years', pv_capacity_kwp: 'pv_capacity_kwp', roof_area_m2: 'roof_area_m2',
      wind_turbine_count: 'wind_turbine_count', hub_height_m: 'hub_height_m', budget_cny: 'budget_cny',
      import_price_cny_per_kwh: 'import_price_cny_per_kwh', allow_export: 'allow_export', pv_quote_complete: 'pv_quote_complete'
    };
    for (const [k, src] of Object.entries(map)) if (inputs && inputs[src] !== undefined) f[k] = inputs[src];
    return f;
  }
  const normForm = (f) => JSON.stringify(FIELDS.map((x) => [x.key, f[x.key] ?? null]));

  /* ------------------------------------------------------------------ */
  /* 状态                                                                */
  /* ------------------------------------------------------------------ */
  const state = {
    mode: 'replay',          // replay：5090 已验算样例；live：本机实时 API
    file: null,              // replay_cases.json
    caseId: null,
    form: blankForm(),
    resultForm: null,        // 产生当前结果时的表单快照
    vm: null,                // 当前结果视图模型
    pending: null,           // 待 5090 验算：{ changes: [...] }
    stale: false,
    step: 1,
    ask: { text: '', applied: [], rejected: [] },
    loading: false,
    error: null
  };
  window.NZH.state = state;

  function changedFields(a, b) {
    if (!a || !b) return [];
    return FIELDS.filter((f) => (a[f.key] ?? null) !== (b[f.key] ?? null)).map((f) => f.key);
  }
  function fieldDisplay(key, v) {
    const f = FIELD[key];
    if (v === null || v === undefined) return '未填写';
    if (f.type === 'select') { const o = f.options.find((x) => String(x[0]) === String(v)); return o ? o[1] : String(v); }
    if (f.type === 'switch') return v ? '允许' : '不允许';
    return `${v}${f.unit ? ' ' + f.unit : ''}`;
  }

  /* ------------------------------------------------------------------ */
  /* 一句话输入：只解析当前修改 schema 支持的字段                         */
  /* （使用时段、预算、光伏容量、小风机台数/高度、电价、是否外送）         */
  /* 房间数、台数、面积、城市等不在 schema 内 → 明确提示“请在下方表单修改” */
  /* ------------------------------------------------------------------ */
  function parseAsk(text) {
    const applied = [], rejected = [];
    const t = String(text || '').replace(/\s+/g, '');
    if (!t) return { applied, rejected };
    const num = (s) => Number(String(s).replace(/,/g, ''));
    let m;
    if ((m = t.match(/(\d{1,2})(?:[:：]00)?点?(?:到|至|-|—|~)(\d{1,2})(?:[:：]00)?点/))) {
      const a = num(m[1]), b = num(m[2]);
      if (a >= 0 && a <= 23 && b >= 1 && b <= 24 && b > a) { applied.push(['start_hour', a]); applied.push(['end_hour', b]); }
      else rejected.push([m[0], '时段不合法']);
    }
    if ((m = t.match(/预算(?:为|是|约)?(\d+(?:\.\d+)?)(万|w|W)?(?:元)?/))) applied.push(['budget_cny', Math.round(num(m[1]) * (m[2] ? 10000 : 1))]);
    if ((m = t.match(/(\d+(?:\.\d+)?)(?:kWp|kwp|千瓦)(?:的)?光伏|光伏(\d+(?:\.\d+)?)(?:kWp|kwp|千瓦)/))) applied.push(['pv_capacity_kwp', num(m[1] || m[2])]);
    if (/不装(?:小)?风机|不要(?:小)?风机/.test(t)) applied.push(['wind_turbine_count', 0]);
    else if ((m = t.match(/([01一])台(?:小)?风机/))) applied.push(['wind_turbine_count', m[1] === '0' ? 0 : 1]);
    else if ((m = t.match(/(\d+)台(?:小)?风机/))) rejected.push([m[0], '小风机目前只支持 0 或 1 台']);
    if ((m = t.match(/(?:风机|轮毂)(?:安装)?(?:高度)?(\d+(?:\.\d+)?)(?:米|m)/))) applied.push(['hub_height_m', num(m[1])]);
    if ((m = t.match(/电价(?:为|是)?(\d+(?:\.\d+)?)元?/))) applied.push(['import_price_cny_per_kwh', num(m[1])]);
    if (/不(?:允许)?外送|不卖电|不上网/.test(t)) applied.push(['allow_export', false]);
    else if (/允许外送|可以外送|余电上网|卖给电网/.test(t)) applied.push(['allow_export', true]);

    // 识别到但不支持一句话修改的内容
    const unsupported = [
      [/(\d+)间/, '房间数'], [/每间(\d+)台|(\d+)台空调/, '空调台数'], [/(\d+(?:\.\d+)?)(?:㎡|平方米|平米|m2)/, '面积'],
      [/广州|北京|哈尔滨|上海|深圳|成都|杭州|武汉|西安|南京/, '城市'], [/(\d+)人/, '人数'], [/(\d+)度|(\d+)℃/, '温度']
    ];
    for (const [re, name] of unsupported) {
      const hit = t.match(re);
      if (hit && !(name === '面积' && /屋顶/.test(t.slice(Math.max(0, hit.index - 4), hit.index)))) rejected.push([hit[0], `${name}请在下方表单修改`]);
    }
    return { applied, rejected };
  }

  /* ------------------------------------------------------------------ */
  /* 路由                                                                */
  /* ------------------------------------------------------------------ */
  function route() {
    const h = location.hash || '#/new/1';
    const plans = h.startsWith('#/plans');
    $('#view-new').hidden = plans;
    $('#view-plans').hidden = !plans;
    $$('.nav a').forEach((a) => a.toggleAttribute('aria-current', false));
    const cur = $(`.nav a[data-nav="${plans ? 'plans' : 'new'}"]`); if (cur) cur.setAttribute('aria-current', 'page');
    if (plans) { renderPlans(); window.scrollTo(0, 0); return; }
    const m = h.match(/#\/new\/(\d)/);
    setStep(m ? Number(m[1]) : 1, false);
  }

  function setStep(n, push = true) {
    state.step = Math.min(4, Math.max(1, n));
    if (push && location.hash !== `#/new/${state.step}`) { history.replaceState(null, '', `#/new/${state.step}`); }
    $$('.stepper a').forEach((a) => {
      const s = Number(a.dataset.step);
      a.toggleAttribute('aria-current', false);
      if (s === state.step) a.setAttribute('aria-current', 'step');
      a.classList.toggle('is-done', s < state.step && hasResult());
    });
    $$('[data-step-panel]').forEach((p) => { p.hidden = Number(p.dataset.stepPanel) !== state.step; });
    $('#resultZone').hidden = state.step === 1;
    $('#intro').classList.toggle('is-compact', state.step !== 1);
    renderStep(state.step);
  }
  const hasResult = () => !!state.vm || !!state.pending;

  /* ------------------------------------------------------------------ */
  /* 第 1 步：描述场景                                                   */
  /* ------------------------------------------------------------------ */
  function fieldHtml(f) {
    const v = state.form[f.key];
    const roomPending = state.mode === 'replay' && f.room && v == null;
    const placeholder = roomPending ? '待5090确认' : (state.mode === 'replay' ? '样例未记录' : '使用模型默认值');
    const id = `f_${f.key}`;
    const hint = f.hint ? `<span class="hint">${esc(f.hint)}</span>` : '';
    if (f.type === 'switch') {
      return `<div class="field"><span class="label">${esc(f.label)}</span>
        <label class="switch"><input type="checkbox" id="${id}" data-field="${f.key}" ${v ? 'checked' : ''}><span class="track"></span><span>${v == null ? '样例未记录' : (v ? '允许' : '不允许')}</span></label>${hint}</div>`;
    }
    if (f.type === 'select') {
      const opts = [`<option value="" ${v == null ? 'selected' : ''} disabled>${esc(placeholder)}</option>`]
        .concat(f.options.map(([val, lab]) => `<option value="${esc(val)}" ${String(v) === String(val) ? 'selected' : ''}>${esc(lab)}</option>`)).join('');
      return `<div class="field${roomPending ? ' is-pending' : ''}"><label for="${id}">${esc(f.label)}</label><select class="select" id="${id}" data-field="${f.key}">${opts}</select>${hint}</div>`;
    }
    const attrs = ['min', 'max', 'step'].filter((k) => f[k] !== undefined).map((k) => `${k}="${f[k]}"`).join(' ');
    const input = `<input class="input" id="${id}" type="number" inputmode="decimal" ${attrs} data-field="${f.key}" value="${v == null ? '' : esc(v)}" placeholder="${esc(placeholder)}">`;
    return `<div class="field${roomPending ? ' is-pending' : ''}"><label for="${id}">${esc(f.label)}</label>${f.unit ? `<div class="input-group">${input}<span class="unit">${esc(f.unit)}</span></div>` : input}${hint}</div>`;
  }

  function sampleListHtml() {
    if (!state.file) return '';
    const items = state.file.cases.map((c) => {
      const vm = D.fromReplay(state.file, c.case_id);
      const sub = c.case_id === state.file.cases[0].case_id ? '完整逐时数据' : '方案汇总';
      return `<button class="sample" type="button" data-action="pick-sample" data-case="${esc(c.case_id)}" aria-pressed="${state.caseId === c.case_id && !state.pending && state.mode === 'replay'}">
        <b>${esc(vm.label)}</b><span>${esc(sub)} · 源码 ${esc(fmt.sha(vm.provenance.sourceCommit))}</span></button>`;
    }).join('');
    return `<section class="card card-flat">
      <div class="section-head"><div><h3 class="card-title">从已验算样例开始</h3>
        <p>以下样例由 5090 计算机完整运行并验收。选择一个即可走完四步；改动条件后会提示“待5090验算”，不会拿旧结果冒充。</p></div></div>
      <div class="sample-list">${items}</div></section>`;
  }

  function askHtml() {
    const a = state.ask;
    const chips = a.applied.map(([k, v]) => `<button class="chip is-applied" type="button" data-action="focus-field" data-field="${k}"><span class="k">${esc(FIELD[k].label)}</span>${esc(fieldDisplay(k, v))}</button>`)
      .concat(a.rejected.map(([txt, why]) => `<span class="chip is-rejected" title="${esc(why)}">${icon('info')}「${esc(txt)}」${esc(why)}</span>`)).join('');
    const none = a.text && !a.applied.length && !a.rejected.length ? `<p class="small subtle">没有识别到可修改的条件，请直接在下方表单修改。</p>` : '';
    return `<section class="stack">
      <form class="ask" id="askForm" autocomplete="off">
        ${icon('spark')}
        <input id="askInput" type="text" value="${esc(a.text)}" aria-label="用一句话描述修改" placeholder="一句话修改条件，例如：工作日 8 点到 18 点，预算 6 万，不装风机">
        <button class="btn btn-primary btn-sm" type="submit">识别</button>
      </form>
      <p class="xs subtle">本地规则识别，只处理使用时段、预算、光伏容量、小风机台数与高度、电价、是否外送；房间数、台数、面积等请在下方表单修改。识别结果直接写入表单，可逐项点改。</p>
      ${chips ? `<div class="chips">${chips}</div>` : ''}${none}
    </section>`;
  }

  function renderStep1() {
    const basic = FIELDS.filter((f) => f.group === 'basic').map(fieldHtml).join('');
    const supply = FIELDS.filter((f) => f.group === 'supply').map(fieldHtml).join('');
    const more = FIELDS.filter((f) => f.group === 'more').map(fieldHtml).join('');
    const modeNote = state.mode === 'replay'
      ? `${icon('info')}<div><p><b>当前为“5090已验算样例”模式</b></p><p class="sub">样例只记录了部分条件；未记录的房间参数显示“待5090确认”。需要任意条件实时计算时，可在“数据与边界”中切换到本机实时计算（需要完整计算环境）。</p></div>`
      : `${icon('info')}<div><p><b>当前为“本机实时计算”模式</b></p><p class="sub">点击“开始试算”会调用本机计算服务；未填写的房间参数使用模型默认值。报价未填写时，对应方案会显示“条件不全”。</p></div>`;
    $('#step1').innerHTML = `
      <div class="step-head"><div><h2>描述场景</h2><p>告诉我们房间怎么用、能装什么、预算多少。数字都写在表单里，随时可改。</p></div></div>
      ${state.mode === 'replay' ? sampleListHtml() : ''}
      <div class="banner banner-brand">${modeNote}</div>
      ${askHtml()}
      <section class="card">
        <div class="section-head"><div><h3 class="card-title">房间与使用</h3><p>按“同类房间”计算：单间负荷乘房间数由计算服务完成，页面不重复相乘。</p></div></div>
        <div class="form-grid">${basic}</div>
      </section>
      <section class="card">
        <div class="section-head"><div><h3 class="card-title">发电设备与预算</h3><p>只用电网始终作为比较基线；这里决定光伏和小风机方案的规模与限制。</p></div></div>
        <div class="form-grid">${supply}</div>
        <details class="more mt-3"><summary>更多条件</summary>
          <div class="form-grid mt-2">${more}</div>
          <p class="xs subtle mt-2">报价明细、寿命、电价档案和上传天气文件将在下一轮接入表单；样例中的报价为用户情景，并非已核实的采购报价。</p>
        </details>
      </section>
      <div class="run-bar">
        <span class="status" id="runStatus">${runStatusHtml()}</span>
        <div class="row">
          ${state.mode === 'replay' && state.pending ? '<button class="btn" type="button" data-action="restore-sample">恢复样例条件</button>' : ''}
          <button class="btn btn-primary btn-lg" type="button" data-action="run">${state.mode === 'replay' ? '查看结果' : '开始试算'} ${icon('arrow')}</button>
        </div>
      </div>`;
  }

  function runStatusHtml() {
    if (state.loading) return `${icon('clock')}正在等待计算服务返回…`;
    if (state.error) return `<span class="neg">${esc(state.error)}</span>`;
    if (state.stale) return `${icon('warn')}条件已修改，需要重新计算`;
    if (state.vm) return `${icon('check')}结果与当前条件一致`;
    return `${icon('info')}尚未计算`;
  }

  /* ------------------------------------------------------------------ */
  /* 计算 / 取结果                                                       */
  /* ------------------------------------------------------------------ */
  function buildLiveRequest() {
    const f = state.form;
    const pick = (keys) => Object.fromEntries(keys.filter((k) => f[k] != null).map((k) => [k, f[k]]));
    const room = pick(['area_m2', 'room_count', 'units_per_room', 'start_hour', 'end_hour', 'cooling_setpoint_c', 'rh_setpoint_percent', 'orientation', 'window_wall_ratio', 'people_count']);
    const hybrid = pick(['pv_capacity_kwp', 'budget_cny', 'import_price_cny_per_kwh', 'allow_export', 'study_years']);
    const wind = pick(['hub_height_m']); if (f.wind_turbine_count != null) wind.turbine_count = f.wind_turbine_count;
    if (Object.keys(wind).length) hybrid.wind = wind;
    const pv = pick(['roof_area_m2']);
    const req = { use_agent: false, room, pv, hybrid };
    if (f.site_id) req.site_id = f.site_id;
    if (f.year) req.year = f.year;
    if (state.ask.text) req.request = state.ask.text;
    return req;
  }

  async function run() {
    state.error = null;
    if (state.mode === 'replay') {
      // 只有当前条件与某个已验算样例完全一致时才显示样例结果
      const match = state.file.cases.find((c) => normForm(formFromInputs(D.fromReplay(state.file, c.case_id).inputs)) === normForm(state.form)
        && (c.case_id === state.caseId));
      if (match) {
        state.vm = D.fromReplay(state.file, match.case_id); state.pending = null;
      } else {
        const base = formFromInputs(D.fromReplay(state.file, state.caseId).inputs);
        state.vm = null; state.pending = { changes: changedFields(base, state.form).map((k) => ({ key: k, from: base[k], to: state.form[k] })) };
      }
      state.resultForm = JSON.parse(JSON.stringify(state.form));
      state.stale = false;
      afterResult();
      return;
    }
    // 实时计算：调用本机服务（5090 或已安装完整依赖的环境）
    state.loading = true; renderStep(state.step);
    try {
      const req = buildLiveRequest();
      const res = await fetch('/api/operation/hybrid/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req) });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || body.status !== 'success') throw new Error(body.error || `计算服务返回 ${res.status}`);
      state.vm = D.fromLive(body.report, req); state.pending = null;
      state.resultForm = JSON.parse(JSON.stringify(state.form)); state.stale = false;
      afterResult();
    } catch (e) {
      state.error = `计算失败：${e.message}`;
      toast(state.error);
    } finally {
      state.loading = false; renderStep(state.step);
    }
  }

  function afterResult() {
    if (window.NZH.onResult) window.NZH.onResult(state);
    setStep(state.step === 1 ? 3 : state.step);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function markChanged() {
    if (!state.resultForm) return;
    const changed = normForm(state.form) !== normForm(state.resultForm);
    state.stale = changed;
    $('#resultZone').classList.toggle('is-stale', changed);
    const rs = $('#runStatus'); if (rs) rs.innerHTML = runStatusHtml();
    if (window.NZH.onStale) window.NZH.onStale(state);
  }

  /* ------------------------------------------------------------------ */
  /* 结果公共片段                                                         */
  /* ------------------------------------------------------------------ */
  function provenanceHtml(vm) {
    if (!vm) return '';
    const p = vm.provenance;
    const room = vm.roomConfig
      ? `房间配置：${vm.roomConfig.roomCount ?? '—'} 间 × 每间 ${vm.roomConfig.unitsPerRoom ?? '—'} 台`
      : '房间配置：待5090确认';
    const src = vm.mode === 'replay'
      ? `${tag('brand', p.kind, 'check')}<span>源码 <span class="mono">${esc(fmt.sha(p.sourceCommit))}</span></span><span>计算版本 <span class="mono">${esc(p.calculationVersion || '—')}</span></span>`
      : `${tag('outline', p.kind)}<span>计算版本 <span class="mono">${esc(p.calculationVersion || '—')}</span></span><span>${esc(fmt.datetime(vm.computedAt))}</span>`;
    return `<div class="provenance-line">${src}<span>${esc(room)}</span><button class="link-btn" type="button" data-action="open-drawer">查看依据</button></div>`;
  }

  function pendingHtml() {
    const rows = (state.pending.changes || []).map((c) => `<li><b>${esc(FIELD[c.key].label)}</b>：${esc(fieldDisplay(c.key, c.from))} → ${esc(fieldDisplay(c.key, c.to))}</li>`).join('');
    return `<div class="empty">
      <div class="icon">${icon('clock')}</div>
      <h3>待5090验算</h3>
      <p>这组条件不在已验算样例中。为避免把旧结果当成新结果，这里不显示任何数字。可以把条件交给 5090 计算，或恢复样例条件。</p>
      ${rows ? `<ul class="small muted" style="text-align:left;margin:0;padding-left:18px">${rows}</ul>` : ''}
      <div class="row" style="justify-content:center"><button class="btn" type="button" data-action="restore-sample">恢复样例条件</button><button class="btn btn-ghost" type="button" data-action="goto-step" data-step="1">返回修改</button></div>
    </div>`;
  }

  function noResultHtml() {
    return `<div class="empty"><div class="icon">${icon('info')}</div><h3>还没有结果</h3><p>先在第 1 步选择样例或填写条件，然后点击“查看结果”。</p>
      <button class="btn btn-primary" type="button" data-action="goto-step" data-step="1">去填写条件</button></div>`;
  }

  function stepNavHtml(prev, next, nextLabel) {
    return `<div class="step-nav">
      ${prev ? `<button class="btn" type="button" data-action="goto-step" data-step="${prev}">${icon('back')}上一步</button>` : '<span></span>'}
      ${next ? `<button class="btn btn-primary" type="button" data-action="goto-step" data-step="${next}">${esc(nextLabel || '下一步')} ${icon('arrow')}</button>` : ''}
    </div>`;
  }

  /* ------------------------------------------------------------------ */
  /* 第 2 步：空调用电                                                    */
  /* ------------------------------------------------------------------ */
  function renderStep2() {
    const host = $('#step2');
    const head = `<div class="step-head"><div><h2>空调用电</h2><p>先看空调一年要用多少电、设定的温湿度能不能达到。后面所有方案都建立在这条用电曲线上。</p></div></div>`;
    if (state.pending) { host.innerHTML = head + pendingHtml(); return; }
    const vm = state.vm;
    if (!vm) { host.innerHTML = head + noResultHtml(); return; }
    const svc = vm.service;
    const gaps = svc && svc.gaps ? svc.gaps : {};
    const svcBanner = !svc ? '' : (svc.tone === 'ok'
      ? `<div class="banner banner-ok">${icon('check')}<div><p><b>${esc(svc.label)}</b></p><p class="sub">${esc(svc.note)}</p></div></div>`
      : `<div class="banner banner-warn">${icon('warn')}<div><p><b>${esc(svc.label)}：约 ${esc(fmt.num(gaps.capacity_shortfall_hours, 0))} 小时冷量不足</b></p>
          <p class="sub">通常意味着设备偏小或目标偏严。${esc(svc.note)}</p></div></div>`);
    const annual = vm.load.annualKwh;
    const stat = (k, v, unit) => `<div class="stat"><span class="k">${esc(k)}</span><span class="v">${esc(v)}<small>${esc(unit)}</small></span></div>`;
    const stats = svc ? `<div class="stats">
        <div class="stat"><span class="k">设定温湿度能否达到</span><span class="v">${tag(svc.tone, svc.label, svc.tone === 'ok' ? 'check' : 'warn')}</span></div>
        ${svc.tone !== 'ok' ? stat('冷量不足', fmt.num(gaps.capacity_shortfall_hours, 0), ' 小时') + stat('温度超标累计', fmt.num(gaps.unmet_temp_degree_hours, 0), ' ℃·h') + stat('湿度超标累计', fmt.num(gaps.unmet_rh_percent_hours, 0), ' %·h') : ''}
      </div>` : '';
    host.innerHTML = `${head}
      <section class="decision">
        <p class="lead">空调全年用电 · ${esc(vm.label)}</p>
        ${D.isNum(annual)
          ? `<div class="figure"><span class="value">${esc(fmt.kwh(annual))}</span><span class="unit">kWh / 年</span></div>`
          : `<p class="headline">这个样例没有单独保存空调年用电</p><p class="small muted mt-1">该样例只保存了方案汇总；完整逐时数据见“默认四方案”样例。</p>`}
        ${stats}
        <div class="foot">${provenanceHtml(vm)}</div>
      </section>
      ${svcBanner}
      <section class="card chart-card">
        <div class="chart-head"><div><h3 class="card-title">逐月空调用电</h3><p>把逐小时用电按月份加总，仅用于显示季节分布；年度数字直接取自计算结果。</p></div>
          <div class="legend"><span><i style="background:var(--brand)"></i>空调用电（kWh）</span></div></div>
        <div id="monthlyChart"></div>
      </section>
      <div class="banner">${icon('info')}<div><p><b>两本账，口径不同</b></p><p class="sub">本页和第 3 步只比较“空调用电从哪里来”：购电费用与发电设备的投入运维。空调设备本身的购置、安装费用是另一本账，下一轮在“空调成本”中单独展示，不与这里的金额相加。</p></div></div>
      ${stepNavHtml(1, 3, '比较供电方案')}`;
    const mc = $('#monthlyChart');
    if (vm.hourly && vm.hourly.load.length) {
      C.monthlyBars(mc, { timestamps: vm.hourly.timestamps, values: vm.hourly.load, color: 'var(--brand)', unit: 'kWh', label: '空调用电', ariaLabel: '逐月空调用电柱状图' });
    } else {
      mc.innerHTML = `<p class="small subtle">该样例没有保存逐小时数据。</p>`;
    }
  }

  /* ------------------------------------------------------------------ */
  /* 第 3、4 步与“我的方案”由 stage.js / deliver.js 提供                  */
  /* ------------------------------------------------------------------ */
  function renderStep3() {
    const host = $('#step3');
    const head = `<div class="step-head"><div><h2>比较供电方案</h2><p>同一条逐小时用电曲线，分别配上四种供电方式，比较 10 年总花费。</p></div></div>`;
    if (state.pending) { host.innerHTML = head + pendingHtml(); return; }
    if (!state.vm) { host.innerHTML = head + noResultHtml(); return; }
    if (window.NZH.stage) { window.NZH.stage.render(host, state.vm, { head, provenanceHtml, stepNavHtml, icon, tag, esc }); return; }
    host.innerHTML = head + `<p class="muted">方案比较模块加载中。</p>` + stepNavHtml(2, 4);
  }
  function renderStep4() {
    const host = $('#step4');
    const head = `<div class="step-head"><div><h2>决策与导出</h2><p>推荐理由、适用边界，以及从当前结果导出的简报和数据。</p></div></div>`;
    if (state.pending) { host.innerHTML = head + pendingHtml(); return; }
    if (!state.vm) { host.innerHTML = head + noResultHtml(); return; }
    if (window.NZH.deliver) { window.NZH.deliver.renderStep4(host, state, { head, provenanceHtml, stepNavHtml, icon, tag, esc }); return; }
    host.innerHTML = head + `<p class="muted">导出模块将在本轮后续提交中加入。</p>` + stepNavHtml(3, null);
  }
  function renderPlans() {
    const host = $('#view-plans');
    if (window.NZH.deliver) { window.NZH.deliver.renderPlans(host, state, { icon, tag, esc }); return; }
    host.innerHTML = `<div class="step-head"><div><h1 id="plansTitle">我的方案</h1><p>保存过的试算会出现在这里。</p></div></div>
      <div class="empty mt-3"><div class="icon">${icon('doc')}</div><h3>还没有保存的方案</h3><p>完成一次试算后，可在第 4 步保存。</p></div>`;
  }

  function renderStep(n) {
    if (n === 1) renderStep1();
    if (n === 2) renderStep2();
    if (n === 3) renderStep3();
    if (n === 4) renderStep4();
    $('#resultZone').classList.toggle('is-stale', state.stale);
  }

  /* ------------------------------------------------------------------ */
  /* 依据抽屉                                                             */
  /* ------------------------------------------------------------------ */
  const TERMS = [
    ['只用电网', 'S0_grid'], ['加装光伏', 'S1_pv'], ['加装小风机', 'S2_wind（SWCC 认证 SD6 功率曲线）'], ['光伏+小风机', 'S3_pv_wind'],
    ['10 年总花费', 'total_cost_npv_cny（成本现值，按研究期折现）'], ['比只用电网多花 / 省下', 'incremental_npv_vs_s0_cny（负数＝多花）'],
    ['净现金流现值', 'npv_cny（通常为负，不是利润）'], ['空调用电由自家发电覆盖的比例', 'load_coverage_rate'],
    ['发了但浪费的电', 'curtailment_kwh'], ['风速随高度换算', 'Hellman 幂律（样例指数 0.14）'], ['光伏发电计算', 'pvlib'],
    ['冷量不足小时数', 'capacity_shortfall_hours']
  ];

  function renderDrawer() {
    const vm = state.vm;
    const p = vm ? vm.provenance : null;
    const w = p && p.weather ? p.weather : null;
    const site = w && w.site ? w.site : (w && w.context ? w.context.site || {} : {});
    const kv = (rows) => `<dl class="kv">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')}</dl>`;
    const mono = (v) => `<span class="mono">${esc(v ?? '—')}</span>`;
    const modeSeg = `<div class="segmented" role="group" aria-label="数据模式">
      <button type="button" data-action="set-mode" data-mode="replay" aria-pressed="${state.mode === 'replay'}">5090已验算样例</button>
      <button type="button" data-action="set-mode" data-mode="live" aria-pressed="${state.mode === 'live'}">本机实时计算</button></div>`;
    $('#drawerBody').innerHTML = `
      <h4>数据模式</h4>${modeSeg}
      <p class="small muted mt-1">已验算样例：读取 <span class="mono">docs/handoff/replay_viewer/</span> 中 5090 运行并验收的结果，只读、不重新计算。本机实时计算：调用本机 <span class="mono">/api/operation/hybrid/run</span>，需要完整计算环境。两种模式的结果都会标明来源。</p>
      ${vm ? `<h4>当前结果来源</h4>${kv([
        ['来源', esc(p.kind)],
        ['样例', esc(vm.label)],
        ['源码提交', mono(p.sourceCommit)],
        ['计算版本', mono(p.calculationVersion)],
        ['结果文件', mono(p.sourceFile)],
        ['结果 SHA-256', mono(p.sourceSha256)],
        ['样例文件', mono(p.sampleFile)],
        ['房间配置', vm.roomConfig ? esc(`${vm.roomConfig.roomCount} 间 × ${vm.roomConfig.unitsPerRoom} 台`) : '待5090确认（样例 load_context 未记录 room_count / units_per_room）']
      ])}` : ''}
      ${w ? `<h4>天气数据</h4>${kv([
        ['城市', esc(site.name || site.site_id || '—')],
        ['时段', esc(`${w.start || '—'} ～ ${w.end || '—'}`)],
        ['来源', esc(site.source || '—')],
        ['文件哈希', mono(w.hash)],
        ['时间口径', esc(w.radiation_definition || w.normalization_version || '—')]
      ])}` : ''}
      <h4>适用边界</h4>
      <ul class="small muted" style="margin:0;padding-left:18px">
        <li>空调负荷是城市级天气驱动的单房间模型情景，未经现场校准，可能存在温湿度或冷量缺口。</li>
        <li>小风机采用公开认证功率曲线和参考空气密度，尚未按当地温度、气压修正。</li>
        <li>报价、寿命、电价是用户输入或情景假设，不是已核实的采购报价。</li>
        <li>未证明：现场节能、真实回本、采购适配、并网审批、人工提效、跨楼宇精度。</li>
        ${vm && vm.notProvided.length ? `<li>本结果未提供：${esc(vm.notProvided.join('、'))}。</li>` : ''}
      </ul>
      <h4>术语对照</h4>
      <div class="table-wrap"><table class="table"><thead><tr><th>页面用语</th><th style="text-align:left">技术字段 / 方法</th></tr></thead>
        <tbody>${TERMS.map(([a, b]) => `<tr><td>${esc(a)}</td><td style="text-align:left;white-space:normal">${esc(b)}</td></tr>`).join('')}</tbody></table></div>
      <h4>早期研究</h4>
      <p class="small muted">原六页签研发工作台（含 BOPTEST 运行方案研究）已移出主导航，代码保留：<a href="/assets/legacy/index.html">打开早期研究工作台</a>。</p>`;
  }

  function openDrawer() {
    renderDrawer();
    $('#drawer').classList.add('is-open'); $('#drawer').setAttribute('aria-hidden', 'false'); $('#scrim').classList.add('is-open');
    setTimeout(() => { const b = $('#drawer [data-action="close-drawer"]'); if (b) b.focus(); }, 50);
  }
  function closeDrawer() {
    $('#drawer').classList.remove('is-open'); $('#drawer').setAttribute('aria-hidden', 'true'); $('#scrim').classList.remove('is-open');
  }

  function setMode(mode) {
    if (mode === state.mode) return;
    state.mode = mode;
    $('#modePill').dataset.mode = mode;
    $('#modeLabel').textContent = mode === 'replay' ? '5090已验算样例' : '本机实时计算';
    if (mode === 'replay') { pickSample(state.caseId || state.file.cases[0].case_id); }
    else {
      // 实时模式下当前样例结果不再对应“实时”来源：保留表单，结果需重新计算
      if (state.vm) { state.resultForm = state.resultForm || JSON.parse(JSON.stringify(state.form)); state.stale = true; }
      state.pending = null;
    }
    renderDrawer(); renderStep(state.step); setStep(state.step, false);
    toast(mode === 'replay' ? '已切换到 5090 已验算样例' : '已切换到本机实时计算：结果需重新计算');
  }

  function pickSample(caseId) {
    state.caseId = caseId;
    const vm = D.fromReplay(state.file, caseId);
    state.form = formFromInputs(vm.inputs);
    state.vm = vm; state.pending = null; state.stale = false;
    state.resultForm = JSON.parse(JSON.stringify(state.form));
    state.ask = { text: '', applied: [], rejected: [] };
    if (window.NZH.onResult) window.NZH.onResult(state);
    renderStep(state.step);
  }

  /* ------------------------------------------------------------------ */
  /* 事件                                                                */
  /* ------------------------------------------------------------------ */
  function readField(target) {
    const key = target.dataset.field, f = FIELD[key];
    let v;
    if (f.type === 'switch') v = target.checked;
    else if (target.value === '') v = null;
    else if (f.bool) v = target.value === 'true';
    else if (f.type === 'number' || f.num) v = Number(target.value);
    else v = target.value;
    if (typeof v === 'number' && !Number.isFinite(v)) v = null;
    state.form[key] = v;
    if (f.type === 'switch') { const s = target.parentElement.querySelector('span:last-child'); if (s) s.textContent = v ? '允许' : '不允许'; }
    markChanged();
  }

  document.addEventListener('change', (e) => { if (e.target.matches('[data-field]')) readField(e.target); });
  document.addEventListener('input', (e) => { if (e.target.matches('input[type="number"][data-field]')) readField(e.target); });

  document.addEventListener('submit', (e) => {
    if (e.target.id !== 'askForm') return;
    e.preventDefault();
    const text = $('#askInput').value.trim();
    const parsed = parseAsk(text);
    state.ask = { text, applied: parsed.applied, rejected: parsed.rejected };
    for (const [k, v] of parsed.applied) state.form[k] = v;
    renderStep1(); markChanged();
    if (parsed.applied.length) toast(`已写入 ${parsed.applied.length} 项条件，可在表单中核对`);
  });

  document.addEventListener('click', (e) => {
    const a = e.target.closest('[data-action]');
    if (!a) return;
    const act = a.dataset.action;
    if (act === 'run') { e.preventDefault(); run(); }
    else if (act === 'goto-step') { e.preventDefault(); setStep(Number(a.dataset.step)); window.scrollTo({ top: 0, behavior: 'smooth' }); }
    else if (act === 'pick-sample') { pickSample(a.dataset.case); toast('已载入样例，结果来自 5090 已验算数据'); }
    else if (act === 'restore-sample') { pickSample(state.caseId || state.file.cases[0].case_id); setStep(state.step, false); }
    else if (act === 'open-drawer') openDrawer();
    else if (act === 'close-drawer') closeDrawer();
    else if (act === 'set-mode') setMode(a.dataset.mode);
    else if (act === 'focus-field') { const f = $(`#f_${a.dataset.field}`); if (f) { f.focus(); f.scrollIntoView({ block: 'center', behavior: 'smooth' }); } }
  });
  $('#aboutBtn').addEventListener('click', openDrawer);
  $('#modePill').addEventListener('click', openDrawer);
  $('#scrim').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });
  $('#stepper').addEventListener('click', (e) => {
    const a = e.target.closest('a[data-step]'); if (!a) return;
    e.preventDefault(); setStep(Number(a.dataset.step));
  });
  window.addEventListener('hashchange', route);

  /* ------------------------------------------------------------------ */
  /* 启动                                                                */
  /* ------------------------------------------------------------------ */
  async function boot() {
    try {
      state.file = await D.loadSampleFile('replay_cases.json');
      const first = state.file.cases[0].case_id;
      pickSample(first);
    } catch (err) {
      state.error = err.message;
      $('#step1').innerHTML = `<div class="banner banner-bad">${icon('warn')}<div><p><b>无法读取已验算样例</b></p><p class="sub">${esc(err.message)}</p></div></div>`;
    }
    route();
  }

  function openSample(caseId) {
    if (state.mode !== 'replay') setMode('replay');
    pickSample(caseId); setStep(3);
  }
  function loadConditions(conds) {
    const f = blankForm();
    (conds || []).forEach((c) => { if (FIELD[c.key]) f[c.key] = c.value; });
    state.form = f; state.ask = { text: '', applied: [], rejected: [] };
    if (!state.resultForm) state.resultForm = JSON.parse(JSON.stringify(blankForm()));
    markChanged(); renderStep(state.step);
    toast('已载入保存的条件，请点击计算');
  }

  window.NZH.app = { openSample, loadConditions, state, FIELDS, FIELD, fieldDisplay, run, setStep, renderStep, openDrawer, toast, icon, tag, esc, parseAsk, buildLiveRequest, provenanceHtml };
  boot();
})();
