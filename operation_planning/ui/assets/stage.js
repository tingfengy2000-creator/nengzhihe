/* 能智核 · 第 3 步主舞台：决策卡、四方案卡、能源日历、电去哪了、典型日
 *
 * 所有金额、电量、比例都直接来自视图模型；推荐方案、状态、排除原因取自 report。
 * 本文件只负责“怎么讲清楚”，不判断哪个方案更好。
 */
(function () {
  'use strict';
  const D = window.NZH.data;
  const C = window.NZH.charts;
  const fmt = D.fmt;
  const isNum = D.isNum;

  const VERB = {
    S0_grid: '暂不加装，只用电网',
    S1_pv: '加装光伏',
    S2_wind: '加装小风机',
    S3_pv_wind: '光伏和小风机都装'
  };
  const SUBSET_VERB = {
    S0_grid: '只用电网最省钱',
    S1_pv: '加装光伏最省钱',
    S2_wind: '加装小风机最省钱',
    S3_pv_wind: '光伏+小风机最省钱'
  };

  const ui = { heatView: 'match', flowId: null, day: null };

  function money(v) { return isNum(v) ? fmt.money(v) : null; }

  /* ---------------- 决策卡 ---------------- */
  function decisionHtml(vm, h) {
    const { esc, tag, icon } = h;
    const rec = vm.recommendation || {};
    const best = vm.candidates.find((c) => c.id === rec.scenarioId);
    const years = isNum(vm.studyYears) ? `${vm.studyYears} 年` : '研究期内';
    let headline;
    if (!best || rec.status === 'not_available') headline = '暂时给不出推荐';
    else if (rec.status === 'conditional_subset') headline = `在条件齐全的方案中，${SUBSET_VERB[best.id] || best.name}`;
    else headline = `建议：${VERB[best.id] || best.name}`;

    const figure = best && isNum(best.totalCost)
      ? `<div class="figure"><span class="value">${esc(money(best.totalCost))}</span><span class="unit">元 · ${esc(years)}总花费</span>
          <span class="caption">${esc(best.name)}：空调用电的购电费${best.id === 'S0_grid' ? '' : '，加上发电设备的投入和运维'}，按研究期折现</span></div>`
      : `<div class="figure"><span class="caption">该样例摘要只保存了各方案与“只用电网”的差额，没有保存总花费；差额见下方。</span></div>`;

    // 只用电网是基线，不出现在差额列表里；其余方案逐一说明相对基线多花/省下或为何不能比较
    const deltas = vm.candidates.filter((c) => c.id !== 'S0_grid').map((c) => {
      let amt;
      if (c.admission.status === 'excluded') amt = `<span class="amt na">已排除：${esc(c.reasons[0] || c.constraintText || '不满足限制条件')}</span>`;
      else if (c.admission.status === 'unknown') amt = `<span class="amt na">条件不全，暂无法比较</span>`;
      else if (c.admission.status === 'equivalent') amt = `<span class="amt na">与${esc((D.SCENARIOS[c.equivalentTo] || {}).name || c.equivalentTo || '其他方案')}相同</span>`;
      else {
        const d = fmt.delta(c.incremental);
        amt = d.dir === 'na' ? `<span class="amt na">${esc(d.text)}</span>` : `<span class="amt ${d.dir}">${esc(d.short || d.text)}</span>`;
      }
      return `<div class="delta"><span class="name">如果${esc(c.name)}</span>${amt}</div>`;
    }).join('');

    const svc = vm.service && vm.service.status === 'service_gap'
      ? `<span>${tag('warn', '空调有缺口', 'warn')} 结论不代表同等舒适度下的最优投资</span>` : '';
    const subsetWarn = rec.status === 'conditional_subset'
      ? `<div class="banner banner-warn mt-3">${icon('warn')}<div><p><b>结论未定</b>：${esc(rec.unknown.map((id) => (D.SCENARIOS[id] || {}).name || id).join('、'))}缺少报价或必要条件，不能说它们已被其他方案击败。</p></div></div>` : '';

    return `<section class="decision" aria-labelledby="decisionHeadline">
      <div class="row-between"><p class="lead">${esc(vm.label)}</p>${tag(rec.tone || 'unknown', rec.label || '—', rec.tone === 'brand' ? 'star' : 'info')}</div>
      <p class="headline" id="decisionHeadline">${esc(headline)}</p>
      ${figure}
      ${deltas ? `<div class="deltas">${deltas}</div>` : ''}
      ${subsetWarn}
      <div class="foot">${h.provenanceHtml(vm)}${svc}</div>
    </section>`;
  }

  /* ---------------- 四方案卡 ---------------- */
  function optionHtml(c, vm, h) {
    const { esc, tag } = h;
    const years = isNum(vm.studyYears) ? `${vm.studyYears} 年总花费` : '总花费';
    const d = fmt.delta(c.incremental);
    let deltaLine;
    if (c.id === 'S0_grid') deltaLine = '<span class="option-delta base">比较基线</span>';
    else if (c.admission.status === 'unknown') deltaLine = '<span class="option-delta na">缺少报价，暂无法比较</span>';
    else deltaLine = `<span class="option-delta ${d.dir}">${esc(d.text)}</span>`;
    const price = isNum(c.totalCost)
      ? `<span class="value">${esc(fmt.money(c.totalCost))}<small>元</small></span>`
      : `<span class="value" style="font-size:18px;color:var(--ink-3)">${c.totalCost === null ? '无法计算' : '样例未保存'}</span>`;
    const notes = [];
    if (c.admission.status === 'excluded') notes.push(`<div class="option-note bad">${esc(c.reasons.join('；') || c.constraintText || '不满足限制条件')}</div>`);
    if (c.admission.status === 'unknown') notes.push(`<div class="option-note unknown">${esc(c.constraintText || '条件不全')}：不是淘汰，补齐报价后才能比较。</div>`);
    if (c.admission.status === 'equivalent') notes.push(`<div class="option-note unknown">与${esc((D.SCENARIOS[c.equivalentTo] || {}).name || c.equivalentTo)}结果相同</div>`);
    const capacity = [isNum(c.pvKwp) && c.pvKwp > 0 ? `光伏 ${fmt.num(c.pvKwp)} kWp` : null, isNum(c.windCount) && c.windCount > 0 ? `小风机 ${c.windCount} 台` : null].filter(Boolean).join(' · ');
    const st = (k, v, u) => `<div class="stat"><span class="k">${esc(k)}</span><span class="v">${esc(v)}${u ? `<small>${esc(u)}</small>` : ''}</span></div>`;
    return `<article class="option${c.isRecommended ? ' is-recommended' : ''}${c.admission.status === 'excluded' ? ' is-excluded' : ''}" aria-label="${esc(c.name)}">
      ${c.isRecommended ? '<span class="ribbon">推荐</span>' : ''}
      <div class="option-head">
        <div><div class="option-name"><span class="option-swatch" style="background:${c.color}"></span>${esc(c.name)}</div>
          <div class="option-desc">${esc(capacity || c.desc)}</div></div>
        ${tag(c.admission.tone, c.admission.label, c.admission.icon)}
      </div>
      <div class="option-price"><div class="k">${esc(years)}</div>${price}<div>${deltaLine}</div></div>
      ${notes.join('')}
      <div class="option-stats">
        ${st('一年发电', fmt.kwh(c.gen), ' kWh')}
        ${st('一年从电网买', fmt.kwh(c.gridImport), ' kWh')}
        ${st('空调用电自给比例', fmt.pct(c.coverage), '')}
        ${st('初始投入', isNum(c.capex) ? fmt.money(c.capex) : (c.capex === null ? '缺报价' : '—'), isNum(c.capex) ? ' 元' : '')}
      </div>
    </article>`;
  }

  /* ---------------- 说明句：发电多 ≠ 省钱 ---------------- */
  function insightHtml(vm, h) {
    const s3 = vm.candidates.find((c) => c.id === 'S3_pv_wind');
    const load = vm.load.annualKwh;
    if (!s3 || !isNum(s3.gen) || !isNum(load) || !isNum(s3.coverage)) return '';
    const more = s3.gen > load;
    return `<div class="banner banner-brand">${h.icon('spark')}<div>
      <p><b>发电多，不等于省钱。</b>光伏+小风机一年发电 ${h.esc(fmt.kwh(s3.gen))} kWh，${more ? '比' : '少于'}空调全年用电 ${h.esc(fmt.kwh(load))} kWh${more ? '还多' : ''}；
      但按逐小时匹配，空调用电中只有 ${h.esc(fmt.pct(s3.coverage))} 是当时由自家发电覆盖的，其余仍要从电网买。</p>
      <p class="sub">原因是发电高峰和空调使用时段不完全重合——下面的能源日历把每一个小时摊开给你看。</p></div></div>`;
  }

  /* ---------------- 能源日历 ---------------- */
  const HEAT_LEGEND = {
    load: '<span><i style="background:linear-gradient(90deg,#EEF6F5,#0A524E);width:48px"></i>空调用电：浅 → 深 = 少 → 多</span><span><i style="background:#F1F3F5"></i>不用电</span>',
    gen: '<span><i style="background:linear-gradient(90deg,#FFF6E5,#8A5A00);width:48px"></i>光伏+风机发电：浅 → 深 = 少 → 多</span><span><i style="background:#F1F3F5"></i>不发电</span>',
    match: '<span><i style="background:var(--c-self)"></i>发的电当时用上</span><span><i style="background:var(--c-waste)"></i>发了没人用（浪费）</span><span><i style="background:var(--c-import)"></i>主要靠电网</span><span><i style="background:#F1F3F5"></i>不用电也不发电</span>'
  };

  function heatCardHtml(vm, h) {
    const { esc } = h;
    if (!vm.hourly) {
      return `<section class="card chart-card"><div class="chart-head"><div><h3 class="card-title">能源日历</h3>
        <p>该样例只保存了方案汇总，没有逐小时数据。选择“默认四方案”样例可查看全年 8784 小时的能源日历。</p></div></div></section>`;
    }
    const sid = vm.hourly.scenarioId; const sname = (D.SCENARIOS[sid] || {}).name || sid;
    const seg = [['match', '发电时空调在用吗'], ['load', '空调用电'], ['gen', '发电']]
      .map(([k, l]) => `<button type="button" data-heat="${k}" aria-pressed="${ui.heatView === k}">${l}</button>`).join('');
    return `<section class="card chart-card" id="heatCard">
      <div class="chart-head"><div><h3 class="card-title">能源日历：全年每一个小时</h3>
        <p>横轴是日期，纵轴是一天中的小时。以「${esc(sname)}」方案为例（样例只保存了这一方案的逐时数据）。把鼠标移到格子上看当时的用电和发电。</p></div>
        <div class="segmented" role="group" aria-label="日历视图">${seg}</div></div>
      <div class="legend" id="heatLegend">${HEAT_LEGEND[ui.heatView]}</div>
      <div id="heatmap"></div>
      <p class="chart-note">${esc(vm.hourly.samplingRule || '完整逐时数据')}。格子颜色只表示当时哪种去向最多；年度数字以方案卡为准。</p>
    </section>`;
  }

  /* ---------------- 电去哪了 ---------------- */
  function flowCardHtml(vm, h) {
    const cands = vm.candidates.filter((c) => c.id !== 'S0_grid' && isNum(c.gen) && c.gen > 0 && isNum(c.selfUse));
    if (!cands.length) return '';
    if (!ui.flowId || !cands.find((c) => c.id === ui.flowId)) ui.flowId = (cands.find((c) => c.id === 'S3_pv_wind') || cands[0]).id;
    const seg = cands.map((c) => `<button type="button" data-flow="${c.id}" aria-pressed="${ui.flowId === c.id}">${h.esc(c.name)}</button>`).join('');
    return `<section class="card chart-card" id="flowCard">
      <div class="chart-head"><div><h3 class="card-title">电去哪了</h3><p>一年发的电分别去了哪里，空调用的电分别从哪里来。</p></div>
        <div class="segmented" role="group" aria-label="选择方案">${seg}</div></div>
      <div class="flow" id="flowBody"></div>
    </section>`;
  }

  function renderFlow(vm) {
    const body = document.getElementById('flowBody'); if (!body) return;
    const c = vm.candidates.find((x) => x.id === ui.flowId); if (!c) return;
    body.innerHTML = '';
    const row = (title, total, parts) => {
      const r = document.createElement('div'); r.className = 'flow-row';
      r.innerHTML = `<div class="flow-label"><span>${title}</span><b>${total}</b></div>`;
      r.appendChild(C.flowBar(parts, 'kWh'));
      body.appendChild(r);
    };
    const val = (v) => (isNum(v) ? v : NaN);
    row('一年发的电', isNum(c.gen) ? `${fmt.kwh(c.gen)} kWh` : '—', [
      { name: '当时给空调用上', value: val(c.selfUse), color: 'var(--c-self)' },
      { name: '卖给电网', value: val(c.gridExport), color: 'var(--c-wind)' },
      { name: '发了没人用（浪费）', value: val(c.curtail), color: 'var(--c-waste)' }
    ]);
    row('空调一年用的电', isNum(vm.load.annualKwh) ? `${fmt.kwh(vm.load.annualKwh)} kWh` : '—', [
      { name: '来自自家发电', value: val(c.selfUse), color: 'var(--c-self)' },
      { name: '从电网买', value: val(c.gridImport), color: 'var(--c-import)' }
    ]);
  }

  /* ---------------- 典型日 ---------------- */
  function dayCardHtml(vm, h) {
    if (!vm.hourly) return '';
    const days = C.dayList(vm.hourly);
    if (!ui.day || !days.includes(ui.day)) ui.day = C.peakLoadDay(vm.hourly);
    return `<section class="card chart-card" id="dayCard">
      <div class="chart-head"><div><h3 class="card-title">一天之内：用电和发电对得上吗</h3>
        <p>同一天 24 小时的空调用电（黑线）、光伏发电（琥珀）和风机发电（蓝色虚线）。默认显示全年空调用电最多的一天。</p></div>
        <div class="row">
          <input class="input" type="date" id="dayPick" value="${h.esc(ui.day)}" min="${h.esc(days[0])}" max="${h.esc(days[days.length - 1])}" style="height:36px;width:auto" aria-label="选择日期">
          <button class="btn btn-sm" type="button" data-day="peak">用电最多的一天</button>
        </div></div>
      <div class="legend"><span><i class="line" style="background:var(--c-load)"></i>空调用电</span><span><i class="line" style="background:var(--c-pv)"></i>光伏发电</span><span><i class="line" style="background:var(--c-wind)"></i>风机发电</span></div>
      <div id="dayChart"></div>
    </section>`;
  }

  /* ---------------- 表格视图 ---------------- */
  function tableHtml(vm, h) {
    const { esc } = h;
    const rows = vm.candidates.map((c) => `<tr><td>${esc(c.name)}</td><td style="text-align:left">${esc(c.admission.label)}</td>
      <td>${esc(isNum(c.totalCost) ? fmt.money(c.totalCost) : '—')}</td><td>${esc(c.id === 'S0_grid' ? '基线' : fmt.delta(c.incremental).text)}</td>
      <td>${esc(fmt.kwh(c.gen))}</td><td>${esc(fmt.kwh(c.gridImport))}</td><td>${esc(fmt.pct(c.coverage))}</td><td>${esc(isNum(c.capex) ? fmt.money(c.capex) : '—')}</td></tr>`).join('');
    return `<details class="more"><summary>用表格查看四个方案</summary>
      <div class="table-wrap mt-2"><table class="table"><thead><tr><th>方案</th><th style="text-align:left">状态</th><th>总花费（元）</th><th>相对只用电网</th><th>年发电（kWh）</th><th>年购电（kWh）</th><th>自给比例</th><th>初始投入（元）</th></tr></thead>
      <tbody>${rows}</tbody></table></div></details>`;
  }

  /* ---------------- 主渲染 ---------------- */
  function render(host, vm, h) {
    host.innerHTML = `${h.head}
      ${decisionHtml(vm, h)}
      <section>
        <div class="section-head"><div><h3 class="card-title">四种供电方式</h3><p>“只用电网”永远作为基线显示在第一位。状态标签说明每个方案能不能参与比较。</p></div></div>
        <div class="grid grid-4">${vm.candidates.map((c) => optionHtml(c, vm, h)).join('')}</div>
      </section>
      ${insightHtml(vm, h)}
      ${heatCardHtml(vm, h)}
      <div class="grid grid-2">${flowCardHtml(vm, h)}${dayCardHtml(vm, h)}</div>
      ${tableHtml(vm, h)}
      ${h.stepNavHtml(2, 4, '查看推荐与导出')}`;
    drawCharts(host, vm);
    bind(host, vm);
  }

  function drawCharts(host, vm) {
    const hm = host.querySelector('#heatmap');
    if (hm && vm.hourly) C.heatmap(hm, vm.hourly, ui.heatView);
    renderFlow(vm);
    const dc = host.querySelector('#dayChart');
    if (dc && vm.hourly) C.dayCurve(dc, vm.hourly, ui.day);
  }

  function bind(host, vm) {
    host.querySelectorAll('[data-heat]').forEach((b) => b.addEventListener('click', () => {
      ui.heatView = b.dataset.heat;
      host.querySelectorAll('[data-heat]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      host.querySelector('#heatLegend').innerHTML = HEAT_LEGEND[ui.heatView];
      C.heatmap(host.querySelector('#heatmap'), vm.hourly, ui.heatView);
    }));
    host.querySelectorAll('[data-flow]').forEach((b) => b.addEventListener('click', () => {
      ui.flowId = b.dataset.flow;
      host.querySelectorAll('[data-flow]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      renderFlow(vm);
    }));
    const pick = host.querySelector('#dayPick');
    if (pick) pick.addEventListener('change', () => { if (pick.value) { ui.day = pick.value; C.dayCurve(host.querySelector('#dayChart'), vm.hourly, ui.day); } });
    const peak = host.querySelector('[data-day="peak"]');
    if (peak) peak.addEventListener('click', () => { ui.day = C.peakLoadDay(vm.hourly); pick.value = ui.day; C.dayCurve(host.querySelector('#dayChart'), vm.hourly, ui.day); });
  }

  // 视口宽度变化时重画（图表坐标跟随容器宽度）
  let rh;
  window.addEventListener('resize', () => {
    clearTimeout(rh);
    rh = setTimeout(() => {
      const st = window.NZH.state; const host = document.getElementById('step3');
      if (st && st.vm && host && !host.hidden) drawCharts(host, st.vm);
    }, 200);
  });

  window.NZH = window.NZH || {};
  window.NZH.stage = { render, ui };
})();
