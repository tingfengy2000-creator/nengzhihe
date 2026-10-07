/* 能见度 · 全局状态与事件。
 * mode：probing（探测中）/ live（已连接本机计算服务）/ sample（未连接，只能查看示例）。 */

const listeners = {};
export const app = {
  mode: 'probing',
  options: null,          // GET /api/operation/options 的原样响应
  lastLive: null,         // 用户最近一次实时计算 { vm, previews, request, at }
  homeSource: null,       // 首页当前数据来源 { kind: 'sample'|'live', caseId }
};

export function on(evt, fn) { (listeners[evt] = listeners[evt] || []).push(fn); }
export function emit(evt, data) { (listeners[evt] || []).forEach((fn) => { try { fn(data); } catch (e) { console.error(e); } }); }
