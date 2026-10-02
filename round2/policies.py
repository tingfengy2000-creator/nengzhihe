"""Round2 policies: common numeric engine; no model calls or hidden-state access."""
from pathlib import Path
import copy,hashlib,json,time,uuid
from baseline_v1 import engine as legacy
import diagnostics
ROOT=Path(__file__).resolve().parent
ACTIONS=['quality','operating_context','air_path','coil_response']
NAMES={'quality':'记录可信度','operating_context':'启停与控制工况','air_path':'混风与风阀响应','coil_response':'关阀与盘管温降'}
BDG_NAMES={'quality':'表计记录可信度','air_path':'电量与天气关系','coil_response':'历史参考差异','operating_context':'用能变化汇总'}
STRATEGIES={'fixed':'固定流程','adaptive_rule':'自适应规则','full_information':'完整信息参照'}

def config():
    path=ROOT/'data/policy_config.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'fixed_order':['operating_context','air_path','coil_response']}

def normalized(d):
    d=copy.deepcopy(d)
    d.setdefault('supporting_evidence',d.get('support_evidence',[]))
    if d.get('label')=='normal':
        d['supporting_evidence']=list(d.get('refuting_evidence',[]))
    d.setdefault('refuting_evidence',[]);d.setdefault('next_actions',[]);d.setdefault('windows',[])
    d.setdefault('current_mode',d.get('mode','尚未取得运行工况'))
    d['mode']=d['current_mode']
    return d

def adaptive_choice(observed,allowed):
    if 'operating_context' in allowed:return 'operating_context','先确认实际启停与控制工况，避免在不适用时段判断设备。'
    # One bounded branch on already acquired control mode, never a hidden label.
    context=observed.get('operating_context',{}).get('features',{})
    modes=context.get('control_modes',{})
    if 'coil_response' in allowed and modes.get('economizer_lockout',0)>=60:
        return 'coil_response','已有至少60分钟经济器锁定机械冷却工况，优先查询稳定关阀热响应。'
    d=diagnostics.diagnose(observed)
    # Recommendations are produced solely from already queried evidence.
    for request in d.get('next_actions',[]):
        if isinstance(request,dict):
            candidate=request.get('action') or request.get('action_id')
            if candidate in allowed:return candidate,'按当前证据缺口选择下一项核查。'
    for a in config()['fixed_order']:
        if a in allowed:return a,'使用已冻结的证据优先顺序。'
    return allowed[0],'查询下一项可用证据。'

def stop(d):
    return d.get('status') in {'supported','inactive','invalid_evidence'} or d.get('stop_recommended',False)

def prepare_case(case,repair=False,start_time=None,end_time=None):
    c=legacy.repair_duplicates(case) if repair else copy.deepcopy(case)
    if start_time or end_time:
        ids=[i for i,t in enumerate(c['timestamps']) if (not start_time or t>=start_time) and (not end_time or t<=end_time)]
        if not ids:raise ValueError('选择时间窗没有记录')
        c['timestamps']=[c['timestamps'][i] for i in ids]
        c['series']={k:[v[i] for i in ids] for k,v in c['series'].items()}
        c['selected_window']={'start':start_time,'end':end_time}
    return c

def run_case(case,strategy='adaptive_rule',budget=4,available_evidence=None,repair=False,save=True,order_override=None,start_time=None,end_time=None):
    if strategy not in STRATEGIES:raise ValueError('Unknown strategy')
    if type(budget)!=int or not 1<=budget<=4:raise ValueError('Budget must be 1..4')
    provided=ACTIONS[1:] if available_evidence is None else available_evidence
    if not isinstance(provided,list) or any(a not in ACTIONS[1:] for a in provided):raise ValueError('Invalid evidence list')
    allowed_pool=['quality']+[a for a in ACTIONS[1:] if a in provided]
    started=time.perf_counter()
    c=prepare_case(case,repair,start_time,end_time)
    q=legacy.quality(c)
    if not q['valid_schema']:raise ValueError('Invalid channel length')
    complete=strategy=='full_information'
    effective_budget=len(allowed_pool) if complete else min(budget,len(allowed_pool))
    obs={};steps=[];warnings=[]
    if c['family']=='bdg2':
        d={'label':'building_review','name':'用能变化待核查','status':'needs_review','detail':'实测电表仅提供变化线索；没有设备故障标签，不能定位设备或计算已实现节能收益。',
           'current_mode':'实测建筑历史用能回放','supporting_evidence':[],'refuting_evidence':['缺少设备点位和设备故障真值'],
           'next_actions':[{'action':'field_review','text':'核对建筑作息、天气和表计口径；若要定位设备，需要同时间段BMS与运维记录。'}],'windows':[]}
    else:d=normalized(diagnostics.diagnose(obs))
    for i in range(effective_budget):
        allowed=[a for a in allowed_pool if a not in obs]
        if i==0:action='quality';reason='先检查记录完整性，数据问题与设备疑点独立处理。'
        elif strategy=='adaptive_rule' and c['family']=='lbnl':action,reason=adaptive_choice(obs,allowed)
        else:
            order=order_override or config()['fixed_order']
            action=next(a for a in order if a in allowed);reason='按冻结顺序核查。' if not complete else '读取全部允许证据，不受预算滑块截断。'
        if c['family']=='lbnl':
            ev=diagnostics.extract(c,action);obs[action]=ev;d=normalized(diagnostics.diagnose(obs))
        else:
            # Keep the measured replay completely separate from simulated device diagnosis.
            mapping={'quality':'quality','air_path':'air_path','coil_response':'coil_response','operating_context':'operating_context'}
            ev=legacy.evidence(c,mapping[action]);obs[action]=ev
            if action!='quality':d['supporting_evidence'].extend(ev.get('evidence',[]))
        steps.append({'index':len(steps)+1,'action':action,'label':(BDG_NAMES if c['family']=='bdg2' else NAMES)[action],'reason':reason,'cost':1,
                      'evidence':ev.get('evidence',[]),'features':ev.get('features',{}),'windows':ev.get('windows',[]),'mode':ev.get('mode'),
                      'diagnosis':copy.deepcopy(d)})
        if not complete and c['family']=='lbnl' and stop(d):break
    if c['family']=='lbnl' and not d.get('next_actions') and d.get('label')=='unresolved':
        d['next_actions']=[{'action':a,'text':'补查'+NAMES[a]} for a in ACTIONS if a not in obs]
    if set(allowed_pool)!=set(ACTIONS):warnings.append('部分证据组被关闭；本次按实际可用证据重新计算，未以历史结论代替。')
    if q['issues']:warnings.append('数据问题仍需处理；设备证据独立判断。')
    if c.get('repair'):warnings.append('仅删除完全重复记录，设备疑点按修正后的记录重新计算。')
    if c['family']=='bdg2':warnings.append('BDG2不参加设备诊断性能比较，不与LBNL关联成真实楼宇定位证据。')
    elapsed=(time.perf_counter()-started)*1000
    result={'run_id':uuid.uuid4().hex[:16],'case_id':c['id'],'family':c['family'],'origin':c['origin'],'perturbation':c.get('perturbation'),
       'strategy':strategy,'strategy_label':STRATEGIES[strategy],'budget':budget,'steps':steps,'final':{**d,'quality':q,'operation':d},
       'cost':{'query_units':len(steps),'field_acquisition_units':0,'latency_ms':round(elapsed,6),'model_calls':0},
       'config':{'available_evidence':allowed_pool,'requested_budget':budget,'budget':effective_budget,'complete_pool':complete,'selected_window':c.get('selected_window')},
       'repair':c.get('repair'),'warnings':warnings,'status':'completed','data_hash':hashlib.sha256(json.dumps(c,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
    if save:
        p=ROOT/'output/runs';p.mkdir(parents=True,exist_ok=True)
        (p/(result['run_id']+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return result
