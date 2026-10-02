"""Frozen, resumable evaluation. Opens labels only after all predictions finish."""
import argparse,csv,datetime,hashlib,json,random,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import ROOT,operating_minutes
from policies import run_case
from freeze import sha

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+'.tmp')
    temp.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8'); temp.replace(p)
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def verify(freeze):
    for path,digest in freeze['files_sha256'].items():
        if sha(ROOT/path)!=digest: raise RuntimeError('Frozen file changed: '+path)

def metric(rows,strategy,budget):
    n=len(rows); correct=sum(r['prediction']==r['truth'] for r in rows)
    wrong=sum(r['prediction'] not in ('unresolved',r['truth']) for r in rows)
    answered=correct+wrong; f=[]
    for label in ['normal','damper_stuck','coil_leakage']:
        tp=sum(r['truth']==label and r['prediction']==label for r in rows)
        fp=sum(r['truth']!=label and r['prediction']==label for r in rows)
        fn=sum(r['truth']==label and r['prediction']!=label for r in rows)
        f.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
    calls=sum(r['model_calls'] for r in rows); invalid=sum(r['invalid_calls'] for r in rows)
    return {'strategy':strategy,'budget':budget,'n':n,'correct':correct,'wrong':wrong,'unresolved':n-answered,
       'accuracy':correct/n if n else None,'macro_f1':sum(f)/3,'coverage':answered/n if n else None,
       'error_rate':wrong/answered if answered else None,'avg_queries':statistics.mean(r['query_units'] for r in rows) if n else None,
       'avg_latency_ms':statistics.mean(r['latency_ms'] for r in rows) if n else None,'model_calls':calls,
       'invalid_model_response_rate':invalid/calls if calls else None,'field_acquisition_units':0}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output-dir',default='output/evaluation_v1'); args=parser.parse_args()
    folder=Path(args.output_dir); folder=folder if folder.is_absolute() else ROOT/folder
    frozen_path=ROOT/'output/protocol_frozen.json'
    freeze=read(frozen_path); verify(freeze)
    folder.mkdir(parents=True,exist_ok=True)
    receipt_path=folder/'execution_receipt.json'; freeze_hash=sha(frozen_path)
    if receipt_path.exists():
        receipt=read(receipt_path)
        if receipt['freeze_sha256']!=freeze_hash: raise RuntimeError('Resume freeze mismatch')
    else:
        receipt={'started_at_utc':utc(),'freeze_sha256':freeze_hash,'first_holdout_payload_read_after_freeze':True,'labels_opened_at_utc':None}
        write(receipt_path,receipt)
    seal=read(ROOT/'data/holdout_seal.json')
    # Public case IDs only; no label filenames are given to strategies.
    ids=sorted(seal['cases_sha256']); rng=random.Random(freeze['protocol']['seed']); rng.shuffle(ids)
    methods=[(s,b) for b in [2,3,4] for s in ['fixed','adaptive_rule','local_model']]+[('full_information',4)]
    total=len(ids)*len(methods); done=0
    for i,cid in enumerate(ids):
        path=ROOT/'data/private/holdout_cases'/(cid+'.json')
        if sha(path)!=seal['cases_sha256'][cid]: raise RuntimeError('Case seal mismatch: '+cid)
        case=read(path)
        scheduled=methods[i%len(methods):]+methods[:i%len(methods)]
        for strategy,budget in scheduled:
            out=folder/'predictions'/f'{cid}__{strategy}__b{budget}.json'
            if out.exists():
                saved=read(out)
                if saved.get('freeze_sha256')!=freeze_hash: raise RuntimeError('Prediction freeze mismatch')
            else:
                if receipt.get('labels_opened_at_utc'):
                    raise RuntimeError('Labels were already opened; missing predictions cannot be regenerated in the primary run. Use a new output directory explicitly labeled reproduction.')
                run=run_case(case,strategy,budget,save=False)
                run['freeze_sha256']=freeze_hash
                run['unique_operating_minutes']=operating_minutes(case)
                write(out,run)
            done+=1
        verify(freeze)
        write(folder/'progress.json',{'completed':done,'total':total,'at_utc':utc(),'labels_opened':bool(receipt.get('labels_opened_at_utc'))})
        print(f'predictions {done}/{total}',flush=True)
    verify(freeze)
    labelpath=ROOT/'data/private/holdout_labels.json'
    if sha(labelpath)!=seal['labels_sha256']: raise RuntimeError('Labels seal mismatch')
    receipt['predictions_completed_at_utc']=receipt.get('predictions_completed_at_utc') or utc()
    receipt['labels_opened_at_utc']=receipt.get('labels_opened_at_utc') or utc(); write(receipt_path,receipt)
    labels=read(labelpath); rows=[]
    for cid in ids:
        truth=labels[cid]
        for strategy,budget in methods:
            r=read(folder/'predictions'/f'{cid}__{strategy}__b{budget}.json')
            rows.append({'case_id':cid,'base_case_id':truth['base_case_id'],'day':truth['day'],'perturbation':truth['perturbation'],
                'strategy':strategy,'budget':budget,'truth':truth['label'],'prediction':r['final']['label'],
                'query_units':r['cost']['query_units'],'latency_ms':r['cost']['latency_ms'],'model_calls':r['cost']['model_calls'],
                'invalid_calls':sum(not c.get('response_valid') for c in r['model_calls']),
                'unique_operating_minutes':r['unique_operating_minutes'],'actions':[s['action'] for s in r['steps']],
                'status':r['status']})
    metrics=[metric([r for r in rows if (r['strategy'],r['budget'])==(s,b)],s,b) for s,b in methods]
    by={(m['strategy'],m['budget']):m for m in metrics}; llm=by['local_model',4]; rule=by['adaptive_rule',4]
    accuracy_gain=llm['correct']-rule['correct']; query_saved=rule['avg_queries']-llm['avg_queries']
    passes=(accuracy_gain>=2 and llm['wrong']<=rule['wrong'] and query_saved>=0) or (accuracy_gain>=0 and llm['wrong']<=rule['wrong'] and query_saved>=.25)
    decision=('主动补证达到预设探索门槛；只保留本单机组仿真范围的有限收益表述，继续核验外部有效性及延时。' if passes else
              '收缩大模型创新表述：本轮未达到相对自适应规则的预设增益门槛。保留核验工作台与证据留痕，将本地模型选择作为实验选项，不追加复杂架构。')
    slices={}
    for name,sub in [('clean',[r for r in rows if r['perturbation']=='none']),
                     ('perturbed',[r for r in rows if r['perturbation']!='none']),
                     ('observable',[r for r in rows if r['unique_operating_minutes']>=60])]:
        slices[name]=[metric([r for r in sub if (r['strategy'],r['budget'])==(s,b)],s,b) for s,b in methods]
    day_pairs=[]
    for day in sorted({r['day'] for r in rows}):
        a=[r for r in rows if r['day']==day and r['strategy']=='local_model' and r['budget']==4]
        b=[r for r in rows if r['day']==day and r['strategy']=='adaptive_rule' and r['budget']==4]
        day_pairs.append({'day':day,'n_paired':len(a),'llm_correct':sum(x['truth']==x['prediction'] for x in a),
                          'rule_correct':sum(x['truth']==x['prediction'] for x in b),
                          'mean_query_difference_llm_minus_rule':statistics.mean(x['query_units'] for x in a)-statistics.mean(x['query_units'] for x in b)})
    benchmark={'status':'completed','protocol':freeze['protocol'],'freeze_sha256':freeze_hash,'metrics':metrics,'decision':decision,
       'decision_gate_passed':passes,'primary_comparison':{'budget':4,'llm_minus_rule_correct':accuracy_gain,
          'rule_minus_llm_mean_queries':query_saved,'llm_minus_rule_latency_ms':llm['avg_latency_ms']-rule['avg_latency_ms']},
       'notes':['42条记录来自21个基础日工况及其重复记录扰动，共7个日期块、1套仿真机组；不能当作42栋楼。',
        '无真实故障楼宇或现场补采；查询单位是离线证据组记账，现场成本未知。',
        '主结果包括运行不足而拒答的记录；observable只是补充切片，不能替代主结果。',
        '完整信息耗费4单位，是信息充分参照，不保证准确率上界。',
        '四份不同标称泄漏严重度文件内容相同，只保留一份；不主张严重度泛化。',
        '模型调用使用本机GPU且串行；耗时受缓存和机器负载影响，未进行多次独立时延实验。'],
       'slices':slices,'paired_date_blocks':day_pairs,'completed_at_utc':utc(),'prediction_runs':len(rows)}
    verify(freeze); receipt['completed_at_utc']=utc();receipt['integrity_verified']=True;write(receipt_path,receipt)
    write(folder/'scored_rows.json',rows); write(ROOT/'output/benchmark.json',benchmark)
    with (folder/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(metrics[0]));writer.writeheader();writer.writerows(metrics)
    lines=['能智核首轮留出对照结果','冻结时间：'+freeze['frozen_at_utc'],'完成时间：'+benchmark['completed_at_utc'],'',decision,'',
        '策略 / 预算 / 正确 / 错误 / 未决 / 平均查询 / 平均毫秒']
    for m in metrics: lines.append(f"{m['strategy']} / {m['budget']} / {m['correct']} / {m['wrong']} / {m['unresolved']} / {m['avg_queries']:.3f} / {m['avg_latency_ms']:.2f}")
    lines+=['']+benchmark['notes'];(ROOT/'output/benchmark_report.txt').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'primary':benchmark['primary_comparison'],'decision':decision,'metrics':metrics},ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
