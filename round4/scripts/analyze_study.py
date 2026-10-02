"""Analyze actual human records plus independently completed manual scores only."""
from pathlib import Path
import json,csv,hashlib,statistics
ROOT=Path(__file__).resolve().parents[1];S=ROOT/'study'
def main():
 people=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((S/'results/participants').glob('P*.json'))]
 people=[p for p in people if p.get('mode')=='real']
 output={'status':'pending_independent_review_and_recruitment','real_participants':len(people),'time_saving_claim':None,'participants':[]}
 scores=S/'results/manual_scores.csv'
 if people and scores.exists():
  rows=list(csv.DictReader(scores.open(encoding='utf-8-sig')));lookup={}
  for r in rows:
   key=(r['participant_id'],r['task_id'])
   if key in lookup:raise ValueError('Duplicate scoring row: '+str(key))
   if not r.get('rater_code') or not r.get('rationale'):raise ValueError('Scoring requires rater and rationale')
   lookup[key]=r
  fields=['E1_time_and_units','E2_quality_and_repair','E3_operating_window','E4_command_vs_response','E5_inspectability','E6_next_evidence']
  for p in people:
   answers={r['task_id']:r for r in p['answers']};task_rows=[]
   for task in p['assignment']:
    a=answers.get(task['task_id']);score=lookup.get((p['participant_id'],task['task_id']))
    if a and a.get('answer_complete'):
     if not score:raise ValueError('Missing manual score; no outcome claim can be computed yet.')
     if score['approved_key_sha256']!=p['approved_key_sha256']:raise ValueError('Reference-key hash mismatch')
     values=[int(score[f]) for f in fields]
     if any(v not in [0,1] for v in values) or int(score['wrong_attribution']) not in [0,1]:raise ValueError('Invalid score')
     omissions=6-sum(values);wrong=int(score['wrong_attribution'])
    else:omissions=6;wrong=int(score['wrong_attribution']) if score else 0
    missing=not a or not a.get('answer_complete') or a.get('not_submitted',False)
    timeout=not a or a.get('timeout',False)
    task_rows.append({**task,'seconds':300 if not a else min(a['elapsed_seconds'],300),'omissions':omissions,'wrong_attribution':wrong,'timeout':timeout,'missing':missing,'failure':bool(timeout or missing or wrong)})
   by={}
   for mode in ['A','B']:
    xs=[x for x in task_rows if x['mode']==mode]
    by[mode]={'assigned':4,'mean_capped_seconds':sum(x['seconds'] for x in xs)/4,'mean_omissions':sum(x['omissions'] for x in xs)/4,
              'wrong_attributions':sum(x['wrong_attribution'] for x in xs),'timeouts':sum(x['timeout'] for x in xs),'failures':sum(x['failure'] for x in xs)}
   output['participants'].append({'participant_id':p['participant_id'],'sequence':p['sequence'],'background':p['background'],'conditions':by,'tasks':task_rows,'paired_time_difference_B_minus_A':by['B']['mean_capped_seconds']-by['A']['mean_capped_seconds']})
  output['status']='descriptive_exploratory_results';output['median_paired_time_difference_B_minus_A']=statistics.median(p['paired_time_difference_B_minus_A'] for p in output['participants'])
  output['interpretation']='Read time alongside omissions, wrong attributions and failures. No causal generalization, unqualified efficiency percentage or simulated users.'
 elif people:output['status']='pending_independent_manual_scoring'
 (S/'results/status.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(output,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
