"""Historical regression and branch failure analysis; never a new held-out score."""
from pathlib import Path
import collections,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from policies import run_case
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
 labels=read(ROOT/'data/regression/labels.json');old=read(ROOT/'data/history/scored_rows_round2.json')
 oldfull={x['case_id']:x for x in old if x['method']=='new_full'};rows=[];groups={};stages=collections.Counter();changed=[]
 for cid,l in labels.items():
  c=read(ROOT/'data/regression/cases'/(cid+'.json'));r=run_case(c,'full_information',4,save=False)
  coil=next(s['features'] for s in r['steps'] if s['action']=='coil_response')
  air=next(s['features'] for s in r['steps'] if s['action']=='air_path')
  if r['final']['label']!=oldfull[cid]['prediction']:changed.append(cid)
  row={'case_id':cid,'day':l['day'],'base_case_id':l['base_case_id'],'source_setting':l['source_file'],'truth':l['label'],
    'perturbation':l['perturbation'],'prediction':r['final']['label'],'branches':r['final']['branches'],
    'coil_stages':coil['eligibility_stages'],'stable_closed_minutes':coil['stable_closed_minutes'],'coil_qualified_minutes':coil['qualified_minutes'],
    'air_state':air['mix_state'],'quality':r['final']['quality']}
  rows.append(row);stages[str(coil['stable_closed_minutes'])]+=1
  if l['perturbation']=='none':
   g=groups.setdefault(l['source_file'],{'base_cases':0,'correct':0,'air_compatible':0})
   g['base_cases']+=1;g['correct']+=int(r['final']['label']==l['label']);g['air_compatible']+=int(air['mix_state']=='compatible')
 old_correct={x['case_id'] for x in old if x['method']=='old_full' and x['prediction']==x['truth']}
 new_correct={x['case_id'] for x in old if x['method']=='new_full' and x['prediction']==x['truth']}
 reasons=collections.Counter()
 for row in rows:
  s=row['coil_stages']
  reason=('无稳定运行工况' if s['post_startup_minutes']==0 else '稳定运行中无零关阀指令' if s['zero_command_during_stable_minutes']==0 else '零关阀片段未通过15分钟等待及传感器联合条件' if s['settled_closed_with_valid_sensors_minutes']==0 else '等待后仅5分钟，无法形成30分钟窗口')
  row['coil_first_blocker']=reason;reasons[reason]+=1
 out={'status':'historical_regression_only','records':len(rows),'base_cases':56,'dates':14,'new_performance_claim':False,
   'coil_first_blocker_counts':dict(reasons),
   'round3_vs_round2_label_changes':changed,'source_groups':groups,'coil_qualified_zero_records':sum(x['coil_qualified_minutes']==0 for x in rows),
   'stable_closed_minutes_distribution':dict(stages),'historical_overlap':{'shared':len(old_correct&new_correct),'added':len(new_correct-old_correct),'lost':len(old_correct-new_correct)},
   'explanation':'108条在风机稳定、零关阀持续等待、有效风机指令和温度的联合条件下0分钟；4条仅5分钟，均不成连续30分钟窗口。不是查询预算问题，也不是通过改序可解决。',
   'scope':'One simulated system. Source settings 025/075 are retained as file-group provenance, never diagnostic input. All 112 now development/regression.',
   'rows':rows}
 (ROOT/'output/regression/analysis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 summary={k:v for k,v in out.items() if k!='rows'}
 (ROOT/'output/regression/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
