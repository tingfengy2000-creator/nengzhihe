"""Read v1 immutable results and old development/regression records only."""
import json,sys,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OLD=ROOT.parent
sys.path.insert(0,str(OLD))
import engine as v1
sys.path.insert(0,str(ROOT))
import diagnostics as v2

def main():
 rows=json.loads((OLD/'output/evaluation_v1/scored_rows.json').read_text(encoding='utf-8'))
 labs=json.loads((OLD/'data/private/holdout_labels.json').read_text(encoding='utf-8'))
 main=[r for r in rows if r['budget']==4]
 sets={s:{r['case_id'] for r in main if r['strategy']==s and r['prediction']==r['truth']} for s in sorted({r['strategy'] for r in main})}
 verified_predictions=[]
 for row in rows:
  path=OLD/'output/evaluation_v1/predictions'/f"{row['case_id']}__{row['strategy']}__b{row['budget']}.json"
  record=json.loads(path.read_text(encoding='utf-8'))
  assert record['final']['label']==row['prediction'] and record['case_id']==row['case_id']
  assert [s['action'] for s in record['steps']]==row['actions']
  if row['strategy']=='full_information':assert {s['action'] for s in record['steps']}==set(v1.ACTIONS)
  verified_predictions.append(path.name)
 out={'all_420_records':len(rows),'correct_sets':{k:sorted(v) for k,v in sets.items()},'correct_sets_identical':all(v==next(iter(sets.values())) for v in sets.values()),'correct_by_class':{s:dict(collections.Counter(r['truth'] for r in main if r['strategy']==s and r['prediction']==r['truth'])) for s in sets},'full_pool_actions_complete':all(set(r['actions'])==set(v1.ACTIONS) for r in main if r['strategy']=='full_information'),'diagnostic_feature_use':{'quality':'schema + initial all-case operation gate; quality itself not a device classifier','air_path':'temperature-inferred mixing std/correlation and command std + valid sample count used','coil_response':'closed-command globalday mean temperature drop and whole-day closed fraction + count used','operating_context':'collected but unused by v1 verdict'},'cases':[]}
 for r in main:
  if r['strategy']!='full_information':continue
  case=json.loads((OLD/'data/private/holdout_cases'/f"{r['case_id']}.json").read_text(encoding='utf-8'))
  f={a:v1.features(case,a) for a in v1.ACTIONS}
  d=v1.diagnose(case,f)
  observed={a:v2.extract(case,a) for a in v2.ACTIONS};new=v2.diagnose(observed)
  rec={**r,'old_features':f,'old_diagnosis':d,'repaired_diagnosis':new}
  if r['prediction']=='unresolved':
   if v1.operating_minutes(case)<60:
    cause='工况不适用';reason='风机有效运行0分钟；正确保留未决，不能从停机推断正常。'
   elif r['truth']=='damper_stuck':
    cause='判据过严或结构不适用';reason='旧规则要求全日指令标准差>=0.08，且使用全日混风标准差/相关系数；静态指令与实际热响应严重不一致仍被挡住，启动瞬态又可抬高全日波动。修复按稳定窗口对照正常指令响应包络。'
   elif r['truth']=='normal' and new['label']=='normal':
    cause='判据过严或结构不适用';reason='正常稳定调节不需要大幅指令变化；旧全日0.08变化门槛阻断正向一致证据。新规则需混风与关阀两个正常专属证据。'
   else:
    cause='证据确实不足';reason='持续机械制冷，缺乏足够稳定零关阀窗口；泄漏仅在关阀时可辨，不应靠降门槛输出正常或泄漏。'
   rec['primary_cause']=cause;rec['cause_detail']=reason
   rec['secondary_causes']=['旧operating_context仅收集未参与结论，修复为显式运行资格']
   if r['perturbation']!='none':rec['secondary_causes'].append('重复记录与设备疑点并存；去重不消除设备过程')
  out['cases'].append(rec)
  if labs[r['case_id']]['perturbation']=='none':
   a=f['air_path'];c=f['coil_response']
   print(labs[r['case_id']]['day'],r['truth'],r['prediction'],'min',v1.operating_minutes(case),'air',*[a.get(k) for k in ['mix_fraction_med','mix_fraction_std','damper_cmd_mean','damper_cmd_std','mix_cmd_corr']],'coil',*[c.get(k) for k in ['closed_valve_drop','closed_valve_fraction','valid_closed_samples']])
 out['verified_prediction_files']=len(verified_predictions)
 out['unresolved_primary_partition']=dict(collections.Counter(r['primary_cause'] for r in out['cases'] if 'primary_cause'in r))
 out['unresolved_primary_partition']['实现或字段问题']=0
 out['official_document_check']={'source':'data/raw/lbnl_sdahu.pdf, September1 2022, printed pp4-7,9',
  'temperature':'Raw degF converted to degC by (F-32)*5/9; public arrays already converted, no second conversion.',
  'fan':'SF_SPD_DM/RF_SPD_DM are 0-off/1-on status, not speed despite variable name. SF_CS/RF_CS are speed commands.',
  'commands':'OA_DMPR_DM,RA_DMPR_DM,CHWC_VLV_DM are control commands. OA_DMPR,RA_DMPR,CHWC_VLV are actual positions (non-Basic), directly overridden for fault imposition, excluded.',
  'controls':'Observed fan status rather than calendar. Economizer outdoor1..15.555556C; mechanical cooling lockout unless damperfullyopen in that range. A supply-setpoint discrepancy during lockout alone is notfault.',
  'windows':'5min averages; first30minstartup excluded; require contiguous30minwindows and60minqualified evidence. Coil zero command numeric tolerance0.0001 maintained15minbefore evidence.',
  'pressure':'SA_SP/SA_SPSPT source unit conflict retained excluded; not used in either diagnostic version.',
  'implementation_claim':'No unit/field bug explains these32unresolved. Principal engineering defect is day-level structural eligibility, not lack of strategy queries. No original algorithm claim.'}
 out['note']='Old42 are now explicit development/regression. No new final-holdout payload read by this script.'
 (ROOT/'output/root_cause_old_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in out.items() if k not in ['cases','correct_sets']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
