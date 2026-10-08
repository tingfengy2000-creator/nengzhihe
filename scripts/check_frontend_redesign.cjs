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
      const storage = [...P.querySelectorAll('[data-sec="storage"] tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent));
      const decision = P.querySelector('.big-decision .tag').textContent;
      return { opts, sweep, carbon, rough, storage, decision };
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
    // 储能：推荐方案（或第一个有上限的方案）各档挽回电量
    const st = c.candidates.find((x) => x.scenario_id === c.recommendation.scenario_id && x.storage_upper_bound && x.storage_upper_bound.status === 'calculated') || c.candidates.find((x) => x.storage_upper_bound && x.storage_upper_bound.status === 'calculated');
    if (st) st.storage_upper_bound.candidates.forEach((s, i) => ok(!!ui.storage[i] && clean(ui.storage[i][2]) === `${kwhF(s.recovered_kwh_year1)} kWh`, `储能 ${s.capacity_kwh} kWh 挽回 ${ui.storage[i] && ui.storage[i][2]}`));
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
    const hit = text.split('\n').filter((l) => BAD.test(l) && !/replay_cases_v6\.json|replay_cases_ui_v9|replay_previews_v7\.json|docs\/handoff/.test(l));
    ok(hit.length === 0, `${route} 出现技术名：${hit.slice(0, 3).join(' | ')}`);
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

  /* ---------- 6. 一句话输入：本地大模型（桩服务）---------- */
  console.log('一句话输入（桩服务）检查');
  await checkAgent(browser);

  /* ---------- 7. 控制台错误 ---------- */
  ok(errors.length === 0, `控制台错误：${errors.slice(0, 5).join(' | ')}`);

  await browser.close();
  console.log(`\n${checks} 项检查，${failures} 项不通过`);
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
