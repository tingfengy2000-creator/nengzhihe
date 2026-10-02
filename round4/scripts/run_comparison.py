from pathlib import Path
from collections import defaultdict
import json,hashlib,sys,time,csv
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(Path(__file__).parent))
from comparators import predict

def main():
 protocol=json.loads((ROOT/'output/comparison_frozen.json').read_text(encoding='utf-8'))
 for f,h in protocol['sha256'].items():assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h,f
 dest=ROOT/'output/comparison';dest.mkdir(exist_ok=True)
 if (dest/'summary.json').exists():raise RuntimeError('Use a new output directory for a rerun, preserve original results.')
 labels=json.loads((ROOT/'data/regression/labels.json').read_text(encoding='utf-8'));rows=[]
 for cid,label in sorted(labels.items(),key=lambda v:(v[1]['day'],v[1]['source_file'],v[1]['perturbation'])):
  for method in protocol['methods']:
   start=time.perf_counter();case=json.loads((ROOT/'data/regression/cases'/(cid+'.json')).read_text(encoding='utf-8'))
   r=predict(case,method);elapsed=(time.perf_counter()-start)*1000
   rows.append({'case_id':cid,**label,'method':method,**r,'elapsed_ms':elapsed})
 bases=[x for x in rows if x['perturbation']=='none'];summaries=[];date_rows=[]
 def aggregate(items):
  support=[x for x in items if x['prediction']=='damper_suspicion'];right=[x for x in support if x['label']=='damper_stuck']
  return {'n':len(items),'supported':len(support),'source_consistent':len(right),'wrong_attributions':len(support)-len(right),'unresolved':len(items)-len(support),'support_coverage':len(support)/len(items),'source_consistent_over_all':len(right)/len(items),'mean_software_ms':sum(x['elapsed_ms'] for x in items)/len(items)}
 for method in protocol['methods']:
  items=[x for x in bases if x['method']==method]
  result={'method':method,**aggregate(items),'groups':{g:aggregate([x for x in items if x['source_file']==g]) for g in sorted({x['source_file'] for x in items})}}
  pairs=defaultdict(list)
  for x in rows:
   if x['method']==method:pairs[x['base_case_id']].append(x)
  result['paired_robustness']={'base_pairs':len(pairs),'records':sum(len(v) for v in pairs.values()),'prediction_changes':sum(len({x['prediction'] for x in v})>1 for v in pairs.values())}
  summaries.append(result)
  for date in sorted({x['day'] for x in items}):date_rows.append({'method':method,'date':date,**aggregate([x for x in items if x['day']==date])})
 summary={'status':'historical_regression_only','base_cases':56,'dates':14,'contiguous_date_blocks':2,'simulated_systems':1,'paired_records':112,'methods':summaries,'new_holdout_evaluation':False,'human_participants':0,'value_study_status':'pending_independent_review_and_recruitment','risk_coverage_curve':False}
 for name,data in [('summary',summary),('rows',rows),('by_date',date_rows)]:
  (dest/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 with (dest/'base_case_results.csv').open('w',newline='',encoding='utf-8-sig') as f:
  fields=['method','day','base_case_id','source_file','label','prediction','elapsed_ms'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(bases)
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
