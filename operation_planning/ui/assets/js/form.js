/* 能见度 · 试算表单：字段定义、请求体构造、从示例请求回填、一句话输入解析。
 * 表单值是用户输入（不是结果）。未填写的可选字段不发送，由计算服务使用其默认值；
 * 报价未填写时不补任何默认值——对应方案会显示“条件不全”。 */
import { isNum } from './util.js';

/* 字段：key、标签、类型、单位、分组；opt 表示可选（留空不发送） */
export const FIELDS = [
  // 场景
  { key: 'site_id', label: '城市', type: 'select', group: 'scene' },
  { key: 'year', label: '天气参考年', type: 'select', group: 'scene', num: true },
  { key: 'room_count', label: '同类房间数', type: 'int', unit: '间', min: 1, max: 10000, group: 'scene', hint: '朝向、面积、使用时段、空调都相同的房间（或空调分区）数' },
  { key: 'area_m2', label: '单间面积', type: 'number', unit: '㎡', min: 1, step: 1, group: 'scene' },
  { key: 'weekdays_only', label: '使用日', type: 'select', group: 'scene', options: [['true', '只在工作日'], ['false', '每天']] },
  { key: 'start_hour', label: '每天开始使用', type: 'int', unit: '点', min: 0, max: 23, group: 'scene' },
  { key: 'end_hour', label: '每天结束使用', type: 'int', unit: '点', min: 1, max: 24, group: 'scene' },
  { key: 'cooling_setpoint_c', label: '目标温度', type: 'number', unit: '℃', min: 16, max: 30, step: 0.5, group: 'scene' },
  { key: 'rh_setpoint_percent', label: '目标湿度', type: 'number', unit: '%', min: 30, max: 80, step: 1, group: 'scene' },
  { key: 'height_m', label: '层高', type: 'number', unit: 'm', min: 2, max: 20, step: 0.1, group: 'scene', opt: true },
  { key: 'people_count', label: '每间人数', type: 'int', unit: '人', min: 0, max: 1000, group: 'scene', opt: true },
  { key: 'equipment_gain_w', label: '每间设备散热', type: 'number', unit: 'W', min: 0, step: 10, group: 'scene', opt: true },
  { key: 'orientation', label: '主要朝向', type: 'select', group: 'scene', opt: true, options: [['', '使用默认'], ['south', '南'], ['north', '北'], ['east', '东'], ['west', '西']] },
  { key: 'window_wall_ratio', label: '窗墙比', type: 'number', min: 0, max: 0.9, step: 0.05, group: 'scene', opt: true, hint: '窗户面积 ÷ 外墙面积，0–0.9' },
  { key: 'insulation_u_w_m2k', label: '外墙传热系数', type: 'number', unit: 'W/㎡K', min: 0.05, step: 0.05, group: 'scene2', opt: true },
  { key: 'ventilation_lps_person', label: '每人新风量', type: 'number', unit: 'L/s', min: 0, step: 0.5, group: 'scene2', opt: true },
  { key: 'infiltration_ach', label: '渗透换气次数', type: 'number', unit: '次/h', min: 0, step: 0.05, group: 'scene2', opt: true },
  // 空调
  { key: 'equipment_id', label: '空调型号', type: 'select', group: 'ac' },
  { key: 'units_per_room', label: '每间台数', type: 'int', unit: '台', min: 1, max: 50, group: 'ac' },
  { key: 'max_units', label: '台数比选最多试到', type: 'int', unit: '台', min: 1, max: 50, group: 'ac-size' },
  // 屋顶与发电设备
  { key: 'roof_area_m2', label: '可装光伏的屋顶面积', type: 'number', unit: '㎡', min: 0, step: 1, group: 'supply', hint: '按单层占地填写，楼层不相乘' },
  { key: 'usable_fraction', label: '屋顶可用比例', type: 'number', min: 0.01, max: 1, step: 0.05, group: 'supply', opt: true, hint: '0–1，扣除设备、通道、遮挡' },
  { key: 'capacity_mode', label: '光伏容量', type: 'seg', group: 'supply', options: [['auto', '自动比选'], ['list', '指定候选容量'], ['fixed', '只看一个容量']] },
  { key: 'capacities', label: '光伏容量（kWp，可填多个，用逗号分隔）', type: 'text', group: 'supply', hint: '例如：0, 5, 10。单个容量的状态（排除/条件不全）请用“只看一个容量”。' },
  { key: 'wind_turbine_count', label: '小风机', type: 'select', group: 'supply', options: [['0', '不装'], ['1', '1 台']], hint: '目前只支持 0 或 1 台完整风机' },
  { key: 'hub_height_m', label: '风机安装高度', type: 'number', unit: 'm', min: 1, step: 0.5, group: 'supply', opt: true },
  // 电价与预算
  { key: 'price_mode', label: '电价', type: 'seg', group: 'price', options: [['tariff', '按电价档案'], ['fixed', '固定电价']] },
  { key: 'tariff_id', label: '电价档案', type: 'select', group: 'price' },
  { key: 'tariff_application', label: '档案用法', type: 'select', group: 'price', options: [['current_tariff_on_reference_weather', '把这份电价结构套用到所选天气年（情景）'], ['historical_weather_date', '严格按天气年份校验档案有效期']] },
  { key: 'import_price', label: '固定购电价', type: 'number', unit: '元/kWh', min: 0, step: 0.01, group: 'price' },
  { key: 'budget_cny', label: '初始投入预算', type: 'number', unit: '元', min: 0, step: 1000, group: 'price', opt: true, hint: '留空表示不设预算上限' },
  { key: 'study_years', label: '比较年限', type: 'int', unit: '年', min: 1, max: 40, group: 'price', opt: true, hint: '留空使用计算服务默认值' },
  { key: 'allow_export', label: '多余电量卖给电网', type: 'check', group: 'price' },
  // 报价（光伏，元/kWp）
  { key: 'pv_module', label: '组件', type: 'number', unit: '元/kWp', min: 0, group: 'pvq', q: ['pv', 'module_cny_per_kwp'] },
  { key: 'pv_inverter', label: '逆变器', type: 'number', unit: '元/kWp', min: 0, group: 'pvq', q: ['pv', 'inverter_cny_per_kwp'] },
  { key: 'pv_structure', label: '支架', type: 'number', unit: '元/kWp', min: 0, group: 'pvq', q: ['pv', 'structure_cny_per_kwp'] },
  { key: 'pv_install', label: '安装', type: 'number', unit: '元/kWp', min: 0, group: 'pvq', q: ['pv', 'installation_cny_per_kwp'] },
  { key: 'pv_grid', label: '并网', type: 'number', unit: '元', min: 0, group: 'pvq', q: ['pv', 'grid_connection_cny'] },
  { key: 'pv_maint', label: '运维', type: 'number', unit: '元/kWp·年', min: 0, group: 'pvq', q: ['pv', 'maintenance_cny_per_kwp_year'] },
  { key: 'pv_inv_year', label: '逆变器更换年份', type: 'int', unit: '第几年', min: 1, group: 'pvq', q: ['pv', 'inverter_replacement_year'] },
  { key: 'pv_inv_frac', label: '更换费用比例', type: 'number', min: 0, max: 1, step: 0.01, group: 'pvq', q: ['pv', 'inverter_replacement_fraction'], hint: '占初始设备费的比例，0–1' },
  { key: 'pv_residual', label: '期末残值比例', type: 'number', min: 0, max: 1, step: 0.01, group: 'pvq', q: ['pv', 'residual_fraction'] },
  // 报价（风机，元）
  { key: 'w_turbine', label: '风机', type: 'number', unit: '元', min: 0, group: 'wq', q: ['wind', 'turbine_cny'] },
  { key: 'w_tower', label: '塔架', type: 'number', unit: '元', min: 0, group: 'wq', q: ['wind', 'tower_cny'] },
  { key: 'w_foundation', label: '基础', type: 'number', unit: '元', min: 0, group: 'wq', q: ['wind', 'foundation_cny'] },
  { key: 'w_install', label: '安装', type: 'number', unit: '元', min: 0, group: 'wq', q: ['wind', 'installation_cny'] },
  { key: 'w_grid', label: '并网', type: 'number', unit: '元', min: 0, group: 'wq', q: ['wind', 'grid_connection_cny'] },
  { key: 'w_maint', label: '运维', type: 'number', unit: '元/年', min: 0, group: 'wq', q: ['wind', 'maintenance_cny_per_year'] },
  { key: 'w_residual', label: '期末残值比例', type: 'number', min: 0, max: 1, step: 0.01, group: 'wq', q: ['wind', 'residual_fraction'] },
  // 碳与储能
  { key: 'factor_id', label: '电网排放因子', type: 'select', group: 'carbon' },
  { key: 'carbon_price', label: '碳价情景', type: 'number', unit: '元/吨', min: 0, step: 0.01, group: 'carbon', opt: true, hint: '留空表示不计碳收益情景' },
  { key: 'storage_caps', label: '储能可选容量（kWh，逗号分隔）', type: 'text', group: 'storage', opt: true, hint: '0 表示不装；留空使用计算服务默认档位' },
  { key: 'st_price', label: '储能单价', type: 'number', unit: '元/kWh', min: 0, group: 'storage', sq: ['quote', 'cny_per_kwh'] },
  { key: 'st_install', label: '储能安装费', type: 'number', unit: '元/kWh', min: 0, group: 'storage', sq: ['quote', 'installation_cny_per_kwh'] },
  { key: 'st_maint', label: '储能年运维', type: 'number', unit: '元/年', min: 0, group: 'storage', sq: ['quote', 'maintenance_cny_per_year'] },
  { key: 'st_life', label: '电池寿命', type: 'int', unit: '年', min: 1, max: 40, group: 'storage', sq: ['quote', 'life_years'] },
  { key: 'ex_price', label: '上网电价（卖电）', type: 'number', unit: '元/kWh', min: 0, step: 0.01, group: 'storage', sq: ['export', 'price_cny_per_kwh'] },
  { key: 'ex_conn', label: '并网投入', type: 'number', unit: '元', min: 0, group: 'storage', sq: ['export', 'connection_cny'], hint: '可留空；留空时计算服务按 0 粗算并写明' }
];
export const FIELD = Object.fromEntries(FIELDS.map((f) => [f.key, f]));

/** 后端 field 路径 → 表单字段 */
export const FIELD_PATH = {
  'room.equipment_id': 'equipment_id', 'room.room_count': 'room_count', 'room.units_per_room': 'units_per_room', 'room': 'room_count',
  'room.area_m2': 'area_m2', 'room.start_hour': 'start_hour', 'room.end_hour': 'end_hour',
  'pv.requested_capacities_kwp': 'capacities', 'pv.capacity_kwp': 'capacities', 'pv.fixed_capacity_kwp': 'capacities',
  'pv.roof_area_m2': 'roof_area_m2', 'pv.usable_fraction': 'usable_fraction',
  'hybrid.budget_cny': 'budget_cny', 'pv.tariff_id': 'tariff_id', 'weather': 'year', 'hybrid.export_limit_kw': 'allow_export',
  'max_units': 'max_units', 'carbon.factor_id': 'factor_id', 'carbon.carbon_price_cny_per_t': 'carbon_price',
  'storage': 'storage_caps', 'storage.capacities_kwh': 'storage_caps', 'storage.quote': 'st_price', 'storage.quote.cny_per_kwh': 'st_price',
  'storage.quote.installation_cny_per_kwh': 'st_install', 'storage.quote.maintenance_cny_per_year': 'st_maint', 'storage.quote.life_years': 'st_life',
  'storage.export': 'ex_price', 'storage.export.price_cny_per_kwh': 'ex_price', 'storage.export.connection_cny': 'ex_conn'
};

/** 空白条件（输入项的初始值，不是结果）。 */
export function blankForm(options) {
  const cities = (options && options.cities) || [];
  const city = cities[0] || null;
  const years = city ? city.cached_years.map(Number) : [];
  const siteTariffs = tariffsForSite(options, city ? city.site_id : 'guangzhou');
  const eq = ((options && options.equipment_models) || [])[0];
  return {
    site_id: city ? city.site_id : 'guangzhou', year: String(years.includes(2024) ? 2024 : (years[years.length - 1] || 2024)),
    room_count: '1', area_m2: '35', weekdays_only: 'true', start_hour: '8', end_hour: '18', cooling_setpoint_c: '26', rh_setpoint_percent: '60',
    height_m: '', people_count: '', equipment_gain_w: '', orientation: '', window_wall_ratio: '', insulation_u_w_m2k: '', ventilation_lps_person: '', infiltration_ach: '',
    equipment_id: eq ? eq.equipment_id : '', units_per_room: '1', max_units: '20',
    roof_area_m2: '35', usable_fraction: '0.8', capacity_mode: 'auto', capacities: '', wind_turbine_count: '1', hub_height_m: '',
    price_mode: siteTariffs.length ? 'tariff' : 'fixed', tariff_id: siteTariffs.length ? siteTariffs[0] : '', tariff_application: 'current_tariff_on_reference_weather', import_price: '',
    budget_cny: '', study_years: '', allow_export: false,
    ...Object.fromEntries(FIELDS.filter((f) => f.q).map((f) => [f.key, ''])),
    factor_id: '', carbon_price: '', storage_caps: '0, 5, 10, 20, 50',
    ...Object.fromEntries(FIELDS.filter((f) => f.sq).map((f) => [f.key, ''])),
    _extras: { room: {}, wind: {}, storageMeta: null }
  };
}

/** 适用于所选城市的电价档案（按档案的 site_ids 匹配，最新生效的排在前面）；没有则返回空。 */
export function tariffsForSite(options, siteId) {
  return tariffList(options).filter((t) => Array.isArray(t.site_ids) && t.site_ids.includes(siteId))
    .sort((a, b) => String(b.effective_start || '').localeCompare(String(a.effective_start || ''))).map((t) => t.tariff_id);
}

export function tariffList(options) {
  return (((options || {}).tariffs || {}).tariffs || []).filter((t) => !String(t.tariff_id).startsWith('boptest'));
}

const n = (v) => { if (v === '' || v == null) return null; const x = Number(String(v).replace(/,/g, '')); return Number.isFinite(x) ? x : NaN; };
export const parseList = (s) => String(s || '').split(/[,，、\s]+/).filter(Boolean).map((x) => Number(x));

/** 本地基本校验（只查格式；数值合理性由计算服务校验并返回中文 message/field）。 */
export function validate(form) {
  const err = {};
  for (const f of FIELDS) {
    if (['select', 'seg', 'check', 'text'].includes(f.type)) continue;
    if (f.group === 'ac-size') continue;
    if ((f.q || f.sq) && form[f.key] === '') continue;
    if (f.key === 'import_price' && form.price_mode !== 'fixed') continue;
    const v = n(form[f.key]);
    if (v === null) { if (!f.opt && !f.q) err[f.key] = '请填写'; continue; }
    if (Number.isNaN(v)) { err[f.key] = '请输入数字'; continue; }
    if (f.type === 'int' && !Number.isInteger(v)) { err[f.key] = '请输入整数'; continue; }
    if (f.min != null && v < f.min) err[f.key] = `不能小于 ${f.min}`;
    else if (f.max != null && v > f.max) err[f.key] = `不能大于 ${f.max}`;
  }
  if (!err.start_hour && !err.end_hour && n(form.end_hour) <= n(form.start_hour)) err.end_hour = '结束时间要晚于开始时间';
  if (form.capacity_mode !== 'auto') {
    const list = parseList(form.capacities);
    if (!list.length) err.capacities = '请至少填写一个容量';
    else if (list.some((x) => !Number.isFinite(x) || x < 0)) err.capacities = '容量必须是非负数字';
    else if (form.capacity_mode === 'fixed' && list.length !== 1) err.capacities = '“只看一个容量”只能填一个数';
  }
  if (form.storage_caps && parseList(form.storage_caps).some((x) => !Number.isFinite(x) || x < 0)) err.storage_caps = '容量必须是非负数字';
  if (form.price_mode === 'tariff' && !form.tariff_id) err.tariff_id = '请选择电价档案';
  return err;
}

function quote(form, kind) {
  const out = {};
  for (const f of FIELDS) if (f.q && f.q[0] === kind && form[f.key] !== '') out[f.q[1]] = n(form[f.key]);
  return Object.keys(out).length ? out : null;
}

/** 表单 → 实时接口请求体（hybrid/run、hybrid/jobs、hybrid/preview 共用字段）。 */
export function buildRequest(form) {
  const room = Object.assign({}, form._extras.room || {}, {
    room_count: n(form.room_count), units_per_room: n(form.units_per_room), area_m2: n(form.area_m2),
    weekdays_only: form.weekdays_only === 'true', start_hour: n(form.start_hour), end_hour: n(form.end_hour),
    cooling_setpoint_c: n(form.cooling_setpoint_c), rh_setpoint_percent: n(form.rh_setpoint_percent), equipment_id: form.equipment_id
  });
  for (const k of ['height_m', 'people_count', 'equipment_gain_w', 'window_wall_ratio', 'insulation_u_w_m2k', 'ventilation_lps_person', 'infiltration_ach']) if (form[k] !== '') room[k] = n(form[k]);
  if (form.orientation) room.orientation = form.orientation;
  delete room.equipment_count;     // 台数只用 units_per_room 一个口径
  const pv = { roof_area_m2: n(form.roof_area_m2), allow_export: !!form.allow_export };
  if (form.usable_fraction !== '') pv.usable_fraction = n(form.usable_fraction);
  if (form.capacity_mode === 'auto') pv.auto_capacity = true;
  else if (form.capacity_mode === 'list') pv.requested_capacities_kwp = parseList(form.capacities);
  else pv.fixed_capacity_kwp = parseList(form.capacities)[0];
  if (form.price_mode === 'tariff') { pv.tariff_id = form.tariff_id; pv.tariff_application = form.tariff_application; }
  if (form.study_years !== '') pv.study_years = n(form.study_years);
  const pq = quote(form, 'pv'); if (pq) pv.quote = pq;
  const wind = Object.assign({}, form._extras.wind || {}, { turbine_count: n(form.wind_turbine_count) });
  if (form.hub_height_m !== '') wind.hub_height_m = n(form.hub_height_m);
  const hybrid = { allow_export: !!form.allow_export, wind };
  if (form.budget_cny !== '') hybrid.budget_cny = n(form.budget_cny);
  if (form.study_years !== '') hybrid.study_years = n(form.study_years);
  if (form.price_mode === 'fixed') hybrid.import_price_cny_per_kwh = n(form.import_price);
  if (pq) hybrid.pv_quote = pq;
  const wq = quote(form, 'wind'); if (wq) hybrid.wind_quote = wq;
  const req = { site_id: form.site_id, year: n(form.year), room, pv, hybrid };
  const carbon = {};
  if (form.factor_id) carbon.factor_id = form.factor_id;
  if (form.carbon_price !== '') carbon.carbon_price_cny_per_t = n(form.carbon_price);
  if (Object.keys(carbon).length) req.carbon = carbon;
  const storage = {};
  if (form.storage_caps) storage.capacities_kwh = parseList(form.storage_caps);
  for (const part of ['quote', 'export']) {
    const obj = {};
    for (const f of FIELDS) if (f.sq && f.sq[0] === part && form[f.key] !== '') obj[f.sq[1]] = n(form[f.key]);
    if (!Object.keys(obj).length) continue;
    // 示例报价的来源说明：只有数值与填入时完全相同才一并发送，用户改过数值就不再沿用示例来源
    const meta = form._extras && form._extras.storageMeta && form._extras.storageMeta[part];
    if (meta && Object.entries(meta.values).every(([k, v]) => obj[k] === v) && Object.keys(obj).every((k) => k in meta.values)) Object.assign(obj, meta.source);
    storage[part] = obj;
  }
  if (Object.keys(storage).length) req.storage = storage;
  return req;
}

/** 预览请求：同一请求体 + preview；预览只看一个容量。 */
export function buildPreview(form, season) {
  const req = buildRequest(form);
  const pv = Object.assign({}, req.pv);
  delete pv.auto_capacity; delete pv.requested_capacities_kwp; delete pv.fixed_capacity_kwp;
  if (form.capacity_mode !== 'auto') {
    const list = parseList(form.capacities); const nz = list.find((x) => x > 0);
    const cap = form.capacity_mode === 'fixed' ? list[0] : (nz != null ? nz : list[0]);
    if (Number.isFinite(cap)) pv.capacity_kwp = cap;
  }
  return Object.assign(req, { pv, preview: { period: 'typical_week', season } });
}

const s = (v) => (v == null ? '' : String(v));
/** 示例请求体 → 表单（用于“从示例开始”和打开示例）。 */
export function formFromRequest(req, options) {
  const f = blankForm(options);
  const room = Object.assign({}, req.room || {}), pv = req.pv || {}, hy = req.hybrid || {}, wind = Object.assign({}, hy.wind || {});
  f.site_id = s(req.site_id || f.site_id); f.year = s(req.year || f.year);
  for (const k of ['room_count', 'units_per_room', 'area_m2', 'start_hour', 'end_hour', 'cooling_setpoint_c', 'rh_setpoint_percent', 'height_m', 'people_count', 'equipment_gain_w', 'window_wall_ratio', 'insulation_u_w_m2k', 'ventilation_lps_person', 'infiltration_ach']) if (room[k] != null) f[k] = s(room[k]);
  if (room.units_per_room == null && room.equipment_count != null) f.units_per_room = s(room.equipment_count);
  if (room.weekdays_only != null) f.weekdays_only = String(!!room.weekdays_only);
  if (room.orientation) f.orientation = room.orientation;
  if (room.equipment_id) f.equipment_id = room.equipment_id;
  const known = new Set(['room_count', 'units_per_room', 'area_m2', 'start_hour', 'end_hour', 'cooling_setpoint_c', 'rh_setpoint_percent', 'height_m', 'people_count', 'equipment_gain_w', 'window_wall_ratio', 'insulation_u_w_m2k', 'ventilation_lps_person', 'infiltration_ach', 'weekdays_only', 'orientation', 'equipment_id', 'equipment_count']);
  f._extras.room = Object.fromEntries(Object.entries(room).filter(([k]) => !known.has(k)));
  f.roof_area_m2 = s(pv.roof_area_m2 ?? ''); f.usable_fraction = s(pv.usable_fraction ?? '');
  if (pv.fixed_capacity_kwp != null) { f.capacity_mode = 'fixed'; f.capacities = s(pv.fixed_capacity_kwp); }
  else if (Array.isArray(pv.requested_capacities_kwp)) { f.capacity_mode = 'list'; f.capacities = pv.requested_capacities_kwp.join(', '); }
  else { f.capacity_mode = 'auto'; f.capacities = ''; }
  f.wind_turbine_count = s(wind.turbine_count ?? 0); f.hub_height_m = s(wind.hub_height_m ?? '');
  f._extras.wind = Object.fromEntries(Object.entries(wind).filter(([k]) => !['turbine_count', 'hub_height_m', 'site_id', 'year'].includes(k)));
  if (pv.tariff_id) { f.price_mode = 'tariff'; f.tariff_id = pv.tariff_id; f.tariff_application = pv.tariff_application || 'historical_weather_date'; }
  else { f.price_mode = 'fixed'; f.import_price = s(hy.import_price_cny_per_kwh ?? pv.import_price_cny_per_kwh ?? ''); }
  f.budget_cny = s(hy.budget_cny ?? ''); f.study_years = s(hy.study_years ?? pv.study_years ?? '');
  f.allow_export = !!(hy.allow_export ?? pv.allow_export);
  const pq = hy.pv_quote || pv.quote || {}, wq = hy.wind_quote || {};
  for (const fd of FIELDS) if (fd.q) { const src = fd.q[0] === 'pv' ? pq : wq; f[fd.key] = src[fd.q[1]] != null ? s(src[fd.q[1]]) : ''; }
  const c = req.carbon || {};
  f.factor_id = c.factor_id || ''; f.carbon_price = c.carbon_price_cny_per_t != null ? s(c.carbon_price_cny_per_t) : '';
  f.storage_caps = req.storage && Array.isArray(req.storage.capacities_kwh) ? req.storage.capacities_kwh.join(', ') : '';
  Object.assign(f, storageFieldsFrom(req));
  f._extras.storageMeta = storageMetaFrom(req);
  return f;
}

/** 储能与卖电输入（来自请求体 storage.quote / storage.export）。 */
export function storageFieldsFrom(req) {
  const st = req.storage || {}, out = {};
  for (const fd of FIELDS) if (fd.sq) { const src = st[fd.sq[0]] || {}; out[fd.key] = src[fd.sq[1]] != null ? String(src[fd.sq[1]]) : ''; }
  return out;
}
/** 示例的储能/卖电来源说明（source、source_url、source_note 等），连同数值快照一起保存。 */
export function storageMetaFrom(req) {
  const st = req.storage || {}, meta = {};
  for (const part of ['quote', 'export']) {
    const o = st[part]; if (!o) continue;
    const values = {}, source = {};
    for (const [k, v] of Object.entries(o)) (typeof v === 'number' ? values : source)[k] = v;
    meta[part] = { values, source };
  }
  return Object.keys(meta).length ? meta : null;
}

/** 示例报价（来自示例回放请求体中的用户情景报价，不是采购报价）。 */
export function quoteFieldsFrom(req) {
  const hy = req.hybrid || {}, pv = req.pv || {};
  const pq = hy.pv_quote || pv.quote || {}, wq = hy.wind_quote || {};
  const out = {};
  for (const fd of FIELDS) if (fd.q) { const src = fd.q[0] === 'pv' ? pq : wq; if (src[fd.q[1]] != null) out[fd.key] = String(src[fd.q[1]]); }
  return out;
}

/* ------------------------------------------------------------------ */
/* 一句话输入：本地规则，只处理使用时段、预算、光伏容量、风机台数/高度、   */
/* 电价、是否外送；房间数、台数、面积、城市等提示“请在表单修改”。         */
/* ------------------------------------------------------------------ */
export function parseAsk(text) {
  const applied = [], rejected = [];
  const t = String(text || '').replace(/\s+/g, '');
  if (!t) return { applied, rejected };
  const num = (x) => Number(String(x).replace(/,/g, ''));
  let m;
  if ((m = t.match(/(\d{1,2})(?:[:：]00)?点?(?:到|至|-|—|~)(\d{1,2})(?:[:：]00)?点/))) {
    const a = num(m[1]), b = num(m[2]);
    if (a >= 0 && a <= 23 && b >= 1 && b <= 24 && b > a) applied.push(['start_hour', String(a), '开始使用'], ['end_hour', String(b), '结束使用']);
    else rejected.push([m[0], '时段不合法']);
  }
  if (/每天|天天|全周|周末也/.test(t)) applied.push(['weekdays_only', 'false', '使用日：每天']);
  else if (/工作日/.test(t)) applied.push(['weekdays_only', 'true', '使用日：工作日']);
  if ((m = t.match(/预算(?:为|是|约|有)?(\d+(?:\.\d+)?)(万|w|W)?(?:元)?/))) applied.push(['budget_cny', String(Math.round(num(m[1]) * (m[2] ? 10000 : 1))), '预算']);
  if ((m = t.match(/(\d+(?:\.\d+)?)(?:kWp|kwp|KWP|千瓦)(?:的)?光伏|光伏(\d+(?:\.\d+)?)(?:kWp|kwp|KWP|千瓦)/))) applied.push(['capacities', String(num(m[1] || m[2])), '光伏容量'], ['capacity_mode', 'list', '光伏容量方式：指定候选容量']);
  if (/不装(?:小)?风机|不要(?:小)?风机/.test(t)) applied.push(['wind_turbine_count', '0', '小风机：不装']);
  else if ((m = t.match(/([01一])台(?:小)?风机/))) applied.push(['wind_turbine_count', m[1] === '0' ? '0' : '1', `小风机：${m[1] === '0' ? '不装' : '1 台'}`]);
  else if ((m = t.match(/(\d+)台(?:小)?风机/))) rejected.push([m[0], '小风机目前只支持 0 或 1 台']);
  if ((m = t.match(/(?:风机|轮毂)(?:安装)?(?:高度)?(\d+(?:\.\d+)?)(?:米|m)/))) applied.push(['hub_height_m', String(num(m[1])), '风机安装高度']);
  if ((m = t.match(/电价(?:为|是)?(\d+(?:\.\d+)?)元?/))) applied.push(['import_price', String(num(m[1])), '固定电价'], ['price_mode', 'fixed', '电价方式：固定电价']);
  if (/不(?:允许)?外送|不卖电|不上网/.test(t)) applied.push(['allow_export', false, '不卖电给电网']);
  else if (/允许外送|可以外送|余电上网|卖给电网|卖电/.test(t)) applied.push(['allow_export', true, '多余电量卖给电网']);
  const unsupported = [[/(\d+)间/, '房间数'], [/每间(\d+)台|(\d+)台空调/, '空调台数'], [/(\d+(?:\.\d+)?)(?:㎡|平方米|平米|m2)/, '面积'],
    [/广州|北京|哈尔滨|上海|深圳|成都|杭州|武汉|西安|南京/, '城市'], [/(\d+)人/, '人数'], [/(\d+)度|(\d+)℃/, '温度']];
  for (const [re, name] of unsupported) {
    const hit = t.match(re);
    if (hit && !(name === '面积' && /屋顶/.test(t.slice(Math.max(0, hit.index - 4), hit.index)))) rejected.push([hit[0], `${name}请在表单修改`]);
  }
  return { applied, rejected };
}

export const isNumStr = (v) => v !== '' && isNum(Number(v));
