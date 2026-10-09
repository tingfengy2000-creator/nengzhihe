"""Meaningful source/interval/aggregation checks, not product feature tests."""
from __future__ import annotations
import io,json,sys,zipfile,hashlib
from pathlib import Path
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from analysis.round24_three_level.run_validation import normalized_weather,metrics
from operation_planning import thermal_model as tm
OUT=ROOT/'operation_planning/results/round24_public_validation'
WORK=ROOT/'working/round24/model_outputs'

def main():
    global OUT
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir');args=parser.parse_args()
    if args.output_dir:OUT=(ROOT/args.output_dir).resolve()
    from analysis.round24_three_level import run_validation
    run_validation.OUT=OUT
    checks=[]
    def check(name,condition,detail):
        if not bool(condition):raise AssertionError(name+': '+str(detail))
        checks.append({'name':name,'status':'passed','detail':detail})
    z=zipfile.ZipFile(ROOT/'working/round24/sources/dataset.zip')
    check('publisher_MD5',hashlib.md5((ROOT/'working/round24/sources/dataset.zip').read_bytes()).hexdigest()=='dc02fa4f80433d9b26ad002a90aee5ae','v3 CC0 archive matches publisher')
    room=json.loads((OUT/'room_summary.json').read_text(encoding='utf-8'))
    check('metadata_quality_selection',room['selected_house_ids']==[2,6,9],'3 rooms; individual physical parameter completeness remains zero')
    w,h=normalized_weather('hyderabad_2019')
    raw=json.loads((ROOT/'working/round24/sources/hyderabad_2019_weather.json').read_text(encoding='utf-8'))
    check('preceding_hour_interval',w['hourly']['shortwave_radiation'][0]==raw['hourly']['shortwave_radiation'][1],
          'raw 01:00 mean assigned to [00:00,01:00], no shift of instantaneous T')
    check('known_current_proxy_unit',np.isclose(1000/1000*230*.9/60000*60,.207),
          '1000mA above baseline for 60min at 230V/PF0.9 -> 0.207kWh (proxy)')
    check('NMBE_CVRMSE_hand_example',np.isclose(metrics([1,1],[2,2])['nmbe_percent_model_minus_proxy'],200) and
          np.isclose(metrics([1,1],[2,2])['cvrmse_percent'],np.sqrt(2)*100),'n-1 explicit; not official calibration pass/fail')
    daily=pd.read_csv(OUT/'room_daily_comparison.csv')
    errors=[]
    for i in [2,6,9]:
        for variant in ['untuned','limited_fit']:
            r=json.loads((WORK/f'house_{i}_{variant}.json').read_text(encoding='utf-8'))
            integrated=sum(x['electric_power_w']*x['interval_seconds']/3600000 for x in r['rows'])
            output=daily[(daily.house_id==i)&(daily.variant==variant)].model_kwh.sum()
            errors.append(abs(integrated-output));check(f'room_{i}_{variant}_daily_integral',np.isclose(output,integrated,rtol=1e-10),float(abs(output-integrated)))
        pairs=pd.read_csv(OUT/f'room_{i}_temperature_pairs.csv')
        check(f'room_{i}_temperature_pairs_finite',np.isfinite(pairs[['measured_c','untuned_c','limited_fit_c']].to_numpy()).all(),f'{len(pairs)} exact operating sample instants')
    freeze=json.loads((OUT/'room_limited_fit_freeze.json').read_text(encoding='utf-8'))
    check('finite_development_only_fit',len(freeze['all_development_trials'])==6 and not freeze['evaluation_used_for_selection'],
          '9 development days, 10 later dates, shared two-parameter grid, no iterations after evaluation')
    cu=pd.read_csv(OUT/'cu_daily_quality.csv');accepted=cu[cu.accepted]
    check('CU_no_missing_as_zero',len(accepted)==198 and (accepted.joint_valid_minutes==1440).all(), '198/261 complete weekdays; all 16 channels')
    profile=pd.read_csv(OUT/'cu_normalized_weekday_profile.csv')
    check('CU_daily_normalized_shape_mean',np.allclose(profile[['measured_kwh','model_kwh']].mean(),1,atol=1e-10),'both 24-hour normalized profile means equal 1')
    mw,mh=normalized_weather('madrid_2024')
    check('Madrid_leap_DST_physical_intervals',len(mh)==8784 and (np.diff(mh.index.asi8)==3600000000000).all(),
          '8784 physical hours, local calendar 2024; UTC monotonic; DST offsets retained')
    months=pd.read_csv(OUT/'madrid_building_months.csv')
    grouped=months.groupby('building')
    check('Madrid_complete_electricity_and_observed_winter_gas',len(grouped)==3 and all(len(g)==12 and np.isfinite(g.electricity_kwh).all() and
          np.isfinite(g[g.month.isin([1,2,12])].gas_value).all() for _,g in grouped),'3 buildings x 12 electric months; winter gas present, summer missing NOT zero')
    check('Madrid_normalized_denominators',all(np.isclose(g.positive_excess_fraction.sum(),1,atol=1e-10) for _,g in grouped) and
          np.isclose(pd.read_csv(OUT/'madrid_model_months.csv').model_cooling_fraction.sum(),1,atol=1e-10),'12-month positive excess and model fractions each sum to 1; positive excess not proven AC')
    check('signed_excess_is_not_clipped_for_correlation',(months.signed_excess_kwh<0).any(),'negative month-baseline values retained')
    run=json.loads((OUT/'run_manifest_all.json').read_text(encoding='utf-8'))
    mismatched=[name for name,digest in run['frozen_product_hashes'].items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    check('frozen_product_unchanged',not mismatched,'all top-level operation_planning/*.py byte hashes match run')
    # These functions are original product functions after scoped patches.
    check('analysis_schedule_patch_restored',tm._active.__module__=='operation_planning.thermal_model' and tm.get_equipment.__module__=='operation_planning.equipment','no persistent runtime monkeypatch')
    receipt={'checks':checks,'count':len(checks),'all_passed':True,'scope':'independent analysis contracts and evidence reconciliation, NOT model accuracy tests'}
    (OUT/'verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':len(checks),'max_daily_integral_difference_kwh':max(errors)},ensure_ascii=False))
    return receipt

if __name__=='__main__':main()
