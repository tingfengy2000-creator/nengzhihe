"""Freeze-once APAR comparison: development calibration then one physical holdout run."""
from pathlib import Path
import sys,json,time,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from adapter import physical
from apar import calibrate,evaluate

def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')

def main():
    dev=physical('development')
    normals=[c for c in dev if c['id'] in {'5138876d3912','b5a5b08a1984'}]
    cal=calibrate(normals)
    cal['source']='NISTIR6994 APAR Table2.1 adapted to FLEXLAB SZVAV points and control sequence'
    cal['calibration_rule']='normal development dates only; one deterministic pass; no fault labels/input settings'
    source=ROOT/'data/raw/SZVAV.csv';split=ROOT/'protocol/external_split.json'
    cal['sha256']={'data/raw/SZVAV.csv':hashlib.sha256(source.read_bytes()).hexdigest(),
                   'protocol/external_split.json':hashlib.sha256(split.read_bytes()).hexdigest(),
                   'src/apar.py':hashlib.sha256((ROOT/'src/apar.py').read_bytes()).hexdigest(),
                   'src/adapter.py':hashlib.sha256((ROOT/'src/adapter.py').read_bytes()).hexdigest()}
    cal['frozen_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    write(ROOT/'protocol/frozen_methods.json',cal)
    hold=physical('holdout',allow_heldout=True)
    allcases=dev+hold
    out=[]
    for c in allcases:
        out.append(evaluate(c,cal,'apar'))
        out.append(evaluate(c,cal,'apar_plus_verification'))
        out.append(evaluate(c,cal,'without_consistency'))
    write(ROOT/'results/apar_physical_case_results.json',out)
    summary={'source':'FLEXLAB SZVAV physical test-cell experiments; one AHU, 11 days',
             'development_ids':[c['id'] for c in dev],'holdout_ids':[c['id'] for c in hold],
             'freeze':{'path':'round5/protocol/frozen_methods.json','sha256':hashlib.sha256((ROOT/'protocol/frozen_methods.json').read_bytes()).hexdigest()},
             'records':len(out),'methods':['apar','apar_plus_verification','without_consistency'],'ground_truth_input_excluded':True}
    for method in summary['methods']:
        rr=[r for r in out if r['method']==method]
        for group,ids in [('development',summary['development_ids']),('holdout',summary['holdout_ids']),('all',summary['development_ids']+summary['holdout_ids'])]:
            q=[r for r in rr if r['id'] in ids]
            summary.setdefault(method,{})[group]={'cases':len(q),'detection':sum(r['any_fault_detected'] for r in q),'damper_suspicion':sum(r['damper_related_suspicion'] for r in q),'states':{s:sum(r['judgment_state']==s for r in q) for s in sorted({x['judgment_state'] for x in q})},'avg_applicable_minutes':float(np.mean([r['apar_applicable_minutes'] for r in q])) if q else 0.}
    write(ROOT/'results/apar_physical_summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
