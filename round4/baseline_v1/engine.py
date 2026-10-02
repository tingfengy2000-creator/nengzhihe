"""Numerical evidence engine. No labels, hidden channels or LLM-generated numbers.

Development-calibrated evidence rules apply to one public simulated system.
They are neither fault probabilities nor claims about a real building.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent
ACTIONS = ['quality', 'air_path', 'coil_response', 'operating_context']
ACTION_LABELS = {'quality': '核查记录完整性', 'air_path': '核查混风与风阀指令',
                 'coil_response': '核查盘管热响应', 'operating_context': '核查运行与区域温度'}
ACTION_DESCRIPTIONS = {
 'quality': 'Inspect timestamp duplicates, missing values and the documented units. A data issue can coexist with equipment faults.',
 'air_path': 'Query outdoor, return and mixed air temperatures and outdoor-air damper COMMAND. No actual damper position is available.',
 'coil_response': 'Query mixed/supply air temperature, supply setpoint and cooling-coil valve COMMAND. No actual valve position is available.',
 'operating_context': 'Query fan status/control and zone temperatures to assess operating context. No occupancy-mode or pressure fields are available.'}
EXCLUDED = {'OA_DMPR','RA_DMPR','CHWC_VLV','OA_CFM','RA_CFM','SA_CFM','SF_SPD','RF_SPD',
            'SF_WAT','RF_WAT','SYS_CTL','SA_SP','SA_SPSPT'}
LABEL_NAMES = {'normal': '正常工况', 'damper_stuck': '风阀卡滞候选', 'coil_leakage': '盘管阀泄漏候选',
               'unresolved': '证据不足', 'building_review': '建筑用能变化待核查'}
FEATURE_GROUPS = {
 'air_path': ['oa_mean','mixed_return_mean','mix_fraction_med','mix_fraction_std','damper_cmd_mean','damper_cmd_std','mix_cmd_corr','mix_low_cmd','mix_high_cmd'],
 'coil_response': ['supply_delta_mean','supply_delta_abs','coil_drop_mean','closed_valve_drop','closed_valve_fraction','coil_cmd_mean','coil_cmd_std','coil_drop_cmd_corr','supply_delta_p90'],
 'operating_context': ['fan_on_fraction','fan_cmd_mean','zone_mean','zone_spread','zone_p90','zone_std']}
CALIBRATION_FILE = ROOT / 'data' / 'calibration.json'


def safe_number(x):
    try:
        f = float(x)
        return round(f, 6) if math.isfinite(f) else None
    except (ValueError, TypeError):
        return None


def arr(case, key):
    n = len(case.get('timestamps', []))
    vals = case.get('series', {}).get(key)
    if vals is None:
        return np.full(n, np.nan)
    return np.array([float(x) if x is not None else np.nan for x in vals], dtype=float)


def stat(a, kind='mean'):
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        return None
    return safe_number({'mean': np.mean, 'std': np.std, 'median': np.median,
                        'p90': lambda v: np.percentile(v, 90), 'max': np.max, 'min': np.min}[kind](a))


def corr(a, b):
    good = np.isfinite(a) & np.isfinite(b)
    if good.sum() < 4 or np.std(a[good]) < 1e-6 or np.std(b[good]) < 1e-6:
        return None
    return safe_number(np.corrcoef(a[good], b[good])[0, 1])


def quality(case):
    ts = case.get('timestamps', [])
    duplicate_count = len(ts) - len(set(ts))
    missing = sum(sum(x is None or not math.isfinite(float(x)) for x in v) for v in case.get('series', {}).values())
    cells = sum(len(v) for v in case.get('series', {}).values())
    invalid_lengths = [k for k, v in case.get('series', {}).items() if len(v) != len(ts)]
    excluded = sorted(EXCLUDED.intersection(case.get('series', {})))
    issues = []
    if duplicate_count:
        issues.append({'code':'duplicate_timestamp','label':'时间戳重复','count':duplicate_count,
                       'detail':'仅能自动删除同一时间戳且所有通道值完全一致的重复记录。'})
    if missing:
        issues.append({'code':'missing_value','label':'监测值缺失','count':missing,
                       'detail':'缺失值保留，不作为零用能或正常设备状态。'})
    if invalid_lengths:
        issues.append({'code':'invalid_length','label':'通道长度不一致','detail':', '.join(invalid_lengths)})
    if excluded:
        raise ValueError('Disallowed simulator channels present in public case: ' + ','.join(excluded))
    return {'status':'needs_review' if issues else 'passed', 'label':'存在记录问题' if issues else '记录检查通过',
            'issues':issues, 'duplicates':duplicate_count, 'missing':missing, 'missing_fraction':safe_number(missing/max(cells,1)),
            'rows':len(ts), 'valid_schema':not invalid_lengths,
            'note':'记录检查通过不代表设备正常；数据问题与设备疑点分别核验。'}


def operating_minutes(case):
    on = arr(case,'SF_SPD_DM') > .5
    return len({t for t,active in zip(case['timestamps'],on) if active}) * case.get('sample_interval_minutes',5)


def repair_duplicates(case):
    """Repair exact duplicate records only. Never restore hidden clean truth."""
    out = copy.deepcopy(case)
    ts = case.get('timestamps', [])
    keys = sorted(case.get('series', {}))
    seen = set()
    keep = []
    for i, t in enumerate(ts):
        fingerprint = (t, *(case['series'][k][i] for k in keys))
        if fingerprint not in seen:
            seen.add(fingerprint)
            keep.append(i)
    out['timestamps'] = [ts[i] for i in keep]
    out['series'] = {k:[case['series'][k][i] for i in keep] for k in keys}
    out['repair'] = {'method':'drop_exact_duplicate_records', 'removed':len(ts)-len(keep),
                     'original_id':case['id'], 'requires_equipment_recheck':True,
                     'note':'仅修复记录重复，原有设备过程未被改变。'}
    out['id'] = case['id'] + '__repaired'
    return out


def features(case, action):
    if action == 'quality':
        q = quality(case)
        return {'duplicates':q['duplicates'], 'missing_fraction':q['missing_fraction'], 'rows':q['rows']}
    s = lambda k: arr(case,k)
    fan = s('SF_SPD_DM') > .5
    if action == 'air_path':
        oa, ma, ra, cmd = [s(k)[fan] for k in ['OA_TEMP','MA_TEMP','RA_TEMP','OA_DMPR_DM']]
        den = oa-ra
        fraction = np.full(len(oa), np.nan)
        ok = np.abs(den) >= 3
        fraction[ok] = (ma[ok]-ra[ok])/den[ok]
        result = dict(zip(FEATURE_GROUPS[action], [stat(oa), stat(ma-ra), stat(fraction,'median'), stat(fraction,'std'),
                     stat(cmd), stat(cmd,'std'), corr(fraction,cmd), stat(fraction[cmd<=.15]), stat(fraction[cmd>=.85])]))
        result['valid_mix_samples'] = len({t for t,valid in zip(np.array(case['timestamps'])[fan],np.isfinite(fraction)&np.isfinite(cmd)) if valid})
        return result
    if action == 'coil_response':
        ma, sa, sp, cmd = [s(k)[fan] for k in ['MA_TEMP','SA_TEMP','SA_TEMPSPT','CHWC_VLV_DM']]
        delta = sa-sp
        drop = ma-sa
        closed = np.isfinite(cmd) & (cmd<=.02)
        result = dict(zip(FEATURE_GROUPS[action], [stat(delta),stat(np.abs(delta)),stat(drop),stat(drop[closed]),
                         safe_number(closed.mean()) if len(closed) else None,stat(cmd),stat(cmd,'std'),corr(drop,cmd),stat(delta,'p90')]))
        result['valid_closed_samples'] = len({t for t,valid in zip(np.array(case['timestamps'])[fan],closed&np.isfinite(drop)) if valid})
        return result
    if action == 'operating_context':
        zones = np.stack([s('ZONE_TEMP_'+str(i))[fan] for i in range(1,6)])
        if np.isfinite(zones).any():
            spreads = np.nanmax(zones,axis=0)-np.nanmin(zones,axis=0)
        else:
            spreads = np.array([np.nan])
        return dict(zip(FEATURE_GROUPS[action], [stat(s('SF_SPD_DM')),stat(s('SF_CS')[fan]),stat(zones.flatten()),
                         stat(spreads),stat(zones.flatten(),'p90'),stat(zones.flatten(),'std')]))
    raise ValueError('Unknown action')


def initial_summary(case):
    q = quality(case)
    if case['family'] == 'lbnl':
        delta = arr(case,'SA_TEMP')-arr(case,'SA_TEMPSPT')
        fan = arr(case,'SF_SPD_DM')>.5
        return {'record_rows':q['rows'],'duplicate_records':q['duplicates'],'missing_fraction':q['missing_fraction'],
                'supply_setpoint_delta_mean_C':stat(delta[fan]), 'fan_on_fraction':stat(arr(case,'SF_SPD_DM')), 'unique_operating_minutes':operating_minutes(case),
                'measurement_type':'simulated_single_duct_ahu', 'note':'Shared initial screening summary, identical for all strategies.'}
    values = next(iter(case.get('series',{}).values()),[])
    return {'record_rows':q['rows'], 'duplicate_records':q['duplicates'], 'measurement_type':'measured_building_meter',
            'note':'No equipment fault labels; building replay cannot identify a device root cause.'}


def evidence(case, action):
    f = features(case,action) if case['family']=='lbnl' or action=='quality' else building_evidence(case,action)
    titles = {'duplicates':'重复记录','missing_fraction':'缺失比例','rows':'记录条数','oa_mean':'室外温度均值 °C',
      'mixed_return_mean':'混合与回风温差 °C','mix_fraction_med':'温度推算混风比例中位数','mix_fraction_std':'推算混风比例波动',
      'damper_cmd_mean':'室外风阀指令均值','damper_cmd_std':'室外风阀指令波动','mix_cmd_corr':'推算混风比例与指令相关',
      'mix_low_cmd':'低开度指令时的推算混风比例','mix_high_cmd':'高开度指令时的推算混风比例',
      'supply_delta_mean':'送风与设定温差均值 °C','supply_delta_abs':'送风设定偏差绝对值 °C',
      'coil_drop_mean':'混合至送风温降 °C','closed_valve_drop':'零冷阀指令时温降 °C',
      'closed_valve_fraction':'零冷阀指令样本比例','coil_cmd_mean':'冷阀指令均值','coil_cmd_std':'冷阀指令波动',
      'coil_drop_cmd_corr':'温降与冷阀指令相关','supply_delta_p90':'送风设定温差 P90 °C',
      'fan_on_fraction':'风机开启比例','fan_cmd_mean':'风机控制指令均值','zone_mean':'区域温度均值 °C',
      'zone_spread':'区域间温差均值 °C','zone_p90':'区域温度 P90 °C','zone_std':'区域温度波动 °C',
      'valid_mix_samples':'有效混风独立时刻数','valid_closed_samples':'有效零冷阀指令独立时刻数'}
    return {'action':action, 'label':ACTION_LABELS[action], 'features':f, 'cost':1,
             'evidence':[{'label':titles.get(k,k),'value':v,'detail':'程序计算；缺失指标显示为空',
                          'source':f'{case["id"]} / {action} / {k}'} for k,v in f.items()]}


def building_evidence(case,action):
    # Replay statistics only. No building-to-AHU inference or fault labels.
    series = case.get('series',{})
    k = 'electricity_kwh' if 'electricity_kwh' in series else ('electricity' if 'electricity' in series else next(iter(series)))
    v = arr(case,k)
    analysis_start=case.get('analysis_start')
    mask=np.array([t>=analysis_start for t in case['timestamps']]) if analysis_start else np.ones(len(v),dtype=bool)
    ref=arr(case,'reference_kwh')
    if action == 'air_path':
        oa=arr(case,'OA_TEMP')
        return {'mean_meter_kwh':stat(v[mask]),'p90_meter_kwh':stat(v[mask],'p90'),
                'outdoor_temperature_mean_C':stat(oa[mask]),'meter_weather_correlation':corr(v[mask],oa[mask])}
    if action == 'coil_response':
        return {'mean_reference_kwh':stat(ref[mask]),'mean_abs_reference_difference_kwh':stat(np.abs(v[mask]-ref[mask])),
                'mean_signed_reference_difference_kwh':stat(v[mask]-ref[mask])}
    difference=v[mask]-ref[mask]
    return {'observed_kwh':safe_number(np.nansum(v[mask])) if np.isfinite(v[mask]).any() else None, 'positive_reference_difference_kwh':safe_number(np.nansum(np.maximum(difference,0))) if np.isfinite(difference).any() else None,
            'sample_count':int(np.isfinite(v[mask]).sum())}


def load_calibration():
    return json.loads(CALIBRATION_FILE.read_text(encoding='utf-8')) if CALIBRATION_FILE.exists() else None


def diagnose(case, observed, calibration=None):
    base={'confidence':None,'support_score':None,'score_note':'可复核证据规则，不输出未经校准的故障概率。'}
    if case['family'] != 'lbnl':
        return {**base,'label':'building_review','name':LABEL_NAMES['building_review'],'status':'needs_review',
                'detail':'实测建筑回放仅提供用能变化线索；没有设备点位和故障真值，不能定位设备故障。'}
    if operating_minutes(case)<60:
        return {**base,'label':'unresolved','name':LABEL_NAMES['unresolved'],'status':'inactive',
                'detail':'去重后有效风机运行不足60分钟；缺乏足够设备响应，不从停机记录推断正常或故障。'}
    calibration = calibration or load_calibration()
    if not calibration or set(calibration.get('classes',[]))!={'normal','damper_stuck','coil_leakage'}:
        return {**base,'label':'unresolved','name':LABEL_NAMES['unresolved'],'status':'not_ready','detail':'三类开发参考未准备齐全。'}
    t=calibration['thresholds']; air=observed.get('air_path',{}); coil=observed.get('coil_response',{})
    air_state=coil_state='unknown'; detail=[]
    def has(obj,*keys):
        return all(obj.get(k) is not None for k in keys)
    if has(air,'mix_fraction_std','damper_cmd_std','mix_cmd_corr','valid_mix_samples') and air['valid_mix_samples']>=12 and air['damper_cmd_std']>=.08:
        if air['mix_fraction_std']<t['mix_std_boundary'] and air['mix_cmd_corr']<t['mix_correlation_boundary']:
            air_state='stuck_candidate'; detail.append('风阀指令变化而温度推算混风比例近乎不动，支持风阀卡滞疑点。')
        elif air['mix_fraction_std']>=t['mix_std_boundary'] and air['mix_cmd_corr']>=t['mix_correlation_boundary']:
            air_state='responsive'; detail.append('混风比例随风阀指令响应，未见本规则定义的卡滞证据。')
        else:
            detail.append('混风响应指标不一致，保留不确定。')
    elif 'air_path' in observed:
        detail.append('混风有效温差、独立时刻或指令变化不足，无法核验卡滞。')
    if has(coil,'closed_valve_drop','closed_valve_fraction','valid_closed_samples') and coil['closed_valve_fraction']>=.1 and coil['valid_closed_samples']>=12:
        if coil['closed_valve_drop']>t['closed_drop_boundary_C']:
            coil_state='leak_candidate'; detail.append('足够零冷阀指令时段的温降偏离正常开发参考，支持盘管阀泄漏疑点。')
        else:
            coil_state='no_leak_evidence'; detail.append('零冷阀指令时温降处于正常开发参考一侧。')
    elif 'coil_response' in observed:
        detail.append('零冷阀指令有效时刻不足，不能据少量温降判断泄漏。')
    label='unresolved'
    if air_state=='stuck_candidate' and coil_state!='leak_candidate': label='damper_stuck'
    elif coil_state=='leak_candidate' and air_state!='stuck_candidate': label='coil_leakage'
    elif air_state=='responsive' and coil_state=='no_leak_evidence': label='normal'
    elif air_state=='stuck_candidate' and coil_state=='leak_candidate': detail.append('两条故障证据冲突；单故障标签范围不足，拒绝强行归类。')
    if not detail: detail=['尚未取得足够设备过程证据；记录检查通过不能推出设备正常。']
    return {**base,'label':label,'name':LABEL_NAMES[label],'status':'supported' if label!='unresolved' else 'insufficient',
            'rule_evidence':{'air_response':air_state,'coil_response':coil_state},'thresholds':t,
            'detail':' '.join(detail)+' 结论仅适用于本公开单机组仿真及限定候选范围，真实设备仍需现场核验。'}


def calibrate(dev_cases, labels, write=True):
    references=[]; classes=['normal','damper_stuck','coil_leakage']
    for case in dev_cases:
        pert=case.get('perturbation') or {}
        if case.get('family')!='lbnl' or case.get('perturbed') or (isinstance(pert,dict) and pert.get('type','none')!='none'): continue
        if operating_minutes(case)<60: continue
        record=labels[case['id']]; label=record if isinstance(record,str) else record['label']
        fs={k:v for a in FEATURE_GROUPS for k,v in features(case,a).items()}
        references.append({'case_id':case['id'],'label':label,'features':fs})
    if set(r['label'] for r in references)!=set(classes): raise ValueError('All three labeled development classes are required')
    def values(name,labels):
        return [r['features'][name] for r in references if r['label'] in labels and r['features'].get(name) is not None]
    def boundary(low,high):
        if not low or not high or max(low)>=min(high): raise ValueError('Development rules cannot separate specified reference ranges')
        return safe_number((max(low)+min(high))/2)
    thresholds={
       'mix_std_boundary':boundary(values('mix_fraction_std',['damper_stuck']),values('mix_fraction_std',['normal','coil_leakage'])),
       'mix_correlation_boundary':boundary(values('mix_cmd_corr',['damper_stuck']),values('mix_cmd_corr',['normal','coil_leakage'])),
       'closed_drop_boundary_C':boundary(values('closed_valve_drop',['normal']),values('closed_valve_drop',['coil_leakage']))}
    obj={'method':'Development-only midpoint boundaries on command-response evidence; no probability model.',
         'classes':classes,'references':references,'thresholds':thresholds,
         'scope':'One simulated SDAHU, three candidate classes; temperature-inferred mixing fraction is not actual damper position. No BDG2 fault inference.',
         'fixed_gates':{'unique_operating_minutes_min':60,'mix_samples_min':12,'damper_cmd_std_min':.08,'closed_samples_min':12,'closed_fraction_min':.1},
         'excluded_channels':sorted(EXCLUDED)}
    if write:
        CALIBRATION_FILE.parent.mkdir(parents=True,exist_ok=True)
        CALIBRATION_FILE.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return obj
