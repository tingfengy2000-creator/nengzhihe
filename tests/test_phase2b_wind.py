"""Short, hand-checkable phase-two B definitions and integration checks."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import math
from unittest.mock import patch
from operation_planning.wind import WindTurbineProfile, WindScenario, WindQuote, generate_wind
from operation_planning.hybrid import HybridScenario, match_hybrid, run_hybrid_planning
from operation_planning.pv import PVScenario, PVQuote, lifecycle_compare, generate_pv, match_load
from operation_planning.economics import discounted_cashflow_npv
from operation_planning.hybrid_agent import HybridPlanningAgent

def _series(load, pv, wind, dt=3600):
    times=["2024-01-01T00:00+08:00"]*len(load)
    # use a real contiguous axis
    from datetime import datetime,timedelta
    t=datetime(2024,1,1)
    times=[(t+timedelta(hours=i)).isoformat() for i in range(len(load))]
    return {"timestamps":times,"interval_seconds":[dt]*len(load),"electric_power_w":[x*3_600_000/dt for x in load]}, {"timestamps":times,"interval_seconds":[dt]*len(load),"pv_ac_power_w":[x*3_600_000/dt for x in pv]}, {"timestamps":times,"interval_seconds":[dt]*len(load),"wind_power_w":[x*3_600_000/dt for x in wind]}

def test_profile_curve_and_units():
    p=WindTurbineProfile.from_file(); assert p.power_curve[10]==[5.50,739]
    # windpowerlib linear interpolation at 5.745 m/s
    from windpowerlib import power_output
    y=power_output.power_curve(5.745,[x[0] for x in p.power_curve],[x[1] for x in p.power_curve],density_correction=False)
    assert abs(float(y)-879.5)<1e-9

def test_height_and_out_of_range():
    profile=WindTurbineProfile.from_file(); weather={"time":["2024-01-01T00:00","2024-01-01T01:00"],"interval_seconds":[3600,3600],"hourly":{"wind_speed_10m":[18,18],"temperature_2m":[20,20],"surface_pressure":[1013,1013]}}
    a=generate_wind(weather,profile,WindScenario(turbine_count=1,source_height_m=10,hub_height_m=10)); assert a["wind_speed_hub_m_s"][0]==5
    assert a["metadata"]["out_of_curve_range_count"]==0
    try:
        WindScenario(turbine_count=1, hub_height_m=21, hub_height_max_m=20)
    except ValueError:
        pass
    else:
        raise AssertionError("height maximum must be enforced")

def test_hybrid_arithmetic_and_common_export():
    load,pv,wind=_series([1.0],[.8],[.7]); r=match_hybrid(load,pv,wind,allow_export=False)
    s=r["summary"]; assert abs(s["self_use_kwh"]-1.0)<1e-9; assert abs(s["grid_import_kwh"])<1e-9; assert abs(s["curtailment_kwh"]-.5)<1e-9
    load,pv,wind=_series([0.2],[.8],[.7]); r=match_hybrid(load,pv,wind,allow_export=True,export_limit_kw=.5); assert abs(r["summary"]["grid_export_kwh"]-.5)<1e-9; assert abs(r["summary"]["curtailment_kwh"]-.8)<1e-9

def test_zero_turbine_and_missing_quote():
    profile=WindTurbineProfile.from_file(); weather={"time":["2024-01-01T00:00","2024-01-01T01:00"],"interval_seconds":[3600,3600],"hourly":{"wind_speed_10m":[10,10],"temperature_2m":[20,20],"surface_pressure":[1013,1013]}}
    z=generate_wind(weather,profile,WindScenario(turbine_count=0)); assert sum(z["wind_energy_kwh"])==0
    assert WindQuote().turbine_cny is None

def test_shared_cashflow_definition():
    assert abs(discounted_cashflow_npv(105.0, [110.0], 0.10) + 5.0) < 1e-12

def _weather_case(n=2):
    weather={"time":[f"2024-01-01T{h:02d}:00:00" for h in range(8,8+n)],"interval_seconds":[3600]*n,"context":{"site":{"latitude":23.13,"longitude":113.26,"timezone":"Asia/Shanghai"}},"hourly":{"shortwave_radiation":[500.0]*n,"direct_normal_irradiance":[400.0]*n,"diffuse_radiation":[100.0]*n,"temperature_2m":[30.0]*n,"wind_speed_10m":[10.0]*n,"surface_pressure":[1013.0]*n}}
    load={"load_series":{"timestamps":list(weather["time"]),"interval_seconds":[3600]*n,"electric_power_w":[1000.0]*n,"service_scope":"cooling_only"},"summary":{}}
    return weather,load

def _complete_quotes():
    return PVQuote(module_cny_per_kwp=1800,inverter_cny_per_kwp=600,structure_cny_per_kwp=500,installation_cny_per_kwp=800,grid_connection_cny=0,maintenance_cny_per_kwp_year=30,inverter_replacement_year=12,inverter_replacement_fraction=.15), WindQuote(turbine_cny=45000,tower_cny=15000,foundation_cny=10000,installation_cny=12000,grid_connection_cny=0,maintenance_cny_per_year=1200)

def test_inverter_replacement_is_inverter_only_and_zero_wind_cost():
    weather,load=_weather_case(); pvq,wq=_complete_quotes(); pvs=PVScenario(roof_area_m2=50,quote=pvq); hs=HybridScenario(pv_capacity_kwp=2,wind=WindScenario(turbine_count=0),study_years=15,pv_quote=pvq,wind_quote=wq,shared_connection_cny=0)
    report=run_hybrid_planning(load,weather,pvs,hs,WindTurbineProfile.from_file(),include_hourly=False)
    pv=next(x for x in report["candidates"] if x["scenario_id"]=="S1_pv"); assert abs(next(r["replacement_cny"] for r in pv["economics"]["yearly"] if r["year"]==12)-180.0)<1e-9
    assert next(x for x in report["candidates"] if x["scenario_id"]=="S2_wind")["economics"]["capex_cny"]==0.0

def test_missing_quote_and_roof_constraint_do_not_select_s0():
    weather,load=_weather_case(); incomplete=PVQuote(); hs=HybridScenario(pv_capacity_kwp=2,wind=WindScenario(turbine_count=0),pv_quote=incomplete,wind_quote=WindQuote(),shared_connection_cny=0); report=run_hybrid_planning(load,weather,PVScenario(roof_area_m2=50,quote=incomplete),hs,WindTurbineProfile.from_file(),include_hourly=False); assert report["recommendation"]["status"]=="not_available"; assert report["recommendation"]["complete_subset_best_scenario_id"]=="S0_grid"
    pvq,wq=_complete_quotes(); hs=HybridScenario(pv_capacity_kwp=2,wind=WindScenario(turbine_count=0),pv_quote=pvq,wind_quote=wq,shared_connection_cny=0); report=run_hybrid_planning(load,weather,PVScenario(roof_area_m2=1,usable_fraction=1,quote=pvq),hs,WindTurbineProfile.from_file(),include_hourly=False); assert next(x for x in report["candidates"] if x["scenario_id"]=="S1_pv")["constraint_status"]=="not_applicable"

def test_match_rejects_nan_and_negative_export_limit():
    load,pv,wind=_series([1.0],[.8],[.7]); load["electric_power_w"][0]=float("nan")
    try: match_hybrid(load,pv,wind)
    except ValueError: pass
    else: raise AssertionError("NaN must be rejected")
    load,pv,wind=_series([1.0],[.8],[.7])
    try: match_hybrid(load,pv,wind,allow_export=True,export_limit_kw=-.1)
    except ValueError: pass
    else: raise AssertionError("negative export limit must be rejected")

def test_pv_and_hybrid_fifteen_year_economics_agree():
    weather,load_result=_weather_case(); pvq,wq=_complete_quotes(); pvs=PVScenario(roof_area_m2=50,quote=pvq,study_years=15,discount_rate=.10); g=generate_pv(weather,2,pvs); baseline=match_load(load_result["load_series"],generate_pv(weather,0,pvs),import_prices=[.66]*2); matched=match_load(load_result["load_series"],g,import_prices=[.66]*2); pv_econ=lifecycle_compare(matched,baseline,2,pvs,load_series=load_result["load_series"],generation=g,import_prices=[.66]*2)
    hs=HybridScenario(pv_capacity_kwp=2,wind=WindScenario(turbine_count=0),study_years=15,discount_rate=.10,pv_quote=pvq,wind_quote=wq,shared_connection_cny=0); report=run_hybrid_planning(load_result,weather,pvs,hs,WindTurbineProfile.from_file(),include_hourly=False); hy_econ=next(x for x in report["candidates"] if x["scenario_id"]=="S1_pv")["economics"]; assert abs(pv_econ["npv_cny"]-hy_econ["npv_cny"])<1e-7

def test_authoritative_price_changes_cost_not_physics():
    weather,load=_weather_case(); pvq,wq=_complete_quotes(); pvs=PVScenario(roof_area_m2=50,quote=pvq); a=run_hybrid_planning(load,weather,pvs,HybridScenario(pv_capacity_kwp=2,wind=WindScenario(turbine_count=0),import_price_cny_per_kwh=.66,pv_quote=pvq,wind_quote=wq,shared_connection_cny=0),WindTurbineProfile.from_file(),include_hourly=False); b=run_hybrid_planning(load,weather,pvs,HybridScenario(pv_capacity_kwp=2,wind=WindScenario(turbine_count=0),import_price_cny_per_kwh=1.20,pv_quote=pvq,wind_quote=wq,shared_connection_cny=0),WindTurbineProfile.from_file(),include_hourly=False); ca=next(x for x in a["candidates"] if x["scenario_id"]=="S1_pv"); cb=next(x for x in b["candidates"] if x["scenario_id"]=="S1_pv"); assert ca["generation_kwh"]==cb["generation_kwh"]; assert ca["economics"]["total_grid_import_cost_cny"]!=cb["economics"]["total_grid_import_cost_cny"]

def test_agent_usage_window_parser_and_single_plan(monkeypatch=None):
    assert HybridPlanningAgent._changes("把使用时段改成18点到22点",{})["start_hour"]==18
    weather,load=_weather_case(); pvq,wq=_complete_quotes(); agent=HybridPlanningAgent(); state={"load_result":load,"pv_weather":weather,"pv":PVScenario(roof_area_m2=50,quote=pvq),"hybrid":HybridScenario(pv_capacity_kwp=2,wind=WindScenario(turbine_count=0),pv_quote=pvq,wind_quote=wq,shared_connection_cny=0),"profile":WindTurbineProfile.from_file()}
    from operation_planning.hybrid import run_hybrid_planning as real_plan
    with patch("operation_planning.hybrid_agent.run_hybrid_planning",side_effect=real_plan) as call:
        agent._tool("compute_generation",state,{})
        agent._tool("match_supply_demand",state,{})
        agent._tool("calculate_lifecycle",state,{})
        assert call.call_count==1 and state["full_plan_calls"]==1

if __name__ == "__main__":
    for name,fn in sorted(globals().items()):
        if name.startswith("test_"): fn(); print("PASS",name)
