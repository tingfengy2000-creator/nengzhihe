/* 能见度 · 由视图模型生成文字
 * 只引用结果中的数值；只做比较（大小、正负），不做加减乘除得出新数字。 */
import { fmt, isNum } from './util.js';
import { SCEN } from './data.js';

export function scheduleText(req) {
  const r = (req && req.room) || {};
  if (r.start_hour == null || r.end_hour == null) return null;
  return `${r.weekdays_only === false ? '每天' : r.weekdays_only === true ? '工作日' : ''} ${r.start_hour}–${r.end_hour} 点`.trim();
}

/** 房间口径摘要：同类房间数 × 每间台数、单间面积（原样搬运请求字段）。 */
export function roomText(vm) {
  const r = (vm.request && vm.request.room) || {};
  const parts = [];
  const rc = vm.roomCount ?? r.room_count, up = vm.unitsPerRoom ?? r.units_per_room;
  // 大档是“厂房空调分区有界代理”（回放带 feasibility 说明），按分区称呼
  const zone = !!vm.feasibility, u = zone ? '区' : '间';
  if (isNum(rc)) parts.push(zone ? `${fmt.int(rc)} 个空调分区` : `${fmt.int(rc)} 间同类房间`);
  if (isNum(r.area_m2)) parts.push(`每${u} ${fmt.d(r.area_m2, 1)}㎡`);
  if (isNum(up)) parts.push(`每${u} ${fmt.int(up)} 台空调`);
  return parts.join(' · ');
}

export function placeText(vm) {
  return [vm.site && vm.site.name, isNum(vm.year) ? `${vm.year} 年天气` : null].filter(Boolean).join(' · ');
}

/** 有发电的方案 */
export const hasGen = (c) => c && isNum(c.gen) && c.gen > 0;

/** 首页“事实/电去哪了/两种算法”聚焦的方案：推荐方案有发电就用推荐方案，否则用光伏+小风机。 */
export function focusScenario(vm) {
  const rec = vm.byId[vm.rec && vm.rec.scenarioId];
  if (hasGen(rec)) return rec;
  return [vm.byId.S1_pv, vm.byId.S3_pv_wind, vm.byId.S2_wind].find(hasGen) || null;
}

export function scenLabel(c) {
  if (!c) return '';
  const bits = [];
  if (isNum(c.pvKwp) && c.pvKwp > 0) bits.push(`光伏 ${fmt.d(c.pvKwp, 2)} kWp`);
  if (isNum(c.windCount) && c.windCount > 0) bits.push(`小风机 ${fmt.int(c.windCount)} 台`);
  return bits.length ? bits.join(' + ') : c.name;
}

/** 推荐一句话 */
export function headline(vm) {
  const rec = vm.rec || {};
  const best = vm.byId[rec.scenarioId];
  if (!best || rec.status === 'not_available') return '暂时给不出推荐';
  if (rec.status === 'conditional_subset') return `在条件齐全的方案中，「${best.name}」最省钱`;
  return `建议：${best.verb}${best.id !== 'S0_grid' && isNum(best.pvKwp) && best.pvKwp > 0 ? `（光伏 ${fmt.d(best.pvKwp, 2)} kWp）` : ''}`;
}

/** 容量比选摘要（比较后端的每行数值；最划算容量取后端 recommended_pv_capacity_kwp）。 */
export function sweepStory(vm) {
  const rows = vm.sweep || [];
  if (!rows.length) return null;
  const best = rows.find((r) => isNum(vm.recommendedKwp) && Math.abs(r.kwp - vm.recommendedKwp) < 1e-9) || null;
  const eligible = rows.filter((r) => r.admission.status === 'eligible' && isNum(r.incremental));
  const losers = eligible.filter((r) => r.incremental < 0 && (!best || r.kwp > best.kwp));
  const worse = losers.length ? losers[0] : null;
  const excluded = rows.filter((r) => r.admission.status === 'excluded');
  let title, text;
  if (best && best.kwp > 0 && isNum(best.incremental) && best.incremental > 0) {
    title = worse ? '装多大，比装不装更关键。' : `装 ${fmt.d(best.kwp, 2)} kWp 最划算。`;
    text = `在 ${rows.length} 个候选容量里，光伏 ${fmt.d(best.kwp, 2)} kWp 的 ${yearsText(vm.studyYears)}总账${fmt.delta(best.incremental).text}`;
    if (worse) text += `；装到 ${fmt.d(worse.kwp, 2)} kWp 反而${fmt.delta(worse.incremental).text}`;
    text += '。';
  } else if (best && best.kwp === 0) {
    title = '这里不装光伏最划算。';
    text = `在 ${rows.length} 个候选容量里，没有一个比只用电网更省。`;
  } else {
    title = '装多大，要看逐小时能用上多少。';
    text = best ? `本次只计算了光伏 ${fmt.d(best.kwp, 2)} kWp 一个容量（${best.admission.label}）。` : '本次没有可比较的容量。';
  }
  if (excluded.length) text += ` ${excluded.map((r) => `${fmt.d(r.kwp, 2)} kWp ${r.reasons[0] || '不满足限制条件'}，已排除`).join('；')}。`;
  return { title, text, best, worse };
}

/** 两种算法对比：粗算（年发电抵年用电）与逐小时结果。 */
export function roughCompare(c) {
  if (!c || !c.rough) return null;
  const r = c.rough.incremental, h = c.incremental;
  if (!isNum(r) || !isNum(h)) return { opposite: false, comparable: false, rough: r, hourly: h };
  const sign = (v) => (Math.round(v) > 0 ? 1 : Math.round(v) < 0 ? -1 : 0);
  return { opposite: sign(r) !== sign(h) && sign(r) !== 0 && sign(h) !== 0, comparable: true, roughHigher: r > h, rough: r, hourly: h };
}

export const yearsText = (y) => (isNum(y) ? `${fmt.int(y)} 年` : '研究期内');
export function sayDelta(v, years) {
  const d = fmt.delta(v), y = yearsText(years);
  if (d.dir === 'more') return `${y}多花 ${d.amount} 元`;
  if (d.dir === 'less') return `${y}省下 ${d.amount} 元`;
  if (d.dir === 'base') return `${y}与只用电网相同`;
  return '暂无法比较';
}

export const SCEN_NAME = (id) => (SCEN[id] ? SCEN[id].name : id);
