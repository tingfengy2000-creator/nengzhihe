"""Software contracts only: no synthetic human participants or benefit results."""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import study_server as s
from quality import inspect_case

def main():
 checks=[]
 def check(name,v):assert v,name;checks.append(name)
 def rejected(name,fn):
  try:fn();ok=False
  except ValueError:ok=True
  check(name,ok)
 check('Independent review remains pending',not s.review_status()['ready'])
 rejected('Real study locked before independent reference review',lambda:s.begin_session({'demo':False,'consent':True}))
 manifest=s.read(s.STUDY/'private/task_manifest.json');protocol=s.read(s.STUDY/'private/protocol.json')
 ids={x['id'] for x in manifest['tasks']}
 check('Eight matched but distinct task inputs',len(ids)==8 and len({x['sha256'] for x in manifest['tasks']})==8)
 for name,seq in protocol['sequences'].items():
  a=seq['tasks'];check(name+' unique tasks, four per condition',len({t['task_id'] for t in a})==8 and sum(t['mode']=='A' for t in a)==4)
 check('Each matched task sees both conditions across sequences',all({t['mode'] for seq in protocol['sequences'].values() for t in seq['tasks'] if t['task_id']==tid}=={'A','B'} for tid in ids))
 for t in manifest['tasks']:
  c=s.read(s.STUDY/t['path']);q=inspect_case(c)
  check(t['id']+' valid time/units and no labels in participant case',q['time_valid'] and not q['unit_errors'] and not any(k in c for k in ['label','source_file','severity','source_declared_severity']))
 demo=s.begin_session({'demo':True,'condition':'A'});session=s.SESSIONS[demo['token']];v=s.task_view(session);started=session['monotonic_start'];s.task_view(session)
 check('Refreshing task does not reset server timer',session['monotonic_start']==started)
 check('Training source is distinct from formal task dates',v['case']['timestamps'][0][:10] not in manifest['dates'])
 session['monotonic_start']-=301
 result=s.submit(session,{'answer':{'quality':'software check','device':'software check','evidence':'software check','next_action':'software check'}})
 check('Late submission is capped and explicitly marked timeout',session['answers'][0]['timeout'] and session['answers'][0]['capped_seconds']==300)
 check('Software exercise is never a real participant',result['record_type']=='software_demo' and s.review_status()['real_participants']==0)
 rejected('Duplicate submission cannot create another task response',lambda:s.submit(session,{}))
 r={'status':'passed','checks':checks,'count':len(checks),'real_participants_created':0,'scope':'Software tests, not simulated user-value evaluation.'}
 (ROOT/'output/study_software_checks.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
