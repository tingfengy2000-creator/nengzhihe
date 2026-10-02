from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'web/app.js';s=p.read_text(encoding='utf-8')
s=s.replace("strategy:'adaptive_rule'","strategy:'full_information'",1)
s=s.replace("function caseTitle(c){return measured(c)?", "function caseTitle(c){return c?.split==='import'?'公开CSV · 导入核验':measured(c)?")
a=s.index('function qualityView(');b=s.index('\nfunction readable(',a)
s=s[:a]+'''function qualityView(q){
 $('#quality-status').textContent=q?.label||translate(q?.status)||'待检查';
 $('#quality-dot').className=q?.status==='passed'?'good':'warning';
 const issues=list(q?.issues).map(readable).filter(Boolean).join('；');
 const repair=state.current?.repair?`已移除 ${fmt(state.current.repair.removed??state.current.repair.removed_rows,0)} 条完全重复记录；`:'';
 $('#quality-detail').textContent=repair+`${fmt(q?.rows,0)} 条记录 · 重复 ${fmt(q?.duplicates,0)} 条 · 缺失 ${fmt(q?.missing,0)} 项。`+(issues||q?.note||'数据质量与设备判断独立。');
}
''' +s[b:]
s=s.replace("function clearComputed(reason='设置已改变，正在重新计算'){", "function clearComputed(reason='设置已改变，正在重新计算'){$('#export-card').disabled=true;$('#branch-status').textContent='等待当前条件下的分支适用性检查。';")
s=s.replace("function renderRun(result){const final=result.final||{};", "function renderRun(result){const final=result.final||{};renderBranches(final.branches||{});$('#export-card').disabled=!result.run_id;")
s=s.replace("function applyCase(result){state.current=result.case||result;", "function applyCase(result){state.current=result.case||result;renderImportReceipt(state.current);")
s=s.replace('${benchmarkSummary(d)}<div class="metric-cards">','${historicalBreakdown(d)}${benchmarkSummary(d)}<div class="metric-cards">')
p.write_text(s,encoding='utf-8')
html=ROOT/'web/index.html';t=html.read_text(encoding='utf-8')
t=t.replace('先比较诊断可用性，再比较核查成本。所有指标读取已完成的真实评测。','下列是第二轮原始对照，112条现仅用于回归与失败分析；本轮不新增性能主张。')
t=t.replace('本轮不增加复杂 Agent，也不优化本地模型。','数据质量、分支适用性和设备疑点独立呈现；公开CSV可以追溯到字段映射与实际核查卡。')
html.write_text(t,encoding='utf-8')
