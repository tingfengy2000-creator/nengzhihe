"""Single quality contract for API, evidence, UI and human-readable export."""
from datetime import datetime
import math

TEMPS={'SA_TEMP','SA_TEMPSPT','OA_TEMP','MA_TEMP','RA_TEMP',*[f'ZONE_TEMP_{i}' for i in range(1,6)]}
FLAGS={'SF_SPD_DM','RF_SPD_DM'}
COMMANDS={'SF_CS','RF_CS','OA_DMPR_DM','RA_DMPR_DM','CHWC_VLV_DM'}
ALLOWED=TEMPS|FLAGS|COMMANDS
BRANCH_POINTS={'air_path':['OA_TEMP','RA_TEMP','MA_TEMP','OA_DMPR_DM','SF_SPD_DM','RF_SPD_DM'],
 'coil_response':['MA_TEMP','SA_TEMP','CHWC_VLV_DM','SF_CS','SF_SPD_DM','RF_SPD_DM'],
 'operating_context':['OA_TEMP','OA_DMPR_DM','CHWC_VLV_DM','SF_CS','RF_CS','SF_SPD_DM','RF_SPD_DM']}
def finite(v):
    try:return v is not None and math.isfinite(float(v))
    except (TypeError,ValueError):return False

def inspect_case(case):
    ts=case.get('timestamps',[]);series=case.get('series',{});lbnl=case.get('family')=='lbnl'
    expected=5 if lbnl else 60;declared=case.get('sample_interval_minutes');issues=[];time_errors=[];unit_errors=[]
    invalid_lengths=[k for k,v in series.items() if not isinstance(v,list) or len(v)!=len(ts)]
    missing=sum(sum(not finite(x) for x in v) for v in series.values() if isinstance(v,list));cells=sum(len(v) for v in series.values() if isinstance(v,list))
    groups={}
    for i,t in enumerate(ts):groups.setdefault(str(t),[]).append(i)
    duplicates=len(ts)-len(groups);conflicts=[]
    if not invalid_lengths:
        for t,ids in groups.items():
            signatures={tuple(str(series[k][i]) for k in sorted(series)) for i in ids}
            if len(signatures)>1:conflicts.append(t)
    if declared!=expected:time_errors.append(f'仅支持声明{expected}分钟的标准输入，当前为{declared}')
    parsed=[]
    try:
        parsed=[datetime.fromisoformat(t) for t in ts]
        awareness={t.tzinfo is not None for t in parsed}
        if len(awareness)>1:raise ValueError('mixed timezone')
        if any(b<a for a,b in zip(parsed,parsed[1:])):time_errors.append('时间戳未按时间递增排列')
    except (ValueError,TypeError):time_errors.append('时间戳格式错误或混合有时区/无时区时间');parsed=[]
    unique=sorted(set(parsed));deltas=[(b-a).total_seconds() for a,b in zip(unique,unique[1:])]
    bad_deltas=[d for d in deltas if d<expected*60 or abs(d/(expected*60)-round(d/(expected*60)))>1e-8]
    gaps=[d for d in deltas if d>expected*60 and d not in bad_deltas]
    if bad_deltas:time_errors.append(f'{len(bad_deltas)}个实际时间间隔与声明{expected}分钟不一致')
    if not ts:time_errors.append('没有时间记录')
    if len(unique)<2:time_errors.append('不足两个独立时刻，无法核验采样间隔')
    if lbnl:
        units=case.get('units',{})
        unit_errors=[k for k in series if k in TEMPS and units.get(k)!='degC' or k in FLAGS and units.get(k)!='binary' or k in COMMANDS and units.get(k)!='fraction']
    disallowed=sorted(set(series)-ALLOWED) if lbnl else []
    range_errors=[k for k in (FLAGS|COMMANDS)&set(series) if any(finite(x) and not -1e-7<=float(x)<=1+1e-7 for x in series[k])] if lbnl else []
    missing_points={a:[k for k in keys if k not in series or not any(finite(x) for x in series[k])] for a,keys in BRANCH_POINTS.items()} if lbnl else {}
    def issue(code,label,detail,count=None):
        row={'code':code,'label':label,'detail':detail}
        if count is not None:row['count']=count
        issues.append(row)
    if duplicates:issue('duplicate_timestamp','时间戳重复','只允许删除完全相同记录；重复不能增加有效运行时长。',duplicates)
    if conflicts:issue('conflicting_timestamp','同一时间戳存在冲突数值','不能自动择一，需要核对原始记录。',len(conflicts))
    if missing:issue('missing_values','监测值缺失','缺测保留，不填为零或正常。',missing)
    if any(missing_points.values()):issue('missing_points','部分分支缺少必要点位','；'.join(a+': '+', '.join(v) for a,v in missing_points.items() if v))
    if invalid_lengths:issue('length','通道长度不一致',', '.join(invalid_lengths))
    if unit_errors:issue('unit_mismatch','单位声明不符合标准',', '.join(unit_errors)+'；需在导入映射中显式转换，不能只改标签。')
    if time_errors:issue('time_axis','时间轴不合格','；'.join(time_errors))
    if gaps:issue('time_gaps','时间记录存在缺口','缺口不计为运行时长，连续窗口在缺口处重新开始。',len(gaps))
    if disallowed:issue('unsupported_points','包含未允许的点位',', '.join(disallowed))
    if range_errors:issue('out_of_range','指令或启停状态超出范围',', '.join(range_errors))
    hard=bool(invalid_lengths or conflicts or unit_errors or time_errors or disallowed or range_errors)
    operating=0
    if not time_errors and not invalid_lengths and lbnl:
        for t,indices in groups.items():
            if t in conflicts:continue
            i=indices[0]
            if all(k in series and finite(series[k][i]) and float(series[k][i])>=.99 for k in FLAGS):operating+=expected
    return {'status':'invalid' if hard else ('needs_review' if issues else 'passed'),
      'quality_status':'invalid' if hard else ('needs_review' if issues else 'passed'),
      'label':'记录不可用于设备判断' if hard else ('存在记录问题' if issues else '记录检查通过'),
      'issues':issues,'rows':len(ts),'unique_rows':len(groups),'duplicates':duplicates,'missing':missing,
      'missing_fraction':round(missing/max(cells,1),6),'valid_schema':not invalid_lengths,'valid_for_diagnosis':not hard,
      'unit_errors':unit_errors,'time_errors':time_errors,'time_valid':not time_errors,'range_errors':range_errors,
      'conflicting_timestamps':len(conflicts),'missing_points':missing_points,'declared_interval_minutes':declared,
      'actual_interval_seconds':sorted(set(deltas))[:12],'bad_interval_count':len(bad_deltas),'gap_count':len(gaps),
      'timestamp_span_minutes':round((unique[-1]-unique[0]).total_seconds()/60,6) if len(unique)>1 else 0,
      'unique_operating_minutes':operating,'duration_basis':'Only validated regular intervals count; final sample represents one declared interval. Gaps and duplicates add no duration.',
      'note':'记录检查通过不代表设备正常；数据质量与设备证据分别判断。'}
