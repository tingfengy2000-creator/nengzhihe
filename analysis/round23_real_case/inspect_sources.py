"""Public measurements: scope/coverage audit, not a model calibration.

Run on the 5090 host: python -X utf8 -m analysis.round23_real_case.inspect_sources
No planning API, weather acquisition, model fitting or backend mutation occurs.
"""
from __future__ import annotations
import calendar
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'working/round23/sources'
OUT = ROOT / 'operation_planning/results/round23_case_admission'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)+'\n', encoding='utf-8')


def cu_audit():
    frame = pd.read_csv(RAW/'2019Floor2.csv')
    times = pd.to_datetime(frame.Date, format='ISO8601', errors='raise')
    expected = pd.date_range('2019-01-01', '2020-01-01', freq='min', inclusive='left')
    # Check ordering and exact coverage before deriving any energy.
    assert times.equals(pd.Series(expected, name='Date'))
    assert not times.duplicated().any()
    assert (times.diff().dropna().dt.total_seconds() == 60).all()
    power = [c for c in frame if c.endswith('(kW)')]
    ac = [c for c in power if '_AC' in c]
    assert len(ac) == 16 and len(power) == 24
    numeric = frame.drop(columns='Date').apply(pd.to_numeric, errors='raise')
    values = numeric.to_numpy(dtype=float)
    valid = np.isfinite(values)
    quality = []
    monthly = []
    for i, col in enumerate(numeric):
        x = values[:, i]
        mask = valid[:, i] & (x >= 0)
        if col.endswith('(RH%)'):
            mask &= x <= 100
        finite_values = x[valid[:, i]]
        quality.append({'channel': col, 'expected_samples': len(frame), 'finite_samples': int(valid[:,i].sum()),
                        'missing_or_nonfinite': int((~valid[:,i]).sum()), 'negative_samples': int((x < 0).sum()),
                        'valid_samples': int(mask.sum()), 'coverage_fraction': float(mask.mean()),
                        'minimum': float(finite_values.min()), 'maximum': float(finite_values.max()),
                        'all_finite_values_zero': bool(np.all(finite_values == 0)),
                        'unit': 'kW' if col in power else ('degC' if '(degC)' in col else 'percent' if '(RH%)' in col else 'lux')})
        for month in range(1,13):
            monthmask = times.dt.month.to_numpy() == month
            observed = mask & monthmask
            count = int(monthmask.sum())
            row = {'month': f'2019-{month:02d}', 'channel':col, 'expected_minutes':count,
                   'valid_minutes': int(observed.sum()), 'missing_or_invalid_minutes': int((monthmask & ~mask).sum()),
                   'coverage_fraction': float(observed.sum()/count)}
            if col in power:
                # A one-minute sample is held constant for its corresponding
                # minute. Source does not establish interval-averaged metering.
                # Only valid samples are integrated; no unknown minute is zeroed.
                row['observed_energy_kwh'] = float(x[observed].sum()/60)
                row['complete_month_energy_kwh'] = row['observed_energy_kwh'] if observed.sum()==count else None
            monthly.append(row)
    pd.DataFrame(quality).to_csv(OUT/'cu_channel_quality.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(monthly).to_csv(OUT/'cu_monthly_coverage.csv',index=False,encoding='utf-8-sig')
    # Sum only jointly observed channels; pandas skipna summation is forbidden.
    ac_values = numeric[ac].to_numpy(dtype=float)
    jointly_valid = np.isfinite(ac_values).all(axis=1) & (ac_values >= 0).all(axis=1)
    records = []
    for month in range(1,13):
        mm = times.dt.month.to_numpy() == month
        both = jointly_valid & mm
        records.append({'month':f'2019-{month:02d}', 'expected_minutes':int(mm.sum()),
                        'jointly_valid_ac_minutes':int(both.sum()), 'coverage_fraction':float(both.sum()/mm.sum()),
                        'observed_all_16_ac_energy_kwh':float(ac_values[both].sum()/60),
                        'complete_month_energy_kwh':float(ac_values[both].sum()/60) if both.sum()==mm.sum() else None})
    pd.DataFrame(records).to_csv(OUT/'cu_floor2_ac_observed_months.csv',index=False,encoding='utf-8-sig')
    # Fixed chronological demonstration, chosen without model fit or best match.
    sample = (times >= pd.Timestamp('2019-07-01')) & (times < pd.Timestamp('2019-07-08'))
    hourly = []
    for date in pd.date_range('2019-07-01', '2019-07-08',freq='h',inclusive='left'):
        mask = (times >= date) & (times < date+pd.Timedelta(hours=1))
        x = numeric.loc[mask, 'z2_AC2(kW)'].to_numpy(dtype=float)
        ok = np.isfinite(x) & (x >= 0)
        hourly.append({'interval_start_local':date.isoformat(), 'interval_end_local':(date+pd.Timedelta(hours=1)).isoformat(),
                       'valid_minutes':int(ok.sum()),'observed_energy_kwh':float(x[ok].sum()/60),
                       'complete_hour_energy_kwh':float(x.sum()/60) if ok.all() and len(x)==60 else None,
                       'indoor_temperature_valid_minutes':int(numeric.loc[mask,'z2_S1(degC)'].notna().sum())})
    pd.DataFrame(hourly).to_csv(OUT/'cu_measured_week_hourly.csv',index=False,encoding='utf-8-sig')
    # Do not silently assign UTC offsets to undocumented source timestamps.
    source = {'file':'2019Floor2.csv','sha256':digest(RAW/'2019Floor2.csv'),
              'dataset_version':json.loads((RAW/'cu_metadata.json').read_text(encoding='utf-8'))['version'],
              'rows':len(frame),'measurement_columns':len(numeric.columns),'ac_channels':len(ac),
              'first_timestamp':str(times.iloc[0]),'last_timestamp':str(times.iloc[-1]),
              'timestamp_scope':'naive timestamps; building in Bangkok, local-clock interpretation; source has no explicit UTC offset',
              'step_seconds':60,'duplicates':int(times.duplicated().sum()),
              'all_16_ac_joint_valid_minutes':int(jointly_valid.sum()),
              'joint_coverage_fraction':float(jointly_valid.mean()),
              'observed_joint_ac_energy_kwh':float(ac_values[jointly_valid].sum()/60),
              'full_year_ac_energy_kwh':None,
              'full_year_energy_reason':'Missing minutes exist. Partial observed integral is not an annual electricity bill or imputed annual total.',
              'complete_ac_channels':sum(q['valid_samples']==len(frame) for q in quality if q['channel'] in ac),
              'largest_ac_observed_kw':max(q['maximum'] for q in quality if q['channel'] in ac),
              'source_equipment_matches_catalogue':False,
              'power_interval_approximation':'Rectangular integration: P(sample in kW)*1/60h, only over valid minutes. Source supplies minutely power, not billing register differences.'}
    write_json(OUT/'cu_summary.json',source)
    return source


def madrid_audit():
    f = pd.read_csv(RAW/'madrid_monthly.csv',sep=';',encoding='utf-8-sig',dtype=str)
    c = f[(f['AÑO']=='2024') & (f.CLASE=='Energía activa') & (f.UNIDADES=='kWh') &
          (f.TIPOEDIFICIO=='Centros administrativos')].copy()
    # The downloaded 2024 records lack ID despite the dictionary's ID field.
    # No ID is invented or parsed from a different meaning in sensor strings.
    candidates = []
    for (building, sensor), part in c.groupby(['EDIFICIO','SENSOR'],dropna=False):
        month = pd.to_numeric(part.MES,errors='raise').astype(int)
        number = part.CONSUMO.str.replace(',','.',regex=False)
        # Non-numeric source markers remain missing, never energy=0.
        energy = pd.to_numeric(number,errors='coerce')
        valid = len(part)==12 and set(month)==set(range(1,13)) and np.isfinite(energy).all() and (energy>=0).all()
        candidates.append({'building':building,'sensor':sensor,'rows':len(part),'months':int(month.nunique()),
                           'complete_12_month_meter':bool(valid),
                           'missing_or_nonnumeric_values':int(energy.isna().sum()),
                           'invalid_source_tokens':'; '.join(sorted(part.loc[energy.isna(),'CONSUMO'].dropna().unique())),
                           'general_meter_name':bool('Electricidad General' in sensor or 'Consumo General' in sensor or 'Consumo total' in sensor or 'Consumo Total' in sensor)})
    candidates.sort(key=lambda item:(item['building'],item['sensor']))
    pd.DataFrame(candidates).to_csv(OUT/'madrid_candidate_meters.csv',index=False,encoding='utf-8-sig')
    eligible = [item for item in candidates if item['complete_12_month_meter'] and item['general_meter_name']]
    selected = eligible[0]  # lexical, no model-output or savings selection
    part = c[(c.EDIFICIO==selected['building'])&(c.SENSOR==selected['sensor'])].copy()
    part['month_number'] = pd.to_numeric(part.MES,errors='raise').astype(int)
    part = part.sort_values('month_number')
    energy = pd.to_numeric(part.CONSUMO.str.replace(',','.',regex=False),errors='raise')
    rows=[]
    for index,row in part.iterrows():
        rows.append({'year':2024,'month':int(row.month_number),'building':row.EDIFICIO,'sensor':row.SENSOR,
                     'consumption_raw':row.CONSUMO,'energy_kwh':float(energy.loc[index]),'sensor_type':row.TIPO,
                     'unit':row.UNIDADES,'class':row.CLASE,'source_building_id':None if pd.isna(row.ID) else row.ID,
                     'billing_amount_eur':None,'ac_submeter_kwh':None})
    pd.DataFrame(rows).to_csv(OUT/'madrid_selected_12_months.csv',index=False,encoding='utf-8-sig')
    assert len(rows)==12 and len({r['month'] for r in rows})==12
    source = {'sha256':digest(RAW/'madrid_monthly.csv'),'raw_rows':len(f),'year':2024,
              'selection_rule':'2024 administrative-building active energy in kWh; exactly 12 unique months; finite nonnegative values; general-meter name; first lexical building/sensor. No model fit used.',
              'selection_amendment':'ID criterion unavailable because all 305 scoped 2024 rows have missing ID; use EDIFICIO+SENSOR without inventing IDs.',
              'scoped_rows':len(c),'scoped_nonnull_id_rows':int(c.ID.notna().sum()),
              'scoped_nonnumeric_energy_rows':int(pd.to_numeric(c.CONSUMO.str.replace(',','.',regex=False),errors='coerce').isna().sum()),
              'candidate_meter_count':len(candidates),'complete_candidate_meter_count':sum(i['complete_12_month_meter'] for i in candidates),
              'selected_building':selected['building'],'selected_sensor':selected['sensor'],
              'monthly_rows':len(rows),'annual_meter_energy_kwh':float(energy.sum()),
              'invoice_available':False,'bill_amount_available':False,'ac_submeter_available':False,
              'scope':'One sensor named general active electricity; meter boundary from naming only, not independently audited full building inclusion.',
              'calibration_admissible':False,'reason':'No matching cooling-only submeter, room/AC specifications, operating schedule, invoice or tariff breakdown.'}
    write_json(OUT/'madrid_summary.json',source)
    return source


def main():
    start = datetime.now(timezone.utc).isoformat()
    clock = time.perf_counter()
    OUT.mkdir(parents=True,exist_ok=True)
    cu = cu_audit()
    madrid = madrid_audit()
    report = {'status':'CALIBRATION_NOT_ESTABLISHED','cu':cu,'madrid':madrid,
              'model_run_count':0,'model_fitting_count':0,'model_accuracy_metrics':None,
              'reason':'Actual measurements acquired; matching building specification and comparable complete AC scope absent. No arbitrary reference room fit to total-meter bills.'}
    write_json(OUT/'admission_summary.json',report)
    outputs={str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='analysis_run_manifest.json'}
    model_paths=['operation_planning/thermal_model.py','operation_planning/pv.py','operation_planning/hybrid.py','operation_planning/agent_parse.py','operation_planning/app.py']
    manifest={'run_id':'round23-public-source-admission-5090','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'analysis_source_sha256':digest(Path(__file__)),
              'workspace_status':subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True).strip(),
              'machine_role':'5090','gpu_probe_command':'nvidia-smi --query-gpu=name,driver_version --format=csv,noheader',
              'gpu_probe_result':subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version','--format=csv,noheader'],text=True).strip(),
              'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,
              'python_executable_name':Path(sys.executable).name,
              'command':'python -X utf8 -m analysis.round23_real_case.inspect_sources',
              'started_utc':start,'ended_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.perf_counter()-clock,
              'exit_status':0,'input_hashes':{p.name:digest(p) for p in sorted(RAW.iterdir()) if p.name in ['cu_metadata.json','2019Floor2.csv','madrid_monthly.csv','cu_paper.pdf','madrid_dictionary.pdf']},
              'frozen_backend_hashes':{p:digest(ROOT/p) for p in model_paths},'output_hashes':outputs,
              'checks':{'cu_exact_525600_minute_axis':'pass','madrid_exact_12_unique_months':'pass','no_unknown_to_zero':'pass',
                        'bill_vs_model_calibration':'not_admissible','model_backend_modified':False},
              'preflight_failures':['Direct external downloads returned HTTP 403; ordinary configured public network downloader succeeded.',
                                    'fitz unavailable in both examined Python runtimes; existing bundled pypdf used to read documents.',
                                    'CU strict timestamp parser expected T but file uses space; changed only audit parser to ISO8601 and verified exact minute axis.'],
              'evidence_kind':'Measured public data profiling and derived integrals; zero new thermal/PV/wind/model experiments'}
    write_json(OUT/'analysis_run_manifest.json',manifest)
    print(json.dumps({'status':report['status'],'cu_ac_joint_coverage':cu['joint_coverage_fraction'],
                      'madrid_building':madrid['selected_building'],'madrid_annual_meter_kwh':madrid['annual_meter_energy_kwh'],
                      'elapsed_seconds':manifest['elapsed_seconds'],'source_commit':manifest['source_commit']},ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':
    main()
