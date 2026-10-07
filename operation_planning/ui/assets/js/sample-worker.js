/* 能见度 · 示例回放读取（Web Worker）。
 *
 * 回放文件 replay_cases_v6.json 约 76 MB，在后台线程读取和解析，避免卡住页面。
 * 这里只“删去界面用不到的大字段”，不改任何数值：
 *   - weather.provenance.normalization（天气时间轴归一化的 8,784 行审计数组）
 *   - candidates[].hourly（各方案逐时序列；示例模式按任务书使用 chart 与 chart_recommended）
 * 其他字段原样传回主线程。
 */
/* eslint-env worker */
const FILES = {
  cases: 'replay_cases_v6.json',
  previews: 'replay_previews_v7.json'
};

async function fetchFirst(name, bases) {
  let last = null;
  for (const base of bases) {
    try {
      const res = await fetch(base + name, { cache: 'force-cache' });
      if (res.ok) return { json: await res.json(), url: base + name };
      last = new Error(`${res.status}`);
    } catch (e) { last = e; }
  }
  throw new Error(`示例文件读取失败：${name}（${last ? last.message : '未知原因'}）`);
}

function slimCases(file) {
  for (const c of file.cases || []) {
    if (c.weather && c.weather.provenance && c.weather.provenance.normalization) {
      c.weather.provenance.normalization = { omitted_in_ui: true };
    }
    for (const cand of c.candidates || []) {
      if (cand.hourly) { delete cand.hourly; cand.hourly_omitted_in_ui = true; }
    }
  }
  return file;
}

self.onmessage = async (e) => {
  const { which, bases } = e.data || {};
  try {
    const name = FILES[which];
    if (!name) throw new Error('未知示例文件');
    const { json, url } = await fetchFirst(name, bases);
    self.postMessage({ ok: true, which, url, data: which === 'cases' ? slimCases(json) : json });
  } catch (err) {
    self.postMessage({ ok: false, which, error: String(err && err.message || err) });
  }
};
