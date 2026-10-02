'use strict';
const importState={text:null,preview:null,name:''};
function renderBranches(branches){
 const entries=Object.entries(branches);
 $('#branch-status').innerHTML=entries.length?entries.map(([k,b])=>`<article class="branch-row"><div><strong>${esc(translate(k))}</strong><span class="badge ${b.state==='supported'?'warning':b.state==='testable'?'measured':''}">${esc(b.label)}</span><small>${fmt(b.qualified_minutes,0)} 分钟合格窗口</small></div><p>${esc(b.reason)}</p><details><summary>具体点位与补证条件</summary><p>${esc(b.required_condition)}</p>${Object.keys(b.eligibility_stages||{}).length?`<p>计时链：风机开启 ${fmt(b.eligibility_stages.fan_on_minutes,0)} → 启动后 ${fmt(b.eligibility_stages.post_startup_minutes,0)} → 零关阀 ${fmt(b.eligibility_stages.zero_command_during_stable_minutes,0)} → 稳定且测点有效 ${fmt(b.eligibility_stages.settled_closed_with_valid_sensors_minutes,0)} → 开发参考覆盖 ${fmt(b.eligibility_stages.calibrated_closed_minutes,0)} → 连续窗口 ${fmt(b.eligibility_stages.contiguous_qualified_minutes,0)} 分钟。</p>`:''}</details></article>`).join(''):'<p class="muted">实测表计回放不进入设备分支诊断。</p>';
}
function renderImportReceipt(c){const p=c?.import_provenance;$('#import-receipt').classList.toggle('hidden',!p);if(p)$('#import-receipt').textContent=`导入记录：${p.input_rows} → ${p.output_rows} 行；${p.source_interval_minutes} → ${p.target_interval_minutes} 分钟。显式单位转换，完整采样桶聚合，无插值。源文件 SHA256 ${p.source_sha256.slice(0,16)}…；完整映射见核查卡。`;}
function historicalBreakdown(d){const a=d.regression_analysis;if(!a)return '';const labels={'AHU_annual.csv':'正常','damper_stuck_025_annual.csv':'风阀来源设置025','damper_stuck_075_annual.csv':'风阀来源设置075','coi_leakage_025_annual.csv':'盘管阀泄漏'};return `<div class="card historical"><h2>第二轮历史结果 · 当前只作回归</h2><p>全部 ${a.records} 条盘管合格核验窗口均为0分钟；108条稳定关阀证据为0分钟，4条仅5分钟。当前工况不能完成该分支检验，不能靠改变查询顺序补出数据。</p><table><thead><tr><th>来源工况设置</th><th>基础日工况</th><th>正确</th></tr></thead><tbody>${Object.entries(a.source_groups).map(([k,v])=>`<tr><td>${esc(labels[k]||k)}</td><td>${v.base_cases}</td><td>${v.correct}</td></tr>`).join('')}</tbody></table><p>原旧→新完整信息：新增20条、失去2条原正确、净增18条；不是每例都改善。025有9个基础日落在正常风路参考内，因此“未发现偏离”不能解释为“排除卡滞”。本轮可靠性修复后原112条结论变化 ${a.round3_vs_round2_label_changes.length} 条。</p></div>`;}
async function stageCSV(text,name){
 importState.text=text;importState.name=name;$('#import-status').textContent='正在检查CSV结构…';
 try{const p=await api('/api/import/preview',{text});importState.preview=p;$('#mapping-area').classList.remove('hidden');$('#confirm-profile').checked=false;
 $('#import-status').textContent=`${name} · ${p.row_count} 行、${p.columns.length} 列。请核对以下字段、单位和原始时间间隔。`;
 $('#source-time').innerHTML=p.columns.map(k=>`<option ${k===p.time_column?'selected':''} value="${esc(k)}">${esc(k)}</option>`).join('');
 $('#mapping-body').innerHTML=p.fields.map(k=>{const units=k.includes('TEMP')?['degF','degC']:k.endsWith('_SPD_DM')?['binary']:['fraction','percent'];return `<tr data-target="${k}"><td><strong>${k}</strong></td><td><select class="map-column" aria-label="${k}源列"><option value="">缺少此点位</option>${p.columns.map(c=>`<option value="${esc(c)}" ${c===p.default_mapping[k]?'selected':''}>${esc(c)}</option>`).join('')}</select></td><td><select class="map-unit" aria-label="${k}单位">${units.map(u=>`<option value="${u}">${({'degF':'°F → °C','degC':'°C','fraction':'0—1 指令','percent':'百分数 → 0—1','binary':'启停状态 0/1'})[u]}</option>`).join('')}</select></td></tr>`;}).join('');
 $('#ignored-columns').textContent=`默认忽略 ${p.ignored_by_default.length} 个非输入字段；实际阀位、故障设置不用于判断。`;
 }catch(e){$('#mapping-area').classList.add('hidden');$('#import-status').textContent=e.message;toast(e.message);}
}
$('#open-import').addEventListener('click',()=>{$('#import-panel').classList.remove('hidden');$('#import-panel').scrollIntoView({behavior:'smooth',block:'start'});});
$('#close-import').addEventListener('click',()=>$('#import-panel').classList.add('hidden'));
$('#load-public-csv').addEventListener('click',async()=>{try{const s=await api('/api/sample-csv');await stageCSV(s.text,s.name);}catch(e){toast(e.message);}});
$('#csv-file').addEventListener('change',async e=>{const f=e.target.files[0];if(!f)return;if(f.size>8*1024*1024)return toast('文件超过8 MiB；只支持单日CSV片段');try{await stageCSV(new TextDecoder('utf-8',{fatal:true}).decode(await f.arrayBuffer()),f.name);}catch(err){toast('请提供UTF-8编码CSV：'+err.message);}});
$('#commit-import').addEventListener('click',async()=>{
 if(state.busy)return toast('请等待当前核验完成');if(!$('#confirm-profile').checked)return toast('请先确认当前公开仿真配置的适用范围');
 const mapping={},units={};$$('#mapping-body tr').forEach(row=>{mapping[row.dataset.target]=$('.map-column',row).value;units[row.dataset.target]=$('.map-unit',row).value;});
 $('#commit-import').disabled=true;
 try{const result=await api('/api/import/commit',{text:importState.text,mapping,units,time_column:$('#source-time').value,source_interval:Number($('#source-cadence').value),profile:'lbnl_sdahu_public_2022'});
 state.strategy='full_information';state.available=['air_path','coil_response','operating_context'];state.budget=4;state.baseline=null;state.revision++;
 applyCase(result);$('#import-panel').classList.add('hidden');await run();$('#import-receipt').scrollIntoView({behavior:'smooth',block:'start'});toast('导入与核验完成，可导出本次核查卡。');
 }catch(e){$('#import-status').textContent='导入已拒绝：'+e.message;toast(e.message);}finally{$('#commit-import').disabled=false;}
});
$('#export-card').addEventListener('click',async()=>{if(!state.run)return;try{const response=await fetch('/api/card/'+state.run.run_id);if(!response.ok)throw new Error('核查卡生成失败');const blob=await response.blob(),a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=`能智核_核查卡_${state.run.run_id}.html`;a.click();URL.revokeObjectURL(url);toast('已导出可离线阅读、浏览器打印的核查卡。');}catch(e){toast(e.message);}});
