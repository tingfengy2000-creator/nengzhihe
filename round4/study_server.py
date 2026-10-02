"""Local supervised human-study runner. No participant/score fabrication."""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from datetime import datetime,timezone
from urllib.parse import urlparse
import argparse,json,secrets,time,hashlib,re,threading,mimetypes
from policies import run_case
import reporter
from followup import prioritize
ROOT=Path(__file__).resolve().parent;STUDY=ROOT/'study';LOCK=threading.RLock();SESSIONS={}
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()

def review_status():
 p=read(STUDY/'private/protocol.json');r=read(STUDY/'admin/independent_review.json')
 ids={x['id'] for x in read(STUDY/'private/task_manifest.json')['tasks']}
 problems=[]
 if r.get('status')!='approved':problems.append('参考答案和评分标准尚未独立复核')
 if not r.get('reviewer_code') or not r.get('reviewer_independent_of_implementation'):problems.append('缺独立复核者签署')
 if not r.get('reviewed_utc') or not r.get('notes'):problems.append('缺复核日期或意见')
 if set(r.get('reviewed_task_ids',[]))!=ids:problems.append('未逐项复核全部8个任务')
 for k in ['raw_signals_and_documentation','matching_and_difficulty','acceptable_conclusions_and_alternatives','rubric_and_failure_rules','no_system_output_as_truth']:
  if r.get('checks',{}).get(k) is not True:problems.append('复核项未通过：'+k)
 for f in p['reference_freeze']:
  if r.get('sha256',{}).get(f)!=sha(STUDY/f):problems.append('参考文件签署哈希不一致：'+f)
 if any(x.get('review_status')!='approved' for x in read(STUDY/'private/answer_key_draft.json')['tasks']):problems.append('逐题参考答案仍有未批准草案')
 return {'ready':not problems,'problems':problems,'real_participants':len(list((STUDY/'results/participants').glob('P*.json'))),
         'status':'ready_for_recruitment' if not problems else 'pending_independent_review_and_recruitment',
         'notice':'签署是团队负责的复核记录，软件不认证复核者身份或专家资格。'}

def save_session(s):
 if s['mode']=='demo':return
 p=STUDY/'results/participants';p.mkdir(parents=True,exist_ok=True)
 safe={k:v for k,v in s.items() if k not in ['token','current','monotonic_start']}
 (p/(s['participant_id']+'.json')).write_text(json.dumps(safe,ensure_ascii=False,indent=2),encoding='utf-8')

def begin_session(req):
 demo=req.get('demo') is True
 if not demo and not review_status()['ready']:raise ValueError('正式邀测未解锁：请先由独立复核者完成参考答案及评分标准签署。可先运行明确标记的软件演练。')
 if not demo and req.get('consent') is not True:raise ValueError('参与者尚未确认自愿参与。')
 if not demo:
  background=req.get('background',{})
  options={'role':{'建筑运维','能源服务','研究/学生','其他'},'hvac_experience_band':{'无','不足1年','1—3年','3年以上'},'csv_experience_band':{'很少','偶尔','经常'},'previous_workbench_exposure':{'未使用','仅培训','曾使用'}}
  if any(background.get(k) not in vs for k,vs in options.items()):raise ValueError('参与者背景字段不完整。')
 else:background={'record_type':'software_demonstration_not_participant'}
 token=secrets.token_hex(20);n=review_status()['real_participants'];seq='S'+str(n%4+1)
 assignment=read(STUDY/'private/protocol.json')['sequences'][seq]['tasks'] if not demo else [{'task_id':'DEMO','mode':req.get('condition','A') if req.get('condition') in ['A','B'] else 'A'}]
 session={'token':token,'mode':'demo' if demo else 'real','participant_id':'DEMO' if demo else f'P{n+1:03}',
  'sequence':seq if not demo else 'non_test_example','background':background,'assignment':assignment,'position':0,'answers':[],
  'started_utc':now(),'approved_key_sha256':sha(STUDY/'private/answer_key_draft.json') if not demo else None,'current':None,'break_until':None}
 SESSIONS[token]=session;save_session(session)
 return {'token':token,'participant_id':session['participant_id'],'sequence':session['sequence'],'total_tasks':len(assignment),'demo':demo}

def current_case(s):
 tid=s['assignment'][s['position']]['task_id']
 if tid=='DEMO':
  c=read(ROOT/'data/demos/NZH-76889C2BA896.json')
  c={k:v for k,v in c.items() if k in ['timestamps','series','units','sample_interval_minutes','family','perturbation']};c.update({'id':'DEMO','origin':'simulated','split':'demo','title':'培训示例（不属于正式8题）','description':'公开仿真加重复记录，软件演练不计参与者。'})
  return c
 return read(STUDY/'private/cases'/(tid+'.json'))

def task_view(s,resume=False):
 if s['position']>=len(s['assignment']):return {'complete':True,'demo':s['mode']=='demo'}
 if resume and s['current'] is None:return {'between_tasks':True}
 if s.get('break_until') and time.monotonic()<s['break_until']:
  return {'break_seconds':round(s['break_until']-time.monotonic()),'message':'两阶段间休息，不提供答案反馈。'}
 if s['current'] is None:
  s['current']=s['assignment'][s['position']].copy();s['monotonic_start']=time.monotonic();s['current']['started_utc']=now();s['current']['events']=[]
 c=current_case(s)
 # Generation metadata is for the host, never a hint in participant input.
 public={k:v for k,v in c.items() if k in ['id','title','description','family','timestamps','series','units','sample_interval_minutes','origin','split']}
 return {'case':public,'condition':s['current']['mode'],'number':s['position']+1,'total':len(s['assignment']),
         'remaining_seconds':max(0,300-(time.monotonic()-s['monotonic_start'])),'demo':s['mode']=='demo',
         'checklist':read(STUDY/'public/checklist.json'),'reference':read(ROOT/'data/calibration.json')['air_envelope']}

def submit(s,req):
 if not s.get('current'):raise ValueError('尚未开始任务或已提交。')
 elapsed=time.monotonic()-s['monotonic_start'];a=req.get('answer',{})
 fields=['quality','device','evidence','next_action']
 if any(not isinstance(a.get(k,''),str) or len(a.get(k,''))>6000 for k in fields):raise ValueError('答案格式或长度不符合要求。')
 row={**s['current'],'submitted_utc':now(),'elapsed_seconds':elapsed,'capped_seconds':min(elapsed,300),
      'timeout':elapsed>=300,'answer':{k:a.get(k,'') for k in fields},'not_submitted':bool(req.get('give_up')),
      'answer_complete':all(a.get(k,'').strip() for k in fields),'condition':s['current']['mode']}
 s['answers'].append(row);s['position']+=1;s['current']=None
 if s['position']==4 and s['mode']=='real':s['break_until']=time.monotonic()+180
 save_session(s)
 return {'accepted':True,'complete':s['position']>=len(s['assignment']),'demo':s['mode']=='demo','record_type':'software_demo' if s['mode']=='demo' else 'real_participant','no_answer_feedback':True}

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def send(self,data,status=200,mime='application/json; charset=utf-8'):
  b=json.dumps(data,ensure_ascii=False,allow_nan=False).encode() if mime.startswith('application/json') else data
  self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b)
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/api/health':return self.send({'status':'ok','local_only':True,'revision':'round4-study'})
  if path=='/api/status':return self.send(review_status())
  if path in ['/','/study.js','/study.css']:
   p=STUDY/'public'/('index.html' if path=='/' else path[1:]);return self.send(p.read_bytes(),mime=(mimetypes.guess_type(p.name)[0] or 'text/plain')+'; charset=utf-8')
  self.send({'error':'not found'},404)
 def do_POST(self):
  try:
   length=int(self.headers.get('Content-Length',0))
   if not 0<length<100000:raise ValueError('Invalid request length')
   req=json.loads(self.rfile.read(length));path=urlparse(self.path).path
   with LOCK:
    if path=='/api/enroll':return self.send(begin_session(req))
    token=req.get('token');s=SESSIONS.get(token)
    if not s:raise ValueError('未知会话；重新开始软件演练或联系主持人。')
    if path=='/api/task':return self.send(task_view(s,req.get('resume') is True))
    if path=='/api/submit':return self.send(submit(s,req))
    if path=='/api/event':
     if s.get('current'):s['current']['events'].append({'event':str(req.get('event',''))[:50],'elapsed_seconds':time.monotonic()-s['monotonic_start']})
     return self.send({'ok':True})
    if path=='/api/verify':
     if not s.get('current') or s['current']['mode']!='B':raise ValueError('常规曲线/表格条件不提供自动诊断。')
     if time.monotonic()-s['monotonic_start']>=300:raise ValueError('任务已超时，请提交当前答案。')
     c=current_case(s);r=prioritize(run_case(c,'full_information',4,repair=req.get('repair') is True,save=False))
     s['current']['events'].append({'event':'workbench_repair' if req.get('repair') else 'workbench_verify','elapsed_seconds':time.monotonic()-s['monotonic_start'],'run_id':r['run_id']})
     return self.send({'final':r['final'],'steps':r['steps'],'card_html':reporter.card(r),'run_id':r['run_id']})
   return self.send({'error':'not found'},404)
  except (ValueError,KeyError,TypeError) as e:self.send({'error':str(e)},400)
  except Exception as e:self.send({'error':type(e).__name__+': '+str(e)},500)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=18196);a=p.parse_args()
 print(f'Local supervised study: http://127.0.0.1:{a.port}; status={review_status()["status"]}',flush=True)
 ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
