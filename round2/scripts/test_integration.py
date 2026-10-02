"""Meaningful contracts on public demos/development only; no final values read."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from policies import run_case
import server
def main():
    checks=[]
    def check(name,x):
        assert x,name
        checks.append(name)
    c=server.get_case('NZH-76889C2BA896')
    full=run_case(c,'full_information',1,save=False)
    check('Full evidence budget1 still acquires every allowed group',len(full['steps'])==4)
    limited=run_case(c,'full_information',4,available_evidence=['operating_context','coil_response'],save=False)
    check('Missing air evidence cannot inherit known damper conclusion',limited['final']['label']=='unresolved')
    tiny=run_case(c,'fixed',1,save=False)
    check('Budget1 cannot inherit budget4 conclusion',tiny['final']['label']=='unresolved' and len(tiny['steps'])==1)
    repaired=run_case(c,'full_information',4,repair=True,save=False)
    check('Repair changes data quality but retains device concern',full['final']['quality']['duplicates']==12 and repaired['final']['quality']['duplicates']==0 and full['final']['label']==repaired['final']['label']=='damper_stuck')
    window=run_case(c,'full_information',4,start_time=c['timestamps'][0],end_time=c['timestamps'][5],save=False)
    check('Actual short window recomputed and cannot certify device',window['final']['label']=='unresolved' and window['final']['quality']['rows']==6)
    c2=copy.deepcopy(c);c2['label']='normal';c2['source_file']='normal.csv';c2['fault_setting']=0;c2['id']='neutral'
    neutral=run_case(c2,'full_information',4,save=False)
    check('Metadata has no numerical influence',neutral['final']==full['final'])
    n=run_case(server.get_case('NZH-90C933F3C475'),'full_information',4,save=False)
    check('Normal has two affirmative support statements',n['final']['label']=='normal' and len(n['final']['supporting_evidence'])>=2)
    b=run_case(server.get_case('NZH-CFF0E57369E1'),'full_information',4,save=False)
    check('BDG cannot become labelled device diagnosis',b['final']['label']=='building_review')
    check('No model calls in any run',all(x['cost']['model_calls']==0 for x in [full,limited,tiny,repaired,window,n,b]))
    check('Workbench exposes only demos and development',all('final' not in x.get('path','') for x in server.index()))
    p=ROOT/'output/integration_checks.json';p.write_text(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
