/* 能智核 · 第 4 步：推荐理由、适用边界、导出；“我的方案”
 *
 * 导出规则：
 *   - 只从当前已显示的视图模型生成（决策简报 HTML/打印、CSV、JSON），不调用任何计算接口；
 *   - 条件已修改（结果失效）或待 5090 验算时，导出全部禁用；
 *   - “我的方案”只存在本机浏览器 localStorage，读写失败时页面照常可用。
 */
(function () {
  'use strict';
  const D = window.NZH.data;
  const fmt = D.fmt;
  const isNum = D.isNum;
  const STORE_KEY = 'nzh.plans.v1';

  const VERB = { S0_grid: '暂不加装，只用电网', S1_pv: '加装光伏', S2_wind: '加装小风机', S3_pv_wind: '光伏和小风机都装' };
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* ------------------------------------------------------------------ */
  /* 由视图模型生成文字（只引用 report 中的数值）                          */
  /* ------------------------------------------------------------------ */
  function headlineOf(vm) {
    const rec = vm.recommendation || {};
    const best = vm.candidates.find((c) => c.id === rec.scenarioId);
    if (!best || rec.status === 'not_available') return '暂时给不出推荐';
    if (rec.status === 'conditional_subset') return `在条件齐全的方案中，${best.name}最省钱`;
    return `建议：${VERB[best.id] || best.name}`;
  }

  function reasonsOf(vm) {
    const rec = vm.recommendation || {};
    const best = vm.candidates.find((c) => c.id === rec.scenarioId);
    const years = isNum(vm.studyYears) ? `${vm.studyYears} 年` : '研究期内';
    const out = [];
    if (best) {
      out.push(isNum(best.totalCost)
        ? `在可以比较的方案中，「${best.name}」${years}总花费最低，约 ${fmt.money(best.totalCost)} 元（折现后）。`
        : `在可以比较的方案中，「${best.name}」相对其他方案花费最低（该样例只保存了相对差额）。`);
    }
    const alts = vm.candidates.filter((c) => c.id !== 'S0_grid' && c.admission.status === 'eligible' && isNum(c.incremental));
    if (alts.length) {
      const parts = alts.map((c) => {
        const d = fmt.delta(c.incremental);
        const waste = isNum(c.curtail) && c.curtail > 0 ? `，其中一年约 ${fmt.kwh(c.curtail)} kWh 发电当时没人用` : '';
        return `${c.name}${d.short || d.text}${waste}`;
      });
      out.push(`与只用电网相比：${parts.join('；')}。`);
    }
    const ex = vm.candidates.filter((c) => c.admission.status === 'excluded');
    const un = vm.candidates.filter((c) => c.admission.status === 'unknown');
    if (ex.length) out.push(`已排除：${ex.map((c) => `${c.name}（${c.reasons[0] || c.constraintText || '不满足限制'}）`).join('、')}。`);
    if (un.length) out.push(`条件不全、暂未比较（不是淘汰）：${un.map((c) => c.name).join('、')}。`);
    if (vm.service && vm.service.status === 'service_gap') out.push('注意：模型中空调有冷量或除湿缺口，结论不代表同等舒适度下的最优投资。');
    return out;
  }

  const BOUNDARIES = [
    '空调负荷是城市级天气驱动的单房间模型情景，未经现场校准。',
    '小风机采用公开认证功率曲线和参考空气密度，未按当地温度、气压修正，也没有现场测风。',
    '报价、寿命、电价为用户情景，不是已核实的采购报价；没有并网、消防、承重审批。',
    '没有证明现场节能、真实回本、采购适配、人工提效或跨楼宇精度。'
  ];

  function conditionsOf(state) {
    const A = window.NZH.app;
    return A.FIELDS.filter((f) => state.resultForm && state.resultForm[f.key] != null)
      .map((f) => ({ key: f.key, label: f.label, value: state.resultForm[f.key], text: A.fieldDisplay(f.key, state.resultForm[f.key]) }));
  }

  /* ------------------------------------------------------------------ */
  /* 导出                                                                */
  /* ------------------------------------------------------------------ */
  function canExport(state) { return !!state.vm && !state.stale && !state.pending && !state.loading; }

  function download(name, mime, text) {
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = name; document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
  }
  const stamp = () => new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '');
  const baseName = (vm) => `nengzhihe_${vm.mode === 'replay' ? vm.caseId : 'live'}_${stamp()}`;

  function csvCell(v) {
    if (v === null || v === undefined) return '';
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }
  function toCsv(rows) { return '﻿' + rows.map((r) => r.map(csvCell).join(',')).join('\r\n'); }

  function summaryCsv(vm) {
    const head = ['scenario_id', '方案', '状态', 'admission_status', 'constraint_status', '排除或缺失原因', 'total_cost_npv_cny', 'incremental_npv_vs_s0_cny', 'npv_cny', 'capex_cny', 'generation_kwh', 'self_use_kwh', 'grid_import_kwh', 'grid_export_kwh', 'curtailment_kwh', 'load_coverage_rate', '推荐'];
    const rows = vm.candidates.map((c) => [c.id, c.name, c.admission.label, c.admission.status, c.constraintStatus, c.reasons.join('；'),
      c.totalCost, c.incremental, c.npv, c.capex, c.gen, c.selfUse, c.gridImport, c.gridExport, c.curtail, c.coverage, c.isRecommended ? '是' : '']);
    const meta = [['# 来源', vm.provenance.kind], ['# 样例', vm.label], ['# 源码提交', vm.provenance.sourceCommit || ''], ['# 计算版本', vm.provenance.calculationVersion || ''],
      ['# 推荐状态', (vm.recommendation || {}).status || ''], ['# 说明', '数值原样取自结果文件；空白表示该样例未保存此字段。导出未重新计算。']];
    return toCsv(meta.concat([[]], [head], rows));
  }

  function hourlyCsv(vm) {
    const h = vm.hourly;
    const head = ['timestamp', 'load_kwh', 'pv_generation_kwh', 'wind_generation_kwh', 'self_use_kwh', 'grid_import_kwh', 'grid_export_kwh', 'curtailment_kwh'];
    const rows = h.timestamps.map((t, i) => [t, h.load[i], h.pv[i], h.wind[i], h.self[i], h.imp[i], h.exp[i], h.curtail[i]]);
    const meta = [['# 方案', h.scenarioId], ['# 来源', vm.provenance.kind], ['# 源码提交', vm.provenance.sourceCommit || ''], ['# 说明', h.samplingRule || '逐时原始值']];
    return toCsv(meta.concat([[]], [head], rows));
  }

  function rawOf(state) {
    const vm = state.vm;
    if (vm.mode === 'replay') return (state.file.cases || []).find((c) => c.case_id === vm.caseId) || null;
    return vm.raw || null;
  }

  function jsonExport(state) {
    const vm = state.vm;
    return JSON.stringify({
      export_meta: {
        product: '能智核', exported_at: new Date().toISOString(), rule: '从当前已显示结果导出；未重新计算。',
        data_mode: vm.mode, source: vm.provenance.kind, sample_case_id: vm.caseId, sample_file: vm.provenance.sampleFile || null,
        source_commit: vm.provenance.sourceCommit || null, calculation_version: vm.provenance.calculationVersion || null,
        room_config: vm.roomConfig || '待5090确认'
      },
      conditions: Object.fromEntries(conditionsOf(state).map((c) => [c.key, c.value])),
      decision: { headline: headlineOf(vm), recommendation: (vm.recommendation || {}).raw || null, reasons: reasonsOf(vm), boundaries: BOUNDARIES, not_provided: vm.notProvided },
      result: rawOf(state)
    }, null, 2);
  }

  function briefHtml(state) {
    const vm = state.vm;
    const p = vm.provenance;
    const years = isNum(vm.studyYears) ? `${vm.studyYears} 年总花费（元）` : '总花费（元）';
    const rows = vm.candidates.map((c) => `<tr class="${c.isRecommended ? 'rec' : ''}"><td>${esc(c.name)}${c.isRecommended ? ' ★' : ''}</td><td>${esc(c.admission.label)}</td>
      <td>${esc(isNum(c.totalCost) ? fmt.money(c.totalCost) : '—')}</td><td>${esc(c.id === 'S0_grid' ? '基线' : (c.admission.status === 'unknown' ? '暂无法比较' : fmt.delta(c.incremental).text))}</td>
      <td>${esc(fmt.kwh(c.gen))}</td><td>${esc(fmt.kwh(c.gridImport))}</td><td>${esc(fmt.pct(c.coverage))}</td></tr>`).join('');
    const conds = conditionsOf(state).map((c) => `<li>${esc(c.label)}：${esc(c.text)}</li>`).join('') || '<li>样例未记录可显示的条件</li>';
    return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>能智核决策简报｜${esc(vm.label)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  @page { size: A4; margin: 16mm 14mm; }
  body { font: 14px/1.6 -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif; color: #1B1F24; margin: 0; padding: 24px; max-width: 820px; }
  header { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 2px solid #0F6E68; padding-bottom: 8px; }
  header b { font-size: 18px; color: #0F6E68; } header span { color: #6B7480; font-size: 12px; }
  h1 { font-size: 24px; margin: 20px 0 4px; } .lead { color: #4A5260; margin: 0 0 16px; }
  .big { font-size: 34px; font-weight: 700; font-variant-numeric: tabular-nums; } .big small { font-size: 14px; color: #4A5260; font-weight: 600; }
  h2 { font-size: 15px; margin: 22px 0 8px; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; font-variant-numeric: tabular-nums; }
  th, td { padding: 7px 8px; border-bottom: 1px solid #E3E7EC; text-align: right; } th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
  thead th { background: #F1F3F5; color: #4A5260; font-weight: 600; } tr.rec td { background: #E6F3F1; font-weight: 600; }
  ul { margin: 0; padding-left: 18px; } li { margin: 2px 0; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 0 24px; }
  .src { margin-top: 22px; padding-top: 10px; border-top: 1px solid #E3E7EC; font-size: 11.5px; color: #6B7480; }
  code { font-family: ui-monospace, Consolas, monospace; font-size: 11px; color: #1B1F24; }
  .warn { background: #FFF4E0; color: #8A5200; padding: 8px 10px; border-radius: 8px; font-size: 12.5px; margin-top: 12px; }
  @media print { body { padding: 0; } .noprint { display: none; } }
</style></head><body>
<header><b>能智核 · 决策简报</b><span>导出时间 ${esc(fmt.datetime(Date.now()))} · ${esc(p.kind)}</span></header>
<h1>${esc(headlineOf(vm))}</h1>
<p class="lead">${esc(vm.label)} · ${esc((vm.recommendation || {}).label || '')}</p>
${(() => { const best = vm.candidates.find((c) => c.isRecommended); return best && isNum(best.totalCost) ? `<div class="big">${esc(fmt.money(best.totalCost))} <small>元 · ${esc(years.replace('（元）', ''))}</small></div>` : ''; })()}
${vm.service && vm.service.status === 'service_gap' ? `<div class="warn">空调有缺口：约 ${esc(fmt.num((vm.service.gaps || {}).capacity_shortfall_hours, 0))} 小时冷量不足。结论不代表同等舒适度下的最优投资。</div>` : ''}
<h2>四种供电方式</h2>
<table><thead><tr><th>方案</th><th>状态</th><th>${esc(years)}</th><th>相对只用电网</th><th>年发电 kWh</th><th>年购电 kWh</th><th>自给比例</th></tr></thead><tbody>${rows}</tbody></table>
<h2>推荐理由</h2><ul>${reasonsOf(vm).map((r) => `<li>${esc(r)}</li>`).join('')}</ul>
<div class="two"><div><h2>计算条件</h2><ul>${conds}</ul><p style="font-size:12px;color:#6B7480">房间配置：${esc(vm.roomConfig ? `${vm.roomConfig.roomCount} 间 × ${vm.roomConfig.unitsPerRoom} 台` : '待5090确认')}</p></div>
<div><h2>适用边界</h2><ul>${BOUNDARIES.map((b) => `<li>${esc(b)}</li>`).join('')}${vm.notProvided.length ? `<li>本结果未提供：${esc(vm.notProvided.join('、'))}。</li>` : ''}</ul></div></div>
<div class="src">数据来源：${esc(p.kind)}；源码提交 <code>${esc(p.sourceCommit || '—')}</code>；计算版本 <code>${esc(p.calculationVersion || '—')}</code>；结果文件 <code>${esc(p.sourceFile || '—')}</code>；SHA-256 <code>${esc(p.sourceSha256 || '—')}</code>。<br>
本简报由页面从当前显示的结果直接生成，没有重新计算。“10 年总花费”指空调用电购电费与发电设备投入运维的折现成本，不含空调设备本身的购置安装费用。</div>
<p class="noprint" style="margin-top:20px"><button onclick="window.print()">打印 / 存为 PDF</button></p>
</body></html>`;
  }

  /* ------------------------------------------------------------------ */
  /* 我的方案（localStorage，仅本机浏览器）                               */
  /* ------------------------------------------------------------------ */
  function readPlans() {
    try { const v = JSON.parse(localStorage.getItem(STORE_KEY) || '[]'); return Array.isArray(v) ? v : []; } catch (e) { return null; }
  }
  function writePlans(list) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(list)); return true; } catch (e) { return false; }
  }

  function savePlan(state) {
    if (!canExport(state)) return { ok: false, msg: '当前结果不可保存：条件已修改或尚未计算' };
    const vm = state.vm;
    const best = vm.candidates.find((c) => c.isRecommended);
    const plan = {
      id: `p${Date.now().toString(36)}`, savedAt: Date.now(), mode: vm.mode, caseId: vm.caseId, label: vm.label,
      source: { kind: vm.provenance.kind, sourceCommit: vm.provenance.sourceCommit || null, calculationVersion: vm.provenance.calculationVersion || null },
      conditions: conditionsOf(state).map((c) => ({ key: c.key, label: c.label, value: c.value, text: c.text })),
      conclusion: { headline: headlineOf(vm), recommendation: (vm.recommendation || {}).label || null, totalCost: best && isNum(best.totalCost) ? best.totalCost : null, studyYears: vm.studyYears ?? null }
    };
    const list = readPlans();
    if (list === null) return { ok: false, msg: '浏览器不允许本地存储，无法保存' };
    list.unshift(plan);
    return writePlans(list.slice(0, 50)) ? { ok: true, msg: '已保存到“我的方案”（仅本机浏览器）' } : { ok: false, msg: '保存失败：浏览器存储不可用' };
  }

  /* ------------------------------------------------------------------ */
  /* 第 4 步                                                              */
  /* ------------------------------------------------------------------ */
  function renderStep4(host, state, h) {
    const vm = state.vm;
    const dis = canExport(state) ? '' : 'disabled aria-disabled="true"';
    host.innerHTML = `${h.head}
      <section class="decision">
        <div class="row-between"><p class="lead">${esc(vm.label)}</p>${h.tag((vm.recommendation || {}).tone || 'unknown', (vm.recommendation || {}).label || '—', 'star')}</div>
        <p class="headline">${esc(headlineOf(vm))}</p>
        <ol class="reasons">${reasonsOf(vm).map((r) => `<li>${esc(r)}</li>`).join('')}</ol>
        <div class="foot">${h.provenanceHtml(vm)}</div>
      </section>
      <div class="grid grid-2">
        <section class="card">
          <h3 class="card-title">适用边界</h3>
          <p class="card-sub">这些条件没有被验证，做采购和施工决定前需要补齐。</p>
          <ul class="checklist">${BOUNDARIES.map((b) => `<li>${h.icon('info')}<span>${esc(b)}</span></li>`).join('')}
            ${vm.notProvided.length ? `<li>${h.icon('info')}<span>本结果未提供：${esc(vm.notProvided.join('、'))}。</span></li>` : ''}</ul>
        </section>
        <section class="card" id="exportCard">
          <h3 class="card-title">导出</h3>
          <p class="card-sub">全部从当前显示的结果生成，不会重新计算。条件修改后导出自动停用。</p>
          <div class="export-list">
            <button class="export-item" type="button" data-export="brief" ${dis}>${h.icon('doc')}<span><b>决策简报</b><small>一页 A4，可打印或存为 PDF</small></span></button>
            <button class="export-item" type="button" data-export="brief-html" ${dis}>${h.icon('doc')}<span><b>决策简报（HTML 文件）</b><small>下载后可离线打开、转发</small></span></button>
            <button class="export-item" type="button" data-export="csv" ${dis}>${h.icon('doc')}<span><b>方案汇总 CSV</b><small>四个方案的状态、费用和电量</small></span></button>
            <button class="export-item" type="button" data-export="hourly" ${dis || (vm.hourly ? '' : 'disabled aria-disabled="true"')}>${h.icon('doc')}<span><b>逐时数据 CSV</b><small>${vm.hourly ? `全年 ${vm.hourly.timestamps.length} 小时原始值` : '该样例未保存逐时数据'}</small></span></button>
            <button class="export-item" type="button" data-export="json" ${dis}>${h.icon('doc')}<span><b>完整结果 JSON</b><small>条件、结论与原始结果对象</small></span></button>
          </div>
          <hr class="divider">
          <div class="row-between"><div><b class="small">保存到“我的方案”</b><p class="xs subtle">仅保存在本机浏览器，换浏览器或清除数据后不可见。</p></div>
            <button class="btn" type="button" data-export="save" ${dis}>保存方案</button></div>
        </section>
      </div>
      ${h.stepNavHtml(3, null)}`;
  }

  function doExport(kind) {
    const state = window.NZH.state;
    const A = window.NZH.app;
    if (!canExport(state)) { A.toast('条件已修改或尚无结果，不能导出旧结果'); return; }
    const vm = state.vm;
    if (kind === 'brief') {
      const w = window.open('', '_blank');
      if (!w) { A.toast('浏览器拦截了新窗口，请改用“决策简报（HTML 文件）”'); return; }
      w.document.open(); w.document.write(briefHtml(state)); w.document.close();
      setTimeout(() => { try { w.focus(); w.print(); } catch (e) { /* 用户可手动打印 */ } }, 400);
    } else if (kind === 'brief-html') download(`${baseName(vm)}_brief.html`, 'text/html;charset=utf-8', briefHtml(state));
    else if (kind === 'csv') download(`${baseName(vm)}_summary.csv`, 'text/csv;charset=utf-8', summaryCsv(vm));
    else if (kind === 'hourly' && vm.hourly) download(`${baseName(vm)}_hourly.csv`, 'text/csv;charset=utf-8', hourlyCsv(vm));
    else if (kind === 'json') download(`${baseName(vm)}.json`, 'application/json;charset=utf-8', jsonExport(state));
    else if (kind === 'save') { const r = savePlan(state); A.toast(r.msg); }
  }

  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-export]');
    if (!b || b.disabled) return;
    doExport(b.dataset.export);
  });

  /* ------------------------------------------------------------------ */
  /* 我的方案页面                                                         */
  /* ------------------------------------------------------------------ */
  const plansUi = { compare: [] };

  function renderPlans(host, state, h) {
    const list = readPlans();
    const head = `<div class="step-head"><div><h1 id="plansTitle">我的方案</h1><p>保存过的试算条件与结论。仅保存在本机浏览器，不上传、不与他人共享。</p></div>
      ${list && list.length ? `<button class="btn btn-ghost btn-sm" type="button" data-plan="clear">清空全部</button>` : ''}</div>`;
    if (list === null) {
      host.innerHTML = head + `<div class="banner banner-warn mt-3">${h.icon('warn')}<div><p><b>浏览器不允许本地存储</b></p><p class="sub">“我的方案”需要本地存储；其他功能照常可用。</p></div></div>`; return;
    }
    if (!list.length) {
      host.innerHTML = head + `<div class="empty mt-3"><div class="icon">${h.icon('doc')}</div><h3>还没有保存的方案</h3><p>完成一次试算后，在第 4 步点击“保存方案”。</p>
        <a class="btn btn-primary" href="#/new/1">去新建试算</a></div>`; return;
    }
    plansUi.compare = plansUi.compare.filter((id) => list.find((p) => p.id === id));
    const cards = list.map((p) => {
      const conds = p.conditions.slice(0, 6).map((c) => `<span class="chip" style="cursor:default"><span class="k">${esc(c.label)}</span>${esc(c.text)}</span>`).join('');
      const sel = plansUi.compare.includes(p.id);
      return `<article class="card plan">
        <div class="row-between"><div class="row">${h.tag(p.mode === 'replay' ? 'brand' : 'outline', p.source.kind)}<span class="xs subtle">${esc(fmt.datetime(p.savedAt))}</span></div>
          <label class="switch small"><input type="checkbox" data-plan="compare" data-id="${esc(p.id)}" ${sel ? 'checked' : ''}><span class="track"></span><span>对比</span></label></div>
        <h3 class="mt-1" style="font-size:18px">${esc(p.conclusion.headline)}</h3>
        <p class="small muted">${esc(p.label)}${p.conclusion.totalCost != null ? ` · ${esc(p.conclusion.studyYears ?? '')} 年总花费约 ${esc(fmt.money(p.conclusion.totalCost))} 元` : ''}${p.source.sourceCommit ? ` · 源码 ${esc(fmt.sha(p.source.sourceCommit))}` : ''}</p>
        <div class="chips mt-2">${conds}${p.conditions.length > 6 ? `<span class="xs subtle">等 ${p.conditions.length} 项</span>` : ''}</div>
        <div class="row mt-2">
          ${p.mode === 'replay' && p.caseId ? `<button class="btn btn-sm btn-primary" type="button" data-plan="open" data-id="${esc(p.id)}">打开样例结果</button>` : `<button class="btn btn-sm" type="button" data-plan="load" data-id="${esc(p.id)}">载入条件重新计算</button>`}
          <button class="btn btn-sm btn-ghost" type="button" data-plan="delete" data-id="${esc(p.id)}">删除</button>
        </div></article>`;
    }).join('');
    host.innerHTML = head + `<div id="planCompare"></div><div class="grid grid-2 mt-3">${cards}</div>`;
    renderCompare(list, h);
  }

  function renderCompare(list, h) {
    const box = document.getElementById('planCompare'); if (!box) return;
    if (plansUi.compare.length !== 2) {
      box.innerHTML = `<p class="small subtle mt-2">勾选两个方案的“对比”可查看条件差异。</p>`; return;
    }
    const [a, b] = plansUi.compare.map((id) => list.find((p) => p.id === id));
    const keys = Array.from(new Set(a.conditions.map((c) => c.key).concat(b.conditions.map((c) => c.key))));
    const get = (p, k) => (p.conditions.find((c) => c.key === k) || {});
    const rows = keys.map((k) => {
      const x = get(a, k), y = get(b, k); const diff = String(x.value) !== String(y.value);
      return `<tr${diff ? ' style="background:var(--warn-weak)"' : ''}><td>${esc(x.label || y.label)}</td><td>${esc(x.text ?? '未记录')}</td><td>${esc(y.text ?? '未记录')}</td></tr>`;
    }).join('');
    box.innerHTML = `<section class="card mt-3"><h3 class="card-title">条件差异</h3><p class="card-sub">黄色行为不同的条件。</p>
      <div class="table-wrap mt-2"><table class="table"><thead><tr><th>条件</th><th>${esc(a.label)}（${esc(fmt.datetime(a.savedAt))}）</th><th>${esc(b.label)}（${esc(fmt.datetime(b.savedAt))}）</th></tr></thead><tbody>
      <tr><td><b>结论</b></td><td>${esc(a.conclusion.headline)}</td><td>${esc(b.conclusion.headline)}</td></tr>${rows}</tbody></table></div></section>`;
  }

  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-plan]');
    if (!b || b.dataset.plan === 'compare') return;
    const A = window.NZH.app; const state = window.NZH.state;
    const list = readPlans() || [];
    const p = list.find((x) => x.id === b.dataset.id);
    if (b.dataset.plan === 'delete') { writePlans(list.filter((x) => x.id !== b.dataset.id)); A.toast('已删除'); renderPlans(document.getElementById('view-plans'), state, { icon: A.icon, tag: A.tag, esc }); }
    else if (b.dataset.plan === 'clear') { writePlans([]); plansUi.compare = []; renderPlans(document.getElementById('view-plans'), state, { icon: A.icon, tag: A.tag, esc }); }
    else if (b.dataset.plan === 'open' && p) { location.hash = '#/new/3'; setTimeout(() => { const btn = document.querySelector(`[data-action="pick-sample"][data-case="${p.caseId}"]`); if (window.NZH.app.openSample) window.NZH.app.openSample(p.caseId); else if (btn) btn.click(); }, 0); }
    else if (b.dataset.plan === 'load' && p) {
      if (window.NZH.app.loadConditions) window.NZH.app.loadConditions(p.conditions);
      location.hash = '#/new/1';
    }
  });
  document.addEventListener('change', (e) => {
    const b = e.target.closest('[data-plan="compare"]'); if (!b) return;
    const id = b.dataset.id;
    plansUi.compare = b.checked ? plansUi.compare.concat(id).slice(-2) : plansUi.compare.filter((x) => x !== id);
    const A = window.NZH.app;
    renderPlans(document.getElementById('view-plans'), window.NZH.state, { icon: A.icon, tag: A.tag, esc });
  });

  /* 结果失效时同步停用导出按钮（遮罩之外的双保险） */
  window.NZH.onStale = function (state) {
    document.querySelectorAll('[data-export]').forEach((b) => {
      const off = !canExport(state) || (b.dataset.export === 'hourly' && !(state.vm && state.vm.hourly));
      b.disabled = off; b.setAttribute('aria-disabled', String(off));
    });
  };

  window.NZH = window.NZH || {};
  window.NZH.deliver = { renderStep4, renderPlans, briefHtml, summaryCsv, hourlyCsv, jsonExport, canExport, headlineOf, reasonsOf, readPlans, savePlan };
})();
