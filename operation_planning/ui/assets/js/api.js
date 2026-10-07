/* 能见度 · 本机实时接口（只绑定 127.0.0.1 的计算服务）。
 * 出错时抛出 ApiError，携带后端给出的中文 message 与 field（用于定位表单控件）。 */

export class ApiError extends Error {
  constructor(message, field, status) { super(message); this.field = field || null; this.status = status || 0; }
}

async function call(method, path, body, { signal } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method, signal, cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined
    });
  } catch (e) {
    if (e && e.name === 'AbortError') throw e;
    throw new ApiError('无法连接本机计算服务，请确认服务仍在运行。', null, 0);
  }
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) {
    const msg = (data && (data.message || data.error)) || `计算服务返回错误（HTTP ${res.status}）`;
    throw new ApiError(typeof msg === 'string' ? msg : JSON.stringify(msg), data && data.field, res.status);
  }
  return data;
}

export const api = {
  options: () => call('GET', '/api/operation/options'),
  thermalSize: (body, opt) => call('POST', '/api/operation/thermal/size', body, opt),
  preview: (body, opt) => call('POST', '/api/operation/hybrid/preview', body, opt),
  submit: (body, opt) => call('POST', '/api/operation/hybrid/jobs', body, opt),
  job: (id, opt) => call('GET', `/api/operation/hybrid/jobs/${encodeURIComponent(id)}`, null, opt),
  runSync: (body, opt) => call('POST', '/api/operation/hybrid/run', body, opt)
};

/**
 * 轮询异步任务。进度只来自后端 progress 与事件（不做假进度）。
 * onProgress({ status, progress, events, elapsedMs })；完成时返回 result.report；失败抛 ApiError。
 */
export async function pollJob(id, onProgress, { signal, interval = 700 } = {}) {
  for (;;) {
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
    const j = await api.job(id, { signal });
    onProgress && onProgress({ status: j.status, progress: j.progress, events: j.events || [], elapsedMs: j.elapsed_ms });
    if (j.status === 'done') {
      const out = j.result || {};
      if (out.status !== 'success' || !out.report) throw new ApiError(out.message || out.error || '计算结果为空', out.field);
      return out.report;
    }
    if (j.status === 'failed') throw new ApiError(j.message || j.error || '计算失败', j.field);
    await new Promise((r) => setTimeout(r, interval));
  }
}
