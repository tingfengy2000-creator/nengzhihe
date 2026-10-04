(() => {
  const $ = (s) => document.querySelector(s);
  const state = { jobId: null, latest: null, pollToken: 0, tariffs: null, customTariff: null, userWeather: null };
  const planNames = { baseline: '模型默认运行', pre_cool: '营业前预冷', setpoint_shift: '营业时段温度调整', pre_cool_and_shift: '预冷并调整温度' };
  const fmt = (v, n = 3) => (v === null || v === undefined || !Number.isFinite(Number(v)) ? '尚未计算' : Number(v).toFixed(n));
  const setText = (el, text) => { if (el) el.textContent = String(text ?? ''); };
  const api = (url, options) => fetch(url, options).then(async r => { const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || `请求失败 ${r.status}`); return d; });

  document.querySelectorAll('.nav button').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('.nav button').forEach(x => x.classList.toggle('active', x === button));
    document.querySelectorAll('.page').forEach(x => x.classList.toggle('active', x.id === button.dataset.page));
    if (button.dataset.page === 'tariffs') loadTariffs();
    if (button.dataset.page === 'history') loadHistory();
  }));

  function selectedTariff() { return $('#tariff').value; }
  let equipmentLoaded = false;
  function loadEquipment() {
    if (equipmentLoaded || !$('#selEquipment')) return;
    api('/api/operation/equipment').then(data => { const select = $('#selEquipment'); select.replaceChildren(); (data.items || []).forEach(item => { const option = document.createElement('option'); option.value = item.equipment_id; option.textContent = `${item.brand} · ${item.model}`; option.selected = true; select.append(option); }); equipmentLoaded = true; }).catch(e => setText($('#selectionStatus'), e.message));
  }
  function configureTariffs() {
    const region = $('#region').value;
    const select = $('#tariff'); select.replaceChildren();
    const options = region === 'fujian_dehua' ? [['fujian_industrial_lt1kv_202607', '福建工商业单一制不满1kV（历史7月）']] : region === 'guangdong_north' ? [['guangdong_north_industrial_lt1kv_202607', '广东粤北工商业单一制不满1kV（历史7月）']] : [['boptest_dynamic', 'BOPTEST 动态电价（USD）'], ['boptest_constant', 'BOPTEST 常数电价（USD）'], ['boptest_highly_dynamic', 'BOPTEST 高动态电价（USD）'], ...(state.customTariff ? [['custom_user', '用户提供分时电价（未核验）']] : [])];
    options.forEach(([value, label]) => { const option = document.createElement('option'); option.value = value; option.textContent = label; select.append(option); });
    $('#calendarDate').disabled = region === 'model_reference';
  }
  $('#region').addEventListener('change', configureTariffs); configureTariffs();
  $('#saveCustom').addEventListener('click', () => { const flat = Number($('#customFlat').value), peak = Number($('#customPeak').value), valley = Number($('#customValley').value); if (![flat, peak, valley].every(Number.isFinite) || [flat, peak, valley].some(x => x < 0)) { setText($('#customStatus'), '请填写完整且非负的三段价格'); return; } state.customTariff = { area: $('#customArea').value || '用户提供供电区域', effective_start: $('#customStart').value, effective_end: $('#customEnd').value, periods: [{ name: 'valley', start: '00:00', end: '08:00', price: valley }, { name: 'peak', start: '08:00', end: '20:00', price: peak }, { name: 'flat', start: '00:00', end: '24:00', price: flat }] }; configureTariffs(); $('#tariff').value = 'custom_user'; setText($('#customStatus'), '已保存到本次试算，标记为用户提供'); });
  loadEquipment();

  function selectionPayload(equipmentId) {
    const payload = { site_id: $('#selSite').value, year: Number($('#selYear').value), annual_price_cny_per_kwh: Number($('#selPrice').value), study_years: Number($('#selYears').value), quantity: Number($('#selQuantity').value), equipment_quote: { equipment_price_cny: Number($('#selEquipmentPrice').value), installation_cny: Number($('#selInstallPrice').value), maintenance_cny_per_year: Number($('#selMaintenancePrice').value) }, room: { area_m2: Number($('#selArea').value), people_count: Number($('#selPeople').value), start_hour: Number($('#selStart').value), end_hour: Number($('#selEnd').value), cooling_setpoint_c: Number($('#selTemp').value), indoor_temp_c: Number($('#selTemp').value), rh_setpoint_percent: Number($('#selRh').value), indoor_rh_percent: Number($('#selRh').value), window_wall_ratio: Number($('#selWwr').value), ventilation_lps_person: Number($('#selVent').value), infiltration_ach: Number($('#selAch').value), orientation: $('#selOrientation').value, equipment_id: equipmentId } };
    if (state.userWeather) payload.weather = state.userWeather;
    return payload;
  }

  $('#selWeatherCsv').addEventListener('change', () => {
    const file = $('#selWeatherCsv').files?.[0]; if (!file) return;
    const reader = new FileReader(); reader.onload = () => api('/api/operation/weather/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ csv: reader.result }) }).then(data => { state.userWeather = data.weather; setText($('#selWeatherStatus'), `已载入用户CSV：${data.weather.time.length}条记录，来源标记为 user_csv`); }).catch(e => { state.userWeather = null; setText($('#selWeatherStatus'), `CSV未通过校验：${e.message}`); }); reader.readAsText(file, 'utf-8');
  });
  function runSelection() {
    const ids = [...$('#selEquipment').selectedOptions].map(x => x.value); if (!ids.length) { setText($('#selectionStatus'), '请至少选择一个型号'); return; }
    setText($('#selectionStatus'), `正在计算 ${ids.length} 个型号的逐时热湿响应…`); $('#runSelection').disabled = true;
    Promise.all(ids.map(id => api('/api/operation/thermal/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(selectionPayload(id)) }).then(data => ({ id, data })))).then(items => { renderSelection(items); setText($('#selectionStatus'), `完成：${items.length} 个型号可比较`); }).catch(e => setText($('#selectionStatus'), e.message)).finally(() => { $('#runSelection').disabled = false; });
  }
  $('#runSelection').addEventListener('click', runSelection);
  function renderSelection(items) {
    $('#selectionResults').hidden = false; setText($('#selectionTitle'), '同一房间与天气条件下的设备比较'); setText($('#selectionSubtitle'), `${$('#selSite').selectedOptions[0].textContent} · ${$('#selYear').value} 参考年 · ${$('#selArea').value}m² · ${$('#selTemp').value}°C / ${$('#selRh').value}%RH · ${$('#selQuantity').value} 个同类房间（成本按数量计）`);
    const metric = $('#selectionMetrics'); metric.replaceChildren(); const first = items[0].data.result.summary; [['单房间年空调电量', `${fmt(first.electric_kwh, 1)} kWh`], ['显热 / 潜热冷却', `${fmt(first.sensible_cooling_kwh, 1)} / ${fmt(first.latent_cooling_kwh, 1)} kWh`], ['温度未满足', `${fmt(first.unmet_temp_degree_hours, 2)} °C·h`], ['湿度未满足', `${fmt(first.unmet_rh_percent_hours, 2)} %RH·h`], ['冷却运行时段', `${fmt(first.cooling_season_hours, 1)} h`]].forEach(([label, value]) => { const box = document.createElement('div'); box.className = 'metric'; const small = document.createElement('small'); small.textContent = label; const strong = document.createElement('strong'); strong.textContent = value; box.append(small, strong); metric.append(box); });
    const table = document.createElement('table'); const trh = document.createElement('tr'); ['型号', '初始投入', '年电量', '年电费参考', `${$('#selYears').value}年全周期成本`, '能力缺口'].forEach(x => { const th = document.createElement('th'); th.textContent = x; trh.append(th); }); const thead = document.createElement('thead'); thead.append(trh); const tbody = document.createElement('tbody'); items.forEach(({ data }) => { const eq = data.result.equipment, sum = data.result.summary, lcc = data.cost.lifecycle || {}; const complete = lcc.status === 'complete'; const tr = document.createElement('tr'); [eq.brand + ' · ' + eq.model, complete ? `${fmt(lcc.initial_cny, 0)} CNY` : '待补报价', `${fmt(sum.electric_kwh, 1)} kWh`, complete ? `${fmt((lcc.electricity_pv_cny || 0) / Number($('#selYears').value), 0)} CNY/年` : '待补报价', complete ? `${fmt(lcc.total_pv_cny, 0)} CNY` : '待补报价', `${sum.capacity_shortfall_hours ? `能力不足 ${fmt(sum.capacity_shortfall_hours, 1)} h` : '未发现能力不足'}`].forEach((value, index) => { const td = document.createElement('td'); td.textContent = value; if (index === 5 && sum.capacity_shortfall_hours) td.className = 'bad'; if (index === 0 && !complete) td.title = (lcc.missing || []).join('、'); tr.append(td); }); tbody.append(tr); }); table.append(thead, tbody); const wrapper = $('#selectionTable'); wrapper.replaceChildren(table); renderSelectionChart(items[0].data.result, items[0].data.cost); const complete = items.filter(x => x.data.cost.lifecycle?.status === 'complete').length; setText($('#selectionInterpretation'), complete ? `已按相同房间、天气和用户参考报价完成 ${complete} 个全周期成本计算；温湿度缺口仍按设备能力单独显示。` : '热湿和耗电已完成；若没有设备、安装或维护报价，系统只给出电量与负荷结果，不把缺失费用当作0。'); $('#selectionRaw').textContent = JSON.stringify(items.map(x => ({ equipment_id: x.id, weather: x.data.weather, summary: x.data.result.summary, lifecycle: x.data.cost.lifecycle, monthly: x.data.cost.monthly })), null, 2);
  }

  function renderSelectionChart(result, cost) { const chart = $('#selectionChart'); chart.replaceChildren(); const monthly = cost.monthly || {}; const keys = Object.keys(monthly).sort(); if (!keys.length) { chart.textContent = '没有可显示的逐月费用（请补充价格情景）。'; return; } const w = 760, h = 260, pad = 38, max = Math.max(...keys.map(k => Number(monthly[k].electric_kwh) || 0), 1); const bars = keys.map((k, i) => { const x = pad + i * (w - pad * 2) / Math.max(1, keys.length), bw = Math.max(5, (w - pad * 2) / Math.max(1, keys.length) - 4), bh = (Number(monthly[k].electric_kwh) || 0) / max * (h - pad * 2); return `<rect x="${x.toFixed(1)}" y="${(h-pad-bh).toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="3" fill="#2563eb"><title>${k}：${fmt(monthly[k].electric_kwh,1)} kWh / ${fmt(monthly[k].cost_cny,0)} CNY</title></rect><text x="${(x+bw/2).toFixed(1)}" y="${h-12}" text-anchor="middle" font-size="10" fill="#64748b">${k.slice(5)}</text>`; }).join(''); chart.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="逐月空调电量柱状图"><line x1="${pad}" y1="${h-pad}" x2="${w-pad}" y2="${h-pad}" stroke="#cbd5e1"/>${bars}<text x="${pad}" y="18" fill="#64748b">每月空调电量（kWh），柱上悬停可见电费</text></svg>`; }

  function taskPayload() {
    const tariff = selectedTariff();
    return { request: $('#request').value, use_agent: $('#useAgent').value === 'true', step_seconds: Number($('#step').value), task: {
      simulation_day: Number($('#weatherDay').value), business_start_hour: Number($('#startHour').value), business_end_hour: Number($('#endHour').value), lower_temp_c: Number($('#low').value), upper_temp_c: Number($('#high').value), objective: $('#objective').value, max_candidates: Number($('#maxCandidates').value), recovery_hours: Number($('#recovery').value), tariff_id: tariff, custom_tariff: tariff === 'custom_user' ? state.customTariff : null, tariff_calendar_date: tariff.startsWith('boptest_') ? null : $('#calendarDate').value, price_profile: tariff.startsWith('boptest_') ? tariff.slice(8) : 'custom', revision: 1,
    }};
  }

  function setBusy(busy) { $('#start').disabled = busy; $('#cancel').disabled = !busy; $('#progress').hidden = !busy; }
  function start() {
    let payload; try { payload = taskPayload(); } catch (e) { setText($('#status'), e.message); return; }
    setBusy(true); setText($('#status'), '正在提交任务…'); $('#resultsPanel').hidden = true; state.latest = null; state.pollToken += 1; const token = state.pollToken;
    api('/api/operation/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(job => { state.jobId = job.job_id; poll(token); }).catch(e => { setBusy(false); setText($('#status'), e.message); });
  }
  $('#start').addEventListener('click', start);
  $('#cancel').addEventListener('click', () => { if (state.jobId) api(`/api/operation/cancel/${state.jobId}`, { method: 'POST' }).then(() => setText($('#status'), '已请求取消，等待当前回放结束')).catch(e => setText($('#status'), e.message)); });

  function poll(token) {
    if (token !== state.pollToken || !state.jobId) return;
    api(`/api/operation/task/${state.jobId}`).then(job => {
      const completed = Number(job.completed_candidates || 0), total = Number(job.total_candidates || 0);
      setText($('#progressText'), total ? `已完成 ${completed}/${total} 个候选` : (job.status === 'running' ? '正在验证任务并准备回放' : '排队中'));
      $('#progressBar').style.width = total ? `${Math.min(100, completed / total * 100)}%` : (job.status === 'running' ? '8%' : '2%');
      if (job.status === 'queued' || job.status === 'running') { setTimeout(() => poll(token), 900); return; }
      setBusy(false); if (job.status === 'done') { state.latest = job; renderJob(job); setText($('#status'), '完成：请复核并确认当前推荐后导出'); } else { setText($('#status'), `任务${job.status === 'cancelled' ? '已取消' : '失败'}：${job.output?.error || '请检查输入'}`); }
    }).catch(e => { if (token === state.pollToken) { setBusy(false); setText($('#status'), e.message); } });
  }

  function currentSelection(job) { const report = job.output?.report || {}; return (report.candidates || []).find(c => c.result?.result_id === job.current_result_id) || (report.candidates || []).find(c => c.plan?.plan_id === report.recommended_plan_id) || report.candidates?.[0]; }
  function renderJob(job) {
    const report = job.output?.report || {}, chosen = currentSelection(job), result = chosen?.result || {}, metrics = result.custom_metrics || {}, task = report.task || {};
    $('#resultsPanel').hidden = false; setText($('#resultTitle'), chosen ? `${planNames[chosen.plan?.kind] || chosen.plan?.plan_id || '当前方案'} · ${chosen.status === 'feasible' ? '满足使用要求' : '部分时段未达标'}` : '没有可用候选');
    setText($('#resultSubtitle'), `${report.candidates?.length || 0} 个候选 · 比较范围由 balanced_v2 候选策略固定 · 天气样本日 ${task.simulation_day || '—'} · 计费日 ${task.tariff_calendar_date || '模型价格日'}`);
    const amount = metrics.total_cost_cny ?? metrics.target_cost_usd; const unit = metrics.cost_currency || (metrics.target_cost_usd !== undefined ? 'USD' : '');
    const cards = [['达标状态', chosen?.status === 'feasible' ? '满足使用要求' : '部分时段未达标', chosen?.status === 'feasible' ? 'ok' : 'bad'], ['目标日空调电量', `${fmt(metrics.target_electric_kwh)} kWh`, ''], ['目标日电费估算', amount === null || amount === undefined ? '尚未计算' : `${fmt(amount)} ${unit}`, ''], ['目标 / 恢复 / 合计', metrics.total_cost_cny === undefined ? (metrics.cost_period || '目标日') : `${fmt(metrics.target_cost_cny)} / ${fmt(metrics.recovery_cost_cny)} / ${fmt(metrics.total_cost_cny)} CNY`, '']];
    const metricBox = $('#metrics'); metricBox.replaceChildren(); cards.forEach(([label, value, cls]) => { const div = document.createElement('div'); div.className = 'metric'; const small = document.createElement('small'); small.textContent = label; const strong = document.createElement('strong'); strong.className = cls; strong.textContent = value; div.append(small, strong); metricBox.append(div); });
    const segs = chosen?.plan?.segments || []; const planText = segs.length ? segs.map(s => `${s.start_minute}–${s.end_minute} 分钟：${s.reason}`).join('；') : '使用模型默认控制时段。'; $('#planSummary').textContent = `${planNames[chosen?.plan?.kind] || '当前方案'}：${planText}`;
    renderChart(result, task); renderTimeline(task, metrics); renderCandidates(report.candidates || []); renderTrace(job.events || [], job.output?.trace || []); $('#rawJson').textContent = JSON.stringify({ task, selected: chosen, report: { recommended_plan_id: report.recommended_plan_id, unresolved_requirements: report.unresolved_requirements } }, null, 2);
  }

  function renderCandidates(candidates) { const wrap = $('#candidateTable'); wrap.replaceChildren(); if (!candidates.length) { wrap.textContent = '没有候选结果'; return; } const table = document.createElement('table'); const head = document.createElement('tr'); ['运行安排', '状态', '费用', '空调电量', '严格越界度时', '计算'].forEach(x => { const th = document.createElement('th'); th.textContent = x; head.append(th); }); const thead = document.createElement('thead'); thead.append(head); const tbody = document.createElement('tbody'); candidates.forEach(c => { const tr = document.createElement('tr'), m = c.result?.custom_metrics || {}, plan = c.plan || {}; [planNames[plan.kind] || plan.plan_id || '—', c.status === 'feasible' ? '满足使用要求' : c.status === 'infeasible' ? '部分时段未达标' : '错误', m.total_cost_cny !== undefined ? `${fmt(m.total_cost_cny)} CNY` : m.target_cost_usd !== undefined ? `${fmt(m.target_cost_usd)} USD` : '—', `${fmt(m.target_electric_kwh)} kWh`, `${fmt(m.occupied_strict_degree_hours)} h·°C`, c.elapsed_seconds !== undefined ? `${fmt(c.elapsed_seconds, 1)} s` : '—'].forEach((value, i) => { const td = document.createElement('td'); td.textContent = value; if (i === 1 && c.status === 'feasible') td.className = 'ok'; if (i === 1 && c.status === 'infeasible') td.className = 'bad'; tr.append(td); }); tbody.append(tr); }); table.append(thead, tbody); wrap.append(table); }
  function renderTrace(events, trace) { const box = $('#trace'); box.replaceChildren(); [...events, ...trace].slice(-50).forEach(item => { const div = document.createElement('div'); div.className = 'trace-item'; const strong = document.createElement('strong'); strong.textContent = item.type || item.action || '核验'; const span = document.createElement('span'); span.textContent = `：${item.message || item.error || (item.plan_id ? `候选 ${item.plan_id}` : '')}`; div.append(strong, span); box.append(div); }); if (!box.children.length) box.textContent = '无额外轨迹'; }

  function renderChart(result, task) {
    const chart = $('#chart'); chart.replaceChildren(); const ts = result.time_seconds || [], ys = result.temperature_c || []; if (ts.length < 2 || ys.length < 2) { chart.textContent = '没有可画的真实结果。'; return; }
    const points = ts.map((t, i) => [Number(t), ys[i] == null ? null : Number(ys[i])]).filter(p => Number.isFinite(p[0])); const valid = points.filter(p => p[1] !== null && Number.isFinite(p[1])); if (!valid.length) { chart.textContent = '温度缺测，保留未决。'; return; }
    const w = 820, h = 280, pad = 42, minX = points[0][0], maxX = points[points.length - 1][0], lower = Number(task.lower_temp_c), upper = Number(task.upper_temp_c), values = valid.map(p => p[1]); const minY = Math.min(...values, lower - 1), maxY = Math.max(...values, upper + 1); const x = t => pad + (w - pad * 2) * (t - minX) / Math.max(1, maxX - minX), y = v => h - pad - (h - pad * 2) * (v - minY) / Math.max(1, maxY - minY);
    const lines = []; let current = []; points.forEach(p => { if (p[1] === null || !Number.isFinite(p[1])) { if (current.length) lines.push(current.join(' ')); current = []; return; } current.push(`${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`); }); if (current.length) lines.push(current.join(' '));
    const targetStart = minX + Number(task.business_start_hour) * 3600, targetEnd = minX + Number(task.business_end_hour) * 3600; const paths = lines.map(line => `<polyline points="${line}" fill="none" stroke="#2563eb" stroke-width="2.4" stroke-linejoin="round"/>`).join(''); const svg = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="真实时间轴温度回放"><line x1="${pad}" y1="${y(lower)}" x2="${w-pad}" y2="${y(lower)}" stroke="#db8b2b" stroke-dasharray="5 4"/><line x1="${pad}" y1="${y(upper)}" x2="${w-pad}" y2="${y(upper)}" stroke="#db8b2b" stroke-dasharray="5 4"/><line x1="${x(targetStart)}" y1="${pad/2}" x2="${x(targetStart)}" y2="${h-pad/2}" stroke="#7c3aed" stroke-dasharray="3 4"/><line x1="${x(targetEnd)}" y1="${pad/2}" x2="${x(targetEnd)}" y2="${h-pad/2}" stroke="#7c3aed" stroke-dasharray="3 4"/>${paths}<text x="${pad}" y="18" fill="#64748b">${minY.toFixed(1)}–${maxY.toFixed(1)}°C · 真实时间 ${Math.round((maxX-minX)/3600)}h · 上下限 ${lower}–${upper}°C</text><text x="${Math.min(w-pad-90, Math.max(pad, x(targetStart)+4))}" y="${h-10}" fill="#64748b">使用开始</text><text x="${Math.min(w-pad-95, Math.max(pad, x(targetEnd)+4))}" y="${h-10}" fill="#64748b">使用结束</text></svg>`; chart.innerHTML = svg;
  }
  function renderTimeline(task, metrics) { const strip = $('#timeline'); strip.replaceChildren(); const tariff = selectedTariff(); for (let i = 0; i < 24; i++) { const span = document.createElement('span'); const occupied = i >= Number(task.business_start_hour) && i < Number(task.business_end_hour); let kind = occupied ? 'peak' : 'flat'; if (tariff.startsWith('boptest_')) kind = i < 6 ? 'valley' : 'flat'; else if (i < 8) kind = 'valley'; else if ([10, 11, 15, 16, 17].includes(i)) kind = 'super_peak'; span.className = `price-${kind}`; span.textContent = `${i}`; span.title = `${i}:00 · ${kind} · ${occupied ? '使用时段' : '恢复/非使用'}`; strip.append(span); } }

  $('#confirm').addEventListener('click', () => { if (!state.jobId) return; api(`/api/operation/confirm/${state.jobId}`, { method: 'POST' }).then(() => setText($('#status'), '已确认当前推荐，可导出')).catch(e => setText($('#status'), e.message)); });
  [['exportJson', 'json'], ['exportHtml', 'html'], ['exportCsv', 'csv']].forEach(([id, format]) => $(`#${id}`).addEventListener('click', () => { if (state.jobId) window.open(`/api/operation/export/${state.jobId}?format=${format}`, '_blank'); }));

  function loadTariffs() { if (state.tariffs) return; api('/api/operation/tariffs').then(data => { state.tariffs = data; const cards = $('#tariffCards'); cards.replaceChildren(); (data.tariffs || []).forEach(t => { const card = document.createElement('article'); card.className = 'tariff-card'; const h = document.createElement('h3'); h.textContent = t.source_title; const meta = document.createElement('div'); meta.className = 'meta'; meta.textContent = `${t.area} · ${t.category} · ${t.voltage_level} · ${t.effective_start}—${t.effective_end}`; const p = document.createElement('p'); p.textContent = `${t.verified ? '官方已核验' : '用户提供'} · ${t.currency}/${t.unit.split('/')[1] || 'kWh'} · ${t.billing_type}`; const source = document.createElement('a'); source.href = t.source_url; source.target = '_blank'; source.rel = 'noreferrer'; source.textContent = '查看官方来源'; card.append(h, meta, p, source); cards.append(card); }); }).catch(e => { $('#tariffCards').textContent = e.message; }); }
  function loadHistory() { api('/api/operation/history').then(data => { const list = $('#historyList'); list.replaceChildren(); if (!data.items?.length) { list.textContent = '暂无历史任务。'; return; } data.items.forEach(item => { const row = document.createElement('div'); row.className = 'history-row'; const left = document.createElement('div'); const title = document.createElement('strong'); title.textContent = item.task?.user_request || item.job_id; const sub = document.createElement('div'); sub.className = 'muted'; sub.textContent = `${item.task?.tariff_id || '—'} · 修订 v${item.task?.revision || item.revision || 1} · ${item.user_confirmed ? '已确认' : '未确认'}`; left.append(title, sub); const chip = document.createElement('span'); chip.className = `status-chip ${item.status}`; chip.textContent = item.status === 'done' ? '已完成' : item.status; row.append(left, chip); list.append(row); }); }).catch(e => { $('#historyList').textContent = e.message; }); }
  loadTariffs();
})();

