/*
 * 能见度前端重构 · 自动验收检查（任务书 docs/handoff/frontend_redesign/PROMPT.md 第 9 节）
 *
 * 用法（仓库根目录）：
 *   python -m operation_planning.run_server            # 另开终端，监听 127.0.0.1:18765
 *   python -m http.server 18799 --bind 127.0.0.1       # 另开终端，用于“未连接计算服务”检查
 *   node scripts/check_frontend_redesign.cjs           # 需要本机已安装 playwright（npm i -g playwright）
 *
 * 一句话输入的本地大模型分支用脚本内启动的**仅测试用**桩服务检查：桩服务监听 127.0.0.1:18767，
 * 只模拟 /api/operation/agent/status 与 /api/operation/agent/parse 的各种返回，其余请求原样转发给
 * 18765 的计算服务。桩服务不提交到 operation_planning/，真实模型联调由 5090 在本机完成。
 *
 * 只读检查：不调用任何计算接口（实时计算流程另由人工/截图核对），不写任何数据或结果文件。
 * 期望值直接从 docs/handoff/replay_viewer/replay_cases_ui_v9.json 读取并按页面的显示规则取整，
 * 与页面上渲染出的文字逐项比较。
 */
const fs = require('fs');
const path = require('path');
const http = require('http');
const { chromium } = require('playwright');

const BASE = process.env.NJD_BASE || 'http://127.0.0.1:18765/';
const STATIC = process.env.NJD_STATIC || 'http://127.0.0.1:18799/operation_planning/ui/index.html';
const ROOT = path.resolve(__dirname, '..');
const replay = JSON.parse(fs.readFileSync(path.join(ROOT, 'docs/handoff/replay_viewer/replay_cases_ui_v9.json'), 'utf8'));

const nf = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });
const money = (v) => nf.format(Math.round(v));
const delta = (v) => { const r = Math.round(v); return r === 0 ? null : r < 0 ? `多花 ${nf.format(-r)} 元` : `省下 ${nf.format(r)} 元`; };
const ADM = { eligible: '可比较', unknown: '条件不全', excluded: '已排除', equivalent: '与其他方案相同' };
const REC = { conditional: '有条件推荐', conditional_subset: '部分比较', not_available: '暂无推荐' };
const kwhF = (v) => (Math.abs(v) < 10 && v !== 0 ? new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(v) : nf.format(Math.round(v)));
const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();

let failures = 0, checks = 0;

/* ---------- 仅测试用桩服务：模拟 agent/status 与 agent/parse，其余转发到计算服务 ---------- */
const stub = { status: 'available', parse: 'ok', parseCalls: 0, computeCalls: 0 };
const PARSE_OK = { status: 'ok', changes: [{ field: 'room.units_per_room', from: 1, to: 3, label: '每间空调台数' }, { field: 'hybrid.budget_cny', from: null, to: 50000, label: '预算' }],
  unsupported: ['“换成格力”：设备目录中没有该品牌型号'], question: null, model: 'local_model', latency_ms: 12 };
function startStub(port = 18767) {
  const target = new URL(BASE);
  const server = http.createServer((req, res) => {
    const send = (code, body) => { const d = Buffer.from(JSON.stringify(body)); res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': d.length }); res.end(d); };
    if (req.url.startsWith('/api/operation/agent/status')) {
      if (stub.status === '404') return send(404, { error: '路径不存在' });
      if (stub.status === 'timeout') return setTimeout(() => send(200, { available: true }), 6000);
      return send(200, { available: stub.status === 'available', mode: 'local_model', label: '本地大模型', checked_at: new Date().toISOString(), reason: stub.status === 'available' ? null : '本地模型未启动' });
    }
    if (req.url.startsWith('/api/operation/agent/parse')) {
      stub.parseCalls++;
      let body = ''; req.on('data', (c) => { body += c; });
      req.on('end', () => {
        const m = stub.parse;
        if (m === '404') return send(404, { error: '路径不存在' });
        if (m === 'timeout') return setTimeout(() => send(200, PARSE_OK), 30000);
        if (m === 'ok') return send(200, PARSE_OK);
        if (m === 'needs_clarification') return send(200, { status: 'needs_clarification', changes: [], unsupported: [], question: '请给出晚上使用时段的开始和结束时间，例如18:00到22:00。', model: 'local_model', latency_ms: 9 });
        if (m === 'unavailable') return send(200, { status: 'unavailable', changes: [], unsupported: [], question: null, reason: '本地模型未启动', model: 'local_model', latency_ms: 1 });
        return send(200, { status: 'failed', changes: [], unsupported: [], question: null, reason: '模型输出不符合契约', model: 'local_model', latency_ms: 5 });
      });
      return;
    }
    if (/\/api\/operation\/hybrid\/(jobs|run|preview)/.test(req.url) && req.method === 'POST') stub.computeCalls++;
    const fwd = http.request({ host: target.hostname, port: target.port, path: req.url, method: req.method, headers: req.headers }, (r) => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
    fwd.on('error', () => send(502, { error: 'stub forward failed' }));
    req.pipe(fwd);
  });
  return new Promise((resolve) => server.listen(port, '127.0.0.1', () => resolve(server)));
}

async function checkAgent(browser) {
  const server = await startStub();
  const SB = 'http://127.0.0.1:18767/';
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs = []; page.on('pageerror', (e) => errs.push(e.message));
  const open = async () => { await page.goto(SB + '#/tool/1'); await page.reload(); await page.waitForSelector('[data-ask] .tag'); await page.waitForTimeout(400); };
  const ask = async (text) => { await page.fill('#askInput', text); await page.click('[data-action="ask"]'); };
  const tagText = () => page.textContent('[data-ask] .tag');
  // 状态：可用 → 标签“本地大模型理解”
  stub.status = 'available'; await open();
  await page.waitForFunction(() => /本地大模型理解/.test(document.querySelector('[data-ask] .tag').textContent), null, { timeout: 8000 }).catch(() => {});
  ok(/本地大模型理解/.test(await tagText()), `可用时标签应为“本地大模型理解”：${await tagText()}`);
  // ok：显示修改清单 → 采用 → 写入表单、高亮、不自动计算
  stub.parse = 'ok'; stub.computeCalls = 0;
  await ask('每间改成3台空调，预算加到5万，换成格力');
  await page.waitForSelector('.proposal', { timeout: 10000 });
  const prop = await page.textContent('.proposal');
  ok(/每间空调台数/.test(prop) && /初始投入预算/.test(prop) && /没能处理/.test(prop) && /格力/.test(prop), `修改清单内容不全：${prop.slice(0, 120)}`);
  await page.click('[data-action="agent-apply"]'); await page.waitForTimeout(400);
  ok(await page.inputValue('[data-field="units_per_room"]') === '3' && await page.inputValue('[data-field="budget_cny"]') === '50000', '采用后表单未写入');
  ok(await page.evaluate(() => !!document.querySelector('[data-wrap="units_per_room"].flash')), '被改动字段没有高亮');
  await page.waitForTimeout(1500);
  ok(stub.computeCalls === 0, `采用修改后不应自动计算（实际 ${stub.computeCalls} 次计算请求）`);
  ok(!(await page.evaluate(() => /50,000|50000/.test(document.querySelector('[data-result-zone]').innerText))), '模型返回值出现在结果区');
  // 取消
  await ask('每间改成3台'); await page.waitForSelector('.proposal'); await page.click('[data-action="agent-cancel"]');
  ok(!(await page.$('.proposal')), '取消后修改清单应消失');
  // needs_clarification
  stub.parse = 'needs_clarification'; await ask('把空调改成晚上使用'); await page.waitForTimeout(800);
  ok(/需要补充/.test(await page.textContent('[data-ask-result]')) && /18:00/.test(await page.textContent('[data-ask-result]')), '追问没有显示');
  // unavailable / failed / 404 / 超时 → 规则识别同一句话
  for (const m of ['unavailable', 'failed', '404', 'timeout']) {
    stub.parse = m; await open(); await page.fill('[data-field="start_hour"]', '8');
    await ask('每天 9 点到 21 点'); await page.waitForFunction(() => /已改用规则识别/.test(document.querySelector('[data-ask-result]').textContent), null, { timeout: 40000 }).catch(() => {});
    const t = await page.textContent('[data-ask-result]');
    ok(/已改用规则识别/.test(t) && await page.inputValue('[data-field="start_hour"]') === '9', `${m}：应提示已改用规则识别并按规则填入（${t.slice(0, 60)}）`);
  }
  // 状态 404 / 超时 → “规则识别”，规则仍可用
  for (const m of ['404', 'timeout', 'offline']) {
    stub.status = m; await open(); await page.waitForTimeout(m === 'timeout' ? 4500 : 600);
    ok(/规则识别/.test(await tagText()), `状态 ${m}：标签应为“规则识别”：${await tagText()}`);
  }
  ok(errs.length === 0, `一句话输入页面错误：${errs.join(' | ')}`);
  await page.context().close();
  server.close();
}
const ok = (cond, msg) => { checks++; if (!cond) { failures++; console.log('  ✗ ' + msg); } };

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(e.message));
  if (process.env.NJD_ONLY === 'agent') { await checkAgent(browser); await browser.close(); console.log(`\n${checks} 项检查，${failures} 项不通过`); process.exit(failures ? 1 : 0); }

  /* ---------- 1. 三档与三个状态变体：第 3 步方案卡、推荐、排除原因、容量比选、碳、粗算、储能 ---------- */
  for (const c of replay.cases) {
    console.log(`案例 ${c.case_id}`);
    await page.goto(BASE + '#/samples/' + c.case_id);
    await page.waitForSelector('[data-step-panel="3"] .compare .opt', { timeout: 60000 });
    const ui = await page.evaluate(() => {
      const P = document.querySelector('[data-step-panel="3"]');
      const opts = [...P.querySelectorAll('.compare .opt')].map((o) => ({ id: o.dataset.scen, rec: o.classList.contains('rec'), price: o.querySelector('.price').textContent, delta: o.querySelector('.delta').textContent, tag: o.querySelector('.meta .tag').textContent, badge: (o.querySelector('.rec-badge') || {}).textContent || null }));
      const sweep = [...P.querySelectorAll('[data-sec="sweep"] tbody tr')].map((tr) => ({ text: tr.textContent, best: tr.classList.contains('is-best') }));
      const carbon = [...P.querySelectorAll('[data-sec="carbon"] tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent));
      const rough = [...P.querySelectorAll('[data-sec="rough"] tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent));
      const decision = P.querySelector('.big-decision .tag').textContent;
      const nc = [...P.querySelectorAll('.numcards > div')].map((d) => d.textContent.replace(/\s+/g, ' ').trim());
      const esc = P.querySelector('[data-sec="escalation"]');
      const escRows = esc ? [...esc.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent.replace(/\s+/g, ' ').trim())) : null;
      return { opts, sweep, carbon, rough, decision, nc, esc: esc ? esc.textContent.replace(/\s+/g, ' ') : null, escRows };
    });
    const order = ['S0_grid', 'S1_pv', 'S2_wind', 'S3_pv_wind'];
    ok(ui.opts.map((o) => o.id).join() === order.join(), `四方案顺序（只用电网第一）：${ui.opts.map((o) => o.id)}`);
    ok(clean(ui.decision) === REC[c.recommendation.status], `推荐状态 ${clean(ui.decision)} ≠ ${REC[c.recommendation.status]}`);
    for (const cand of c.candidates) {
      const o = ui.opts.find((x) => x.id === cand.scenario_id);
      ok(clean(o.tag) === ADM[cand.admission_status], `${cand.scenario_id} 状态 ${clean(o.tag)} ≠ ${ADM[cand.admission_status]}`);
      ok(o.rec === (cand.scenario_id === c.recommendation.scenario_id), `${cand.scenario_id} 推荐高亮不一致`);
      const complete = (cand.economics_status || (cand.economics || {}).status) === 'complete';
      if (cand.admission_status === 'unknown') {
        ok(clean(o.price) === '—', `${cand.scenario_id} 条件不全不应显示金额：${o.price}`);
        ok(/条件不全/.test(o.delta) && !/排除/.test(o.delta), `${cand.scenario_id} 条件不全被显示成排除：${o.delta}`);
      } else {
        ok(complete && clean(o.price).replace(/元$/, '') === money(cand.total_cost_npv_cny), `${cand.scenario_id} 总花费 ${o.price} ≠ ${money(cand.total_cost_npv_cny)}`);
      }
      if (cand.admission_status === 'excluded') {
        for (const r of cand.constraint_reasons) ok(o.delta.includes(r), `${cand.scenario_id} 排除原因原文缺失：${r}`);
      } else if (cand.scenario_id === 'S0_grid') {
        ok(clean(o.delta) === '比较基线', 'S0 应显示比较基线');
      } else if (cand.admission_status === 'eligible') {
        ok(clean(o.delta) === delta(cand.incremental_npv_vs_s0_cny), `${cand.scenario_id} 差额 ${o.delta} ≠ ${delta(cand.incremental_npv_vs_s0_cny)}`);
      }
    }
    // 容量比选：行数、最划算标注
    const fixed = c.request.pv.fixed_capacity_kwp != null;
    ok(ui.sweep.length === c.pv_capacity_sweep.length, `容量比选行数 ${ui.sweep.length} ≠ ${c.pv_capacity_sweep.length}`);
    c.pv_capacity_sweep.forEach((r, i) => {
      const isBest = !fixed && r.requested_capacity_kwp === c.pv_recommendation.recommended_capacity_kwp && r.admission_status === 'eligible';
      ok(ui.sweep[i] && ui.sweep[i].best === isBest, `容量 ${r.requested_capacity_kwp} 最划算标注应为 ${isBest}`);
      ok(ui.sweep[i] && ui.sweep[i].text.includes(ADM[r.admission_status]), `容量 ${r.requested_capacity_kwp} 状态缺失`);
      if (r.admission_status === 'eligible' && Math.round(r.incremental_npv_vs_s0_cny) !== 0) ok(ui.sweep[i].text.includes(delta(r.incremental_npv_vs_s0_cny)), `容量 ${r.requested_capacity_kwp} 差额不一致`);
      if (r.admission_status === 'excluded' || r.admission_status === 'unknown') ok(ui.sweep[i].text.includes('不参与比较'), `容量 ${r.requested_capacity_kwp} 已排除/条件不全却显示差额`);
    });
    // 碳：第 1 年减碳、研究期累计
    c.candidates.forEach((cand, i) => {
      const k = cand.carbon || c.carbon[cand.scenario_id];
      ok(!!ui.carbon[i] && clean(ui.carbon[i][2]) === `${kwhF(k.avoided_kgco2_year1)} kg`, `${cand.scenario_id} 第1年减碳 ${ui.carbon[i] && ui.carbon[i][2]} ≠ ${kwhF(k.avoided_kgco2_year1)}`);
      ok(ui.carbon[i] && clean(ui.carbon[i][3]) === `${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(k.avoided_tco2_study_period)} t`, `${cand.scenario_id} 研究期减碳 ${ui.carbon[i] && ui.carbon[i][3]}`);
    });
    // 粗算：比只用电网（粗算列）
    c.candidates.filter((x) => x.scenario_id !== 'S0_grid').forEach((cand, i) => {
      const e = cand.annual_offset_estimate.claimed_incremental_npv_vs_s0_cny;
      ok(!!ui.rough[i] && clean(ui.rough[i][5]) === (e == null ? '暂无法比较' : (delta(e) || '与基线相同')), `${cand.scenario_id} 粗算差额 ${ui.rough[i] && ui.rough[i][5]} ≠ ${delta(e)}`);
    });
    // 三个数字卡：推荐方案 load_coverage_rate / capex_cny / simple_payback_years
    const recC = c.candidates.find((x) => x.scenario_id === c.recommendation.scenario_id);
    ok(ui.nc.length === 3, `数字卡应为 3 个：${ui.nc.length}`);
    if (recC.scenario_id === 'S0_grid') {
      ok(/0\s*元/.test(ui.nc[1]) && /只用电网，无需投入/.test(ui.nc[1]) && /只用电网，无需投入/.test(ui.nc[2]), `只用电网推荐时数字卡应写“无需投入”：${ui.nc.slice(1).join(' | ')}`);
    } else {
      ok(ui.nc[0].includes(`${Math.round(recC.load_coverage_rate * 100)}%`), `数字卡自发比例 ${ui.nc[0]} ≠ ${recC.load_coverage_rate}`);
      ok(ui.nc[1].includes(money(recC.capex_cny)), `数字卡初始投入 ${ui.nc[1]} ≠ ${money(recC.capex_cny)}`);
      const pb = recC.economics.simple_payback_years;
      ok(pb == null ? /不回本|—/.test(ui.nc[2]) : ui.nc[2].includes(`${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(pb)}年`), `数字卡回本 ${ui.nc[2]} ≠ ${pb}`);
    }
    ok(/简单回本：初始投入 ÷ 每年净节省，不折现，仅供参考/.test(ui.nc[2] || ''), '数字卡缺少简单回本说明');
    // 电价年涨幅敏感性
    const es = c.escalation_sensitivity;
    if (es.recommendation_scenario_id === 'S0_grid') ok(/推荐只用电网，无需投入/.test(ui.esc || '') && !ui.escRows.length, `只用电网推荐时电价表应为一句话：${(ui.esc || '').slice(0, 60)}`);
    else {
      ok(ui.escRows && ui.escRows.length === es.rows.length, `电价表行数 ${ui.escRows && ui.escRows.length} ≠ ${es.rows.length}`);
      ok(/等比调整，不是电价预测/.test(ui.esc || ''), '电价表缺少“等比调整，不是电价预测”');
      es.rows.forEach((r, i) => {
        const row = (ui.escRows || [])[i] || [];
        ok(row[1] === `${money(r.s0_total_cost_npv_cny)} 元` && row[2] === `${money(r.recommended_total_cost_npv_cny)} 元`, `电价 ${r.rate} 总花费 ${row[1]} / ${row[2]}`);
        ok(row[3] === (delta(r.incremental_npv_vs_s0_cny) || '与基线相同'), `电价 ${r.rate} 差额 ${row[3]} ≠ ${delta(r.incremental_npv_vs_s0_cny)}`);
        ok(r.cumulative_payback_year == null ? !/第 \d+ 年/.test(row[4]) : row[4].includes(`第 ${r.cumulative_payback_year} 年`), `电价 ${r.rate} 回本年 ${row[4]} ≠ ${r.cumulative_payback_year}`);
      });
    }
    // 多余的电去哪儿：逐个发电方案切换，储能各档与卖电读 surplus_paths
    const gens = await page.$$eval('[data-step-panel="3"] [data-sec="surplus"] [data-r-store]', (bs) => bs.map((b) => b.dataset.rStore));
    ok(gens.length >= 1, '多余的电卡片缺少方案切换');
    for (const sid of gens) {
      await page.click(`[data-step-panel="3"] [data-r-store="${sid}"]`); await page.waitForTimeout(150);
      const cand = c.candidates.find((x) => x.scenario_id === sid), sp = cand.surplus_paths, st = sp.storage, ex = sp.export.path;
      const u = await page.evaluate(() => { const S = document.querySelector('[data-step-panel="3"] [data-sec="surplus"]');
        return { head: S.querySelector('.sec-head').textContent.replace(/\s+/g, ' '), rows: [...S.querySelectorAll('.st-table tbody tr')].map((tr) => ({ best: tr.classList.contains('is-best') || /最划算/.test(tr.textContent), cells: [...tr.children].map((td) => td.textContent.replace(/\s+/g, ' ').trim()) })),
          text: S.textContent.replace(/\s+/g, ' '), kv: [...S.querySelectorAll('.kv > div')].map((d) => d.textContent.replace(/\s+/g, ' ').trim()) }; });
      ok(u.head.includes(kwhF(sp.surplus_kwh_year1)), `${sid} 多余电量 ≠ ${kwhF(sp.surplus_kwh_year1)}`);
      ok(u.rows.length === st.candidates.length, `${sid} 储能行数 ${u.rows.length} ≠ ${st.candidates.length}`);
      const sgn = (v) => `${Math.round(v) < 0 ? '−' : ''}${money(Math.abs(v))} 元`;
      st.candidates.forEach((x, i) => {
        const r = u.rows[i] || { cells: [] };
        const pct0 = (v) => `${Math.round(v * 100)}%`, d1 = (v) => new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(v);
        if (x.economics_status === 'complete') {
          ok(r.cells[1] === `${money(x.initial_investment_cny)} 元` && r.cells[2] === `${money(x.annual_bill_saving_cny)} 元` && r.cells[3] === sgn(x.annual_net_benefit_cny) && r.cells[5] === sgn(x.study_period_net_benefit_cny), `${sid} 储能 ${x.capacity_kwh} kWh 投入/年节省/年净收益/研究期净收益 ${r.cells.slice(1, 6).join(' / ')}`);
          ok(r.cells[4] === (x.simple_payback_years != null ? `${d1(x.simple_payback_years)} 年` : (x.payback_status || '—')), `${sid} 储能 ${x.capacity_kwh} kWh 回本 ${r.cells[4]} ≠ ${x.simple_payback_years ?? x.payback_status}`);
        } else ok(/条件不全/.test(r.cells.join(' ')), `${sid} 储能 ${x.capacity_kwh} kWh 计价不完整应显示条件不全`);
        ok(r.cells[r.cells.length - 1] === `${pct0(x.self_consumption_rate_before)} → ${pct0(x.self_consumption_rate_after)}`, `${sid} 储能 ${x.capacity_kwh} kWh 自用比例 ${r.cells[r.cells.length - 1]}`);
        ok(r.best === (st.recommended_capacity_kwh > 0 && x.capacity_kwh === st.recommended_capacity_kwh), `${sid} 储能 ${x.capacity_kwh} kWh 最划算标注应为 ${st.recommended_capacity_kwh > 0 && x.capacity_kwh === st.recommended_capacity_kwh}`);
      });
      if (st.recommended_capacity_kwh === 0) ok(/不建议装储能/.test(u.text), `${sid} 推荐 0 kWh 时应写“不建议装储能”`);
      ok(u.kv[0] && u.kv[0].includes(kwhF(ex.sold_kwh_year1)) && u.kv.some((k) => k.includes(money(ex.annual_revenue_cny))) && u.kv.some((k) => k.includes(money(ex.study_period_revenue_cny))), `${sid} 卖电 ${u.kv.join(' | ')}`);
      ok(u.kv.some((k) => k === `上网电价 ${ex.price_cny_per_kwh} 元/kWh`) && u.kv.some((k) => k === `并网投入 ${ex.connection_cost_assumed_zero ? '未填写，按 0 粗算' : money(ex.connection_cny) + ' 元'}`), `${sid} 卖电电价/并网投入 ${u.kv.join(' | ')}`);
      ok(u.kv.some((k) => k === `回本 ${ex.simple_payback_years != null ? new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(ex.simple_payback_years) + ' 年' : (ex.payback_status || '无额外投入')}`), `${sid} 卖电回本 ${u.kv.join(' | ')}`);
      ok(/不叠加/.test(u.text) && /不含电池衰减/.test(u.text) && /以当地电网批复为准/.test(u.text), `${sid} 多余的电边界说明缺失`);
    }
    // 第 2 步单间与项目合计
    await page.goto(BASE + '#/tool/2'); await page.waitForTimeout(300);
    ok((await page.textContent('[data-step-panel="2"]')).includes(money(c.load_context.single_room_annual_kwh)), `单间年用电缺失 ${money(c.load_context.single_room_annual_kwh)}`);
    await page.goto(BASE + '#/tool/3'); await page.waitForTimeout(200);
    // 第 2 步年用电与服务状态
    await page.goto(BASE + '#/tool/2'); await page.waitForTimeout(400);
    const s2 = await page.evaluate(() => ({ big: document.querySelector('[data-step-panel="2"] .num.big').textContent, tag: document.querySelector('[data-step-panel="2"] .decision .tag').textContent }));
    ok(clean(s2.big) === money(c.load_context.electric_load_kwh), `年用电 ${s2.big} ≠ ${money(c.load_context.electric_load_kwh)}`);
    ok(clean(s2.tag) === (c.service_quality.status === 'service_gap' ? '空调有缺口' : '空调达标'), `服务状态 ${s2.tag}`);
    // 大档边界
    if (c.feasibility) { await page.goto(BASE + '#/tool/4'); await page.waitForTimeout(300); ok(/只计厂房空调区/.test(await page.textContent('[data-step-panel="4"]')) && /偏保守/.test(await page.textContent('[data-step-panel="4"]')), '大档边界文字缺失'); }
  }

  /* ---------- 2. 主界面不出现技术名（依据抽屉、关于页除外） ---------- */
  console.log('术语检查');
  const BAD = /pvlib|SD6|Hellman|NPV|\bS[0-3]\b|S[0-3]_|[a-z]+_[a-z_]+|PV-only/;
  for (const [route, id] of [['#/', 'tier_small'], ['#/samples', null], ['#/plans', null], ['#/tool/1', null]].concat([2, 3, 4].map((n) => [`#/tool/${n}`, null]))) {
    if (id) { await page.goto(BASE + '#/samples/' + id); await page.waitForSelector('[data-step-panel="3"] .compare .opt'); }
    await page.goto(BASE + route); await page.waitForTimeout(2500);
    const text = await page.evaluate(() => { const v = [...document.querySelectorAll('[data-view]')].find((x) => !x.hidden); const c = v.cloneNode(true); c.querySelectorAll('.mono, [data-r-basis], select, option').forEach((n) => n.remove()); return c.innerText; });
    const hit = text.split('\n').filter((l) => BAD.test(l) && !/replay_cases_ui_v9|replay_previews_v7\.json|docs\/handoff/.test(l));
    ok(hit.length === 0, `${route} 出现技术名：${hit.slice(0, 3).join(' | ')}`);
  }

  /* ---------- 2b. 不引用旧 v6 示例；页面与导出不含机器路径、用户名、账号 ---------- */
  console.log('来源与匿名检查');
  const PRIV = /[A-Za-z]:\\|\/home\/|\/Users\/|\/root\/|\/tmp\/|tingfengy|xiangyi|乡艺/;
  for (const f of fs.readdirSync(path.join(ROOT, 'operation_planning/ui/assets/js'))) {
    const t = fs.readFileSync(path.join(ROOT, 'operation_planning/ui/assets/js', f), 'utf8');
    ok(!/replay_cases_v6/.test(t), `${f} 仍引用 replay_cases_v6`);
  }
  await page.goto(BASE + '#/samples/tier_medium'); await page.waitForSelector('[data-step-panel="3"] .compare .opt');
  for (const r of ['#/', '#/tool/1', '#/tool/2', '#/tool/3', '#/tool/4', '#/samples', '#/plans', '#/about']) {
    await page.goto(BASE + r); await page.waitForTimeout(r === '#/' ? 1500 : 400);
    const html = await page.content();
    ok(!/replay_cases_v6/.test(html), `${r} 页面出现 replay_cases_v6`);
    ok(!PRIV.test(html), `${r} 页面出现机器路径或账号：${(html.match(PRIV) || [])[0]}`);
  }
  const grab = async (p, kind) => { await p.goto(BASE + '#/tool/4'); await p.waitForSelector(`[data-export="${kind}"]:not([disabled])`); const [d] = await Promise.all([p.waitForEvent('download'), p.click(`[data-export="${kind}"]`)]); return fs.readFileSync(await d.path(), 'utf8'); };
  {
    const sum = await grab(page, 'summary'), brief = await grab(page, 'brief'), js = await grab(page, 'json');
    for (const [k, t] of [['方案汇总 CSV', sum], ['决策简报', brief], ['完整 JSON', js]]) ok(!PRIV.test(t), `${k} 含机器路径或账号：${(t.match(PRIV) || [])[0]}`);
    ok(/多余的电去哪儿/.test(sum) && /,储能,20,/.test(sum) && /卖给电网/.test(sum), '方案汇总 CSV 缺少多余的电（储能/卖电）');
    ok(/多余的电去哪儿/.test(brief), '决策简报缺少多余的电');
    ok(/replay_cases_ui_v9/.test(js) && !/replay_cases_v6/.test(sum + brief + js), '导出来源应为 replay_cases_ui_v9');
  }

  /* ---------- 2c. 示例缺少 escalation_sensitivity 时隐藏电价表 ---------- */
  console.log('电价表缺字段检查');
  {
    const pe = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    await pe.route('**/replay_cases_ui_v9.json', async (route) => { const r = await route.fetch(); const j = await r.json(); j.cases.forEach((c) => { delete c.escalation_sensitivity; }); await route.fulfill({ response: r, json: j }); });
    await pe.goto(BASE + '#/samples/tier_medium'); await pe.waitForSelector('[data-step-panel="3"] .compare .opt', { timeout: 60000 });
    ok(!(await pe.$('[data-step-panel="3"] [data-sec="escalation"]')), '缺少 escalation_sensitivity 时电价表应隐藏');
    await pe.context().close();
  }

  /* ---------- 2d. 我的方案：nzh.plans.v1 一次性迁移 ---------- */
  console.log('我的方案迁移检查');
  {
    const pm = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    await pm.goto(BASE + '#/');
    await pm.evaluate(() => { localStorage.clear(); localStorage.setItem('nzh.plans.v1', JSON.stringify([{ id: 'pold1', savedAt: 1759000000000, mode: 'replay', caseId: 'tier_small', label: '旧方案甲', source: { kind: '示例回放' }, conditions: [{ key: 'room_count', label: '房间数', value: 2, text: '2 间' }, { key: 'units_per_room', label: '每间台数', value: 1, text: '1 台' }], conclusion: { headline: '建议：加装光伏', recommendation: '有条件推荐', totalCost: 5814.2, studyYears: 10 } }])); });
    const count = async () => { await pm.goto(BASE + '#/plans'); await pm.reload(); await pm.waitForSelector('[data-plans]'); await pm.waitForTimeout(300); return pm.$$eval('[data-plans] .plan-card', (a) => a.map((x) => x.textContent.replace(/\s+/g, ' '))); };
    const a1 = await count(), a2 = await count();
    const st = await pm.evaluate(() => ({ old: !!localStorage.getItem('nzh.plans.v1'), mark: !!localStorage.getItem('nzh.plans.v1.migrated'), n: JSON.parse(localStorage.getItem('njd.plans.v1') || '[]').length }));
    ok(a1.length === 1 && a2.length === 1 && st.n === 1, `旧方案应只迁移一次：${a1.length}/${a2.length}/${st.n}`);
    ok(st.old && st.mark, `迁移后应保留旧键并写标记：${JSON.stringify(st)}`);
    ok(/建议：加装光伏/.test(a1[0] || '') && /5,814/.test(a1[0] || '') && /—/.test(a1[0] || ''), `迁移方案显示：${(a1[0] || '').slice(0, 120)}`);
    await pm.evaluate(() => localStorage.clear());
    await pm.context().close();
  }

  /* ---------- 3. 1440/1024/390 × 浅色/深色：无横向滚动 ---------- */
  console.log('横向滚动检查');
  for (const scheme of ['light', 'dark']) for (const w of [1440, 1024, 390]) {
    const p2 = await (await browser.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme })).newPage();
    p2.on('pageerror', (e) => errors.push(e.message));
    await p2.goto(BASE + '#/samples/tier_medium'); await p2.waitForSelector('[data-step-panel="3"] .compare .opt', { timeout: 60000 });
    for (const r of ['#/', '#/tool/1', '#/tool/2', '#/tool/3', '#/tool/4', '#/samples', '#/plans', '#/about']) {
      await p2.goto(BASE + r); await p2.waitForTimeout(r === '#/' ? 2500 : 700);
      const m = await p2.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
      ok(m.sw <= m.cw, `${scheme} ${w}px ${r} 横向滚动 ${m.sw} > ${m.cw}`);
    }
    await p2.context().close();
  }

  /* ---------- 4. 减少动态效果 ---------- */
  console.log('减少动态效果检查');
  const p3 = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })).newPage();
  await p3.goto(BASE + '#/'); await p3.waitForTimeout(2500);
  const rm = await p3.evaluate(() => { const els = [...document.querySelectorAll('*')]; return { anim: els.filter((e) => { const s = getComputedStyle(e); return s.animationName !== 'none' && parseFloat(s.animationDuration) > 0.011; }).length, trans: els.filter((e) => parseFloat(getComputedStyle(e).transitionDuration) > 0.011).length, pre: document.querySelectorAll('.reveal.pre').length }; });
  ok(rm.anim === 0 && rm.trans === 0 && rm.pre === 0, `减少动态效果下仍有动画/过渡：${JSON.stringify(rm)}`);
  await p3.context().close();

  /* ---------- 5. 未连接计算服务（静态服务器）：自动进入示例模式并提示 ---------- */
  console.log('示例模式检查');
  const p4 = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const errs4 = []; p4.on('console', (m) => { if (m.type() === 'error') errs4.push(m.text()); }); p4.on('pageerror', (e) => errs4.push(e.message));
  try {
    await p4.goto(STATIC); await p4.waitForTimeout(4000);
    const sm = await p4.evaluate(() => ({ mode: document.querySelector('#modeBadge').dataset.mode, banner: !document.querySelector('#modeBanner').hidden && document.querySelector('#modeBanner').textContent, hud: document.querySelector('[data-hud="load"]').textContent }));
    ok(sm.mode === 'sample' && /未连接计算服务/.test(sm.banner || ''), `静态打开未进入示例模式：${JSON.stringify(sm)}`);
    ok(sm.hud !== '—', '静态模式下首页示例数据未加载');
    ok(errs4.length === 0, `静态模式控制台错误：${errs4.join(' | ')}`);
  } catch (e) { ok(false, `静态服务器不可用（${STATIC}）：${e.message}`); }
  await p4.context().close();

  /* ---------- 5b. 实时：储能/卖电报价、自定义分时电价、电价年涨幅 ---------- */
  console.log('实时计算检查（储能、卖电、自定义电价、年涨幅）');
  if (process.env.NJD_SKIP_LIVE) console.log('  （已跳过）');
  else {
    const pl = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    const errsL = []; pl.on('pageerror', (e) => errsL.push(e.message)); pl.on('console', (m) => { if (m.type() === 'error') errsL.push(m.text()); });
    let lastReq = null; pl.on('request', (r) => { if (/\/api\/operation\/.*(run|jobs)$/.test(r.url()) && r.method() === 'POST') { try { lastReq = JSON.parse(r.postData()); } catch (e) {} } });
    const compute = async () => { await pl.click('.actionbar [data-action="compute"]'); await pl.waitForFunction(() => location.hash === '#/tool/2', null, { timeout: 240000 }); await pl.goto(BASE + '#/tool/3'); await pl.waitForSelector('[data-step-panel="3"] [data-sec="surplus"]'); };
    const zone = async () => clean(await pl.textContent('[data-step-panel="3"]'));
    // 第 1 次：示例报价 + 自定义分时电价（峰段改 1.5）+ 年涨幅 3%
    await pl.goto(BASE + '#/tool/1'); await pl.waitForSelector('[data-quick-case]'); await pl.click('[data-quick-case="tier_small"]');
    await pl.fill('[data-field="capacities"]', '1');
    await pl.click('[data-seg="price_mode"][data-val="tariff"]'); await pl.waitForTimeout(150);
    await pl.selectOption('[data-field="tariff_id"]', 'custom_user'); await pl.waitForTimeout(200);
    const pre = await pl.evaluate(() => ['tou_valley', 'tou_flat', 'tou_peak', 'tou_super'].map((k) => document.querySelector(`[data-field="${k}"]`).value));
    ok(pre.every((v) => v !== '' && Number.isFinite(Number(v))), `自定义电价四个价格应默认填入官方档案价格：${pre}`);
    ok(/未经官方核验/.test(await pl.textContent('#view-tool')), '自定义电价缺少“未经官方核验”标注');
    await pl.fill('[data-field="tou_peak"]', '1.5'); await pl.fill('[data-field="escalation_pct"]', '3');
    await compute();
    const pv = (lastReq || {}).pv || {}, hy = (lastReq || {}).hybrid || {}, sto = (lastReq || {}).storage || {};
    ok(pv.tariff_id === 'custom_user' && pv.custom_tariff && Array.isArray(pv.custom_tariff.periods) && pv.custom_tariff.periods.some((x) => x.name === 'peak' && x.price === 1.5), `请求缺少自定义电价：${JSON.stringify(pv.custom_tariff || null).slice(0, 120)}`);
    ok(hy.tariff_escalation_rate === 0.03, `请求年涨幅应为 0.03：${hy.tariff_escalation_rate}`);
    ok(sto.quote && sto.quote.cny_per_kwh > 0 && sto.export && sto.export.price_cny_per_kwh > 0, `请求缺少储能/卖电报价：${JSON.stringify(sto).slice(0, 120)}`);
    let z = await zone();
    ok(/用户自定义电价（未经官方核验）/.test(z), '结果未标注“用户自定义电价（未经官方核验）”');
    ok(/电价变了，结论还成立吗？/.test(z) && /本次计算按每年 \+3%/.test(z), '结果缺少电价年涨幅表或未写本次 +3%');
    ok(await pl.$$eval('[data-step-panel="3"] .st-table tbody tr', (a) => a.length) >= 2 && !/条件不全：请填写储能报价/.test(z), '有报价时储能表应完整');
    ok(/每年收入/.test(z), '有上网电价时应显示卖电收入');
    // 改报价 → 结果过期
    await pl.goto(BASE + '#/tool/1'); await pl.fill('[data-field="st_price"]', '600'); await pl.goto(BASE + '#/tool/3'); await pl.waitForTimeout(400);
    ok(await pl.evaluate(() => document.querySelector('[data-result-zone]').classList.contains('is-stale')), '修改储能报价后结果应标为过期');
    // 第 2 次：清空储能与卖电报价 → 条件不全、只给电量，不报错
    await pl.goto(BASE + '#/tool/1');
    for (const k of ['st_price', 'st_install', 'st_maint', 'st_life', 'ex_price', 'ex_conn']) await pl.fill(`[data-field="${k}"]`, '');
    await compute();
    z = await zone();
    ok(/条件不全：请填写储能报价/.test(z) && /填写上网电价后可估算收入/.test(z) && !/每年收入/.test(z), '无报价时应显示条件不全且卖电只给电量');
    ok(errsL.length === 0, `实时计算页面错误：${errsL.slice(0, 3).join(' | ')}`);
    await pl.context().close();
  }

  /* ---------- 6. 一句话输入：本地大模型（桩服务）---------- */
  console.log('一句话输入（桩服务）检查');
  await checkAgent(browser);

  /* ---------- 7. 控制台错误 ---------- */
  ok(errors.length === 0, `控制台错误：${errors.slice(0, 5).join(' | ')}`);

  await browser.close();
  console.log(`\n${checks} 项检查，${failures} 项不通过`);
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
