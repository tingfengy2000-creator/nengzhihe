import json, time, urllib.request, urllib.error
from pathlib import Path
base='http://127.0.0.1:18766'
task={'room':{'room_count':1,'units_per_room':2,'start_hour':8,'end_hour':18,'area_m2':35,'equipment_id':'midea_msagbu12_mox201'},'hybrid':{'budget_cny':30000,'allow_export':True,'pv_capacity_kwp':1}}
examples=[
 ('units','每间改成3台空调','room.units_per_room',3),
 ('model','型号换成midea_gaia12','room.equipment_id','midea_gaia12'),
 ('budget','预算改为50000元','hybrid.budget_cny',50000),
 ('period','使用时间改为18:00到22:00','room.start_hour',18),
 ('export','不卖电，余电全部弃用','hybrid.allow_export',False),
 ('pv','光伏容量改为2kWp','hybrid.pv_capacity_kwp',2),
]
def get(path):
 t=time.perf_counter();
 with urllib.request.urlopen(base+path,timeout=3) as x: body=json.loads(x.read().decode('utf-8'))
 return round((time.perf_counter()-t)*1000,2),body
def post(path,payload,timeout=20):
 t=time.perf_counter(); req=urllib.request.Request(base+path,data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json'},method='POST')
 try:
  with urllib.request.urlopen(req,timeout=timeout) as x: body=json.loads(x.read().decode('utf-8')); code=x.status
 except urllib.error.HTTPError as e:
  body=json.loads(e.read().decode('utf-8')); code=e.code
 return round((time.perf_counter()-t)*1000,2),code,body
out={"source_commit":"665f08346fd3c403858c318f65d923e83123cb97","endpoint":"loopback","status":None,"examples":[],"boundary":[]}
ms,body=get('/api/operation/agent/status'); out['status']={'outer_latency_ms':ms,'response':body}
for name,text,field,val in examples:
 ms,code,body=post('/api/operation/agent/parse',{'request':text,'current_task':task})
 fields={x.get('field'):x.get('to') for x in body.get('changes',[])}
 out['examples'].append({'id':name,'request':text,'http_status':code,'outer_latency_ms':ms,'response':body,'assertions':{'status_ok':body.get('status')=='ok','expected_field_value':fields.get(field)==val}})
ms,code,body=post('/api/operation/agent/parse',{'request':'请把储能每天按峰谷价自动套利并保证回本','current_task':task})
out['boundary'].append({'id':'unsupported','http_status':code,'outer_latency_ms':ms,'response':body,'assertions':{'unsupported_nonempty':bool(body.get('unsupported')),'no_changes':not body.get('changes')}})
ms,code,body=post('/api/operation/agent/parse',{'request':'把空调改成晚上使用','current_task':task})
out['boundary'].append({'id':'clarification','http_status':code,'outer_latency_ms':ms,'response':body,'assertions':{'needs_clarification':body.get('status')=='needs_clarification','question_nonempty':bool(body.get('question'))}})
ms,code,body=post('/api/operation/agent/parse',{'request':'','current_task':task})
out['boundary'].append({'id':'invalid','http_status':code,'outer_latency_ms':ms,'response':body,'assertions':{'http_400':code==400}})
# all contract assertions, excluding offline which is covered by deterministic unit patch
checks=[value for item in out['examples'] for value in item['assertions'].values()]+[value for item in out['boundary'] for value in item['assertions'].values()]
out['all_live_assertions_pass']=all(checks)
out['offline_test']='tests.test_agent_parse_contract uses patched config/model to verify fail-closed clarification; live status probe remains available'
out['measured_parse_latency_ms']=[x['response'].get('latency_ms') for x in out['examples']]
out['max_parse_latency_ms']=max(out['measured_parse_latency_ms'])
out['min_parse_latency_ms']=min(out['measured_parse_latency_ms'])
path=Path('operation_planning/results/phase2b_agent_round18'); path.mkdir(parents=True,exist_ok=True)
(path/'agent_parse_http_results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'all_live_assertions_pass':out['all_live_assertions_pass'],'status_outer_ms':ms,'parse_latencies_ms':out['measured_parse_latency_ms'],'path':str(path/'agent_parse_http_results.json')},ensure_ascii=False))
