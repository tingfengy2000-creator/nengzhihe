'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {cases:[], current:null, currentView:null, strategy:'adaptive_rule', preferredStrategy:'adaptive_rule', budget:3, run:null, shown:0, filter:'all', model:null, busy:false, benchmark:null, caseRequest:0, includeDev:false};
const strategyNames = {fixed:'固定流程',fixed_order:'固定流程',adaptive_rule:'自适应规则',rules:'自适应规则',rule:'自适应规则',adaptive_rules:'自适应规则',local_model:'本地模型',model:'本地模型',llm:'本地模型',full:'完整信息',full_info:'完整信息',full_information:'完整信息'};
const statusNames = {completed:'评测已完成',complete:'评测已完成',frozen:'冻结评测已完成',supported:'证据支持候选判断',model_error:'本地模型动作失败',not_run:'尚未运行',unknown:'待核验',pending:'待核验',unchecked:'待检查',insufficient:'证据不足',insufficient_evidence:'证据不足',inconclusive:'证据不足',needs_evidence:'需要补充证据',normal:'未见充分异常证据',healthy:'未见充分异常证据',ok:'记录通过检查',clean:'记录通过检查',good:'记录通过检查',suspect:'存在待核查疑点',suspicious:'存在待核查疑点',anomaly:'发现异常候选',abnormal:'存在运行异常',fault:'发现设备故障证据',fault_detected:'发现设备故障证据',confirmed:'证据支持异常判断',quality_issue:'发现数据问题',corrupted:'发现数据问题',issues:'发现数据问题',warning:'存在待核查问题',repaired:'已修正 · 仍需核验',corrected:'已修正 · 仍需核验',unavailable:'当前不可用',not_applicable:'不适用',sensor_fault:'疑似传感器记录问题',damper_stuck:'室外风阀卡滞',oa_damper_stuck:'室外风阀卡滞',valve_leakage:'冷却盘管阀泄漏',cooling_valve_leakage:'冷却盘管阀泄漏',cooling_coil_valve_leakage:'冷却盘管阀泄漏'};
const evidenceKeys = {value:'观测值',detail:'核查说明',result:'计算结果',status:'状态',unit:'单位',threshold:'判定阈值',count:'数量',mean:'均值',median:'中位数',score:'计算评分',ratio:'比例',label:'证据项',source:'来源',reason:'选择依据',issue:'数据问题',diagnosis:'判断',points:'点位',available:'是否可用',feature:'特征',metric:'指标',window:'时间范围',query_units:'查询单位',field_acquisition_units:'现场补采单位'};

async function api(path, body) {
  const options = body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
  const response = await fetch(path, options);
  const kind = response.headers.get('content-type') || '';
  const data = kind.includes('json') ? await response.json() : {error:await response.text()};
  if (!response.ok) throw new Error(data.error || data.detail || `数据服务返回 ${response.status}`);
  return data;
}
function notify(message, persistent = false) {
  if (persistent) {$('#global-notice').textContent=message;$('#global-notice').classList.remove('hidden');return;}
  const el=$('#toast');el.textContent=message;el.classList.remove('hidden');clearTimeout(notify.timer);notify.timer=setTimeout(()=>el.classList.add('hidden'),4500);
}
function textValue(value) {if (value === null || value === undefined) return '—';if (typeof value === 'boolean') return value?'是':'否';if (typeof value === 'object') return JSON.stringify(value);return String(value);}
function translate(value) {return statusNames[String(value)] || textValue(value);}
function asArray(value) {if (!value) return [];return Array.isArray(value)?value:[value];}
function finite(value) {return typeof value==='number'&&Number.isFinite(value);}
function fmt(value, digits=2) {return finite(value)?value.toLocaleString('zh-CN',{maximumFractionDigits:digits}):'—';}
function pct(value) {return finite(value)?`${(value*100).toFixed(1)}%`:'—';}
function duration(value) {return finite(value)?(value>=1000?`${(value/1000).toFixed(2)}s`:`${Math.round(value)}ms`):'—';}
function isMeasured(item) {return /bdg|measured|实测|real/i.test([item.family,item.origin,item.source,item.dataset].join(' '));}
function isPerturbed(item) {const p=item.perturbation;return Boolean(item.perturbed===true || (typeof p==='object'&&p!==null&&p.type&&p.type!=='none') || (typeof p==='string'&&p!=='none'&&p!=='') || /human_generated|人为扰动/.test(item.origin||''));}
function caseTitle(item) {if(item.split==='demo'){if(isMeasured(item))return '真实建筑 · 用能回放';if(isPerturbed(item))return '记录修正 · 持续核查';return '空调机组 · 证据核验';}return item.title||item.name||item.id;}
function orderCases(cases) {return [...cases].sort((a,b)=>((a.split==='demo'?0:10)+(isMeasured(a)?0:isPerturbed(a)?2:1))-((b.split==='demo'?0:10)+(isMeasured(b)?0:isPerturbed(b)?2:1)));}
function badges(item) {
  const measured=isMeasured(item);
  return `<span class="badge ${measured?'measured':'simulated'}">${measured?'实测 · BDG2':'仿真 · LBNL'}</span>${isPerturbed(item)?'<span class="badge perturbed">人为扰动</span>':''}${/holdout|test|留出/.test(item.split||'')?'<span class="badge holdout">留出案例</span>':''}`;
}
function qualityTone(value) {const str=String(value||'');if (/repaired|corrected|clean|good|normal|healthy|passed|ok|通过|已修正/.test(str)) return 'good';if (/fault|abnormal|confirmed|异常|故障/.test(str))return 'danger';if (/issue|corrupt|suspect|warning|needs_review|insufficient|缺|问题|疑/.test(str))return 'warning';return 'neutral';}
function readableIssues(quality) {
  const issues=asArray(quality?.issues);
  if (issues.length) return issues.map(issue=>typeof issue==='string'?issue:issue.detail||issue.description||issue.label||issue.type||JSON.stringify(issue)).join('；');
  return quality?.detail || quality?.description || '记录质量与运行状态分别核查。';
}
function renderStates(quality={}, operation={}) {
  if (typeof quality==='string')quality={status:quality};if(typeof operation==='string')operation={status:operation};
  $('#quality-status').textContent=state.current?.repair?'已修正 · 记录重新检查':translate(quality.label || quality.status || 'unchecked');
  $('#quality-detail').textContent=readableIssues(quality);
  $('#quality-indicator').className=`state-indicator ${qualityTone(quality.status)}`;
  $('#operation-status').textContent=operation.name || translate(operation.label || operation.status || 'pending');
  $('#operation-detail').textContent=operation.detail||operation.description||'数据问题修正后，设备与运行疑点仍须独立核查。';
  $('#operation-indicator').className=`state-indicator ${qualityTone(operation.status)}`;
  const repairAllowed = !state.current?.repair && (quality.repairable ?? state.current?.repairable ?? (Number(quality.duplicates)>0));
  $('#repair-btn').disabled=state.busy||!repairAllowed;
  $('#repair-btn').innerHTML=state.current?.repair||/repaired|corrected/.test(quality.status||'')?'已修正，继续核验 <span>✓</span>':'修正数据问题 <span>↗</span>';
}
function renderCases() {
  const hasDemo=state.cases.some(item=>item.split==='demo');const library=state.cases.filter(item=>!hasDemo||state.includeDev||item.split==='demo');
  $('#case-count').textContent=library.length;
  $('#case-library-toggle').classList.toggle('hidden',!hasDemo||state.cases.every(item=>item.split==='demo'));$('#case-library-toggle').innerHTML=state.includeDev?'仅显示演示案例 <span>−</span>':'展开开发案例 <span>＋</span>';
  const cases=orderCases(library.filter(item=>state.filter==='all'||(state.filter==='measured'?isMeasured(item):!isMeasured(item))));
  $('#case-list').innerHTML=cases.length?cases.map((item,index)=>`<button class="case-option ${state.current?.id===item.id||state.current?.original_case_id===item.id?'active':''}" data-case-id="${escapeHTML(item.id)}"><div class="case-number"><span>${item.split==='demo'?'DEMO':'DEV'} ${String(index+1).padStart(2,'0')}</span>${state.current?.id===item.id?'<b>↗</b>':''}</div><h3>${escapeHTML(caseTitle(item))}</h3><p>${escapeHTML(item.description || item.summary || '')}</p><div class="badges">${badges(item)}</div></button>`).join(''):'<div class="empty-state compact"><p>暂无此类案例</p></div>';
  $$('.case-option').forEach(button=>button.addEventListener('click',()=>loadCase(button.dataset.caseId)));
}
function normalizeSeries(data) {
  const c=data.case||data;const view=data.view||{};let source=view.initial_series||c.initial_series||c.series||[];
  if(!Array.isArray(source))source=Object.entries(source).map(([key,value])=>Array.isArray(value)?{key,label:key,values:value,unit:c.units?.[key]}:{key,...value});
  const labels={electricity_kwh:'实测用电量',reference_kwh:'历史参考用电量',electricity:'建筑电力表计',air_temperature:'室外温度'};const units={degC:'°C','kWh per hour':'kWh'};
  return source.map((series,index)=>({key:series.key||series.name||String(index),label:labels[series.key]||labels[series.label]||series.label||series.name||series.key||`观测 ${index+1}`,unit:['electricity_kwh','reference_kwh'].includes(series.key)?'kWh':units[series.unit]||series.unit||c.units?.[series.key]||'',values:asArray(series.values||series.data).map(point=>typeof point==='object'&&point!==null?point.value??point.y??null:point)}));
}
async function loadCase(id) {
  if(state.busy)return;
  const request=++state.caseRequest;state.busy=true;$('#run-btn').disabled=true;$('#repair-btn').disabled=true;$('.analysis-column').classList.add('case-switch-loading');refreshControls();
  try {const data=await api(`/api/case/${encodeURIComponent(id)}`);if(request!==state.caseRequest)return;applyCase(data);$('#global-notice').classList.add('hidden');}
  catch(error){if(request===state.caseRequest)notify(`案例未能加载：${error.message}`,true);}
  finally{if(request===state.caseRequest){state.busy=false;$('.analysis-column').classList.remove('case-switch-loading');refreshControls();}}
}
function applyCase(data) {
  const c=data.case||data;state.current={...(state.cases.find(item=>item.id===c.id)||{}),...c};if(c.id?.endsWith('__repaired'))state.current.original_case_id=c.id.replace(/__repaired$/,'');state.currentView=data.view||{};state.series=normalizeSeries(data);state.run=null;state.shown=0;
  state.strategy=isMeasured(state.current)?'fixed':state.preferredStrategy;
  $('#case-title').textContent=caseTitle(state.current)||'核验案例';$('#case-description').textContent=c.description||c.summary||'';$('#case-id').textContent=c.id||'';$('#case-badges').innerHTML=badges(state.current);renderCases();
  $('#series-select').innerHTML=state.series.length?state.series.map((series,index)=>`<option value="${index}">${escapeHTML(series.label)}</option>`).join(''):'<option value="">暂无序列</option>';
  renderChart(0);renderStates(state.currentView.quality||c.quality, state.currentView.operation||c.operation);resetRunView();
}
function resetRunView() {
  $('#evidence-list').innerHTML='<div class="empty-state evidence-empty"><div class="evidence-illustration"><span></span><span></span><span></span><b>✓</b></div><h3>从一条证据开始</h3><p>选择案例与策略后开始核验。<br>这里将展示真实计算返回的证据。</p></div>';
  $('#run-state').className='live-pill';$('#run-state').textContent='尚未运行';$('#evidence-description').textContent='每一步都有来源，每项结论都有依据。';$('#final-result').classList.add('hidden');$('#step-btn').disabled=true;$('#export-btn').disabled=true;$('#query-cost').textContent='—';$('#field-cost').textContent='—';$('#latency-cost').textContent='—';
}
function refreshControls() {
  const measured=isMeasured(state.current||{});if(measured)state.strategy='fixed';
  if(state.strategy==='full_information'){state.budget=4;$('#budget-input').value=4;}
  $('#run-btn').disabled=state.busy||!state.current||(state.strategy==='local_model'&&state.model?.available===false);
  $('#run-btn').innerHTML=state.busy?'<span>正在计算</span><span class="loading-ring"></span>':`<span>${measured?'开始回放':'开始核验'}</span><span>→</span>`;
  $('#strategy-title').textContent=measured?'确定性统计回放':'核验策略';$('#strategy-hint').textContent=measured?'BDG2 不参与策略对照':'共享证据池与预算';
  $$('.strategy-option').forEach(button=>{button.disabled=state.busy||(measured&&button.dataset.strategy!=='fixed')||(button.dataset.strategy==='local_model'&&state.model?.available===false);button.classList.toggle('active',button.dataset.strategy===state.strategy);});
  $$('.case-option,[data-filter],#case-library-toggle').forEach(button=>{button.disabled=state.busy;});
  $('#budget-input').disabled=state.busy||state.strategy==='full_information';$('#budget-value').textContent=state.budget;
  $('#budget-note').textContent=measured?(state.budget===1?'预算 1 仅检查记录质量；BDG2 为固定统计回放，不调用模型、不参与策略比较。':'BDG2 仅固定统计回放，不调用模型、不参与策略比较，不定位设备故障。'):state.budget===1?'预算 1 仅完成强制记录质量检查；没有设备过程证据，不能用于故障定位。':state.strategy==='full_information'?'完整信息固定查询全部 4 组，仅在预算 4 下公平对照；现场补采单独记账。':'记录检查固定计 1 单位，另有 3 组分析证据；现场补采单独记账。';
  if(state.current){const view=state.currentView||{};const last=state.run?.steps?.[state.shown-1];renderStates(last?.quality||view.quality||state.current.quality,last?.operation||last?.diagnosis||view.operation||state.current.operation);}
}

function renderChart(index=0) {
  const series=state.series?.[Number(index)];const target=$('#chart');
  if(!series||!series.values.some(finite)){target.innerHTML='<div class="empty-state"><span class="empty-glyph">⌁</span><p>此案例暂无可绘制观测序列</p></div>';return;}
  const values=series.values;const timestamps=state.current?.timestamps||[];const valid=values.filter(finite);let min=Math.min(...valid),max=Math.max(...valid);const padding=(max-min)*.14||Math.abs(max)*.1||1;min-=padding;max+=padding;
  const W=600,H=215,L=48,R=15,T=13,B=30;const plotW=W-L-R,plotH=H-T-B;const x=i=>L+(i/Math.max(values.length-1,1))*plotW;const y=v=>T+(max-v)/(max-min)*plotH;
  let path='',started=false;values.forEach((value,i)=>{if(!finite(value)){started=false;return;}path+=`${started?'L':'M'}${x(i).toFixed(2)},${y(value).toFixed(2)} `;started=true;});
  let grid='';for(let i=0;i<5;i++){const val=min+(max-min)*i/4;grid+=`<line x1="${L}" y1="${y(val)}" x2="${W-R}" y2="${y(val)}" stroke="#eaf0f2" stroke-dasharray="3 4"/><text x="${L-10}" y="${y(val)+3}" text-anchor="end" fill="#a8b8c0" font-size="8" font-family="Segoe UI">${escapeHTML(fmt(val,1))}</text>`;}
  let ticks='';for(let i=0;i<5;i++){const idx=Math.round(i*(values.length-1)/4);let label=timestamps[idx]?formatTime(timestamps[idx]):String(idx+1);ticks+=`<text x="${x(idx)}" y="${H-7}" text-anchor="${i===0?'start':i===4?'end':'middle'}" fill="#a8b8c0" font-size="8" font-family="Segoe UI">${escapeHTML(label)}</text>`;}
  const first=values.findIndex(finite);let last=values.length-1;while(last>0&&!finite(values[last]))last--;
  const area=values.every(finite)?`${path}L${x(last)},${H-B} L${x(first)},${H-B} Z`:'';
  target.innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${escapeHTML(series.label)}观测曲线"><defs><linearGradient id="curve-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#73b7a4" stop-opacity=".17"/><stop offset="100%" stop-color="#73b7a4" stop-opacity=".01"/></linearGradient></defs>${grid}${area?`<path d="${area}" fill="url(#curve-fill)"/>`:''}<path d="${path}" fill="none" stroke="#2d9b89" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>${ticks}<line id="hover-line" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="#9ec9be" stroke-dasharray="3 3" visibility="hidden"/><circle id="hover-point" r="3.5" fill="#269783" stroke="#fff" stroke-width="2" visibility="hidden"/><rect x="${L}" y="${T}" width="${plotW}" height="${plotH}" fill="transparent" id="chart-hit"/></svg><div class="chart-tooltip hidden"></div>`;
  $('#chart-unit').textContent=series.unit?`/ ${series.unit}`:'';$('#chart-legend').textContent=series.label;
  $('#chart-caption').textContent=state.current?.time_range||(`${values.length} 个观测点${timestamps[0]?` · ${String(timestamps[0]).slice(0,10)}`:''}`);
  const hit=$('#chart-hit');const svg=$('svg',target);const tooltip=$('.chart-tooltip',target);
  hit.addEventListener('pointermove',event=>{const box=svg.getBoundingClientRect();const px=(event.clientX-box.left)/box.width*W;const idx=Math.max(0,Math.min(values.length-1,Math.round((px-L)/plotW*(values.length-1))));if(!finite(values[idx])){tooltip.classList.add('hidden');return;}const line=$('#hover-line');line.setAttribute('x1',x(idx));line.setAttribute('x2',x(idx));line.setAttribute('visibility','visible');const point=$('#hover-point');point.setAttribute('cx',x(idx));point.setAttribute('cy',y(values[idx]));point.setAttribute('visibility','visible');tooltip.innerHTML=`${escapeHTML(timestamps[idx]||`观测点 ${idx+1}`)}<strong>${escapeHTML(fmt(values[idx],3))} ${escapeHTML(series.unit)}</strong>`;tooltip.classList.remove('hidden');tooltip.style.left=`${Math.max(4,Math.min(event.clientX-box.left+12,box.width-170))}px`;tooltip.style.top='8px';});
  hit.addEventListener('pointerleave',()=>{tooltip.classList.add('hidden');$('#hover-line').setAttribute('visibility','hidden');$('#hover-point').setAttribute('visibility','hidden');});
}
function formatTime(value){const str=String(value);if(str.includes('T')||str.includes(' '))return str.slice(5,16).replace('T',' ');return str.length>13?str.slice(0,13):str;}

async function runVerification() {
  if(state.busy||!state.current)return;state.busy=true;state.run=null;state.shown=0;resetRunView();refreshControls();$('#run-state').textContent='实际计算中';$('#run-state').className='live-pill running';$('#evidence-list').innerHTML='<div class="empty-state evidence-empty"><span class="loading-ring"></span><h3>正在执行核验程序</h3><p>读取允许使用的证据，记录查询成本。<br>本地模型策略可能需要更长时间。</p></div>';
  try{const result=await api('/api/run',{case_id:state.current.id,strategy:state.strategy,budget:state.budget,repair:false});state.run=result;state.shown=Math.min(1,(result.steps||[]).length);renderRun();}
  catch(error){$('#run-state').textContent='运行未完成';$('#run-state').className='live-pill';$('#evidence-list').innerHTML=`<div class="empty-state"><h3>核验未完成</h3><p>${escapeHTML(error.message)}</p></div>`;notify(`核验未完成：${error.message}`);}
  finally{state.busy=false;refreshControls();if(state.run)renderRun();}
}
function evidenceHTML(evidence) {
  if(typeof evidence==='string')return `<div class="evidence-box"><p>${escapeHTML(evidence)}</p></div>`;
  if(evidence===null||evidence===undefined)return '';
  const title=evidence.label||evidence.name||evidence.action||evidence.metric||evidence.key||'计算证据';
  const source=evidence.source||evidence.provenance||evidence.source_file;const detail=evidence.detail||evidence.description||evidence.summary;
  const rest=Object.entries(evidence).filter(([key])=>!['label','name','action','metric','key','source','provenance','source_file','detail','description','summary'].includes(key));
  return `<div class="evidence-box"><strong>${escapeHTML(title)}</strong>${detail?`<p>${escapeHTML(textValue(detail))}</p>`:''}${rest.length?`<p>${rest.map(([key,value])=>`${escapeHTML(evidenceKeys[key]||key)}：${escapeHTML(typeof value==='object'?JSON.stringify(value):textValue(value))}`).join('<br>')}</p>`:''}${source?`<p class="evidence-source">来源：${escapeHTML(textValue(source))}</p>`:''}</div>`;
}
function ruleEvidenceHTML(value) {
  if(!value)return '';
  const ruleLabels={air_response:'混风与风阀响应',coil_response:'盘管响应'};const ruleValues={stuck_candidate:'存在卡滞候选证据',responsive:'观察到响应',unknown:'现有证据不足',leak_candidate:'存在泄漏候选证据',no_leak_evidence:'未见满足规则的泄漏证据'};
  const records=Array.isArray(value)?value:(typeof value==='object'&&!value.label&&!value.rule?Object.entries(value).map(([label,item])=>typeof item==='object'&&item!==null?{label:ruleLabels[label]||label,...item}:{label:ruleLabels[label]||label,value:ruleValues[item]||item}):[value]);
  if(!records.length)return '';
  return `<details class="rule-proof"><summary>查看规则核验依据 <span>${records.length}</span></summary>${records.map(evidenceHTML).join('')}</details>`;
}
function renderRun() {
  const run=state.run;if(!run)return;const steps=run.steps||[];const complete=state.shown>=steps.length;const visible=steps.slice(0,state.shown);
  $('#run-state').className=`live-pill ${complete?'complete':''}`;$('#run-state').textContent=complete?'核验已完成':`${state.shown} / ${steps.length} 步`;
  $('#evidence-description').textContent=`${run.family==='bdg2'?'固定统计回放':run.strategy_label||strategyNames[run.strategy]||run.strategy} · 预算 ${run.budget??'—'} · 真实结果逐步回放`;
  $('#evidence-list').innerHTML=visible.length?visible.map((step,index)=>`<article class="evidence-step"><div class="step-count"><span>STEP ${String(index+1).padStart(2,'0')}</span><span>${finite(step.cost)?`${step.cost} 查询单位`:finite(step.cost?.query_units)?`${step.cost.query_units} 查询单位`:''}${finite(step.latency_ms)?` · ${duration(step.latency_ms)}`:''}</span></div><h3>${escapeHTML(step.label||step.action||'证据核查')}</h3>${step.reason?`<p class="step-reason">${escapeHTML(step.reason)}</p>`:''}${asArray(step.evidence||step.result).map(evidenceHTML).join('')}${step.diagnosis?`<p class="step-reason">当前判断：${escapeHTML(step.diagnosis.name||translate(step.diagnosis.label||step.diagnosis.status||step.diagnosis))}</p>`:''}</article>`).join(''):'<div class="empty-state compact"><p>本次运行未产生查询步骤，请查看结论与警告。</p></div>';
  if(state.shown>1){const list=$('#evidence-list');const lastNode=list.lastElementChild;if(lastNode)list.scrollTop+=lastNode.getBoundingClientRect().top-list.getBoundingClientRect().top;}
  $('#step-btn').disabled=complete;$('#step-btn').innerHTML=complete?'全部证据已展开 <span>✓</span>':'查看下一步证据 <span>↓</span>';
  $('#export-btn').disabled=!run.run_id;
  const cost=run.cost||{};$('#query-cost').textContent=fmt(cost.query_units??cost.queries,1);$('#field-cost').textContent=fmt(cost.field_acquisition_units,1);$('#latency-cost').textContent=duration(cost.latency_ms??run.latency_ms);
  const last=visible[visible.length-1];const final=run.final||{};
  renderStates(complete?(final.quality||last?.quality||state.currentView.quality):(last?.quality||state.currentView.quality),complete?(final.operation||{status:final.status,label:final.label,detail:run.summary}):(last?.operation||last?.diagnosis||state.currentView.operation));
  const result=$('#final-result');result.classList.toggle('hidden',!complete);
  if(complete){const uncertain=/insufficient|unknown|inconclusive|model_error|inactive|not_ready|缺|不足/.test(final.status||final.label||'');result.classList.toggle('warning',uncertain);result.innerHTML=`<span class="result-label">核验结论 / VERIFICATION</span><h3>${escapeHTML(final.name||translate(final.label||final.status||'已完成核验'))}</h3><p>${escapeHTML(final.detail||run.summary||final.description||'请结合证据来源及适用边界审阅本次结果。')}</p>${ruleEvidenceHTML(final.rule_evidence)}${asArray(run.warnings).length?`<ul class="result-warnings">${asArray(run.warnings).map(warning=>`<li>${escapeHTML(textValue(warning))}</li>`).join('')}</ul>`:''}`;}
}
async function repairCase() {
  if(state.busy||!state.current)return;state.busy=true;refreshControls();
  try{const previous=state.current.id;const result=await api('/api/repair',{case_id:previous});applyCase(result);if(!state.current.original_case_id)state.current.original_case_id=previous;renderCases();notify('数据修正结果已加载。设备疑点仍需继续核验，请再次开始核验。');}
  catch(error){notify(`未能修正数据：${error.message}`);}
  finally{state.busy=false;refreshControls();}
}

async function loadCases() {
  try{const data=await api('/api/cases');state.cases=asArray(data.cases);state.model=data.model||{};$('#service-dot').style.background='#5bbfaa';$('#service-label').textContent='数据服务已连接';$('#model-name').textContent=state.model.name||'本地模型待配置';$('#model-status').textContent=state.model.available?'本地可用 · 数值由程序计算':state.model.reason||'尚未就绪 · 如实标记不可用';if(state.model.available===false&&state.strategy==='local_model')state.strategy='adaptive_rule';renderCases();if(!state.current&&state.cases.length)await loadCase(orderCases(state.cases)[0].id);else refreshControls();if(!state.cases.length)notify('数据服务已连接，尚未提供核验案例。',true);}
  catch(error){$('#service-dot').style.background='#d2a665';$('#service-label').textContent='数据服务尚未连接';$('#model-name').textContent='模型状态不可用';$('#model-status').textContent='等待本地数据服务';$('#case-list').innerHTML='<div class="empty-state compact"><p>暂无可用案例<br>请启动本地数据服务后刷新</p></div>';notify(`尚未读取到真实数据：${error.message}`,true);}
}
async function loadBenchmark() {
  try{const result=await api('/api/benchmark');state.benchmark=result;renderBenchmark(result);}
  catch(error){$('#benchmark-content').innerHTML=`<div class="card empty-state"><span class="empty-glyph">▥</span><h3>尚未读取到冻结评测结果</h3><p>${escapeHTML(error.message)}<br>完成真实评测后在此展示，不预填性能数值。</p></div>`;}
}
function metricsTable(rows,title,subtitle) {
  if(!rows.length)return '';
  return `<section class="card table-card"><div class="panel-title"><h2>${escapeHTML(title)}</h2><span class="subtle-text">${escapeHTML(subtitle)}</span></div><div class="table-overflow"><table><thead><tr><th>策略</th><th>预算</th><th>总数</th><th>正确</th><th>错误</th><th>未决</th><th>整体正确率</th><th>Macro F1</th><th>覆盖率</th><th>已决错判率</th><th>平均查询</th><th>平均耗时</th><th>模型调用</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${escapeHTML(strategyNames[row.strategy]||row.strategy)}</td><td>${escapeHTML(textValue(row.budget))}</td><td>${fmt(row.n,0)}</td><td class="count-correct">${fmt(row.correct,0)}</td><td>${fmt(row.wrong,0)}</td><td class="count-unresolved">${fmt(row.unresolved,0)}</td><td>${pct(row.accuracy)}</td><td>${finite(row.macro_f1)?row.macro_f1.toFixed(3):'—'}</td><td>${pct(row.coverage)}</td><td>${pct(row.error_rate)}</td><td>${fmt(row.avg_queries,3)}</td><td>${duration(row.avg_latency_ms)}</td><td>${fmt(row.model_calls,0)}</td></tr>`).join('')}</tbody></table></div></section>`;
}
function sliceTables(slices) {
  const names={clean:'未加扰动记录',perturbed:'人为重复记录扰动',observable:'运行充分子集'};
  const cards=Object.entries(names).map(([key,title])=>{const rows=asArray(slices?.[key]).filter(row=>Number(row.budget)===4);if(!rows.length)return '';return `<section class="card slice-card"><div class="panel-title"><h2>${title}</h2><span class="count-badge">${fmt(rows[0].n,0)}</span></div><div class="table-overflow"><table><thead><tr><th>策略</th><th>正确</th><th>错误</th><th>未决</th><th>平均查询</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${escapeHTML(strategyNames[row.strategy]||row.strategy)}</td><td>${fmt(row.correct,0)}</td><td>${fmt(row.wrong,0)}</td><td class="count-unresolved">${fmt(row.unresolved,0)}</td><td>${fmt(row.avg_queries,3)}</td></tr>`).join('')}</tbody></table></div></section>`;}).join('');
  return cards?`<div class="slice-heading"><h2>预算 4 · 补充分组</h2><p>运行充分子集只作补充；主分析仍包含全部未决记录。扰动与原始记录成对，不是独立建筑。</p></div><div class="slice-grid">${cards}</div>`:'';
}
function renderBenchmark(data) {
  const metrics=asArray(data.metrics);const protocol=data.protocol||{};
  if(!metrics.length){$('#benchmark-content').innerHTML=`<div class="card empty-state"><span class="empty-glyph">▥</span><h3>${escapeHTML(data.status==='running'?'评测仍在进行':'尚无已完成的对照结果')}</h3><p>${escapeHTML(data.message||data.notes?.join?.('；')||'完成冻结案例评测后，实际结果将显示在此。')}</p></div>`;return;}
  const primary=metrics.filter(row=>Number(row.budget)===4);const secondary=metrics.filter(row=>Number(row.budget)!==4);const model=primary.find(row=>row.strategy==='local_model');const sampleCount=primary[0]?.n??metrics[0]?.n;
  const decision=typeof data.decision==='object'?(data.decision.recommendation||data.decision.summary||'请审阅本地评测结论'):data.decision;
  const protocolText=typeof protocol==='string'?protocol:protocol.description||protocol.summary||'预算 4 为预设主分析；预算 2、3 为次要分析。所有策略使用相同允许证据池。';
  $('#benchmark-content').innerHTML=`<div class="benchmark-info"><div class="card"><span>冻结评测</span><strong>${escapeHTML(translate(data.status||'已完成'))}</strong><small>主比较：预算 4 · 四种策略</small></div><div class="card"><span>主分析记录数</span><strong>${fmt(sampleCount,0)}</strong><small>包含全部未决记录，不排除拒答</small></div><div class="card"><span>本地模型 · 整体正确率</span><strong>${pct(model?.accuracy)} <em>${fmt(model?.correct,0)} / ${fmt(model?.n,0)}</em></strong><small>错误 ${fmt(model?.wrong,0)} · 未决 ${fmt(model?.unresolved,0)}</small></div></div>${decision?`<div class="card decision-card ${data.decision_gate_passed===false?'negative':''}"><span class="decision-icon">↗</span><div><h2>继续或收缩建议</h2><p>${escapeHTML(decision)}</p></div></div>`:''}<div class="metric-definition"><strong>整体正确率 = 正确数 ÷ 全部记录数，未决仍计入分母。</strong><span>已决错判率仅描述已给出判断的记录；零错判不能代替正确率和覆盖率。</span></div>${metricsTable(primary,'预算 4 · 预设主分析','相同最大查询预算；未决单独列出')}<section class="card benchmark-chart-card"><h2>真实对照图</h2><p>默认展示主预算 4；预算 2、3 仅作为次要分析。所有数值读取实际评测结果。</p><div class="benchmark-controls"><label for="comparison-select">分析范围</label><select id="comparison-select"><option value="primary">预算 4 · 主分析</option><option value="all">全部预算 · 含次要分析</option></select><label for="metric-select">比较指标</label><select id="metric-select"><option value="accuracy">整体正确率（含未决）</option><option value="macro_f1">Macro F1</option><option value="coverage">结论覆盖率</option><option value="error_rate">已决错判率</option><option value="avg_queries">平均查询成本</option><option value="avg_latency_ms">平均耗时（毫秒）</option></select></div><div class="benchmark-chart" id="benchmark-chart"></div><div class="chart-color-key" id="benchmark-key"></div></section>${metricsTable(secondary,'预算 2、3 · 次要分析','不替代预设预算 4 主比较')}${sliceTables(data.slices)}<section class="card benchmark-notes"><h2>实验口径与结果边界</h2><ul><li>${escapeHTML(protocolText)}</li>${asArray(data.notes).map(note=>`<li>${escapeHTML(textValue(note))}</li>`).join('')}</ul></section>`;
  $('#metric-select').addEventListener('change',event=>renderBenchmarkChart(event.target.value));$('#comparison-select').addEventListener('change',()=>renderBenchmarkChart($('#metric-select').value));renderBenchmarkChart('accuracy');
}
function renderBenchmarkChart(metric) {
  const primaryOnly=$('#comparison-select')?.value!=='all';const rows=asArray(state.benchmark?.metrics).filter(row=>finite(row[metric])&&(!primaryOnly||Number(row.budget)===4));const target=$('#benchmark-chart');
  if(!rows.length){target.innerHTML='<div class="empty-state"><p>该指标暂无已完成结果</p></div>';$('#benchmark-key').innerHTML='';return;}
  const colors=['#278e7b','#8fa6b4','#9b8bbb','#c6a266','#71a4bb'];const groups=[...new Set(rows.map(row=>row.strategy))];const budgets=[...new Set(rows.map(row=>row.budget))].sort((a,b)=>Number(a)-Number(b));
  const W=1000,H=250,L=58,R=30,T=18,B=36;const ratio=['accuracy','macro_f1','coverage','error_rate'].includes(metric);const max=ratio?1:Math.max(...rows.map(row=>row[metric]))*1.12||1;const plotW=W-L-R,plotH=H-T-B;const x=budget=>L+(budgets.indexOf(budget)+.5)/budgets.length*plotW;const y=value=>T+(1-value/max)*plotH;
  let grid='';for(let i=0;i<5;i++){const value=max*i/4;grid+=`<line x1="${L}" y1="${y(value)}" x2="${W-R}" y2="${y(value)}" stroke="#eaf0f2" stroke-dasharray="4 5"/><text x="${L-12}" y="${y(value)+3}" text-anchor="end" fill="#9bafb9" font-size="10">${ratio?Math.round(value*100)+'%':escapeHTML(fmt(value,0))}</text>`;}
  const barWidth=Math.min(45,plotW/budgets.length/(groups.length+2));let bars='';groups.forEach((strategy,groupIndex)=>{const color=colors[groupIndex%colors.length];rows.filter(row=>row.strategy===strategy).forEach(row=>{const xpos=x(row.budget)+(groupIndex-(groups.length-1)/2)*barWidth;const top=y(row[metric]);bars+=`<rect x="${xpos-barWidth*.34}" y="${top}" width="${barWidth*.68}" height="${Math.max(1,H-B-top)}" rx="3" fill="${color}" opacity=".83"><title>${escapeHTML(strategyNames[strategy]||strategy)} · 预算 ${escapeHTML(row.budget)} · ${ratio?pct(row[metric]):fmt(row[metric])}</title></rect><text x="${xpos}" y="${top-7}" text-anchor="middle" fill="${color}" font-size="9">${ratio?(row[metric]*100).toFixed(0)+'%':fmt(row[metric],1)}</text>`;});});
  const ticks=budgets.map(budget=>`<text x="${x(budget)}" y="${H-10}" text-anchor="middle" fill="#9bafb9" font-size="10">${escapeHTML(budget==='full'?'完整信息':`预算 ${budget}`)}</text>`).join('');
  target.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="按预算比较策略实际${escapeHTML(metric)}结果">${grid}${bars}${ticks}</svg>`;
  $('#benchmark-key').innerHTML=groups.map((strategy,index)=>`<span><i style="background:${colors[index%colors.length]}"></i>${escapeHTML(strategyNames[strategy]||strategy)}</span>`).join('');
}
function navigate(page) {
  if(!['workbench','benchmark','protocol'].includes(page))page='workbench';$$('.page').forEach(el=>el.classList.toggle('active',el.id===`page-${page}`));$$('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.page===page));$('#breadcrumb-label').textContent={workbench:'核验工作台',benchmark:'对照实验',protocol:'证据与边界'}[page];if(page==='benchmark')loadBenchmark();
}
$$('.nav-item').forEach(button=>button.addEventListener('click',()=>{window.location.hash=button.dataset.page;}));window.addEventListener('hashchange',()=>navigate(location.hash.slice(1)));
$$('[data-filter]').forEach(button=>button.addEventListener('click',()=>{state.filter=button.dataset.filter;$$('[data-filter]').forEach(el=>el.classList.toggle('active',el===button));renderCases();}));
$$('.strategy-option').forEach(button=>button.addEventListener('click',()=>{if(isMeasured(state.current||{}))state.strategy='fixed';else{state.strategy=button.dataset.strategy;state.preferredStrategy=state.strategy;}if(state.strategy==='full_information'){state.budget=4;$('#budget-input').value=4;}refreshControls();}));
$('#budget-input').addEventListener('input',event=>{state.budget=Number(event.target.value);refreshControls();});
$('#series-select').addEventListener('change',event=>renderChart(event.target.value));$('#run-btn').addEventListener('click',runVerification);$('#repair-btn').addEventListener('click',repairCase);
$('#step-btn').addEventListener('click',()=>{if(state.run){state.shown=Math.min(state.shown+1,(state.run.steps||[]).length);renderRun();}});
$('#export-btn').addEventListener('click',()=>{if(state.run?.run_id){const anchor=document.createElement('a');anchor.href=`/api/export/${encodeURIComponent(state.run.run_id)}`;anchor.download=`${state.run.run_id}.json`;document.body.appendChild(anchor);anchor.click();anchor.remove();}});
$('#refresh-btn').addEventListener('click',()=>{loadCases();if($('#page-benchmark').classList.contains('active'))loadBenchmark();});$('#benchmark-refresh').addEventListener('click',loadBenchmark);
$('#case-library-toggle').addEventListener('click',()=>{state.includeDev=!state.includeDev;renderCases();});
navigate(location.hash.slice(1));loadCases();
