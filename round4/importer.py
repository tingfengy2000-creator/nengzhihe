"""Bounded CSV intake for the documented public LBNL SDAHU simulation profile."""
from pathlib import Path
from datetime import datetime
import csv,io,json,hashlib,math,uuid
import pandas as pd
from quality import TEMPS,FLAGS,COMMANDS,ALLOWED,inspect_case
ROOT=Path(__file__).resolve().parent
FIELDS=['SA_TEMP','SA_TEMPSPT','OA_TEMP','MA_TEMP','RA_TEMP','SF_SPD_DM','RF_SPD_DM','SF_CS','RF_CS','OA_DMPR_DM','RA_DMPR_DM','CHWC_VLV_DM',*[f'ZONE_TEMP_{i}' for i in range(1,6)]]
FORBIDDEN={'OA_DMPR','RA_DMPR','CHWC_VLV','OA_CFM','RA_CFM','SA_CFM','SF_SPD','RF_SPD','SYS_CTL','label','fault','severity','target','SF_WAT','RF_WAT','SA_SP','SA_SPSPT'}
def parse_text(text):
    if not isinstance(text,str) or len(text.encode('utf-8'))>8*1024*1024:raise ValueError('只接受不超过8 MiB的UTF-8 CSV日片段')
    if '\x00' in text:raise ValueError('不支持含NUL或二进制内容')
    reader=csv.reader(io.StringIO(text.lstrip('\ufeff')));header=next(reader,[])
    if not header or len(header)>80 or len(set(header))!=len(header):raise ValueError('CSV表头为空、重复或超过80列')
    rows=[row for row in reader if row]
    if not 2<=len(rows)<=3000:raise ValueError('只支持2—3000行的单日原始片段，年度文件请先按日导出')
    if any(len(row)!=len(header) for row in rows):raise ValueError('CSV行列数不一致')
    return header,rows

def preview(text):
    header,rows=parse_text(text)
    return {'columns':header,'sample_rows':rows[:5],'row_count':len(rows),'fields':FIELDS,
      'default_mapping':{k:k if k in header else '' for k in FIELDS},'time_column':'Datetime' if 'Datetime' in header else header[0],
      'ignored_by_default':[k for k in header if k not in FIELDS and k!='Datetime'],
      'scope':'只接入当前LBNL单风道机组公开仿真CSV；非真实建筑通用导入。1分钟完整原始桶显式均值为5分钟，或原有5分钟数据；温度degF/degC、指令fraction/percent。'}

def convert(text,mapping,time_column,units,source_interval,profile,save=True):
    if profile!='lbnl_sdahu_public_2022':raise ValueError('不支持其他设备/真实建筑配置，仅接受LBNL SDAHU公开仿真配置')
    header,rows=parse_text(text)
    if time_column not in header:raise ValueError('时间列不存在')
    if type(source_interval)!=int or source_interval not in (1,5):raise ValueError('原始采样间隔仅支持1或5分钟')
    if not isinstance(mapping,dict) or set(mapping)-ALLOWED:raise ValueError('映射包含不支持的目标点位')
    chosen={k:v for k,v in mapping.items() if v}
    if not chosen:raise ValueError('至少映射一个已知点位，缺点位会在核验分支中明确标记')
    if len(set(chosen.values()))!=len(chosen):raise ValueError('不能把同一源列同时映射到多个点位')
    if any(v not in header or v==time_column for v in chosen.values()):raise ValueError('映射列不存在或与时间列重用')
    if any(v in FORBIDDEN or any(s in v.lower() for s in ['fault','label','severity']) for v in chosen.values()):raise ValueError('实际位置反馈、故障标签/设置及非Basic字段不允许映射为诊断输入')
    times=[];values={k:[] for k in chosen};unknown=[]
    for k in chosen:
        allowed=['degF','degC'] if k in TEMPS else (['binary'] if k in FLAGS else ['fraction','percent'])
        if units.get(k) not in allowed:raise ValueError(k+'单位只支持 '+','.join(allowed))
    for n,row in enumerate(rows,2):
        try:
            t=datetime.fromisoformat(row[header.index(time_column)])
            if t.tzinfo is not None:raise ValueError('timezone')
            times.append(t)
        except ValueError:raise ValueError(f'第{n}行时间不可解析；本配置只支持仿真原生无时区ISO时间，不作时区推断')
        for k,col in chosen.items():
            raw=row[header.index(col)].strip()
            if raw.lower() in {'','nan','na','null','none'}:v=float('nan')
            else:
                try:v=float(raw)
                except ValueError:raise ValueError(f'第{n}行{col}不是数值')
                if not math.isfinite(v):raise ValueError(f'第{n}行{col}为非有限数值')
            if k in TEMPS and units[k]=='degF':v=(v-32)*5/9
            if k in COMMANDS and units[k]=='percent':v/=100
            if k in FLAGS|COMMANDS and math.isfinite(v) and not -1e-7<=v<=1+1e-7:raise ValueError(k+'归一化值超出0—1范围')
            values[k].append(v)
    if any(b<=a for a,b in zip(times,times[1:])):raise ValueError('原始导入必须时间递增且无重复；请核对原始文件，不能用重采样隐藏重复/冲突')
    if len({t.date() for t in times})!=1:raise ValueError('只支持单日片段，不接收跨日或年度数据')
    delta=[(b-a).total_seconds() for a,b in zip(times,times[1:])]
    if any(d<source_interval*60 or d%(source_interval*60)!=0 for d in delta):raise ValueError('实际时间间隔与原始采样间隔声明不一致，拒绝累计时长')
    if any(t.second or t.microsecond or (source_interval==5 and t.minute%5) for t in times):raise ValueError('时间必须对齐声明的分钟/5分钟采样栅格')
    frame=pd.DataFrame(values,index=pd.DatetimeIndex(times))
    if source_interval==1:
        counts=frame.resample('5min').size()
        if any(n not in (0,5) for n in counts):raise ValueError('1分钟重采样存在不足5个真实时刻的桶，不能把部分分钟充作5分钟；请补齐或截取完整桶')
        # A present timestamp is not proof that every point was measured.
        # Preserve a missing input cell as an unavailable five-minute value.
        valid_counts=frame.resample('5min').count()
        frame=frame.resample('5min').mean().mask(valid_counts<5)
        frame=frame.loc[counts==5]
    timestamps=frame.index.strftime('%Y-%m-%dT%H:%M:%S').tolist()
    source_sha=hashlib.sha256(text.encode('utf-8')).hexdigest();cid='IMP-'+uuid.uuid4().hex[:16].upper()
    c={'id':cid,'family':'lbnl','origin':'simulated','split':'import','title':'公开CSV导入核验',
       'description':'导入LBNL单风道机组公开仿真日片段；没有新增真实建筑部署或独立验证。',
       'source_ref':'lbnl_sdahu_2022','sample_interval_minutes':5,'timezone':'source naive simulation clock',
       'timestamps':timestamps,'series':{k:[None if pd.isna(v) else round(float(v),5) for v in frame[k]] for k in chosen},
       'units':{k:'degC' if k in TEMPS else ('binary' if k in FLAGS else 'fraction') for k in chosen},
       'perturbation':{'type':'none','origin':'none','description':'未人为改变源数据'},
       'attribution':'Granderson et al. LBNL SDAHU public simulation, CC BY 4.0.',
       'import_provenance':{'profile':profile,'source_sha256':source_sha,'input_rows':len(rows),'output_rows':len(frame),
          'source_interval_minutes':source_interval,'target_interval_minutes':5,'time_column':time_column,
          'mapping':chosen,'source_units':{k:units[k] for k in chosen},'ignored_columns':[k for k in header if k not in chosen.values() and k!=time_column],
          'transform':'Explicit (F-32)*5/9 or percent/100; complete 1-minute buckets averaged to 5-minute only when all five point values exist. Missing cells remain missing. No interpolation or hidden label use.'}}
    q=inspect_case(c)
    if not q['valid_for_diagnosis']:raise ValueError('导入后的质量校验不通过：'+'；'.join(x['detail'] for x in q['issues']))
    if save:
        p=ROOT/'data/imports';p.mkdir(exist_ok=True)
        (p/(cid+'.json')).write_text(json.dumps(c,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        (p/(cid+'.source.csv')).write_text(text,encoding='utf-8')
    return c
