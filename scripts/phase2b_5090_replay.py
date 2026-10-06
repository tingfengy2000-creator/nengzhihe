"""Generate small 5090-only API/replay fixtures from the current source."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from operation_planning.weather import load_weather, load_pv_weather
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.pv import PVQuote, PVScenario
from operation_planning.wind import WindQuote, WindScenario, WindTurbineProfile
from operation_planning.hybrid import HybridScenario, run_hybrid_planning

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "operation_planning" / "results" / "phase2b_semantics_5090"
PVQ = PVQuote(module_cny_per_kwp=1800, inverter_cny_per_kwp=600, structure_cny_per_kwp=500, installation_cny_per_kwp=800, grid_connection_cny=0, maintenance_cny_per_kwp_year=30, inverter_replacement_year=12, inverter_replacement_fraction=.15, residual_fraction=.05)
WQ = WindQuote(turbine_cny=45000, tower_cny=15000, foundation_cny=10000, installation_cny=12000, grid_connection_cny=0, maintenance_cny_per_year=1200, residual_fraction=.05)


def run_case(case_id, *, budget=90000, roof=50, quote=PVQ, service=True):
    lw = load_weather("guangzhou", 2024); pw = load_pv_weather("guangzhou", 2024)
    room = RoomSpec(area_m2=35, people_count=4, start_hour=8, end_hour=18, cooling_setpoint_c=26, rh_setpoint_percent=60)
    load = simulate_room(lw, room)
    if not service:
        load["summary"] = {**load.get("summary", {}), "capacity_shortfall_hours": 0, "unmet_temp_degree_hours": 0, "unmet_rh_percent_hours": 0}
    pvs = PVScenario(site_id="guangzhou", year=2024, roof_area_m2=roof, usable_fraction=.8, import_price_cny_per_kwh=.66, quote=quote)
    hs = HybridScenario(site_id="guangzhou", year=2024, pv_capacity_kwp=2, wind=WindScenario(site_id="guangzhou", year=2024, turbine_count=1, hub_height_m=9), budget_cny=budget, allow_export=False, import_price_cny_per_kwh=.66, study_years=10, shared_connection_cny=0, pv_quote=quote, wind_quote=WQ)
    report = run_hybrid_planning(load, pw, pvs, hs, WindTurbineProfile.from_file(), include_hourly=False)
    return {"case_id": case_id, "source": {"site": "guangzhou", "year": 2024, "weather_hash": report["weather_provenance"].get("hash"), "calculation_version": report["calculation_version"]}, "request": {"budget_cny": budget, "roof_area_m2": roof, "pv_quote_complete": quote.module_cny_per_kwp is not None}, "service_quality": report["load_context"]["service_quality"], "recommendation": report["recommendation"], "candidates": [{"scenario_id": c["scenario_id"], "pv_capacity_kwp": c["pv_capacity_kwp"], "wind_turbine_count": c["wind_turbine_count"], "generation_kwh": c["generation_kwh"], "grid_import_kwh": c["grid_import_kwh"], "capex_cny": c["economics"].get("capex_cny"), "incremental_npv_vs_s0_cny": c["economics"].get("incremental_npv_vs_s0_cny"), "constraint_status": c["constraint_status"], "admission_status": c.get("admission_status"), "constraint_reasons": c["constraint_reasons"], "economics_status": c["economics"].get("status")} for c in report["candidates"]]}


def main():
    cases = [run_case("default_90000"), run_case("budget_60000", budget=60000), run_case("missing_pv_quote", quote=PVQuote()), run_case("roof_1m2", roof=1)]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "replay_cases.json").write_text(json.dumps({"source_commit": "pending-source-commit", "cases": cases}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cases": len(cases), "path": str(OUT / "replay_cases.json")}, ensure_ascii=False))


if __name__ == "__main__": main()
