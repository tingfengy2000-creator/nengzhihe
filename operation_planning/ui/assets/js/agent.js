/* 能见度 · 一句话输入的本地大模型理解（契约：docs/handoff/5090_carbon_request.md 第 18 节）
 *
 * 大模型只负责“理解用户的话 → 提出表单修改”。修改清单由用户确认后才写入表单，
 * 不自动开始计算；所有数字仍由计算服务在用户点击「计算」后算出。
 * 模型返回的任何内容都不作为结果数字显示。
 * 状态接口不可用（404、超时、未启动）时，界面退回本地规则识别。 */
import { app, emit } from './state.js';

const STATUS_TIMEOUT_MS = 3500;
export const PARSE_TIMEOUT_MS = 25000;   // 后端超过 20 秒自行返回 failed；前端再留余量

async function fetchJson(url, opts, timeout) {
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), timeout);
  try {
    const res = await fetch(url, Object.assign({ cache: 'no-store', signal: ctl.signal }, opts || {}));
    let body = null; try { body = await res.json(); } catch (e) { body = null; }
    return { ok: res.ok, status: res.status, body };
  } finally { clearTimeout(t); }
}

/** 探测本地大模型；结果放在 app.agent = { available, label, reason } */
export async function checkStatus() {
  if (app.mode !== 'live') { app.agent = { available: false, reason: '未连接计算服务' }; emit('agent', app.agent); return app.agent; }
  try {
    const r = await fetchJson('/api/operation/agent/status', null, STATUS_TIMEOUT_MS);
    if (!r.ok || !r.body || typeof r.body.available !== 'boolean') throw new Error(r.status === 404 ? '接口不存在' : `状态接口返回 ${r.status}`);
    app.agent = { available: r.body.available === true, label: r.body.label || '本地大模型', reason: r.body.reason || null };
  } catch (e) {
    app.agent = { available: false, label: '本地大模型', reason: e.name === 'AbortError' ? '探测超时' : (e.message || '不可用') };
  }
  emit('agent', app.agent);
  return app.agent;
}

/**
 * 请求理解。返回 { status: 'ok'|'needs_clarification'|'unavailable'|'failed', changes, unsupported, question, reason }。
 * 404、网络错误、超时都折算为 unavailable（由界面改用规则识别）。
 */
export async function parse(text, currentTask) {
  try {
    const r = await fetchJson('/api/operation/agent/parse', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request: text, current_task: currentTask })
    }, PARSE_TIMEOUT_MS);
    if (r.status === 404) return { status: 'unavailable', reason: '理解接口不存在', changes: [], unsupported: [] };
    const b = r.body || {};
    if (!r.ok) return { status: 'failed', reason: b.message || b.error || `理解接口返回 ${r.status}`, changes: [], unsupported: [] };
    const status = ['ok', 'needs_clarification', 'unavailable', 'failed'].includes(b.status) ? b.status : 'failed';
    return {
      status, reason: b.reason || b.message || null, question: b.question || null,
      changes: Array.isArray(b.changes) ? b.changes.filter((c) => c && typeof c.field === 'string') : [],
      unsupported: Array.isArray(b.unsupported) ? b.unsupported.map(String) : []
    };
  } catch (e) {
    return { status: 'unavailable', reason: e.name === 'AbortError' ? '本地大模型响应超时' : '无法连接理解接口', changes: [], unsupported: [] };
  }
}
