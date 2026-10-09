"""Three distinct evidence levels; imports frozen model without modifying it.

Run on the 5090 host: python -X utf8 analysis/round24_three_level/run_validation.py
Full minute/hourly model responses stay in ignored working/. Committed outputs
are derived daily/monthly records, definitions, hashes and honest summaries.
"""
from __future__ import annotations
import argparse, hashlib, io, json, platform, subprocess, sys, time, zipfile
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from operation_planning import thermal_model as tm
from operation_planning.equipment import get_equipment
from operation_planning.weather import normalize_preceding_hour_payload

HERE=Path(__file__).parent
RAW=ROOT/'working/round24/sources'
WORK=ROOT/'working/round24/model_outputs'
OUT=ROOT/'operation_planning/results/round24_public_validation'
PROTOCOL=json.loads((HERE/'protocol.json').read_text(encoding='utf-8'))
VARS=['temperature_2m','relative_humidity_2m','surface_pressure','shortwave_radiation']

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,x):
    (OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def save_csv(name,df): df.to_csv(OUT/name,index=False,float_format='%.12g')
def corr(a,b):
    a,b=np.asarray(a,float),np.asarray(b,float)
    return float(np.corrcoef(a,b)[0,1]) if np.std(a)>0 and np.std(b)>0 else None
def metrics(obs,pred):
    o,p=np.asarray(obs,float),np.asarray(pred,float); e=p-o
    if len(o)<2 or o.mean()<=0 or not np.isfinite(o).all() or not np.isfinite(p).all(): raise ValueError('Invalid comparison denominator/data')
    return {'n_days':len(o),'proxy_observed_total_kwh':float(o.sum()),'model_total_kwh':float(p.sum()),
        'nmbe_percent_model_minus_proxy':float(e.sum()/((len(o)-1)*o.mean())*100),
        'cvrmse_percent':float(np.sqrt(np.sum(e**2)/(len(o)-1))/o.mean()*100),
        'denominator':'n-1 descriptive convention; no fitted-parameter DOF correction, not formal ASHRAE14 calibration',
        'pearson':corr(o,p)}

def normalized_weather(site):
    raw=json.loads((RAW/(site+'_weather.json')).read_text(encoding='utf-8'))
    h=raw['hourly']; times=pd.DatetimeIndex(h['time'])
    if site=='hyderabad_2019':
        start,end=pd.Timestamp('2019-05-10'),pd.Timestamp('2019-05-29');tz='Asia/Kolkata'
    elif site=='bangkok_2019':
        start,end=pd.Timestamp('2019-01-01'),pd.Timestamp('2020-01-01');tz='Asia/Bangkok'
    else:
        # Evaluate local-calendar 2024 (8784 physical hours), with true DST.
        start=pd.Timestamp('2024-01-01',tz='Europe/Madrid').tz_convert('UTC').tz_localize(None)
        end=pd.Timestamp('2025-01-01',tz='Europe/Madrid').tz_convert('UTC').tz_localize(None);tz='UTC'
    mask=(times>=start)&(times<end);boundary=times==end
    p={**raw,'hourly':{k:list(np.asarray(v)[mask]) for k,v in h.items()}}
    b={'hourly':{k:list(np.asarray(v)[boundary]) for k,v in h.items()}}
    n=normalize_preceding_hour_payload(p,calendar_start=start.isoformat(),calendar_end=end.isoformat(),boundary_payload=b)
    idx=pd.DatetimeIndex(n['time']).tz_localize(tz).as_unit('ns')
    if site=='madrid_2024':idx=idx.tz_convert('Europe/Madrid')
    frame=pd.DataFrame({v:n['hourly'][v] for v in VARS},index=idx)
    if not np.isfinite(frame.to_numpy(float)).all():raise ValueError('Weather missing/nonfinite')
    w={'time':[t.isoformat() for t in idx], 'hourly':{v:frame[v].tolist() for v in VARS},
       'source_file':(RAW/(site+'_weather.json')).relative_to(ROOT).as_posix(),
       'hash':sha(RAW/(site+'_weather.json')),'weather_normalization':n['_interval_semantics']}
    provenance={'site':site,'requested_model':'era5','response_model_identifier':'not returned; explicit single-model request recorded',
      'api_timezone':raw['timezone'],'analysis_timezone':str(idx.tz),'grid_latitude':raw['latitude'],'grid_longitude':raw['longitude'],
      'rows':len(idx),'first_interval_start':idx[0].isoformat(),
      'last_interval_end':(idx[-1]+pd.Timedelta(hours=1)).isoformat(),
      'interval_hours':1,'hash':w['hash'],'boundary':'independent actual next-hour response row; no wrap/copy/zero',
      'radiation':'right-labelled preceding-hour source shifted to physical interval, other variables retained at start',
      'dst':'Europe/Madrid offset preserved; repeated local clock hours have different offsets'}
    write(site+'_weather_context.json',provenance)
    return w,frame

def minute_weather(hourly,minute_index):
    hidx=hourly.index.asi8.astype(float)
    midx=minute_index.asi8.astype(float)
    # The final source boundary supplies interpolation, not a copied last row.
    raw=json.loads((RAW/'hyderabad_2019_weather.json').read_text(encoding='utf-8'))
    bidx=pd.DatetimeIndex(raw['hourly']['time']).tz_localize('Asia/Kolkata').as_unit('ns')
    h={}
    for v in VARS:
        if v=='shortwave_radiation':
            positions=hourly.index.get_indexer(minute_index.floor('h'))
            if (positions<0).any():raise ValueError('Missing radiation physical interval')
            h[v]=hourly[v].to_numpy()[positions].tolist()
        else:
            h[v]=np.interp(midx,bidx.asi8.astype(float),np.asarray(raw['hourly'][v],float)).tolist()
    return {'time':[t.isoformat() for t in minute_index],'hourly':h,
      'source_file':'working/round24/sources/hyderabad_2019_weather.json',
      'hash':sha(RAW/'hyderabad_2019_weather.json'),'weather_normalization':
      'instantaneous T/RH/pressure linear interpolation; hourly-mean GHI constant within correct physical hour; no measured indoor-state interpolation'}

def select_rooms(z):
    meta=pd.read_csv(io.BytesIO(z.read('dataset/Household information/ACDetails.csv')))
    selection=[];rooms=[]
    for _,r in meta.iterrows():
        i=int(r.HouseID); reasons=[]
        if r['AC(#)']!=1:reasons.append('more than one AC; primary-phase scope ambiguous')
        if r['primary AC type']!='Non-Inverter' or r['Type of system (primary AC)']!='split':reasons.append('not requested non-inverter split subset')
        if reasons:
            selection.append({'house_id':i,'included':False,'reasons':reasons});continue
        g=pd.read_csv(io.BytesIO(z.read(f'dataset/Garud/G{i:02d}.csv')))
        e=pd.read_csv(io.BytesIO(z.read(f'dataset/Envilog/E{i:02d}.csv')))
        gi=pd.DatetimeIndex(pd.to_datetime(g.datetime,dayfirst=True)).tz_localize('Asia/Kolkata').as_unit('ns')
        ei=pd.DatetimeIndex(pd.to_datetime(e.datetime,dayfirst=True)).tz_localize('Asia/Kolkata').as_unit('ns')
        if len(g)!=27360 or gi.has_duplicates or not gi.is_monotonic_increasing or not (np.diff(gi.as_unit('ns').asi8)==60_000_000_000).all():reasons.append('invalid minute grid')
        if ei.has_duplicates or not ei.is_monotonic_increasing:reasons.append('indoor timestamp duplicate/out-of-order; not silently repaired')
        if e.isna().any().any() or g.isna().any().any():reasons.append('missing source measurements')
        if len(rooms)>=3:reasons.append('after first three metadata/quality-eligible rooms; no outcome inspection for selection')
        included=not reasons
        selection.append({'house_id':i,'included':included,'reasons':reasons,'indoor_duplicate_rows':int(ei.duplicated(keep=False).sum()),
                         'indoor_monotonic':bool(ei.is_monotonic_increasing),'minute_records':len(g),'indoor_records':len(e)})
        if included:
            g.index=gi;e.index=ei;rooms.append((i,r,g,e))
    if not 2<=len(rooms)<=4:raise ValueError('No suitable 2-4-room subset')
    write('room_selection.json',selection)
    return rooms

def make_room(i,r,e):
    # Only source-supported changes; all unsourced office defaults remain
    # visible assumptions, not invented bedroom measurements.
    base=get_equipment('midea_msagbu12_mox201')
    cap=float(r['primary AC tonnage'])*3.516852842
    eq=replace(base,equipment_id=f'hyderabad_house_{i}_reference',brand='unknown',model='source tonnage + reference COP',
       rated_cooling_kw=cap,rated_input_kw=cap/base.cop,source='ACDetails.csv tonnage; COP3.4 reference, not BEE-star conversion',
       limitations=['no measured COP/SHR/part-load map','whole-house phase current; not AC submeter'])
    room=tm.RoomSpec(area_m2=20,equipment_id=eq.equipment_id,cooling_setpoint_c=float(r['primary AC setpoint as given by homeowner (oC)']),
       indoor_temp_c=float(e.iloc[0].Temperature),indoor_rh_percent=float(e.iloc[0].RelativeHumidity),pre_cool_minutes=0,
       weekdays_only=False,start_hour=0,end_hour=24)
    return room,eq

def simulate_labelled(w,room,eq,status):
    # Inject schedule and source equipment as analysis inputs ONLY. No equation,
    # controller or product file is changed. Patches are scoped and restored.
    schedule={t.isoformat():bool(v) for t,v in status.items()}
    with patch.object(tm,'_active',lambda ts,r:schedule[ts]),patch.object(tm,'get_equipment',lambda _:eq):
        result=tm.simulate_room(w,room)
    return result

def room_outputs(result,g,e,baseline):
    rows=result['rows']; idx=pd.DatetimeIndex([r['timestamp'] for r in rows]).tz_convert('Asia/Kolkata').as_unit('ns')
    phase=g['R'].reindex(idx).to_numpy(float)
    status=g['AC Status'].reindex(idx).to_numpy(float)
    proxy=np.maximum(phase-baseline,0)/1000*230*.9*status/60000 # W / (60 min * 1000)
    power=np.array([r['electric_power_w'] for r in rows]); energy=power/60000
    d=pd.DataFrame({'proxy_kwh':proxy,'model_kwh':energy,'on_minutes':status},index=idx).resample('D').sum()
    d['date']=[t.date().isoformat() for t in d.index]
    ends=idx+pd.Timedelta(minutes=1)
    modelT=pd.Series([r['indoor_temp_c'] for r in rows],index=ends)
    # Only exact sample instants are matched. Sensor clock jitter is not "fixed"
    # to improve agreement. Initial one-hour comparison is excluded.
    valid=e.index.intersection(ends)
    valid=valid[valid>=idx[0]+pd.Timedelta(hours=1)]
    previous=valid-pd.Timedelta(minutes=1)
    active=g['AC Status'].reindex(previous).to_numpy()==1
    valid=valid[active]
    t=pd.DataFrame({'measured_c':e.loc[valid,'Temperature'].to_numpy(float),
                    'model_c':modelT.loc[valid].to_numpy(float)},index=valid)
    t['date']=[x.date().isoformat() for x in t.index]
    return d,t

def room_metrics(d,t):
    m=metrics(d.proxy_kwh,d.model_kwh)
    err=t.model_c-t.measured_c
    m.update(temperature_samples=len(t),temperature_rmse_c=float(np.sqrt(np.mean(err**2))),
             temperature_bias_c=float(err.mean()),temperature_mae_c=float(np.abs(err).mean()))
    return m

def rooms_layer():
    w,hourly=normalized_weather('hyderabad_2019')
    z=zipfile.ZipFile(RAW/'dataset.zip');selected=select_rooms(z)
    bundles=[];definitions=[]
    for i,r,g,e in selected:
        if set(g['AC Status'].unique())!={0,1} or (g['R']<0).any():raise ValueError('Invalid current/tag')
        dev=g.index<pd.Timestamp('2019-05-19',tz='Asia/Kolkata')
        off=g.loc[dev & (g['AC Status']==0),'R']
        if off.empty:raise ValueError('No development OFF baseline')
        baseline=float(off.median());room,eq=make_room(i,r,e)
        mw=minute_weather(hourly,g.index)
        n=int(dev.sum());dw={**mw,'time':mw['time'][:n],'hourly':{v:mw['hourly'][v][:n] for v in VARS}}
        bundles.append((i,g,e,baseline,room,eq,mw,dw,n))
        definitions.append({'house_id':i,'phase':'R','tonnage':float(r['primary AC tonnage']),
          'star_rating':int(r['primary AC star rating']),'setpoint_c':room.cooling_setpoint_c,
          'room':asdict(room),'equipment':asdict(eq),'baseline_ma_dev_OFF_median':baseline,
          'initialization':'first indoor observation 2-3 minutes after start used as initial approximation; first hour excluded from temperature scoring',
          'supported_changes':['tonnage from ACDetails','reported homeowner setpoint, not time-varying remote-control log',
                               'actual AC ON/OFF labels as schedule','initial T/RH','20m2 paper average, not individually measured'],
          'unknowns':['individual room area/height/orientation/U/mass/occupancy/ventilation/internal gains',
                      'voltage/PF/COP/SHR/part-load performance','room microclimate and thermostat changes'],
          'schedule_boundary':'label ON does not mean compressor continuously ON; frozen demand model not compressor cycling model'})
    write('room_parameter_basis.json',definitions)
    # Report untuned first, before selecting the limited development-only fit.
    untuned_results={}; all_daily=[]; summaries=[];temp_summaries=[]
    for i,g,e,b,room,eq,mw,dw,n in bundles:
        result=simulate_labelled(mw,room,eq,g['AC Status']);d,t=room_outputs(result,g,e,b)
        untuned_results[i]=(d,t)
        p=WORK/f'house_{i}_untuned.json';p.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        devd=d[d.date<'2019-05-19'];devt=t[t.date<'2019-05-19']
        evald=d[d.date>='2019-05-19'];evalt=t[t.date>='2019-05-19']
        summaries.append({'house_id':i,'untuned_all':room_metrics(d,t),'untuned_development':room_metrics(devd,devt),
                          'untuned_evaluation':room_metrics(evald,evalt),'full_response_hash':sha(p)})
        d=d.copy();d['house_id']=i;d['variant']='untuned';d['period']=np.where(d.date<'2019-05-19','development','evaluation');all_daily.append(d)
        ts=t.groupby('date').agg(measured_c=('measured_c','mean'),model_c=('model_c','mean'),samples=('measured_c','size')).reset_index()
        ts['house_id']=i;ts['variant']='untuned';temp_summaries.append(ts)
    write('room_untuned_summary.json',summaries)
    save_csv('room_daily_untuned.csv',pd.concat(all_daily,ignore_index=True))
    trials=[]
    for mass in PROTOCOL['limited_tuning']['thermal_mass_kj_per_m2']:
        for u in PROTOCOL['limited_tuning']['insulation_u_w_m2k']:
            scores=[]
            for i,g,e,b,room,eq,mw,dw,n in bundles:
                res=simulate_labelled(dw,replace(room,thermal_mass_kj_per_m2=mass,insulation_u_w_m2k=u),eq,g['AC Status'].iloc[:n])
                d,t=room_outputs(res,g,e,b);m=room_metrics(d,t)
                scores.append(m['cvrmse_percent']/100+m['temperature_rmse_c']/2)
            trials.append({'mass':mass,'u':u,'development_score':float(np.mean(scores))})
    best=min(trials,key=lambda x:(x['development_score'],x['mass'],x['u']))
    frozen={'selected':best,'all_development_trials':trials,'selection_data_end':'2019-05-18T24:00 Asia/Kolkata',
            'evaluation_used_for_selection':False,'frozen_utc':datetime.now(timezone.utc).isoformat(),
            'note':'only two assumed envelope parameters; shared fit across rooms, still proxy-based and no independently measured room area'}
    write('room_limited_fit_freeze.json',frozen)
    for row,(i,g,e,b,room,eq,mw,dw,n) in zip(summaries,bundles):
        res=simulate_labelled(mw,replace(room,thermal_mass_kj_per_m2=best['mass'],insulation_u_w_m2k=best['u']),eq,g['AC Status'])
        d,t=room_outputs(res,g,e,b);p=WORK/f'house_{i}_limited_fit.json';p.write_text(json.dumps(res,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        row.update(limited_fit_evaluation=room_metrics(d[d.date>='2019-05-19'],t[t.date>='2019-05-19']),
                   limited_fit_all=room_metrics(d,t),limited_fit_response_hash=sha(p))
        row['multiplier_sensitivity_untuned_evaluation']=[{'multiplier':s,**metrics(untuned_results[i][0].query("date >= '2019-05-19'").proxy_kwh*s,
          untuned_results[i][0].query("date >= '2019-05-19'").model_kwh)} for s in [.9,1,1.1]]
        d=d.copy();d['house_id']=i;d['variant']='limited_fit';d['period']=np.where(d.date<'2019-05-19','development','evaluation');all_daily.append(d)
        ts=t.groupby('date').agg(measured_c=('measured_c','mean'),model_c=('model_c','mean'),samples=('measured_c','size')).reset_index()
        ts['house_id']=i;ts['variant']='limited_fit';temp_summaries.append(ts)
        # Retain all operating 5-min temperature pairs (not complete raw responses).
        pairs=pd.concat([untuned_results[i][1].rename(columns={'model_c':'untuned_c'}),t[['model_c']].rename(columns={'model_c':'limited_fit_c'})],axis=1)
        pairs.insert(0,'timestamp',[x.isoformat() for x in pairs.index]);save_csv(f'room_{i}_temperature_pairs.csv',pairs)
    write('room_summary.json',{'selected_house_ids':[b[0] for b in bundles],'dates':'2019-05-10 through 2019-05-28 IST',
      'licence':'figshare v3 CC0','source_year':'2019 from all selected CSV timestamps; paper body 2021 is inconsistent',
      'rooms_with_individually_complete_physical_parameters':0,'proxy_not_submeter':True,
      'untuned_precedes_fitting':True,'limited_fit':best,'rooms':summaries,
      'calibration_established':False,'label_dependency':'ON/OFF labels manually derived from current and room T; conditional temperature comparison not an independent thermostat experiment'})
    save_csv('room_daily_comparison.csv',pd.concat(all_daily,ignore_index=True));save_csv('room_daily_operating_temperature.csv',pd.concat(temp_summaries,ignore_index=True))

def office_result(site):
    w,h=normalized_weather(site);result=tm.simulate_room(w,tm.RoomSpec())
    p=WORK/(site+'_office_full.json');p.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    # Named zones plus nanosecond storage avoid pandas 3 mixed-resolution
    # alignment corner cases. UTC instants/physical intervals remain identical.
    idx=pd.DatetimeIndex(pd.to_datetime([r['timestamp'] for r in result['rows']],utc=True)).tz_convert(h.index.tz).as_unit('ns')
    m=pd.DataFrame({'model_kwh':[r['electric_power_w']/1000 for r in result['rows']],
                    'outdoor_temp_c':h.temperature_2m.to_numpy()},index=idx)
    write(site+'_model_context.json',{'room':result['room'],'equipment':result['equipment'],'response_hash':sha(p),
        'full_response_file':p.relative_to(ROOT).as_posix(),'physical_hours':len(m),
        'scope':'one uncalibrated default office room, not matched building size; cooling-only; no fitting'})
    return m

def relative_slope(y,t):
    y,t=np.array(y,float),np.array(t,float)
    slope=float(np.polyfit(t,y,1)[0]);mean=float(y.mean())
    return {'daily_energy_mean_kwh':mean,'slope_kwh_per_c':slope,'relative_slope_per_c':slope/mean,
            'pearson':corr(t,y),'n_days':len(y),'confounders':'weekday-only, no occupancy/solar/season adjustment; descriptive association, not causal cooling coefficient'}

def cu_layer():
    path=ROOT/'working/round23/sources/2019Floor2.csv'
    columns=pd.read_csv(path,nrows=0).columns; ac=[c for c in columns if '_AC' in c]
    d=pd.read_csv(path,usecols=['Date']+ac);idx=pd.DatetimeIndex(pd.to_datetime(d.pop('Date'))).tz_localize('Asia/Bangkok').as_unit('ns')
    if len(d)!=525600 or idx.has_duplicates or not (np.diff(idx.as_unit('ns').asi8)==60_000_000_000).all():raise ValueError('CU grid invalid')
    a=d.to_numpy(float);valid=np.isfinite(a).all(axis=1)&(a>=0).all(axis=1)
    power=pd.Series(np.where(valid,a.sum(axis=1),np.nan),index=idx)
    validcounts=power.resample('D').count();weekday=validcounts.index.weekday<5
    accepted=validcounts.index[(validcounts==1440)&weekday]
    if len(accepted)<30:raise ValueError('Insufficient complete common weekdays')
    measured=power.resample('h').sum(min_count=60)/60
    model=office_result('bangkok_2019')
    compare=pd.DataFrame({'measured_kwh':measured,'model_kwh':model.model_kwh,'outdoor_temp_c':model.outdoor_temp_c})
    compare=compare[compare.index.normalize().isin(accepted)]
    if compare.isna().any().any():raise ValueError('Accepted common days incomplete')
    means=compare[['measured_kwh','model_kwh']].groupby(compare.index.normalize()).transform('mean')
    normal=compare[['measured_kwh','model_kwh']]/means
    shape=normal.groupby(normal.index.hour).mean();shape['hour']=shape.index
    save_csv('cu_normalized_weekday_profile.csv',shape.reset_index(drop=True))
    days=compare.resample('D').agg(measured_kwh=('measured_kwh','sum'),model_kwh=('model_kwh','sum'),outdoor_temp_c=('outdoor_temp_c','mean')).loc[accepted]
    days.insert(0,'date',[t.date().isoformat() for t in days.index]);save_csv('cu_complete_weekdays.csv',days)
    save_csv('cu_daily_quality.csv',pd.DataFrame({'date':[t.date().isoformat() for t in validcounts.index],
      'joint_valid_minutes':validcounts.to_numpy(),'is_weekday':weekday,'accepted':validcounts.index.isin(accepted)}))
    write('cu_summary.json',{'floor':2,'ac_channels':ac,'year':2019,'source_license':'CC BY 4.0, figshare v6',
       'accepted_weekdays':len(accepted),'all_weekdays':int(weekday.sum()),'incomplete_weekdays_excluded':int(weekday.sum())-len(accepted),
       'normalized_hourly_shape_correlation':corr(shape.measured_kwh,shape.model_kwh),
       'normalized_shape_rmse':float(np.sqrt(np.mean((shape.measured_kwh-shape.model_kwh)**2))),
       'measured_relative_sensitivity':relative_slope(days.measured_kwh,days.outdoor_temp_c),
       'model_relative_sensitivity':relative_slope(days.model_kwh,days.outdoor_temp_c),
       'calibration_established':False,'validation_scope':'floor-level AC weekday shape and temperature association only; scale removed, unknown zones/schedule/capacity remain'})

def madrid_layer():
    d=pd.read_csv(ROOT/'working/round23/sources/madrid_monthly.csv',sep=';',dtype=str,encoding='utf-8-sig')
    d=d[(d['AÑO']=='2024') & (d.TIPOEDIFICIO=='Centros administrativos')].copy()
    d['value']=pd.to_numeric(d.CONSUMO.str.replace(',','.',regex=False).str.strip(),errors='coerce')
    d['month']=pd.to_numeric(d.MES,errors='coerce')
    all_buildings=[];selected=[]
    for name,g in d.groupby('EDIFICIO',sort=True):
        reason=[];elec=g[g.CLASE=='Energía activa'];gas=g[g.CLASE=='Gas']
        general=elec[elec.SENSOR.str.contains('General|Consumo total|Consumo Total|Contador TL|Contador]',regex=True,na=False)]
        if gas.empty:reason.append('no same-name gas measurement')
        if general.empty:reason.append('no unambiguous general active-energy meter')
        if general.SENSOR.nunique()!=1:reason.append('general meter ambiguous/renamed or absent; no parent-child summation')
        if gas.SENSOR.nunique()!=1:reason.append('gas meter ambiguous or absent')
        for x,label,units in [(general,'electricity',{'kWh'}),(gas[gas.month.isin([1,2,12])],'gas winter',{'kWh','m3'})]:
            required=set(range(1,13)) if label=='electricity' else {1,2,12}
            if len(x)!=len(required) or set(x.month)!=required or x.month.duplicated().any():reason.append(label+' missing/duplicate months')
            if x.value.isna().any() or (x.value<0).any():reason.append(label+' nonnumeric/missing/negative readings')
            if not set(x.UNIDADES).issubset(units):reason.append(label+' unsupported units')
            if label=='gas winter' and not (x.value>0).any():reason.append('no observed positive winter gas usage')
        if gas.month.duplicated().any():reason.append('duplicate gas-month scope')
        all_buildings.append({'building':name,'included':not reason,'reasons':list(dict.fromkeys(reason)),
          'electricity_records':len(general),'gas_records':len(gas),'electricity_sensors':general.SENSOR.nunique(),'gas_sensors':gas.SENSOR.nunique()})
        if not reason:selected.append((name,general.sort_values('month'),gas.sort_values('month')))
    write('madrid_building_selection.json',all_buildings)
    if len(selected)<2:raise ValueError('Insufficient gas-metered office buildings')
    model=office_result('madrid_2024')
    monthly=model.groupby(model.index.month).agg(model_kwh=('model_kwh','sum'))
    cdd=np.maximum(model.outdoor_temp_c.to_numpy()-18,0)/24
    monthly['cdd18']=pd.Series(cdd,index=model.index).groupby(model.index.month).sum()
    monthly['model_cooling_fraction']=monthly.model_kwh/monthly.model_kwh.sum()
    records=[];stats=[]
    for name,elec,gas in selected:
        e=elec.set_index('month').value.reindex(range(1,13)).to_numpy(float)
        baseline=float(np.mean(e[np.array(PROTOCOL['baseline_months'])-1]));delta=e-baseline;positive=np.maximum(delta,0)
        if positive.sum()<=0:raise ValueError('Proxy normalization denominator zero')
        fraction=positive/positive.sum();jja=np.array([5,6,7]);winter=np.array([0,1,11])
        s={'building':name,'baseline_monthly_kwh':baseline,'summer_signed_increment_kwh':float(delta[jja].sum()),
           'summer_positive_excess_fraction':float(fraction[jja].sum()),'winter_positive_excess_fraction':float(fraction[winter].sum()),
           'signed_increment_cdd18_correlation_12_months':corr(delta,monthly.cdd18),
           'positive_excess_shape_correlation':corr(fraction,monthly.model_cooling_fraction),
           'gas_units':gas.UNIDADES.iloc[0],'gas_winter_positive':bool((gas[gas.month.isin([1,2,12])].value>0).any()),
           'meter':elec.SENSOR.iloc[0],'gas_meter':gas.SENSOR.iloc[0]}
        stats.append(s)
        for month in range(1,13):
            records.append({'building':name,'month':month,'electricity_kwh':e[month-1],
              'gas_value':float(gas.set_index('month').value.get(month,np.nan)),'gas_units':gas.UNIDADES.iloc[0],
              'baseline_monthly_kwh':baseline,'signed_excess_kwh':delta[month-1],'positive_excess_kwh':positive[month-1],
              'positive_excess_fraction':fraction[month-1],'model_cooling_fraction':float(monthly.loc[month,'model_cooling_fraction']),
              'cdd18':float(monthly.loc[month,'cdd18'])})
    save_csv('madrid_building_months.csv',pd.DataFrame(records));save_csv('madrid_building_statistics.csv',pd.DataFrame(stats))
    save_csv('madrid_model_months.csv',monthly.assign(month=monthly.index).reset_index(drop=True))
    dist=lambda v:{'min':float(np.min(v)),'median':float(np.median(v)),'max':float(np.max(v))}
    write('madrid_summary.json',{'year':2024,'all_administrative_building_names':len(all_buildings),'included_buildings':len(stats),
       'excluded_building_names':len(all_buildings)-len(stats),'buildings':[s['building'] for s in stats],
       'transition_baseline_months':PROTOCOL['baseline_months'],'summer_months':[6,7,8],
       'signed_increment_vs_cdd18_correlation':dist([s['signed_increment_cdd18_correlation_12_months'] for s in stats]),
       'positive_excess_shape_correlation':dist([s['positive_excess_shape_correlation'] for s in stats]),
       'summer_positive_excess_fraction':dist([s['summer_positive_excess_fraction'] for s in stats]),
       'model_summer_cooling_fraction':float(monthly.loc[[6,7,8],'model_cooling_fraction'].sum()),
       'winter_excess_warning_buildings':sum(s['winter_positive_excess_fraction']>0 for s in stats),
       'gas_boundary':'Gas metering does NOT prove predominant gas heating; winter electricity excess and other seasonal loads remain visible',
       'calibration_established':False,'scope':'one city, selected general meters, gas-matched administrative buildings; seasonal proxies only'})

def main():
    global OUT
    p=argparse.ArgumentParser();p.add_argument('--layer',choices=['rooms','cu','madrid','all'],default='all')
    p.add_argument('--output-dir',help='New repository-relative directory for an independent rerun; published evidence never overwritten')
    args=p.parse_args()
    if args.output_dir:
        OUT=(ROOT/args.output_dir).resolve()
        if not OUT.is_relative_to(ROOT):raise ValueError('Output must remain inside this repository')
    if list(OUT.glob('run_manifest_*.json')):
        raise ValueError('Completed evidence exists; rerun with --output-dir working/round24/reproduce_NEW_ID')
    OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
    start=datetime.now(timezone.utc).isoformat();tic=time.perf_counter()
    paths=list((ROOT/'operation_planning').glob('*.py'));before={x.relative_to(ROOT).as_posix():sha(x) for x in paths}
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    try:
        for name,func in [('rooms',rooms_layer),('cu',cu_layer),('madrid',madrid_layer)]:
            if args.layer in ('all',name):
                print('RUN',name,flush=True);f=time.perf_counter();func();print('DONE',name,round(time.perf_counter()-f,3),flush=True)
        assert before=={x.relative_to(ROOT).as_posix():sha(x) for x in paths},'Frozen product changed'
        manifest={'run_id':'round24-'+args.layer+'-'+start.replace(':',''), 'source_commit':commit,
          'workspace_status_at_start':status,'machine_role':'5090','gpu_command':['nvidia-smi','--query-gpu=name,driver_version','--format=csv,noheader'],
          'gpu_output':subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version','--format=csv,noheader'],text=True).strip(),
          'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'model':'no LLM called',
          'command':['python','-X','utf8','analysis/round24_three_level/run_validation.py','--layer',args.layer],
          'start_utc':start,'end_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.perf_counter()-tic,
          'exit_status':0,'protocol_sha256':sha(HERE/'protocol.json'),'frozen_product_hashes':before,
          'outputs':{x.relative_to(ROOT).as_posix():sha(x) for x in sorted(OUT.glob('*')) if x.is_file() and not x.name.startswith('run_manifest')},
          'full_outputs_ignored':{x.relative_to(ROOT).as_posix():sha(x) for x in sorted(WORK.glob('*.json'))},
          'claims':'uncalibrated comparisons and descriptive associations; no real savings/accuracy/participant claims'}
        write('run_manifest_'+args.layer+'.json',manifest)
    except Exception as exc:
        write('failed_'+args.layer+'_'+datetime.now(timezone.utc).strftime('%H%M%S')+'.json',
          {'start_utc':start,'source_commit':commit,'error_type':type(exc).__name__,'error':str(exc),'command':sys.argv})
        raise

if __name__=='__main__':main()
