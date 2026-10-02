"""Mode/window-qualified numerical verification for one simulated SDAHU.

Engineering repair, not a new original classifier. Only documented Basic sensor
and command channels are read. diagnose receives revealed evidence, never a case.
"""
from __future__ import annotations
import copy, hashlib, json, math
from pathlib import Path
import numpy as np
from quality import inspect_case,BRANCH_POINTS

ROOT=Path(__file__).resolve().parent
ACTIONS=['quality','air_path','coil_response','operating_context']
ACTION_LABELS={'quality':'先核查数据记录','air_path':'核查混风指令与热响应','coil_response':'核查稳定关阀时段','operating_context':'核实启停与控制工况'}
LABEL_NAMES={'normal':'已核验工况正常','damper_stuck':'风阀卡滞候选','coil_leakage':'盘管阀泄漏候选','unresolved':'待补证','building_review':'真实用能变化待核查'}
ALLOWED={'SA_TEMP','SA_TEMPSPT','OA_TEMP','MA_TEMP','RA_TEMP','SF_SPD_DM','RF_SPD_DM','SF_CS','RF_CS','OA_DMPR_DM','RA_DMPR_DM','CHWC_VLV_DM',*[f'ZONE_TEMP_{i}' for i in range(1,6)]}
TEMPS={'SA_TEMP','SA_TEMPSPT','OA_TEMP','MA_TEMP','RA_TEMP',*[f'ZONE_TEMP_{i}' for i in range(1,6)]}
CONFIG_FILE=ROOT/'data/calibration.json'
# Fixed engineering eligibility, declared before final time-block evaluation.
GATES={'warmup_minutes':30,'closed_settle_minutes':15,'window_minutes':30,'minimum_qualified_minutes':60,
       'mix_delta_min_C':3.0,'minimum_mix_fraction_margin':0.03,'normal_thermal_margin_C':0.15,
       'normal_window_fraction_min':0.90,'fault_window_fraction_min':0.80,'command_bin_width':0.05,
       'fan_command_bin_width':0.10,'economizer_min_C':1.0,'economizer_max_C':15.555556,
       'coil_closed_command_max':0.0001,'cooling_on_command_min':0.05}

def num(x):
 try:
  f=float(x); return round(f,6) if math.isfinite(f) else None
 except (TypeError,ValueError):return None
def stat(v,kind='median'):
 a=np.asarray(v,dtype=float);a=a[np.isfinite(a)]
 if not len(a):return None
 return num({'median':np.median,'mean':np.mean,'min':np.min,'max':np.max,'std':np.std}[kind](a))
def load_calibration():
 return json.loads(CONFIG_FILE.read_text(encoding='utf-8')) if CONFIG_FILE.exists() else None

def prepare(case):
 """Whitelisted numerical view; metadata/labels/file names never enter features."""
 quality=inspect_case(case)
 ts=case.get('timestamps',[]);series=case.get('series',{})
 if case.get('family')=='lbnl' and set(series)-ALLOWED:
  raise ValueError('未许可点位: '+','.join(sorted(set(series)-ALLOWED)))
 if any(len(v)!=len(ts) for v in series.values()):raise ValueError('通道长度与时间戳不符')
 groups={}
 for i,t in enumerate(ts):groups.setdefault(t,[]).append(i)
 keys=sorted(series);keep=[];conflicts=[]
 for t,inds in sorted(groups.items()):
  signatures={tuple(series[k][i] for k in keys) for i in inds}
  if len(signatures)>1:conflicts.append(t)
  else:keep.append(inds[0])
 unique_ts=[ts[i] for i in keep]
 try:sec=np.array([np.datetime64(t,'s').astype(np.int64) for t in unique_ts])
 except (ValueError,TypeError):sec=np.arange(len(unique_ts))*300
 vals={k:np.array([float(series[k][i]) if series[k][i] is not None else np.nan for i in keep]) for k in keys}
 n=len(keep);get=lambda k:vals.get(k,np.full(n,np.nan))
 step=5.0;on=(get('SF_SPD_DM')>=.99)&(get('RF_SPD_DM')>=.99)
 if not quality['time_valid']:on[:]=False
 age=np.zeros(n);a=0.
 for i,active in enumerate(on):
  a=a+step if active and (i==0 or sec[i]-sec[i-1]<=step*60+1) else (step if active else 0.)
  age[i]=a
 stable=on&(age>GATES['warmup_minutes'])
 unit_errors=quality['unit_errors']
 if not quality['valid_for_diagnosis']:stable[:]=False
 return {'t':unique_ts,'s':get,'sec':sec,'on':on,'stable':stable,'step':step,'unit_errors':unit_errors,
         'conflicts':conflicts,'rows':len(ts),'unique':len(unique_ts),'duplicates':len(ts)-len(groups),'missing':sum(sum(num(x) is None for x in v) for v in series.values()),'quality':quality}

def _mode(v):
 s=v['s'];oa=s('OA_TEMP');cmd=s('OA_DMPR_DM');cool=s('CHWC_VLV_DM')
 econ=(oa>=GATES['economizer_min_C'])&(oa<=GATES['economizer_max_C'])
 mode=np.full(len(oa),'missing',dtype=object)
 good=np.isfinite(oa)&np.isfinite(cmd)&np.isfinite(cool)
 mode[good&~v['on']]='off'
 mode[good&v['on']&~v['stable']]='startup'
 mode[good&v['stable']&~econ]='mechanical_or_minimum_air'
 mode[good&v['stable']&econ&(cmd>=.98)]='economizer_with_mechanical_enable'
 mode[good&v['stable']&econ&(cmd<.98)]='economizer_lockout'
 return mode

def _windows(v,mask,columns):
 """Non-overlapping contiguous 30 min blocks; gaps and invalid points break runs."""
 n=int(GATES['window_minutes']/v['step']);blocks=[];run=[]
 for i,ok in enumerate(mask):
  if not ok or (run and v['sec'][i]-v['sec'][run[-1]]!=v['step']*60):run=[]
  if not ok:continue
  run.append(i)
  if len(run)==n:
   blocks.append({'start':v['t'][run[0]],'end':v['t'][run[-1]],'minutes':GATES['window_minutes'],
                  'samples':len(run),**{k:stat(a[run]) for k,a in columns.items()},'_indices':run[:]})
   run=[]
 return blocks

def raw_air(case):
 v=prepare(case);s=v['s'];oa,ra,ma,cmd=[s(k) for k in ['OA_TEMP','RA_TEMP','MA_TEMP','OA_DMPR_DM']]
 den=oa-ra;mix=np.full(len(oa),np.nan);ok=np.abs(den)>=GATES['mix_delta_min_C']
 mix[ok]=(ma[ok]-ra[ok])/den[ok]
 # Physical non-mixture temperatures cannot be used to infer actuator behavior.
 valid=v['stable']&ok&np.isfinite(mix)&np.isfinite(cmd)&(cmd>=0)&(cmd<=1)&(mix>=-.05)&(mix<=1.05)
 return v,cmd,mix,valid

def raw_coil(case):
 v=prepare(case);s=v['s'];cmd=s('CHWC_VLV_DM');drop=s('MA_TEMP')-s('SA_TEMP');fan=s('SF_CS')
 closed=np.isfinite(cmd)&(cmd<=GATES['coil_closed_command_max'])&v['stable'];age=np.zeros(len(cmd));a=0.
 for i,yes in enumerate(closed):
  a=a+v['step'] if yes and (i==0 or v['sec'][i]-v['sec'][i-1]<=v['step']*60+1) else (v['step'] if yes else 0.)
  age[i]=a
 valid=closed&(age>GATES['closed_settle_minutes'])&np.isfinite(drop)&np.isfinite(fan)&(fan>.1)&(fan<=1.)
 return v,fan,drop,valid

def _bin(x,width):return max(0,min(int(1/width)-1,int(math.floor((float(x)+1e-8)/width))))

def calibrate(normal_cases,leak_cases=None,write=True):
 """Normal response envelopes; known development overlap forbids a normal claim."""
 air={};coil={};ids=[];hashes=[]
 for c in normal_cases:
  v,cmd,mix,ok=raw_air(c)
  if v['unit_errors']:raise ValueError('Development units invalid')
  for x,y in zip(cmd[ok],mix[ok]):air.setdefault(_bin(x,GATES['command_bin_width']),[]).append(float(y))
  v,fan,drop,ok=raw_coil(c)
  for x,y in zip(fan[ok],drop[ok]):coil.setdefault(_bin(x,GATES['fan_command_bin_width']),[]).append(float(y))
  ids.append(c['id']);hashes.append(hashlib.sha256(json.dumps(c,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
 def envelope(data,margin):
  # Full development extrema, expanded rather than cherry-picked percentiles.
  return {str(k):{'low':num(min(a)-margin),'high':num(max(a)+margin),'samples':len(a)} for k,a in data.items() if len(a)>=12}
 leak_limits={};leak_ids=[];leak_hashes=[]
 for c in leak_cases or []:
  v,fan,drop,ok=raw_coil(c)
  for x,y in zip(fan[ok],drop[ok]):leak_limits.setdefault(_bin(x,GATES['fan_command_bin_width']),[]).append(float(y))
  leak_ids.append(c['id']);leak_hashes.append(hashlib.sha256(json.dumps(c,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
 # This ONLY tightens normal eligibility: overlapping normal/leak thermal values
 # remain unresolved, rather than calling absence of a fault trigger 'normal'.
 normal_exclusive={str(k):num(min(a)-GATES['normal_thermal_margin_C']) for k,a in leak_limits.items() if len(a)>=12}
 out={'method':'Normal command-conditioned envelopes with development class-overlap rejection and fixed settled-window gates; engineering repair.',
      'scope':'one simulated SDAHU; temperature-inferred air fraction is NOT actuator position; no direct feedback',
      'gates':GATES,'air_envelope':envelope(air,GATES['minimum_mix_fraction_margin']),
      'coil_envelope':envelope(coil,GATES['normal_thermal_margin_C']),'coil_normal_exclusive_high':normal_exclusive,
      'development_case_ids':ids,'development_case_sha256':hashes,'overlap_check_case_ids':leak_ids,'overlap_check_case_sha256':leak_hashes,
      'temperature_units':'degC','original_source_units':'degF converted by (F-32)*5/9',
      'source_document':'LBNL SDAHU September2022 pp4-7: fans, economizer1..15.555556C, Basic command definitions',
      'not_claimed':'Not a universal sensor accuracy envelope or original algorithm; bounds apply to the source simulation only.'}
 if write:CONFIG_FILE.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 return out

def extract(case,action,calibration=None):
 if action not in ACTIONS:raise ValueError('Unknown evidence action')
 if case.get('family')!='lbnl':
  # No HVAC fault inference on building meter replay.
  return {'action':action,'label':ACTION_LABELS[action],'features':{'family':'bdg2','status':'building_review'},'evidence':[],'windows':[],'cost':1}
 calibration=calibration or load_calibration();v=prepare(case);s=v['s'];mode=_mode(v);windows=[]
 f={'family':'lbnl','action':action,'unit_errors':v['unit_errors'],'time_errors':v['quality']['time_errors'],
    'quality_invalid':not v['quality']['valid_for_diagnosis'],'conflicting_timestamps':len(v['conflicts']),
    'missing_points':v['quality']['missing_points'].get(action,[])}
 if action=='quality':
  f.update(v['quality'])
 elif action=='operating_context':
  active=v['stable'];sf,rf=s('SF_CS'),s('RF_CS')
  valid=active&np.isfinite(sf)&np.isfinite(rf)&(sf>.1)&(sf<=1)&(rf>0)&(rf<=1)
  f.update({'stable_minutes':int(valid.sum()*v['step']),'startup_excluded_minutes':int((v['on']&~v['stable']).sum()*v['step']),
            'fan_command_median':stat(sf[valid]),'return_supply_command_ratio':stat((rf/np.maximum(sf,.001))[valid]),
            'control_modes':{m:int(np.sum(mode==m)*v['step']) for m in sorted(set(mode))},
            'context_qualified':int(valid.sum()*v['step'])>=GATES['minimum_qualified_minutes'],
            'mode_basis':'Observed fan status + OA temperature + commands; not calendar occupancy or SYS_CTL.',
            'zone_temperature_median_C':stat(np.concatenate([s(f'ZONE_TEMP_{i}')[valid] for i in range(1,6)]))})
  windows=_windows(v,valid,{'fan_command':sf})
 elif action=='air_path':
  v,cmd,mix,valid=raw_air(case);bounds=(calibration or {}).get('air_envelope',{})
  lo=np.full(len(cmd),np.nan);hi=lo.copy()
  for i in np.flatnonzero(valid):
   env=bounds.get(str(_bin(cmd[i],GATES['command_bin_width'])))
   if env:lo[i]=env['low'];hi[i]=env['high']
  known=valid&np.isfinite(lo);inside=(mix>=lo)&(mix<=hi);outside=(mix<lo)|(mix>hi)
  windows=_windows(v,known,{'command':cmd,'inferred_mix_fraction':mix,'reference_low':lo,'reference_high':hi})
  for w in windows:
   inds=w['_indices'];w['compatible_fraction']=num(inside[inds].mean());w['mismatch_fraction']=num(outside[inds].mean())
   w['state']='mismatch' if w['mismatch_fraction']>=GATES['fault_window_fraction_min'] else ('compatible' if w['compatible_fraction']>=GATES['normal_window_fraction_min'] else 'mixed')
  mismatch=sum(w['minutes'] for w in windows if w['state']=='mismatch');compatible=sum(w['minutes'] for w in windows if w['state']=='compatible')
  f.update({'qualified_minutes':sum(w['minutes'] for w in windows),'mismatch_minutes':mismatch,'compatible_minutes':compatible,
            'valid_temperature_minutes':int(valid.sum()*v['step']),'uncalibrated_command_minutes':int((valid&~known).sum()*v['step']),
            'mix_fraction_median':stat(mix[known]),'damper_command_median':stat(cmd[known]),
            'mix_state':'stuck_candidate' if mismatch>=GATES['minimum_qualified_minutes'] else ('compatible' if compatible>=GATES['minimum_qualified_minutes'] and mismatch==0 and np.sum(inside[known])/max(np.sum(known),1)>=GATES['normal_window_fraction_min'] else 'unknown'),
            'qualification':'稳定双风机运行且室外/回风温差至少3°C；对照开发正常指令响应包络，非把指令当实测阀位。'})
 elif action=='coil_response':
  v,fan,drop,valid=raw_coil(case);bounds=(calibration or {}).get('coil_envelope',{})
  lo=np.full(len(fan),np.nan);hi=lo.copy();exclusive=lo.copy()
  for i in np.flatnonzero(valid):
   env=bounds.get(str(_bin(fan[i],GATES['fan_command_bin_width'])))
   if env:lo[i]=env['low'];hi[i]=env['high']
   cap=(calibration or {}).get('coil_normal_exclusive_high',{}).get(str(_bin(fan[i],GATES['fan_command_bin_width'])))
   if cap is not None:exclusive[i]=min(hi[i],cap)
  known=valid&np.isfinite(lo);excess=drop>hi;inside=(drop>=lo)&(drop<=exclusive)
  windows=_windows(v,known,{'closed_command_drop_C':drop,'reference_low_C':lo,'reference_high_C':hi,'normal_exclusive_high_C':exclusive,'fan_command':fan})
  for w in windows:
   inds=w['_indices'];w['excess_cooling_fraction']=num(excess[inds].mean());w['compatible_fraction']=num(inside[inds].mean())
   w['state']='excess_cooling' if w['excess_cooling_fraction']>=GATES['fault_window_fraction_min'] else ('compatible' if w['compatible_fraction']>=GATES['normal_window_fraction_min'] else 'mixed')
  abnormal=sum(w['minutes'] for w in windows if w['state']=='excess_cooling');compatible=sum(w['minutes'] for w in windows if w['state']=='compatible')
  closed_cmd=np.isfinite(v['s']('CHWC_VLV_DM'))&(v['s']('CHWC_VLV_DM')<=GATES['coil_closed_command_max'])
  f.update({'qualified_minutes':sum(w['minutes'] for w in windows),'excess_cooling_minutes':abnormal,'compatible_minutes':compatible,
            'stable_closed_minutes':int(valid.sum()*v['step']),'closed_drop_median_C':stat(drop[known]),
            'eligibility_stages':{'fan_on_minutes':int(v['on'].sum()*v['step']),
               'post_startup_minutes':int(v['stable'].sum()*v['step']),
               'zero_command_during_stable_minutes':int((v['stable']&closed_cmd).sum()*v['step']),
               'settled_closed_with_valid_sensors_minutes':int(valid.sum()*v['step']),
               'calibrated_closed_minutes':int(known.sum()*v['step']),
               'contiguous_qualified_minutes':sum(w['minutes'] for w in windows)},
            'coil_state':'leak_candidate' if abnormal>=GATES['minimum_qualified_minutes'] else ('compatible' if compatible>=GATES['minimum_qualified_minutes'] and abnormal==0 and np.sum(inside[known])/max(np.sum(known),1)>=GATES['normal_window_fraction_min'] else 'unknown'),
            'qualification':'启动30分钟后，零关阀指令持续15分钟后计入连续30分钟窗口；比较相同风机指令区间正常温降包络。正常/泄漏开发响应重叠区拒判。'})
 for w in windows:w.pop('_indices',None)
 f['windows']=windows;f['control_modes'] = f.get('control_modes',{m:int(np.sum(mode==m)*v['step']) for m in sorted(set(mode))}) if action!='quality' else {}
 metric_names={'rows':'原始记录条数','duplicates':'重复时间戳条数','missing':'缺失数','unique_operating_minutes':'独立运行分钟','stable_minutes':'稳定运行分钟','qualified_minutes':'合格证据窗口分钟','mismatch_minutes':'混风不一致分钟','compatible_minutes':'正常包络内分钟','excess_cooling_minutes':'关阀异常温降分钟','stable_closed_minutes':'稳定关阀分钟','closed_drop_median_C':'稳定关阀温降 °C','mix_fraction_median':'温度推算混风比例','damper_command_median':'风阀指令中位数'}
 evidence=[{'label':metric_names.get(k,k),'value':val,'detail':'由允许测点程序计算；窗口和开发参考均可复核。'} for k,val in f.items() if k in metric_names]
 return {'action':action,'label':ACTION_LABELS[action],'features':f,'evidence':evidence,'windows':windows,'mode':f.get('control_modes',{}),'cost':1,
         **({'quality':v['quality']} if action=='quality' else {})}

def branch_status(observed,invalid=False):
 """Inspectability of each hypothesis; missing data is not a negative diagnosis."""
 obs={a:v.get('features',v) for a,v in observed.items()};out={}
 requirements={
 'air_path':'需要OA_TEMP、RA_TEMP、MA_TEMP、OA_DMPR_DM及双风机启停；启动30分钟后，室外/回风温差≥3°C，至少两个连续30分钟窗口且指令位于已校准范围。',
 'coil_response':'需要MA_TEMP、SA_TEMP、CHWC_VLV_DM、SF_CS及双风机启停；风机已稳定，零关阀指令（容差0.01%）持续至少75分钟，获得15分钟等待后的两个30分钟窗口；还需开发参考覆盖。',
 'operating_context':'需要双风机启停和转速指令、OA_TEMP、风阀与冷阀指令；连续运行至少90分钟可提供启动30分钟后的60分钟证据。'}
 labels={'testable':'可检验','not_applicable':'工况不适用','missing_points':'缺点位','evidence_conflict':'证据冲突','supported':'已有支持证据','not_queried':'尚未查询'}
 for action in requirements:
  f=obs.get(action,{});mins=f.get('qualified_minutes',f.get('stable_minutes',0));state='testable'
  if action not in obs:state='not_queried';reason='该证据组尚未取得；不会沿用历史结论。'
  elif invalid:state='evidence_conflict';reason='单位、时间轴或记录冲突使本次证据无效；需先修正质量问题。'
  elif f.get('missing_points'):state='missing_points';reason='缺少可用点位：'+', '.join(f['missing_points'])
  elif action=='operating_context':
   if not f.get('context_qualified'):state='not_applicable';reason='可用稳定运行不足60分钟；停机或启动不能判断正常。'
   else:reason='已取得可用稳定运行工况；仍需分别核验风路和盘管。'
  elif action=='air_path':
   if f.get('mix_state')=='stuck_candidate':state='supported';reason='存在持续指令—混风热响应偏离，支持卡滞候选；尚需核实传感器和执行器。'
   elif mins<60:state='not_applicable';reason='温差、连续时长或开发参考覆盖不足，当前窗口不可完成风路检验。'
   elif f.get('mix_state')=='compatible':reason='当前窗口未发现足够的风路偏离证据；不能据此排除卡滞。'
   else:state='evidence_conflict';reason='不同窗口/样本响应不一致，尚不能形成稳定风路结论。'
  else:
   if f.get('coil_state')=='leak_candidate':state='supported';reason='稳定关阀后仍有超参考冷却，支持泄漏候选；需水侧或现场关闭核验。'
   elif mins<60:
    state='not_applicable';st=f.get('eligibility_stages',{})
    if not st.get('post_startup_minutes'):reason='未取得启动30分钟后的稳定运行时段；停机或启动不能检验关阀泄漏。'
    elif not st.get('zero_command_during_stable_minutes'):reason='稳定运行时没有零关阀指令；持续制冷温降不能检验关闭时泄漏。'
    elif not st.get('settled_closed_with_valid_sensors_minutes'):reason='零关阀片段未满足15分钟等待及有效温度/风机指令的联合条件。'
    elif not st.get('calibrated_closed_minutes'):reason='存在等待后的关阀片段，但其风机指令未被开发参考覆盖。'
    else:reason=f"等待并经参考覆盖后仅有{st.get('calibrated_closed_minutes',0)}分钟；尚不足以形成共60分钟的连续合格窗口。"
   elif f.get('coil_state')=='compatible':reason='合格关阀窗口位于开发正常专属参考；只支持当前有限工况，不作普遍排除。'
   else:state='evidence_conflict';reason='关阀热响应重叠或窗口响应不一致，无法区分正常与泄漏。'
  out[action]={'state':state,'label':labels[state],'reason':reason,'qualified_minutes':mins,
               'missing_points':f.get('missing_points',[]),'required_condition':requirements[action],
               'eligibility_stages':f.get('eligibility_stages',{})}
 return out

def diagnose(observed,calibration=None):
 obs={a:(x.get('features',x) if isinstance(x,dict) else {}) for a,x in observed.items()}
 base={'confidence':None,'support_score':None,'score_note':'确定性证据规则；无未经校准的故障概率。','label':'unresolved','status':'insufficient'}
 supports=[];refutes=[];nexts=[];windows=[];a=obs.get('air_path',{});c=obs.get('coil_response',{});ctx=obs.get('operating_context',{});q=obs.get('quality',{})
 if any(v.get('family')=='bdg2' for v in obs.values()):
  return {**base,'label':'building_review','name':LABEL_NAMES['building_review'],'detail':'BDG2为真实用能回放，无设备点位或故障真值。','support_evidence':[],'refuting_evidence':[],'next_actions':[{'action':'field','text':'核对营业/使用时段与总表口径；设备诊断需独立点位。','type':'field_unmeasured'}],'windows':[],'current_mode':{}}
 invalid=any(v.get('unit_errors') or v.get('time_errors') or v.get('quality_invalid') or v.get('conflicting_timestamps') for v in obs.values())
 air=a.get('mix_state','unknown');coil=c.get('coil_state','unknown')
 if air=='stuck_candidate':supports.append(f"混风热响应在{a['mismatch_minutes']}分钟窗口偏离同指令正常参考，支持风阀卡滞候选。")
 elif air=='compatible':refutes.append(f"{a['compatible_minutes']}分钟混风响应处于开发参考包络；当前窗口未发现足够的风路偏离证据，不能据此排除卡滞。")
 if coil=='leak_candidate':supports.append(f"稳定关阀后{c['excess_cooling_minutes']}分钟存在超出正常风机温升参考的降温，支持泄漏候选。")
 elif coil=='compatible':refutes.append(f"{c['compatible_minutes']}分钟稳定关阀热响应处于开发参考包络；该证据只覆盖当前工况，不足以排除所有阀泄漏。")
 for action in ['quality','operating_context','air_path','coil_response']:
  if action not in obs:nexts.append({'action':action,'text':ACTION_LABELS[action],'type':'data_query','query_cost':1})
 if 'operating_context' in obs and not ctx.get('context_qualified'):
  nexts.append({'action':'later_operating_period','text':'补取双风机连续运行至少90分钟的时段，排除启动前30分钟；停机不等于正常。','type':'archived_or_field_unmeasured'})
 if 'air_path' in obs and air=='unknown':
  nexts.append({'action':'air_response_window','text':'补取室外与回风温差≥3°C、风机稳定且风阀有可核验指令的连续时段；当前温差/参考/窗口不足。必要时独立核验混风温度或阀位反馈。','type':'archived_or_field_unmeasured'})
 if 'coil_response' in obs and coil=='unknown':
  nexts.append({'action':'closed_valve_window','text':'补取冷阀指令为零（数值容差0.01%）持续至少75分钟且风机已稳定的时段；持续制冷无法排除关闭时泄漏，必要时另采盘管前后温度/水侧流量。','type':'archived_or_field_unmeasured'})
 if invalid:
  base['status']='invalid_evidence';nexts.insert(0,{'action':'correct_source','text':'先核对单位、实际时间间隔或冲突时间戳，再计算时长；不能用不可信记录给设备结论。','type':'data_correction'})
 elif q and ctx.get('context_qualified'):
  if air=='stuck_candidate' and coil=='leak_candidate':base['status']='conflicting_evidence'
  elif air=='stuck_candidate':base.update(label='damper_stuck',status='supported')
  elif coil=='leak_candidate' and air=='compatible':base.update(label='coil_leakage',status='supported')
  elif air=='compatible' and coil=='compatible':base.update(label='normal',status='supported')
 elif q and q.get('unique_operating_minutes',0)<60:base['status']='inactive'
 for action in ['air_path','coil_response','operating_context']:
  for w in obs.get(action,{}).get('windows',[]):windows.append({'action':action,**w})
 if base['label']=='normal':
  detail='混风指令响应与稳定关阀热响应均有正向一致证据；仅称已核验时段和限定三类范围正常。'
  supports=[f"本次风路参考内窗口{a.get('compatible_minutes',0)}分钟、盘管参考内窗口{c.get('compatible_minutes',0)}分钟，满足当前两个分支的有限参考一致性条件。"]
 elif base['label']=='damper_stuck':detail='存在持续的指令—混风热响应矛盾，形成风阀卡滞候选；需现场核实传感器及执行器，未使用实测阀位。'
 elif base['label']=='coil_leakage':detail='混风证据一致，但稳定关阀后仍有异常冷却，形成盘管阀泄漏候选；仍需现场关闭和水侧核验。'
 else:detail='已取得证据尚不能作三分类结论；保留未决并列出可改变判断的补证时段或点位。'
 branches=branch_status(observed,invalid)
 return {**base,'name':LABEL_NAMES[base['label']],'detail':detail,'support_evidence':supports,'refuting_evidence':refutes,'branches':branches,
         'next_actions':nexts,'windows':windows,'current_mode':ctx.get('control_modes',a.get('control_modes',c.get('control_modes',{}))),
         'rule_evidence':{'air_response':air,'coil_response':coil,'context_qualified':ctx.get('context_qualified',False)},
         'scope':'同一公开仿真单风道机组的正常/风阀卡滞/盘管阀泄漏候选；不能外推为真实楼宇定位。'}

def repair_duplicates(case):
 out=copy.deepcopy(case);seen=set();keep=[];keys=sorted(case['series'])
 for i,t in enumerate(case['timestamps']):
  fp=(t,*(case['series'][k][i] for k in keys))
  if fp not in seen:seen.add(fp);keep.append(i)
 out['timestamps']=[case['timestamps'][i] for i in keep];out['series']={k:[case['series'][k][i] for i in keep] for k in keys}
 out['id']=case['id']+'__repaired';out['repair']={'removed':len(case['timestamps'])-len(keep),'method':'drop_exact_duplicate_records','original_id':case['id'],'requires_equipment_recheck':True}
 return out
