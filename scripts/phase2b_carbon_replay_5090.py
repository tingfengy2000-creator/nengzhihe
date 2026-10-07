"""Generate the immutable v3 carbon replay for 5060 review.

This script uses the existing four room-contract cases and three explicit
state variants.  It writes a compact candidate summary plus one complete
hourly chart per case; old replay files remain untouched.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from operation_planning.carbon import REFERENCE_CARBON_PRICE_CNY_PER_T, REFERENCE_CARBON_PRICE_SOURCE
from operation_planning.hybrid import HybridScenario, run_hybrid_planning
from operation_planning.pv import PVQuote, PVScenario
from operation_planning.project_load import aggregate_project_load
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.weather import load_pv_weather, load_weather
from operation_planning.wind import WindScenario, WindTurbineProfile, WindQuote


OUT = ROOT / "operation_planning" / "results" / "phase2b_carbon_5090"
VIEWER_OUT = ROOT / "docs" / "handoff" / "replay_viewer" / "replay_cases_v3.json"
WEATHER_REL = "operation_planning/data/weather_pv/guangzhou_2024.json"


def _sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _source() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _quotes(*, pv_complete: bool = True) -> tuple[PVQuote, WindQuote]:
    pv = PVQuote(module_cny_per_kwp=1800, inverter_cny_per_kwp=600, structure_cny_per_kwp=500, installation_cny_per_kwp=800, grid_connection_cny=0, maintenance_cny_per_kwp_year=30, inverter_replacement_year=12, inverter_replacement_fraction=0.15, residual_fraction=0.05) if pv_complete else PVQuote()
    wind = WindQuote(turbine_cny=45000, tower_cny=15000, foundation_cny=10000, installation_cny=12000, grid_connection_cny=0, maintenance_cny_per_year=1200, residual_fraction=0.05)
    return pv, wind


def _scenarios(*, budget: Optional[float] = 90000, roof: float = 50, pv_complete: bool = True) -> tuple[PVScenario, HybridScenario, Dict[str, Any]]:
    pv_quote, wind_quote = _quotes(pv_complete=pv_complete)
    pv = PVScenario(site_id="guangzhou", year=2024, roof_area_m2=roof, requested_capacities_kwp=[0, 2], quote=pv_quote, import_price_cny_per_kwh=0.66, study_years=10)
    hybrid = HybridScenario(site_id="guangzhou", year=2024, pv_capacity_kwp=2, wind=WindScenario(site_id="guangzhou", year=2024, turbine_count=1, hub_height_m=9, source_height_m=10, hellman_exponent=0.14), budget_cny=budget, allow_export=False, import_price_cny_per_kwh=0.66, study_years=10, pv_quote=pv_quote, wind_quote=wind_quote, shared_connection_cny=0)
    return pv, hybrid, {"pv_quote": asdict(pv_quote), "wind_quote": asdict(wind_quote), "hub_height_m": hybrid.wind.hub_height_m, "hellman_exponent": hybrid.wind.hellman_exponent}


def _candidate(item: Dict[str, Any]) -> Dict[str, Any]:
    econ = item.get("economics") or {}
    return {
        "scenario_id": item.get("scenario_id"),
        "pv_capacity_kwp": item.get("pv_capacity_kwp"),
        "wind_turbine_count": item.get("wind_turbine_count"),
        "generation_kwh": item.get("generation_kwh"),
        "pv_generation_kwh": item.get("pv_generation_kwh"),
        "wind_generation_kwh": item.get("wind_generation_kwh"),
        "self_use_kwh": item.get("self_use_kwh"),
        "grid_import_kwh": item.get("grid_import_kwh"),
        "grid_export_kwh": item.get("grid_export_kwh"),
        "curtailment_kwh": item.get("curtailment_kwh"),
        "load_coverage_rate": item.get("load_coverage_rate"),
        "constraint_status": item.get("constraint_status"),
        "constraint_reasons": item.get("constraint_reasons"),
        "admission_status": item.get("admission_status"),
        "equivalent_to": item.get("equivalent_to"),
        "economics_status": econ.get("status"),
        "capex_cny": econ.get("capex_cny"),
        "npv_cny": econ.get("npv_cny"),
        "total_cost_npv_cny": econ.get("total_cost_npv_cny"),
        "incremental_npv_vs_s0_cny": econ.get("incremental_npv_vs_s0_cny"),
        "economics": {"study_years": econ.get("study_years"), "yearly": econ.get("yearly"), "cashflow_convention": econ.get("cashflow_convention")},
        "carbon": item.get("carbon"),
        "annual_offset_estimate": item.get("annual_offset_estimate"),
    }


def _case(case_id: str, label: str, demo_role: str, room_spec: RoomSpec, weather: Dict[str, Any], pv_weather: Dict[str, Any], source_commit: str, *, budget: Optional[float] = 90000, roof: float = 50, pv_complete: bool = True, carbon_request: Optional[Dict[str, Any]] = None, variant_reason: Optional[str] = None, add_price_view: bool = False) -> Dict[str, Any]:
    single = simulate_room(weather, room_spec)
    project = aggregate_project_load(single)
    pv, hybrid, quote_input = _scenarios(budget=budget, roof=roof, pv_complete=pv_complete)
    report = run_hybrid_planning(project, pv_weather, pv, hybrid, WindTurbineProfile.from_file(), include_hourly=True, carbon=carbon_request)
    s3 = next(item for item in report["candidates"] if item["scenario_id"] == "S3_pv_wind")
    weather_context = pv_weather.get("context") or {}
    input_data = {
        "site_id": "guangzhou", "year": 2024, "room": asdict(room_spec),
        "pv_capacity_kwp": 2, "wind_turbine_count": 1, "budget_cny": budget,
        "roof_area_m2": roof, "usable_fraction": pv.usable_fraction,
        "import_price_cny_per_kwh": 0.66, "allow_export": False, "study_years": 10,
        "pv_quote": quote_input["pv_quote"], "wind_quote": quote_input["wind_quote"],
        "hub_height_m": quote_input["hub_height_m"], "hellman_exponent": quote_input["hellman_exponent"],
        "carbon": carbon_request or {"carbon_price_cny_per_t": None},
    }
    total_cost = {item["scenario_id"]: (item.get("economics") or {}).get("total_cost_npv_cny") for item in report["candidates"]}
    case = {
        "case_id": case_id, "label": label, "demo_role": demo_role, "variant_reason": variant_reason,
        "source": {"source_commit": source_commit, "calculation_version": report["calculation_version"], "source_result_file": "operation_planning/results/phase2b_carbon_5090/replay_cases_v3.json", "mode": "fixed_replay_only; 5090 full-year calculation"},
        "input": input_data, "weather": {"source": WEATHER_REL, "hash": pv_weather.get("hash"), "site": weather_context.get("site"), "start": weather_context.get("start"), "end": weather_context.get("end"), "normalization_version": (pv_weather.get("weather_normalization") or {}).get("version")},
        "load_context": {**report["load_context"], "project_load_contract": project.get("project_load_contract"), "single_room_summary": project.get("single_room_summary"), "project_scope": project["load_series"].get("scope")},
        "project_load_contract": project.get("project_load_contract"), "room_count": project["load_series"].get("room_count"), "units_per_room": project["load_series"].get("units_per_room"),
        "service_quality": report["load_context"]["service_quality"], "carbon_context": report["carbon_context"], "recommendation": report["recommendation"],
        "total_cost_npv_cny": total_cost,
        "candidates": [_candidate(item) for item in report["candidates"]],
        "chart": {"scenario_id": "S3_pv_wind", **s3["hourly"]},
        "not_provided": ["不同房间朝向、时段、设备和独立天气未建模", "报价、电价、寿命和碳价为用户情景", "不代表现场精度、经核证减排量、采购建议或碳市场资格"],
    }
    if add_price_view:
        ref_request = {"carbon_price_cny_per_t": REFERENCE_CARBON_PRICE_CNY_PER_T}
        ref_report = run_hybrid_planning(project, pv_weather, pv, hybrid, WindTurbineProfile.from_file(), include_hourly=False, carbon=ref_request)
        case["carbon_price_scenarios"] = [
            {"carbon_price_cny_per_t": None, "label": "不计碳收益", "source": None, "candidate_carbon": {x["scenario_id"]: x["carbon"] for x in report["candidates"]}},
            {"carbon_price_cny_per_t": REFERENCE_CARBON_PRICE_CNY_PER_T, "label": "公开报告参考情景，不代表可成交", "source": REFERENCE_CARBON_PRICE_SOURCE, "candidate_carbon": {x["scenario_id"]: x["carbon"] for x in ref_report["candidates"]}},
        ]
    case["case_hash"] = _sha(case)
    return case


def main() -> int:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_commit = _source()
    weather = load_weather("guangzhou", 2024)
    pv_weather = load_pv_weather("guangzhou", 2024)
    if list(weather["time"]) != list(pv_weather["time"]):
        raise AssertionError("负荷与风光天气时间轴不一致")
    adequate_one = RoomSpec(area_m2=35, orientation="north", window_wall_ratio=0.1, insulation_u_w_m2k=0.3, people_count=2, equipment_gain_w=100, equipment_count=6, units_per_room=6, room_count=1)
    adequate_three = RoomSpec(area_m2=35, orientation="north", window_wall_ratio=0.1, insulation_u_w_m2k=0.3, people_count=2, equipment_gain_w=100, equipment_count=6, units_per_room=6, room_count=3)
    undersized = RoomSpec(equipment_count=1, units_per_room=1, room_count=1)
    two_unit = RoomSpec(equipment_count=2, units_per_room=2, room_count=1)
    no_price = {"carbon_price_cny_per_t": None}
    cases = [
        _case("primary_adequate_one_room", "主演示：容量充足的单房间项目负荷", "primary_no_service_gap", adequate_one, weather, pv_weather, source_commit, carbon_request=no_price, add_price_view=True),
        _case("primary_adequate_three_rooms", "主演示：三间同类房间项目负荷", "primary_no_service_gap", adequate_three, weather, pv_weather, source_commit, carbon_request=no_price),
        _case("comparison_undersized_one_unit", "对照：默认一台设备的服务缺口", "undersized_comparison", undersized, weather, pv_weather, source_commit, carbon_request=no_price),
        _case("comparison_two_unit_reference", "口径对照：默认房间改为每间两台设备", "two_unit_reference", two_unit, weather, pv_weather, source_commit, carbon_request=no_price),
        _case("variant_budget_insufficient", "状态变体：预算不足，保留预算内候选", "state_variant", adequate_one, weather, pv_weather, source_commit, budget=30000, carbon_request=no_price, variant_reason="风机与风光组合超过预算；S0/S1仍可在已完整报价子集内比较"),
        _case("variant_missing_pv_quote", "状态变体：缺少光伏报价", "state_variant", adequate_one, weather, pv_weather, source_commit, pv_complete=False, carbon_request=no_price, variant_reason="光伏物理结果保留，S1/S3经济字段未决；不证明S0最优"),
        _case("variant_roof_area_insufficient", "状态变体：屋顶面积不足", "state_variant", adequate_one, weather, pv_weather, source_commit, roof=1, carbon_request=no_price, variant_reason="2kWp超过可用屋顶上限，PV相关候选明确排除"),
    ]
    package = {"format_version": "5090-carbon-replay-v3", "description": "阶段二B碳排放与年度粗算对照回放；旧回放保留。所有物理数值、碳字段和经济字段来自5090确定性工具。", "source": {"source_commit": source_commit, "calculation_version": "phase2b-carbon-5090-v1", "weather_hash": pv_weather.get("hash"), "mode": "fixed_replay_only"}, "cases": cases, "display_contract": {"numbers_from_data": True, "carbon_fields_from_backend": True, "annual_offset_is_comparison_only": True, "unknown_new_inputs": "待5090验算", "old_replays_immutable": True}}
    OUT.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(package, ensure_ascii=False, indent=2)
    VIEWER_OUT.write_text(raw, encoding="utf-8")
    (OUT / "replay_cases_v3.json").write_text(raw, encoding="utf-8")
    manifest = {"status": "passed", "source_commit": source_commit, "started_utc": started, "ended_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "machine_role": "5090", "case_count": len(cases), "case_summaries": [{"case_id": c["case_id"], "room_count": c["room_count"], "units_per_room": c["units_per_room"], "service_status": c["service_quality"]["status"], "carbon_factor_id": c["carbon_context"]["factor"]["factor_id"], "reference_price_cny_per_t": REFERENCE_CARBON_PRICE_CNY_PER_T if "carbon_price_scenarios" in c else None, "chart_scenario_id": c["chart"]["scenario_id"], "case_hash": c["case_hash"]} for c in cases], "package_sha256": _sha(package), "viewer_path": "docs/handoff/replay_viewer/replay_cases_v3.json", "note": "完整年回放；旧 replay_cases.json 与 replay_cases_room_contract.json 保留为历史证据。"}
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
