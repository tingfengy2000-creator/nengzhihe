"""One frozen new-date evaluation; original 42 cases are never test cases here."""
import argparse,collections,csv,datetime,hashlib,json,random,statistics,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from baseline_v1 import engine as legacy
from policies import run_case
CLASSES=['normal','damper_stuck','coil_leakage']
METHODS=['old_full','new_full','fixed','adaptive_rule']
NAMES={'old_full':'首轮诊断器·完整信息','new_full':'修复诊断器·完整信息','fixed':'修复诊断器·固定流程','adaptive_rule':'修复诊断器·自适应规则'}
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');q.replace(p)
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def verify(frozen):
    for path,h in frozen['files_sha256'].items():
        if sha(ROOT/path)!=h:raise RuntimeError('Frozen file changed: '+path)
def old_full(case):
    observed={a:legacy.features(case,a) for a in legacy.ACTIONS}
    d=legacy.diagnose(case,observed)
    return {'final':d,'steps':[{'action':a,'features':observed[a]} for a in legacy.ACTIONS],
            'cost':{'query_units':len(legacy.ACTIONS),'field_acquisition_units':0,'model_calls':0}}
def measure(path,method):
    start=time.perf_counter();case=read(path)
    if method=='old_full':r=old_full(case)
    else:r=run_case(case,'full_information' if method=='new_full' else method,4,save=False)
    # Timing includes input read/parse, preparation, queries, inference, and output JSON encoding.
    json.dumps(r,ensure_ascii=False,allow_nan=False)
    end=time.perf_counter();r['cost']['end_to_end_ms']=(end-start)*1000
    r['method']=method;r['input_file_sha256']=sha(path)
    return r
def metric(rows,method):
    n=len(rows);answered=[r for r in rows if r['prediction'] in CLASSES]
    correct=sum(r['prediction']==r['truth'] for r in rows);wrong=sum(r['prediction']!=r['truth'] for r in answered)
    recall={};f1={};matrix={}
    for label in CLASSES:
        target=[r for r in rows if r['truth']==label];tp=sum(r['prediction']==label for r in target)
        fp=sum(r['prediction']==label and r['truth']!=label for r in rows);fn=len(target)-tp
        recall[label]=tp/len(target) if target else None
        f1[label]=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0
        matrix[label]=dict(collections.Counter(r['prediction'] for r in target))
    return {'method':method,'label':NAMES[method],'budget':4,'n':n,'correct':correct,'wrong':wrong,'unresolved':n-len(answered),
      'accuracy':correct/n if n else None,'recall':recall,'coverage':len(answered)/n if n else None,'error_rate':wrong/len(answered) if answered else None,
      'macro_f1':statistics.mean(f1.values()),'avg_queries':statistics.mean(r['query_units'] for r in rows) if rows else None,
      'avg_latency_ms':statistics.mean(r['end_to_end_ms'] for r in rows) if rows else None,'p95_latency_ms':sorted(r['end_to_end_ms'] for r in rows)[max(0,int(.95*n)-1)] if rows else None,
      'field_acquisition_units':0,'confusion':matrix}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',default='output/evaluation_final');p.add_argument('--reproduction',action='store_true');args=p.parse_args()
    frozen=read(ROOT/'output/frozen.json');verify(frozen);frozen_hash=sha(ROOT/'output/frozen.json')
    folder=ROOT/args.output_dir
    if not folder.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Output must stay in round2')
    receiptpath=folder/'receipt.json'
    if receiptpath.exists():
        receipt=read(receiptpath)
        if receipt['freeze_sha256']!=frozen_hash:raise RuntimeError('Resume mismatch')
    else:
        if (ROOT/'output/benchmark.json').exists() and not args.reproduction:raise RuntimeError('Final results already viewed: new runs must be marked reproduction')
        receipt={'started_at_utc':utc(),'freeze_sha256':frozen_hash,'labels_opened_at_utc':None,'reproduction':args.reproduction};write(receiptpath,receipt)
    seal=read(ROOT/'data/final_seal.json');ids=sorted(seal['case_sha256']);random.Random(20261001).shuffle(ids)
    for i,cid in enumerate(ids):
        path=ROOT/'data/final/cases'/(cid+'.json')
        if sha(path)!=seal['case_sha256'][cid]:raise RuntimeError('Case seal changed')
        order=METHODS[i%4:]+METHODS[:i%4]
        for method in order:
            dest=folder/'predictions'/f'{cid}__{method}.json'
            if dest.exists():
                if read(dest)['freeze_sha256']!=frozen_hash:raise RuntimeError('Prediction version mismatch')
            else:
                if receipt['labels_opened_at_utc']:raise RuntimeError('Cannot add predictions after labels opened')
                r=measure(path,method);r['freeze_sha256']=frozen_hash;write(dest,r)
        if i%14==13:print(f'Completed {i+1}/{len(ids)} cases ({4*(i+1)} runs)',flush=True)
    verify(frozen)
    receipt['predictions_completed_at_utc']=receipt.get('predictions_completed_at_utc') or utc();write(receiptpath,receipt)
    labelpath=ROOT/'data/final/labels.json'
    if sha(labelpath)!=seal['labels_sha256']:raise RuntimeError('Label seal changed')
    receipt['labels_opened_at_utc']=receipt.get('labels_opened_at_utc') or utc();write(receiptpath,receipt)
    labels=read(labelpath);rows=[]
    for cid in ids:
        lab=labels[cid]
        for method in METHODS:
            r=read(folder/'predictions'/f'{cid}__{method}.json');prediction=r['final']['label']
            if prediction not in CLASSES:prediction='unresolved'
            rows.append({'case_id':cid,'base_case_id':lab['base_case_id'],'day':lab['day'],'perturbation':lab['perturbation'],'truth':lab['label'],
              'method':method,'prediction':prediction,'raw_status':r['final'].get('status'),'query_units':r['cost']['query_units'],
              'end_to_end_ms':r['cost']['end_to_end_ms'],'actions':[s['action'] for s in r['steps']]})
    metrics={method:metric([r for r in rows if r['method']==method],method) for method in METHODS}
    old,new=metrics['old_full'],metrics['new_full'];fixed,adaptive=metrics['fixed'],metrics['adaptive_rule']
    error_cap=max(old['error_rate'] or 0,.02)
    diagnosis_gain=new['coverage']>=old['coverage']+.05 and new['error_rate'] is not None and new['error_rate']<=error_cap and new['wrong']/new['n']<=old['wrong']/old['n']+.02
    policy_gain=adaptive['correct']>=fixed['correct'] and adaptive['wrong']<=fixed['wrong'] and adaptive['coverage']>=fixed['coverage'] and adaptive['avg_queries']<fixed['avg_queries']-.05
    decision=('新诊断器在本次时间留出中提高结论覆盖，且错误率满足预先定义的相近范围；可表述为工况与证据窗口工程修复的收益。' if diagnosis_gain else
              '新诊断器未达到预设覆盖和错误率改善条件；保留已核验的实现修复，收缩普遍性能收益主张。')
    decision+=('自适应规则在相近判断质量下减少了离线查询单位。' if policy_gain else '未证实自适应规则相对固定流程的查询收益；不追加新方法。')
    slices={}
    for variant in ['none','duplicate_records_12']:
        slices[variant]=[metric([r for r in rows if r['perturbation']==variant and r['method']==m],m) for m in METHODS]
    perday=[]
    for day in sorted({r['day'] for r in rows}):
        perday.append({'day':day,'metrics':[metric([r for r in rows if r['day']==day and r['method']==m],m) for m in METHODS]})
    result={'status':'completed','freeze_sha256':frozen_hash,'diagnosis_comparison':[old,new],'policy_comparison':[fixed,adaptive,new],
      'scope':{'records':len(ids),'base_scenarios':len({r['base_case_id'] for r in rows}),'dates':len({r['day'] for r in rows}),'contiguous_blocks':2,'systems':1,'origin':'simulated','validation':'new-date temporal holdout only'},
      'decision':decision,'diagnosis_gain':diagnosis_gain,'policy_gain':policy_gain,'slices':slices,'per_day':perday,'completed_at_utc':utc(),
      'notes':['未决与异常未定位均计入整体分母，不能算三分类正确。','同一仿真系统新日期验证，不是跨设备或真实建筑故障验证。',
        '没有使用实际阀位、故障文件名、真实标签或注入设置做诊断；温度推算混风响应不是阀位反馈。',
        '完整信息参照读取全部4组允许证据，独立于常规预算循环；固定与自适应主预算均为4。',
        '查询成本为离线证据组记账；没有现场补采，未测量现场成本或人工工时节省。',
        '端到端耗时为本机输入文件读取解析至结果JSON编码，包含预处理、查询和诊断；单轮顺序轮换测量，不含网络传输、日志落盘或前端绘制。',
        '本轮未调用或优化大模型；旧42条已用于开发回归，不作为验证成绩。']}
    verify(frozen);write(folder/'scored_rows.json',rows);write(folder/'benchmark_first_run.json',result)
    if not args.reproduction:write(ROOT/'output/benchmark.json',result)
    receipt['completed_at_utc']=utc();receipt['frozen_files_unchanged']=True;write(receiptpath,receipt)
    with (folder/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        selected=['method','n','correct','wrong','unresolved','accuracy','coverage','error_rate','macro_f1','avg_queries','avg_latency_ms']
        w=csv.DictWriter(f,fieldnames=selected);w.writeheader();w.writerows({k:m[k] for k in selected} for m in metrics.values())
    print(json.dumps({k:v for k,v in result.items() if k not in ['slices','per_day']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
