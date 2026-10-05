"""Short, hand-checkable phase-two B definitions and integration checks."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import math
from operation_planning.wind import WindTurbineProfile, WindScenario, WindQuote, generate_wind
from operation_planning.hybrid import HybridScenario, match_hybrid, run_hybrid_planning
from operation_planning.pv import PVScenario, PVQuote

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

if __name__ == "__main__":
    for name,fn in sorted(globals().items()):
        if name.startswith("test_"): fn(); print("PASS",name)
