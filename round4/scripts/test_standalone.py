"""Start an isolated copy and exercise HTTP intake/run/export, no parent data access."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,time,urllib.request,urllib.error,re,socket
ROOT=Path(__file__).resolve().parents[1]
def main():
 with socket.socket() as probe:probe.bind(('127.0.0.1',18197))
 dest=ROOT/'output'/('standalone_'+str(time.time_ns()));dest.mkdir()
 for name in ['followup.py','diagnostics.py','quality.py','policies.py','importer.py','reporter.py','server.py','requirements.txt']:shutil.copy2(ROOT/name,dest/name)
 for name in ['baseline_v1','web']:shutil.copytree(ROOT/name,dest/name,ignore=shutil.ignore_patterns('__pycache__'))
 (dest/'data').mkdir();(dest/'output').mkdir()
 shutil.copytree(ROOT/'output/comparison',dest/'output/comparison')
 for name in ['demos','public_csv','history']:shutil.copytree(ROOT/'data'/name,dest/'data'/name)
 for name in ['calibration.json','demo_index.json','policy_config.json']:shutil.copy2(ROOT/'data'/name,dest/'data'/name)
 proc=subprocess.Popen([sys.executable,'-X','utf8',str(dest/'server.py'),'--port','18197'],cwd=dest,stdout=(dest/'output/server.log').open('w'),stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 base='http://127.0.0.1:18197';checks=[]
 def call(path,payload=None):
  request=urllib.request.Request(base+path,data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(request,timeout=15) as r:
   b=r.read().decode();return json.loads(b) if 'json' in r.headers.get('Content-Type','') else b
 def check(label,value):assert value,label;checks.append(label)
 try:
  for _ in range(50):
   if proc.poll() is not None:raise RuntimeError('Isolated process exited; inspect server.log')
   try:health=call('/api/health');break
   except urllib.error.URLError:time.sleep(.1)
  else:raise RuntimeError('Isolated server did not start')
  check('Isolated local server ready',health['revision']=='round4')
  check('Historical comparison available in standalone copy',bool(call('/api/benchmark')))
  cases=call('/api/cases')['cases'];check('Three independent local demos present',len(cases)==3)
  for c in cases:
   r=call('/api/run',{'case_id':c['id'],'strategy':'full_information','budget':4})
   check('Demo runs '+c['id'],bool(r['final']['quality']))
   if r['final'].get('label')=='damper_stuck':
    check('Follow-up advice consistent in UI and card '+c['id'],r['final']['next_actions']==r['final']['operation']['next_actions'] and r['final']['next_actions'][0]['action']=='damper_field_check')
  raw=call('/api/sample-csv');preview=call('/api/import/preview',{'text':raw['text']})
  req={'text':raw['text'],'mapping':preview['default_mapping'],'time_column':'Datetime','units':{k:'degF' if 'TEMP' in k else 'binary' if k.endswith('_SPD_DM') else 'fraction' for k in preview['fields']},'source_interval':1,'profile':'lbnl_sdahu_public_2022'}
  try:call('/api/import/commit',req|{'source_interval':5});blocked=False
  except urllib.error.HTTPError as e:blocked=e.code==400
  check('HTTP refuses false raw cadence',blocked)
  v=call('/api/import/commit',req);check('HTTP original CSV maps to 288 records',len(v['case']['timestamps'])==288)
  r=call('/api/run',{'case_id':v['case']['id'],'strategy':'full_information','budget':1})
  check('Full information includes all four evidence groups even budget1',len(r['steps'])==4)
  html=call('/api/card/'+r['run_id']);q=json.loads(re.search(r'<script id="canonical-quality" type="application/json">(.*?)</script>',html,re.S).group(1))
  check('HTTP view, evidence, decision and HTML share quality',v['view']['quality']==r['final']['quality']==r['steps'][0]['quality']==q)
  check('HTML card includes source mapping and hash',v['case']['import_provenance']['source_sha256'] in html and 'source_units' in html)
  prior=r['run_id'];r=call('/api/run',{'case_id':v['case']['id'],'strategy':'full_information','budget':4,'available_evidence':['operating_context','coil_response']})
  check('Changed evidence truly recomputes into an unresolved result',r['run_id']!=prior and r['final']['label']=='unresolved')
  out={'passed':len(checks),'checks':checks,'isolated_root':str(dest),'parent_data_used':False,'http_port':18197,'source_script_sha256':hashlib.sha256((ROOT/'server.py').read_bytes()).hexdigest()}
  (ROOT/'output/standalone_tests.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2))
 finally:
  proc.terminate();proc.wait(timeout=10)
if __name__=='__main__':main()
