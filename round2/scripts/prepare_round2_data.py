"""Prepare predeclared date blocks without exposing final values to development."""
import argparse,datetime,hashlib,json,sys,zipfile
from pathlib import Path
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; OLD=ROOT.parent
sys.path.insert(0,str(OLD/'scripts'))
import prepare_data as v1

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def days(blocks): return [d.strftime('%Y-%m-%d') for start,end in blocks for d in pd.date_range(start,end)]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--split',choices=['dev','final'],required=True);args=parser.parse_args()
    if (ROOT/'output/frozen.json').exists():raise SystemExit('Already frozen; refusing data preparation')
    plan=json.loads((ROOT/'data/split_plan.json').read_text(encoding='utf-8'))
    chosen=days(plan['development_blocks' if args.split=='dev' else 'final_blocks'])
    if set(days(plan['development_blocks']))&set(days(plan['final_blocks'])):raise ValueError('Date overlap')
    out=ROOT/'data'/args.split;index=[];labels={}
    # Whole source streams are parsed by the preparation program only; no out-of-split values emitted.
    for filename in plan['sources']:
        frame=v1.lbnl_frame(filename)
        for day in chosen:
            for polluted in (False,True):
                obj,lab=v1.lbnl_case(frame,filename,day,args.split,polluted)
                oldid=obj['id']; newid='NZH2-'+hashlib.sha256(('round2|'+oldid).encode()).hexdigest()[:12].upper()
                obj['id']=newid;lab['id']=newid
                lab['base_case_id']='NZH2-'+hashlib.sha256(('round2|'+lab['base_case_id']).encode()).hexdigest()[:12].upper()
                obj['attribution']+=' Round2: same preprocessing, distinct date-block split.'
                obj['split']=args.split
                path=out/'cases'/(newid+'.json');write(path,obj);labels[newid]=lab
                index.append({'id':newid,'split':args.split,'family':'lbnl','origin':'simulated','path':path.relative_to(ROOT).as_posix(),
                              'title':'新日期开发案例' if args.split=='dev' else '封存评测案例','perturbation':obj['perturbation']})
        del frame
    write(out/'index.json',index);write(out/'labels.json',labels)
    seal={'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'split_plan_sha256':sha(ROOT/'data/split_plan.json'),
          'case_count':len(index),'base_day_scenarios':len(plan['sources'])*len(chosen),'date_blocks':len(chosen),'simulated_systems':1,
          'case_sha256':{x['id']:sha(ROOT/x['path']) for x in index},'labels_sha256':sha(out/'labels.json'),
          'old_used_days_excluded':True,'note':'Paired records are dependent; counts include both clean and artificial duplicates.'}
    write(ROOT/'data'/(args.split+'_seal.json'),seal)
    print(json.dumps({'split':args.split,'cases':len(index),'base_scenarios':seal['base_day_scenarios'],'date_blocks':len(chosen),'values_not_printed':True}))
if __name__=='__main__':main()
