"""Four comparable policies over an identical evidence pool and numerical engine."""
from __future__ import annotations
import hashlib
import json
import time
import uuid
from pathlib import Path

from engine import (ACTIONS,ACTION_LABELS,ACTION_DESCRIPTIONS,ROOT,evidence,features,quality,
                    initial_summary,diagnose,load_calibration,LABEL_NAMES,repair_duplicates)
from model_client import choose_action

STRATEGIES={'fixed':'固定流程','adaptive_rule':'自适应规则','local_model':'本地模型主动补证','full_information':'完整信息'}
POLICY_CONFIG=ROOT/'data'/'policy_config.json'


def fixed_order():
    if POLICY_CONFIG.exists():
        return json.loads(POLICY_CONFIG.read_text(encoding='utf-8')).get('fixed_order',['coil_response','air_path','operating_context'])
    return ['coil_response','air_path','operating_context']


def rule_choice(summary,observed,diagnosis,allowed):
    """Explicit no-LLM rules; same initial and revealed evidence as model policy."""
    delta=summary.get('supply_setpoint_delta_mean_C')
    if 'coil_response' in allowed and delta is not None and delta < 0:
        return 'coil_response','送风低于设定，优先查看盘管指令与温降。'
    if 'air_path' in allowed and delta is not None and delta >= 0:
        return 'air_path','送风高于设定，优先查看混风过程与风阀指令。'
    coil=observed.get('coil_response',{})
    if 'air_path' in allowed and coil:
        return 'air_path','已取得盘管响应，追加混风证据区分上游变化。'
    if 'coil_response' in allowed and 'air_path' in observed:
        return 'coil_response','已取得混风证据，追加盘管响应进行交叉核验。'
    return next(a for a in fixed_order() if a in allowed),'按开发阶段冻结的通用核验优先级选择下一证据组。'


def should_stop(d,observed):
    # Shared stop condition; avoids claiming fewer queries by always abstaining.
    return d.get('status')=='supported'


def run_case(case,strategy='fixed',budget=4,repair=False,calibration=None,save=True):
    if strategy not in STRATEGIES:
        raise ValueError('Unknown strategy')
    if not isinstance(budget,int) or not 1<=budget<=4:
        raise ValueError('Budget must be an integer from 1 to 4')
    if strategy=='full_information' and budget!=4:
        raise ValueError('完整信息需要全部4组证据，查询预算必须为4；不能免费获得额外信息。')
    if repair:
        case=repair_duplicates(case)
    start=time.perf_counter()
    q=quality(case)
    if not q['valid_schema']:
        raise ValueError('Invalid input schema')
    summary=initial_summary(case)
    observed={}
    steps=[]
    calls=[]
    warnings=[]
    calibration=calibration or load_calibration()
    final=diagnose(case,observed,calibration)
    for step_no in range(budget):
        allowed=[a for a in ACTIONS if a not in observed]
        if not allowed:
            break
        selection_latency=0
        if step_no==0:
            action='quality'
            reason='所有策略共享并计费的记录完整性检查；数据问题与设备疑点可并存。'
        elif strategy in ('fixed','full_information') or case['family']!='lbnl':
            action=next(a for a in fixed_order() if a in allowed)
            reason='按开发阶段冻结的固定核验顺序查询。' if strategy!='full_information' else '获取全部允许证据，并计入实际查询成本。'
        elif strategy=='adaptive_rule':
            action,reason=rule_choice(summary,observed,final,allowed)
        else:
            payload={'initial_screening':summary,'revealed_evidence':observed,
                     'program_diagnosis':{k:final.get(k) for k in ['label','status','rule_evidence']},
                     'shared_verifier':{'thresholds':calibration.get('thresholds',{}),
                       'logic':'Air-path command variation with flat temperature-inferred mixing supports damper_stuck. Sufficient closed-valve periods with abnormal temperature drop support coil_leakage. Normal needs responsive air AND no leak evidence. Conflicting fault evidence is unresolved. Operating_context is descriptive and does not itself resolve these fault candidates.',
                       'stop':'All non-full policies stop on a supported verdict or inadequate running time. Choose evidence that can change the currently unresolved verdict.'},
                     'remaining_query_budget':budget-len(steps),'available_actions':{a:ACTION_DESCRIPTIONS[a] for a in allowed},
                     'query_cost_each':1,'field_acquisition_cost':'Not performed; unknown real-world cost',
                     'scope':'One simulated AHU; no actual actuator positions or hidden fault labels.'}
            call=choose_action(payload,allowed)
            calls.append(call)
            action=call.get('action')
            selection_latency=call.get('latency_ms',0)
            reason=call.get('reason','')
            if not call.get('response_valid') or action not in allowed:
                warnings.append('本地模型未返回有效动作；本次运行明确失败，不使用规则结果冒充模型结果。')
                final={'label':'unresolved','name':LABEL_NAMES['unresolved'],'status':'model_error','confidence':None,'support_score':None,
                       'detail':call.get('error','模型动作无效')}
                break
        step_start=time.perf_counter()
        ev=evidence(case,action)
        observed[action]=ev['features']
        final=diagnose(case,observed,calibration)
        steps.append({'index':len(steps)+1,'action':action,'label':ACTION_LABELS[action],'reason':reason,
                      'cost':1,'latency_ms':round((time.perf_counter()-step_start)*1000+selection_latency,3),
                      'selection_latency_ms':selection_latency,'evidence':ev['evidence'],'features':ev['features'],
                      'diagnosis':final,'quality':q})
        if strategy!='full_information' and (final.get('status')=='inactive' or should_stop(final,observed)):
            break
    elapsed=(time.perf_counter()-start)*1000
    if case['family']=='bdg2':
        warnings.append('实测建筑回放没有设备故障真值；结果不能用于证明真实楼宇故障定位或实际节能收益。')
        warnings.append('本案例采用确定性统计回放，不参与主动补证策略性能比较。正向基线差额不是已实现节能量。')
    if q['issues']:
        warnings.append('记录问题与运行疑点分别保留；建议修正可验证的数据问题后重新核验设备。')
    if case.get('repair'):
        warnings.append('本次仅去除完全重复记录；设备疑点仍按修正后的数据重新计算。')
    cost={'query_units':len(steps),'field_acquisition_units':0,'latency_ms':round(elapsed,3),'model_calls':len(calls),
          'model_latency_ms':round(sum(c.get('latency_ms',0) for c in calls),3),
          'cost_note':'查询单位是离线实验记账，不等于现场采集费用或实际人民币成本。'}
    run={'run_id':uuid.uuid4().hex[:16],'case_id':case['id'],'strategy':strategy,'strategy_label':STRATEGIES[strategy],
         'budget':budget,'family':case['family'],'origin':case.get('origin'),'perturbation':case.get('perturbation'),
         'repair':case.get('repair'),'initial_summary':summary,'steps':steps,'final':{**final,'quality':q,'operation':final},
         'cost':cost,'warnings':warnings,'model_calls':calls,
         'summary':final.get('detail',''),'data_hash':hashlib.sha256(json.dumps(case,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
         'status':'completed' if final.get('status')!='model_error' else 'model_error'}
    if save:
        folder=ROOT/'output'/'runs'
        folder.mkdir(parents=True,exist_ok=True)
        (folder/(run['run_id']+'.json')).write_text(json.dumps(run,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return run
