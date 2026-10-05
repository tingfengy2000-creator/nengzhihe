"""Reproducible phase-two A evidence generator.

Run from repository root:
    python scripts/phase2a_demo.py
"""
from __future__ import annotations
import csv, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from operation_planning.weather import load_weather, load_pv_weather
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.pv import PVQuote, PVScenario, run_pv_planning

OUT=ROOT/'operation_planning'/'results'/'pv_phase2a'; OUT.mkdir(parents=True,exist_ok=True)
QUOTE=PVQuote(module_cny_per_kwp=1800,inverter_cny_per_kwp=600,structure_cny_per_kwp=500,installation_cny_per_kwp=800,grid_connection_cny=0,maintenance_cny_per_kwp_year=30,inverter_replacement_year=12,inverter_replacement_fraction=0.8,residual_fraction=0.05,source='用户确认的演示情景报价；不是采购报价')

def run(site,year,room,scenario,include=False):
    w=load_weather(site,year); pw=load_pv_weather(site,year); load=simulate_room(w,room); return run_pv_planning(load,pw,scenario,include_selected_series=include)

def compact(report):
    out=dict(report); out['candidates']=[]
    for c in report['candidates']:
        row={k:v for k,v in c.items() if k not in {'hourly'}}; out['candidates'].append(row)
    return out

base_room=RoomSpec(area_m2=35,people_count=4,start_hour=8,end_hour=18,cooling_setpoint_c=26,rh_setpoint_percent=60,equipment_id='midea_msagbu12_mox201')
base_scenario=PVScenario(site_id='guangzhou',year=2024,roof_area_m2=50,usable_fraction=.8,tilt_deg=23,azimuth_open_meteo_deg=0,requested_capacities_kwp=[0,1,2,3],import_price_cny_per_kwh=.66,study_years=10,quote=QUOTE)
base=run('guangzhou',2024,base_room,base_scenario,True)
# Keep one selected curve in the artifact; the API still returns the complete selected curve.
for c in base['candidates']:
    if c.get('capacity_kwp') != base.get('selected_capacity_kwp'): c.pop('hourly',None)
# Same physical PV weather and capacities, shifted HVAC use window.
shift_room=RoomSpec(**{**base_room.__dict__,'start_hour':18,'end_hour':24})
shift=run('guangzhou',2024,shift_room,base_scenario,True)
for c in shift['candidates']:
    if c.get('capacity_kwp') != shift.get('selected_capacity_kwp'): c.pop('hourly',None)
# Roof/budget change: physical PV generation is recomputed only for feasible capacities.
constrained=PVScenario(**{**base_scenario.__dict__,'roof_area_m2':20,'budget_cny':9000})
constrained.quote=QUOTE
small=run('guangzhou',2024,base_room,constrained,False)
long_scenario=PVScenario(**{**base_scenario.__dict__,'study_years':15}); long_scenario.quote=QUOTE
long_study=run('guangzhou',2024,base_room,long_scenario,False)
# Fixed 2 kWp across existing weather years: a time-year sensitivity, not independent buildings.
rows=[]
for site in ('guangzhou','beijing','harbin'):
 for year in (2023,2024,2025):
    s=PVScenario(**{**base_scenario.__dict__,'site_id':site,'year':year,'requested_capacities_kwp':[0,2]}); s.quote=QUOTE
    r=run(site,year,base_room,s,False); c=next(x for x in r['candidates'] if x['capacity_kwp']==2.0)
    rows.append({'site':site,'year':year,'weather_hash':r['weather_provenance']['hash'],'rows':len(r['baseline']['monthly']),'load_kwh':r['load_context']['electric_load_kwh'],'pv_2kwp_kwh':c['generation_kwh'],'self_use_kwh':c['self_use_kwh'],'grid_import_kwh':c['grid_import_kwh'],'curtailment_kwh':c['curtailment_kwh'],'load_coverage_rate':c['load_coverage_rate'],'economics_status':c['economics']['status'],'npv_cny':c['economics']['npv_cny']})
(base_path:=OUT/'guangzhou_2024_full_chain.json').write_text(json.dumps({'scope':'phase2A first full chain; Guangzhou 2024; fixed first-stage AC scenario','base':base,'shifted_hours':shift,'roof_budget_constrained':small,'study_15_years':long_study},ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'fixed_2kwp_9_years.json').write_text(json.dumps({'scope':'fixed 2 kWp sensitivity over existing cached years; not independent validation','rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'fixed_2kwp_9_years.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
summary={'status':'complete','full_chain':'Guangzhou 2024','base_capacity_candidates':[{k:v for k,v in c.items() if k!='hourly'} for c in base['candidates']],'selected_capacity_kwp':base.get('selected_capacity_kwp'),'time_shift_generation_comparison':'same PV weather and physical inputs; matching changes with HVAC hours','constrained_candidate_capacities':[x['capacity_kwp'] for x in small['candidates']], 'study_15_years_selected_capacity_kwp':long_study.get('selected_capacity_kwp'),'fixed_2kwp_years':rows,'repro_command':'python scripts/phase2a_demo.py'}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'README.md').write_text('''# 第二阶段A：光伏—空调负荷—投资成本联算\n\n本目录由 `python scripts/phase2a_demo.py` 生成。第一条完整链为广州 2024，固定第一阶段的单房间空调情景；同一 PV 天气输入下，将负荷时间窗改为 18:00–24:00 用于验证物理发电不因负荷时段改变。另有 20m²/9000 CNY 约束场景及广州、北京、哈尔滨 2023–2025 年固定 2kWp 的时间年敏感性。\n\n- `guangzhou_2024_full_chain.json`：发电、逐时匹配、逐月聚合、报价生命周期和两个可操作对照。\n- `fixed_2kwp_9_years.json/csv`：固定容量的历史年份比较，不把年度最佳容量平均成一套安装，也不把日期重复计作独立建筑验证。\n- 供需按每个时间区间电量守恒；无外送时余电计弃电。\n- 报价、电价、衰减、寿命和屋顶可用比例均是用户可修改的情景；第一阶段负荷未校准，结果不代表真实楼宇节能或投资收益。\n''',encoding='utf-8')
print(json.dumps({'output':str(OUT),'base_selected_kwp':base.get('selected_capacity_kwp'),'fixed_rows':len(rows),'files':[p.name for p in OUT.iterdir()]},ensure_ascii=False))




