"""Standalone printable HTML verification card, generated from the actual run."""
import html,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def card(run):
    esc=lambda x:html.escape(str(x))
    d=run['final'];q=d['quality'];branches=d.get('branches',{});prov=run.get('import_provenance') or {}
    quality_style={'passed':'background:#e7f2ed;color:#203b39','needs_review':'background:#fff1d6;color:#75521b','invalid':'background:#fde9e7;color:#922d27'}[q['status']]
    issues=''.join('<li>'+esc(i.get('detail',i))+'</li>' for i in q['issues']) or '<li>当前记录检查通过；不代表设备正常。</li>'
    branchrows=''.join('<tr><td>'+esc({'air_path':'风路','coil_response':'盘管','operating_context':'运行工况'}.get(a,a))+'</td><td>'+esc(x['label'])+'</td><td>'+esc(x['reason'])+'</td><td>'+esc(x['qualified_minutes'])+'</td><td>'+esc(x['required_condition'])+'</td></tr>' for a,x in branches.items())
    supporting=''.join('<li>'+esc(x if isinstance(x,str) else x.get('label','')+': '+str(x.get('value','')))+'</li>' for x in d.get('supporting_evidence',[])) or '<li>本次没有单独支持项。</li>'
    limits=''.join('<li>'+esc(x)+'</li>' for x in d.get('refuting_evidence',[])) or '<li>缺少反向证据不代表排除其他原因。</li>'
    actions=''.join('<li>'+esc(x.get('text',x))+'</li>' for x in d.get('next_actions',[])) or '<li>保留记录，在其他运行工况持续观察；不据此宣布普遍无故障。</li>'
    steps=''.join('<tr><td>'+str(s['index'])+'</td><td>'+esc(s['label'])+'</td><td>'+esc(s['reason'])+'</td></tr>' for s in run['steps'])
    quality_json=json.dumps(q,ensure_ascii=False,indent=2).replace('<','\\u003c')
    text=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>能智核 核查卡 {esc(run['run_id'])}</title>
<style>body{{font:15px/1.65 "Microsoft YaHei",sans-serif;color:#203b39;max-width:1000px;margin:38px auto;padding:0 25px}}h1{{font-size:28px}}h2{{font-size:20px;margin-top:28px}}.badge{{padding:4px 10px;background:#e7f2ed;border-radius:5px}}.dim{{color:#526763}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #bbcfc8;padding:9px;text-align:left}}th{{background:#e7f2ed}}pre{{font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere}}@media print{{body{{margin:0;padding:0}}h2{{break-after:avoid}}tr{{break-inside:avoid}}.screen{{display:none}}}}</style>
<h1>能智核 公共建筑风阀疑点核验卡</h1><p class="dim">运行编号 {esc(run['run_id'])} · 数据 {esc(run['case_id'])} · {esc(run['origin'])} · 仅本次可用证据</p>
<div class="two"><section><h2>数据质量</h2><strong class="badge" style="{quality_style}">{esc(q['label'])}</strong><p>{q['rows']}条记录，重复{q['duplicates']}条，缺失{q['missing']}项；有效运行{q['unique_operating_minutes']}分钟。</p><ul>{issues}</ul></section>
<section><h2>设备判断</h2><strong class="badge">{esc(d['name'])}</strong><p>{esc(d['detail'])}</p><p class="dim">数据修正不等于设备正常；未检出偏离不等于排除故障。</p></section></div>
<h2>各分支当前能否检验</h2><table style="table-layout:fixed"><colgroup><col style="width:8%"><col style="width:11%"><col style="width:29%"><col style="width:8%"><col style="width:44%"></colgroup><tr><th>分支</th><th>状态</th><th>依据</th><th>分钟</th><th>补证条件</th></tr>{branchrows}</table>
<div class="two"><section><h2>已有支持证据</h2><ul>{supporting}</ul></section><section><h2>证据限制与缺口</h2><ul>{limits}</ul></section></div>
<h2>下一步核查动作</h2><ol>{actions}</ol><h2>实际核查过程</h2><table><tr><th>序号</th><th>证据组</th><th>选择理由</th></tr>{steps}</table>
<p>离线查询 {run['cost']['query_units']} 单位；现场补采未实施，费用/人工节省未测。本次程序计算耗时{run['cost']['latency_ms']:.3f}毫秒，不是人工运维提效证据。</p>
<h2>输入转换与适用范围</h2><p>仅支持当前LBNL公开单风道机组仿真配置及已校准输入范围；BDG2只作独立实测用能回放。故障候选需独立核实，不推算实际节能收益。</p><pre>{esc(json.dumps(prov,ensure_ascii=False,indent=2))}</pre>
<details><summary>查看与服务、诊断账本一致的质量对象</summary><pre>{esc(json.dumps(q,ensure_ascii=False,indent=2))}</pre></details>
<script id="canonical-quality" type="application/json">{quality_json}</script></html>'''
    p=ROOT/'output/cards';p.mkdir(exist_ok=True);(p/(run['run_id']+'.html')).write_text(text,encoding='utf-8')
    return text
