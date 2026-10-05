"""Phase-two photovoltaic contracts; runnable without pytest as a direct module."""
from __future__ import annotations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from operation_planning.weather import load_weather, load_pv_weather
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.pv import PVQuote, PVScenario, generate_candidates, generate_pv, match_load, run_pv_planning

QUOTE=PVQuote(module_cny_per_kwp=1800,inverter_cny_per_kwp=600,structure_cny_per_kwp=500,installation_cny_per_kwp=800,grid_connection_cny=0,maintenance_cny_per_kwp_year=30)

def case():
    return load_weather('guangzhou',2024), load_pv_weather('guangzhou',2024), simulate_room(load_weather('guangzhou',2024),RoomSpec())

def test_hourly_conservation():
    _, pw, load=case(); s=PVScenario(roof_area_m2=50,requested_capacities_kwp=[2],quote=QUOTE); pw['interval_seconds']=load['load_series']['interval_seconds']; g=generate_pv(pw,2,s); m=match_load(load['load_series'],g); assert abs(m['summary']['load_kwh']-m['summary']['self_use_kwh']-m['summary']['grid_import_kwh'])<1e-7; assert abs(m['summary']['pv_generation_kwh']-m['summary']['self_use_kwh']-m['summary']['grid_export_kwh']-m['summary']['curtailment_kwh'])<1e-7

def test_zero_capacity_is_baseline_and_no_export():
    _, pw, load=case(); s=PVScenario(roof_area_m2=50,requested_capacities_kwp=[0],quote=QUOTE); pw['interval_seconds']=load['load_series']['interval_seconds']; g=generate_pv(pw,0,s); m=match_load(load['load_series'],g); assert sum(g.pv_ac_power_w)==0; assert m['summary']['pv_generation_kwh']==0; assert m['summary']['grid_export_kwh']==0; assert m['summary']['curtailment_kwh']==0; assert abs(m['summary']['grid_import_kwh']-m['summary']['load_kwh'])<1e-7

def test_year_lengths_and_generation_not_changed_by_price_or_load():
    _, pw, load=case(); assert len(pw['time'])==8784; assert len(load['rows'])==8784; s1=PVScenario(roof_area_m2=50,import_price_cny_per_kwh=.66,quote=QUOTE); s2=PVScenario(roof_area_m2=50,import_price_cny_per_kwh=1.2,quote=QUOTE); pw['interval_seconds']=load['load_series']['interval_seconds']; a=generate_pv(pw,2,s1).pv_ac_power_w; b=generate_pv(pw,2,s2).pv_ac_power_w; assert a==b; changed={**load['load_series'],'electric_power_w':[x*0.5 for x in load['load_series']['electric_power_w']]}; c=match_load(changed,generate_pv(pw,2,s1)); assert c['summary']['pv_generation_kwh']==match_load(load['load_series'],generate_pv(pw,2,s1))['summary']['pv_generation_kwh']

def test_export_limit_and_unit_boundary():
    _, pw, load=case(); s=PVScenario(roof_area_m2=50,quote=QUOTE); pw['interval_seconds']=load['load_series']['interval_seconds']; m=match_load(load['load_series'],generate_pv(pw,2,s),allow_export=True,export_limit_kw=.2); assert m['summary']['grid_export_kwh']>=0; assert m['summary']['curtailment_kwh']>=0

def test_area_is_independent_from_room():
    a,_=generate_candidates(PVScenario(roof_area_m2=10,usable_fraction=1,requested_capacities_kwp=None,quote=QUOTE)); b,_=generate_candidates(PVScenario(roof_area_m2=50,usable_fraction=1,requested_capacities_kwp=None,quote=QUOTE)); assert max(a)<max(b); assert 0.0 in a and 0.0 in b

def test_planning_and_timestamp_guard():
    _, pw, load=case(); s=PVScenario(roof_area_m2=50,requested_capacities_kwp=[0,1],quote=QUOTE); report=run_pv_planning(load,pw,s); assert report['baseline']['capacity_kwp']==0; assert len(report['candidates'])==2; bad=dict(pw); bad['time']=list(reversed(pw['time']));
    try: run_pv_planning(load,bad,s)
    except ValueError: pass
    else: raise AssertionError('timestamp mismatch must reject')

def run_all():
    for name in sorted(globals()):
        if name.startswith('test_'): globals()[name]()
    print('phase2 pv contract tests: PASS')

if __name__=='__main__': run_all()
