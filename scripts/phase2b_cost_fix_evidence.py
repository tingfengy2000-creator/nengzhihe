"""Write compact, reviewable evidence for the phase-two B cost/constraint fix."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from operation_planning.economics import discounted_cashflow_npv
from operation_planning.hybrid import HybridScenario, match_hybrid, run_hybrid_planning
from operation_planning.pv import PVQuote, PVScenario, generate_pv, match_load, lifecycle_compare
from operation_planning.wind import WindQuote, WindScenario, WindTurbineProfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "operation_planning" / "results" / "phase2b_cost_fix"


def short_case():
    times = [(datetime(2024, 1, 1, 8) + timedelta(hours=i)).isoformat() for i in range(2)]
    weather = {"time": times, "interval_seconds": [3600, 3600], "context": {"site": {"latitude": 23.13, "longitude": 113.26, "timezone": "Asia/Shanghai"}}, "hourly": {"shortwave_radiation": [500.0, 500.0], "direct_normal_irradiance": [400.0, 400.0], "diffuse_radiation": [100.0, 100.0], "temperature_2m": [30.0, 30.0], "wind_speed_10m": [10.0, 10.0], "surface_pressure": [1013.0, 1013.0]}}
    load = {"load_series": {"timestamps": times, "interval_seconds": [3600, 3600], "electric_power_w": [1000.0, 1000.0], "service_scope": "cooling_only"}, "summary": {}}
    return weather, load


def main():
    weather, load = short_case()
    pvq = PVQuote(module_cny_per_kwp=1800, inverter_cny_per_kwp=600, structure_cny_per_kwp=500, installation_cny_per_kwp=800, grid_connection_cny=0, maintenance_cny_per_kwp_year=30, inverter_replacement_year=12, inverter_replacement_fraction=.15)
    wq = WindQuote(turbine_cny=45000, tower_cny=15000, foundation_cny=10000, installation_cny=12000, grid_connection_cny=0, maintenance_cny_per_year=1200)
    pvs = PVScenario(roof_area_m2=50, quote=pvq, study_years=15)
    hs = HybridScenario(pv_capacity_kwp=2, wind=WindScenario(turbine_count=0), pv_quote=pvq, wind_quote=wq, shared_connection_cny=0, study_years=15)
    report = run_hybrid_planning(load, weather, pvs, hs, WindTurbineProfile.from_file(), include_hourly=False)
    pv = next(row for row in report["candidates"] if row["scenario_id"] == "S1_pv")
    wind0 = next(row for row in report["candidates"] if row["scenario_id"] == "S2_wind")
    pvs_discounted = PVScenario(roof_area_m2=50, quote=pvq, study_years=15, discount_rate=.10)
    pv_generation = generate_pv(weather, 2, pvs_discounted)
    pv_baseline = match_load(load["load_series"], generate_pv(weather, 0, pvs_discounted), import_prices=[.66, .66])
    pv_match = match_load(load["load_series"], pv_generation, import_prices=[.66, .66])
    pv_only_engine = lifecycle_compare(pv_match, pv_baseline, 2, pvs_discounted, load_series=load["load_series"], generation=pv_generation, import_prices=[.66, .66])
    hybrid_discounted = HybridScenario(pv_capacity_kwp=2, wind=WindScenario(turbine_count=0), pv_quote=pvq, wind_quote=wq, shared_connection_cny=0, study_years=15, discount_rate=.10)
    hybrid_discounted_report = run_hybrid_planning(load, weather, pvs_discounted, hybrid_discounted, WindTurbineProfile.from_file(), include_hourly=False)
    hybrid_only_engine = next(row for row in hybrid_discounted_report["candidates"] if row["scenario_id"] == "S1_pv")["economics"]
    missing = run_hybrid_planning(load, weather, PVScenario(roof_area_m2=50, quote=PVQuote()), HybridScenario(pv_capacity_kwp=2, wind=WindScenario(turbine_count=0), pv_quote=PVQuote(), wind_quote=WindQuote(), shared_connection_cny=0), WindTurbineProfile.from_file(), include_hourly=False)
    roof = run_hybrid_planning(load, weather, PVScenario(roof_area_m2=1, usable_fraction=1, quote=pvq), HybridScenario(pv_capacity_kwp=2, wind=WindScenario(turbine_count=0), pv_quote=pvq, wind_quote=wq, shared_connection_cny=0), WindTurbineProfile.from_file(), include_hourly=False)
    load_s, pv_s, wind_s = ({"timestamps": ["2024-01-01T00:00:00"], "interval_seconds": [3600], "electric_power_w": [1000.0]}, {"timestamps": ["2024-01-01T00:00:00"], "interval_seconds": [3600], "pv_ac_power_w": [800.0]}, {"timestamps": ["2024-01-01T00:00:00"], "interval_seconds": [3600], "wind_power_w": [700.0]})
    try:
        match_hybrid({**load_s, "electric_power_w": [float("nan")]}, pv_s, wind_s)
        nan_result = "accepted"
    except ValueError as exc:
        nan_result = f"rejected: {exc}"
    old_path = ROOT / "operation_planning" / "results" / "phase2b_wind" / "guangzhou_2024_full_chain.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    new = json.loads((OUT / "guangzhou_2024_full_chain.json").read_text(encoding="utf-8"))
    def compact(doc):
        return {row["scenario_id"]: {"capex_cny": row["economics"].get("capex_cny"), "old_or_new_npv_cny": row["economics"].get("npv_cny"), "incremental_npv_vs_s0_cny": row["economics"].get("incremental_npv_vs_s0_cny"), "total_lifecycle_spend_cny": row["economics"].get("total_lifecycle_spend_cny")} for row in doc["candidates"]}
    evidence = {"calculation_version": "phase2b-cost-fix-v1", "cashflow_definition": {"initial_cny": 105.0, "year_end_cny": [110.0], "discount_rate": .10, "npv_cny": discounted_cashflow_npv(105.0, [110.0], .10)}, "default_guangzhou_2024_old": compact(old), "default_guangzhou_2024_new": compact(new), "pv_only_15y_nonzero_discount_engine_compare": {"pv_lifecycle_npv_cny": pv_only_engine["npv_cny"], "hybrid_lifecycle_npv_cny": hybrid_only_engine["npv_cny"], "absolute_difference_cny": abs(float(pv_only_engine["npv_cny"]) - float(hybrid_only_engine["npv_cny"]))}, "short_case": {"pv_15y_replacement_year12_cny": next(row["replacement_cny"] for row in pv["economics"]["yearly"] if row["year"] == 12), "zero_turbine_capex_cny": wind0["economics"].get("capex_cny"), "missing_quote_recommendation": missing["recommendation"], "roof_1m2_s1_status": next(row["constraint_status"] for row in roof["candidates"] if row["scenario_id"] == "S1_pv"), "nan_guard": nan_result}, "notes": ["旧112条/九组结果只作回归；新结果使用同一缓存天气和修复后规则。", "npv_cny为净现金流现值；incremental_npv_vs_s0_cny用于方案比较；total_cost_npv_cny为其相反数。"]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "regression_evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence["cashflow_definition"] | evidence["short_case"], ensure_ascii=False))


if __name__ == "__main__":
    main()
