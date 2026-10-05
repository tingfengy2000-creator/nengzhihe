"""Freeze and run the phase-two B four-plan comparison from cached public weather."""
from __future__ import annotations
import json, hashlib, sys
from dataclasses import asdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from operation_planning.weather import load_weather, load_pv_weather
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.pv import PVScenario, PVQuote
from operation_planning.wind import WindScenario, WindQuote, WindTurbineProfile
from operation_planning.hybrid import HybridScenario, run_hybrid_planning

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"operation_planning"/"results"/"phase2b_wind"
PVQ=PVQuote(module_cny_per_kwp=1800,inverter_cny_per_kwp=600,structure_cny_per_kwp=500,installation_cny_per_kwp=800,grid_connection_cny=0,maintenance_cny_per_kwp_year=30,inverter_replacement_year=12,inverter_replacement_fraction=.15,residual_fraction=.05)
WQ=WindQuote(turbine_cny=45000,tower_cny=15000,foundation_cny=10000,installation_cny=12000,grid_connection_cny=0,maintenance_cny_per_year=1200,residual_fraction=.05)

def run(site,year,include_hourly=True):
    lw=load_weather(site,year); pw=load_pv_weather(site,year); room=RoomSpec(area_m2=35,people_count=4,start_hour=8,end_hour=18,cooling_setpoint_c=26,rh_setpoint_percent=60); load=simulate_room(lw,room)
    pvs=PVScenario(site_id=site,year=year,roof_area_m2=50,usable_fraction=.8,tilt_deg=23,azimuth_open_meteo_deg=0,import_price_cny_per_kwh=.66,quote=PVQ)
    hs=HybridScenario(site_id=site,year=year,pv_capacity_kwp=2,wind=WindScenario(site_id=site,year=year,turbine_count=1,hub_height_m=9,source_height_m=10,hellman_exponent=.14),budget_cny=90000,allow_export=False,import_price_cny_per_kwh=.66,study_years=10,pv_quote=PVQ,wind_quote=WQ)
    return run_hybrid_planning(load,pw,pvs,hs,WindTurbineProfile.from_file(),include_hourly=include_hourly)

def main():
    OUT.mkdir(parents=True,exist_ok=True); profile=WindTurbineProfile.from_file(); all_rows=[]
    primary=run("guangzhou",2024,True); (OUT/"guangzhou_2024_full_chain.json").write_text(json.dumps(primary,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    for site in ("guangzhou","beijing","harbin"):
        for year in (2023,2024,2025):
            report=primary if (site,year)==("guangzhou",2024) else run(site,year,False)
            row={"site_id":site,"year":year,"calculation_version":report["calculation_version"],"weather_hash":report["weather_provenance"]["hash"],"profile_id":profile.profile_id,"candidates":[{"scenario_id":c["scenario_id"],"pv_generation_kwh":c["pv_generation_kwh"],"wind_generation_kwh":c["wind_generation_kwh"],"self_use_kwh":c["self_use_kwh"],"grid_import_kwh":c["grid_import_kwh"],"grid_export_kwh":c["grid_export_kwh"],"curtailment_kwh":c["curtailment_kwh"],"load_coverage_rate":c["load_coverage_rate"],"budget_ok":c["budget_ok"],"economics":c["economics"]} for c in report["candidates"]]}
            all_rows.append(row)
    summary={"calculation_version":"phase2b-wind-v1","profile":{"profile_id":profile.profile_id,"source_url":profile.source_url,"source_sha256":profile.source_sha256,"curve_hash":profile.curve_hash()},"fixed_configuration":{"pv_capacity_kwp":2,"wind_turbine_count":1,"hub_height_m":9,"hellman_exponent":.14,"budget_cny":90000,"allow_export":False,"study_years":10,"tariff":"user_constant 0.66 CNY/kWh"},"scope":"3 cities x 3 cached weather years; same fixed configuration; Guangzhou 2024 full hourly evidence; other groups summary evidence","groups":all_rows}
    (OUT/"fixed_configuration_9_groups.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    print(json.dumps({"primary":str(OUT/"guangzhou_2024_full_chain.json"),"fixed":str(OUT/"fixed_configuration_9_groups.json"),"groups":len(all_rows)},ensure_ascii=False))
if __name__=="__main__": main()
