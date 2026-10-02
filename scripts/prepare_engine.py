"""Build development references and select a competent fixed order, dev only."""
import itertools
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import ROOT,calibrate,features,diagnose,quality
from policies import run_case,should_stop

def main():
    idx=json.loads((ROOT/'data/index.json').read_text(encoding='utf-8'))
    cases=[json.loads((ROOT/'data/cases'/(x['id']+'.json')).read_text(encoding='utf-8')) for x in idx if x['split']=='dev' and x['family']=='lbnl']
    labels=json.loads((ROOT/'data/private/dev_labels.json').read_text(encoding='utf-8'))
    calibration=calibrate(cases,labels)
    candidates=[]
    for order in itertools.permutations(['air_path','coil_response','operating_context']):
        correct=wrong=0
        for case in cases:
            day=case['timestamps'][0][:10]
            local=calibrate([c for c in cases if c['timestamps'][0][:10]!=day],labels,write=False)
            for budget in (2,3):
                obs={'quality':features(case,'quality')}
                d=diagnose(case,obs,local)
                for a in order[:budget-1]:
                    if d.get('status')=='inactive' or should_stop(d,obs): break
                    obs[a]=features(case,a)
                    d=diagnose(case,obs,local)
                correct+=d['label']==labels[case['id']]['label']
                wrong+=d['label'] not in ('unresolved',labels[case['id']]['label'])
        candidates.append({'order':list(order),'correct':correct,'wrong':wrong,'score':correct-wrong})
    candidates.sort(key=lambda r:(-r['score'],-r['correct'],r['wrong'],r['order']))
    config={'fixed_order':candidates[0]['order'],'selection':'Development-only leave-day-out threshold calibration, selecting order at budgets 2 and 3. These are tuning counts, not validation performance.',
            'candidate_counts':candidates,'mandatory_first_action':'quality','same_initial_screening_for_all':True}
    (ROOT/'data/policy_config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    results=[]
    for row in idx:
        if row['family']!='lbnl' or row['split'] not in ('dev','demo'):
            continue
        case=json.loads((ROOT/'data/cases'/(row['id']+'.json')).read_text(encoding='utf-8'))
        result=run_case(case,'full_information',4,save=False)
        results.append({'id':case['id'],'split':case['split'],'quality':quality(case),'diagnosis':result['final'],'cost':result['cost']})
    (ROOT/'output').mkdir(exist_ok=True)
    (ROOT/'output/development_check.json').write_text(json.dumps({'note':'Development and demonstration checks only, not held-out performance.','results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'references':len(calibration['references']),'fixed_order':config['fixed_order'],
         'checks':[{'id':r['id'],'split':r['split'],'label':r['diagnosis']['label'],'score':r['diagnosis'].get('support_score')} for r in results]},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
