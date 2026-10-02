"""Choose a competent fixed control using development data only, once."""
import itertools,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from policies import run_case
def main():
    if (ROOT/'output/frozen.json').exists():raise RuntimeError('Policy selection is closed after freeze')
    labels=json.loads((ROOT/'data/dev/labels.json').read_text(encoding='utf-8'))
    cases=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT/'data/dev/cases').glob('*.json'))]
    rows=[]
    for order in itertools.permutations(['operating_context','air_path','coil_response']):
        runs=[run_case(c,'fixed',4,save=False,order_override=order) for c in cases]
        correct=sum(r['final']['label']==labels[c['id']]['label'] for c,r in zip(cases,runs))
        wrong=sum(r['final']['label'] not in {'unresolved',labels[c['id']]['label']} for c,r in zip(cases,runs))
        rows.append({'order':list(order),'correct':correct,'wrong':wrong,'queries':sum(r['cost']['query_units'] for r in runs),'n':len(runs)})
    best=min(rows,key=lambda r:(r['wrong'],-r['correct'],r['queries'],tuple(r['order'])))
    cfg={'fixed_order':best['order'],'selection':'One finite enumeration of six fixed orders on development only: fewer wrong, more correct, fewer queries, lexicographic tie-break.',
         'adaptive_rule':'quality then operating_context; if economizer_lockout >=60min query coil first, otherwise air first; stop on supported, inactive or invalid evidence; no learned model.',
         'development_selection':rows,'chosen':best,'query_cost':1,'field_cost':'Not measured: no physical acquisition performed.'}
    (ROOT/'data/policy_config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(cfg,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
