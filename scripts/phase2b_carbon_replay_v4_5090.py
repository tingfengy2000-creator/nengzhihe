"""Generate the phase-two-B v4 replay with Guangzhou TOU and three tiers.

The v3 replay is immutable.  This runner recalculates the same room-contract
cases plus small/medium/large bounded scenarios using the official Guangzhou
TOU benchmark as the main tariff and constant-price sensitivities.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from copy import deepcopy
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from operation_planning.carbon import REFERENCE_CARBON_PRICE_CNY_PER_T, REFERENCE_CARBON_PRICE_SOURCE
from operation_planning.hybrid import HybridScenario, run_hybrid_planning
from operation_planning.economics import discounted_cashflow_npv
from operation_planning.pv import PVQuote, PVScenario
from operation_planning.project_load import aggregate_project_load
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.weather import load_pv_weather, load_weather
from operation_planning.wind import WindScenario, WindTurbineProfile, WindQuote

OUT = ROOT / "operation_planning" / "results" / "phase2b_carbon_5090"
VIEWER_OUT = ROOT / "docs" / "handoff" / "replay_viewer" / "replay_cases_v4.json"
WEATHER_REL = "operation_planning/data/weather_pv/guangzhou_2024.json"
OFFICIAL_TARIFF_ID = "guangzhou_industrial_lt1kv_202110"


def _sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _quotes(*, pv_complete: bool = True) -> tuple[PVQuote, WindQuote]:
    pv = PVQuote(module_cny_per_kwp=1800, inverter_cny_per_kwp=600, structure_cny_per_kwp=500, installation_cny_per_kwp=800, grid_connection_cny=0, maintenance_cny_per_kwp_year=30, inverter_replacement_year=12, inverter_replacement_fraction=0.15, residual_fraction=0.05) if pv_complete else PVQuote()
    wind = WindQuote(turbine_cny=45000, tower_cny=15000, foundation_cny=10000, installation_cny=12000, grid_connection_cny=0, maintenance_cny_per_year=1200, residual_fraction=0.05)
    return pv, wind


def _scenarios(*, budget: Optional[float], roof: float, pv_complete: bool, pv_capacity: float, wind_count: int, import_price: float, study_years: int, tariff_id: str, tariff_application: str) -> tuple[PVScenario, HybridScenario, Dict[str, Any]]:
    pv_quote, wind_quote = _quotes(pv_complete=pv_complete)
    pv = PVScenario(site_id="guangzhou", year=2024, roof_area_m2=roof, requested_capacities_kwp=[0, pv_capacity], quote=pv_quote, import_price_cny_per_kwh=import_price, tariff_id=tariff_id, tariff_application=tariff_application, study_years=study_years)
    hybrid = HybridScenario(site_id="guangzhou", year=2024, pv_capacity_kwp=pv_capacity, wind=WindScenario(site_id="guangzhou", year=2024, turbine_count=wind_count, hub_height_m=9, source_height_m=10, hellman_exponent=0.14), budget_cny=budget, allow_export=False, import_price_cny_per_kwh=import_price, study_years=study_years, pv_quote=pv_quote, wind_quote=wind_quote, shared_connection_cny=0)
    return pv, hybrid, {"pv_quote": asdict(pv_quote), "wind_quote": asdict(wind_quote), "hub_height_m": hybrid.wind.hub_height_m, "hellman_exponent": hybrid.wind.hellman_exponent}


def _candidate(item: Dict[str, Any]) -> Dict[str, Any]:
    econ = item.get("economics") or {}
    return {"scenario_id": item.get("scenario_id"), "pv_capacity_kwp": item.get("pv_capacity_kwp"), "wind_turbine_count": item.get("wind_turbine_count"), "generation_kwh": item.get("generation_kwh"), "pv_generation_kwh": item.get("pv_generation_kwh"), "wind_generation_kwh": item.get("wind_generation_kwh"), "self_use_kwh": item.get("self_use_kwh"), "grid_import_kwh": item.get("grid_import_kwh"), "grid_export_kwh": item.get("grid_export_kwh"), "curtailment_kwh": item.get("curtailment_kwh"), "load_coverage_rate": item.get("load_coverage_rate"), "constraint_status": item.get("constraint_status"), "constraint_reasons": item.get("constraint_reasons"), "admission_status": item.get("admission_status"), "equivalent_to": item.get("equivalent_to"), "economics_status": econ.get("status"), "capex_cny": econ.get("capex_cny"), "npv_cny": econ.get("npv_cny"), "total_cost_npv_cny": econ.get("total_cost_npv_cny"), "incremental_npv_vs_s0_cny": econ.get("incremental_npv_vs_s0_cny"), "economics": {"study_years": econ.get("study_years"), "yearly": econ.get("yearly"), "cashflow_convention": econ.get("cashflow_convention")}, "carbon": item.get("carbon"), "annual_offset_estimate": item.get("annual_offset_estimate"), "storage_upper_bound": item.get("storage_upper_bound")}


def _chart(report: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    item = next(x for x in report["candidates"] if x["scenario_id"] == scenario_id)
    return {"scenario_id": scenario_id, **item["hourly"]}


def _compact_chart(chart: Dict[str, Any]) -> Dict[str, Any]:
    fields = ("timestamps", "load_kwh", "pv_generation_kwh", "wind_generation_kwh", "self_use_kwh", "grid_import_kwh", "curtailment_kwh")
    out = {"scenario_id": chart.get("scenario_id"), **{k: [round(float(v), 4) if isinstance(v, (int, float)) and not isinstance(v, bool) else v for v in chart.get(k, [])] if isinstance(chart.get(k), list) else chart.get(k) for k in fields}}
    if any(abs(float(v)) > 1e-12 for v in chart.get("grid_export_kwh", [])):
        out["grid_export_kwh"] = [round(float(v), 4) for v in chart["grid_export_kwh"]]
    return out


def _constant_sensitivity(report: Dict[str, Any], price: float, label: str) -> Dict[str, Any]:
    """Reprice the already matched annual trajectories; physics is unchanged."""
    rows = []
    baseline = next(x for x in report["candidates"] if x["scenario_id"] == "S0_grid")
    base_econ = baseline.get("economics") or {}
    rate = float(base_econ.get("discount_rate", 0.0) or 0.0)
    base_yearly = list(base_econ.get("yearly") or [])
    base_costs = [float(r.get("grid_import_kwh", 0.0) or 0.0) * float(price) for r in base_yearly if int(r.get("year", 0)) > 0]
    baseline_npv = discounted_cashflow_npv(0.0, [-x for x in base_costs], rate)
    for source in report["candidates"]:
        econ = deepcopy(source.get("economics") or {})
        if econ.get("status") not in {"complete", "feasible"}:
            new_econ = {"status": econ.get("status"), "total_cost_npv_cny": None, "incremental_npv_vs_s0_cny": None}
        else:
            yearly = list(econ.get("yearly") or [])
            cash = []
            for row in yearly:
                if int(row.get("year", 0)) == 0:
                    continue
                imp = float(row.get("grid_import_kwh", 0.0) or 0.0) * float(price)
                cash.append(-imp - float(row.get("maintenance_cny", 0.0) or 0.0) - float(row.get("replacement_cny", 0.0) or 0.0) + float(row.get("residual_cny", 0.0) or 0.0))
            npv = discounted_cashflow_npv(float(econ.get("capex_cny", 0.0) or 0.0), cash, rate)
            new_econ = {"status": econ.get("status"), "total_cost_npv_cny": -npv, "incremental_npv_vs_s0_cny": npv - baseline_npv, "capex_cny": econ.get("capex_cny"), "study_years": econ.get("study_years"), "discount_rate": rate}
        rows.append({"scenario_id": source["scenario_id"], "total_cost_npv_cny": new_econ.get("total_cost_npv_cny"), "incremental_npv_vs_s0_cny": new_econ.get("incremental_npv_vs_s0_cny"), "self_use_kwh": source.get("self_use_kwh"), "generation_kwh": source.get("generation_kwh"), "curtailment_kwh": source.get("curtailment_kwh"), "constraint_status": source.get("constraint_status"), "admission_status": source.get("admission_status"), "economics_status": new_econ.get("status")})
    eligible = [x for x in rows if x.get("admission_status") == "eligible" and x.get("incremental_npv_vs_s0_cny") is not None]
    best = max(eligible, key=lambda x: float(x["incremental_npv_vs_s0_cny"])) if eligible else None
    unknown = [x for x in rows if x.get("admission_status") == "unknown"]
    return {"label": label, "tariff_id": "user_constant", "price_cny_per_kwh": float(price), "recommendation": {"status": "conditional" if best and not unknown else ("conditional_subset" if best else "not_available"), "scenario_id": best["scenario_id"] if best else None, "all_candidates_conclusion": "unresolved" if unknown else "resolved_with_exclusions"}, "candidates": rows, "reprice_basis": "same matched hourly trajectories and quote constraints; only tariff cashflow recalculated"}


def _carbon_reference(null_carbon: Dict[str, Any]) -> Dict[str, Any]:
    """Add the public reference carbon-price scenario without rerunning physics."""
    out = deepcopy(null_carbon)
    rate = float(out.get("yearly", [{}])[0].get("carbon_revenue_present_value_cny") or 0.0) if out.get("yearly") else 0.0
    revenues = []
    for row in out.get("yearly", []):
        year = int(row.get("year", 0))
        avoided_t = float(row.get("avoided_kgco2", 0.0) or 0.0) / 1000.0
        rev = avoided_t * REFERENCE_CARBON_PRICE_CNY_PER_T
        pv = rev / ((1.0 + rate) ** year) if year > 0 else 0.0
        row["carbon_revenue_cny"] = rev
        row["carbon_revenue_present_value_cny"] = pv
        revenues.append((rev, pv))
    out["carbon_revenue_cny_study_period"] = sum(x[0] for x in revenues)
    out["carbon_revenue_present_value_cny"] = sum(x[1] for x in revenues)
    inc = out.get("cost_per_tco2_cny")
    # Use the candidate's original incremental NPV when available.
    original_incremental = None
    if out.get("avoided_tco2_study_period") and inc is not None:
        original_incremental = -float(inc) * float(out["avoided_tco2_study_period"])
    out["incremental_npv_with_carbon_cny"] = None if original_incremental is None else original_incremental + out["carbon_revenue_present_value_cny"]
    return out


def _case(case_id: str, label: str, demo_role: str, room_spec: RoomSpec, weather: Dict[str, Any], pv_weather: Dict[str, Any], source_commit: str, *, budget: Optional[float] = 90000, roof: float = 50, pv_complete: bool = True, pv_capacity: float = 2, wind_count: int = 1, study_years: int = 10, building: Optional[Dict[str, Any]] = None, variant_reason: Optional[str] = None, storage_capacities: Optional[list[float]] = None, feasibility: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    single = simulate_room(weather, room_spec)
    project = aggregate_project_load(single)
    storage_request = {"capacities_kwh": storage_capacities or ([0, 50, 100, 200, 500] if room_spec.room_count >= 20 else [0, 5, 10, 20, 50]), "round_trip_efficiency": 0.90}
    main_pv, main_hybrid, quote_input = _scenarios(budget=budget, roof=roof, pv_complete=pv_complete, pv_capacity=pv_capacity, wind_count=wind_count, import_price=0.66, study_years=study_years, tariff_id=OFFICIAL_TARIFF_ID, tariff_application="current_tariff_on_reference_weather")
    null_carbon = {"carbon_price_cny_per_t": None}
    report = run_hybrid_planning(project, pv_weather, main_pv, main_hybrid, WindTurbineProfile.from_file(), include_hourly=True, carbon=null_carbon, storage=storage_request)
    # Sensitivities use the same physical trajectories; only annual cashflows
    # are repriced.  The carbon-price view is likewise derived from the
    # validated yearly avoided-emission rows.
    sensitivity = [_constant_sensitivity(report, price, name) for price, name in ((0.66, "恒价0.66用户情景"), (1.20, "恒价1.20用户情景"))]
    recommendation_id = report["recommendation"].get("scenario_id") or "S0_grid"
    total_cost = {x["scenario_id"]: (x.get("economics") or {}).get("total_cost_npv_cny") for x in report["candidates"]}
    context = pv_weather.get("context") or {}
    main_input = {"site_id": "guangzhou", "year": 2024, "room": asdict(room_spec), "building": building or {"floors": 1, "rooms_per_floor": room_spec.room_count, "roof_area_m2": roof, "roof_area_basis": "single-floor footprint; site condition"}, "pv_capacity_kwp": pv_capacity, "wind_turbine_count": wind_count, "budget_cny": budget, "roof_area_m2": roof, "usable_fraction": main_pv.usable_fraction, "tariff_id": OFFICIAL_TARIFF_ID, "tariff_application": "current_tariff_on_reference_weather", "tariff_basis": "广州官方2021-10峰平谷表；用于2024参考天气的现行档案情景，不是2024实际账单", "sensitivity_import_prices_cny_per_kwh": [0.66, 1.20], "allow_export": False, "study_years": study_years, "pv_quote": quote_input["pv_quote"], "wind_quote": quote_input["wind_quote"], "hub_height_m": quote_input["hub_height_m"], "hellman_exponent": quote_input["hellman_exponent"], "carbon": null_carbon, "carbon_price_reference": {"carbon_price_cny_per_t": REFERENCE_CARBON_PRICE_CNY_PER_T, "source": REFERENCE_CARBON_PRICE_SOURCE}, "storage": storage_request}
    ref_carbon = {x["scenario_id"]: _carbon_reference(x["carbon"]) for x in report["candidates"]}
    case = {"case_id": case_id, "label": label, "demo_role": demo_role, "variant_reason": variant_reason, "feasibility": feasibility, "source": {"source_commit": source_commit, "calculation_version": report["calculation_version"], "source_result_file": "operation_planning/results/phase2b_carbon_5090/replay_cases_v4.json", "mode": "fixed_replay_only; 5090 full-year calculation"}, "input": main_input, "weather": {"source": WEATHER_REL, "hash": pv_weather.get("hash"), "site": context.get("site"), "start": context.get("start"), "end": context.get("end"), "normalization_version": (pv_weather.get("weather_normalization") or {}).get("version")}, "load_context": {**report["load_context"], "project_load_contract": project.get("project_load_contract"), "single_room_summary": project.get("single_room_summary"), "project_scope": project["load_series"].get("scope")}, "project_load_contract": project.get("project_load_contract"), "room_count": project["load_series"].get("room_count"), "units_per_room": project["load_series"].get("units_per_room"), "service_quality": report["load_context"]["service_quality"], "carbon_context": report["carbon_context"], "recommendation": report["recommendation"], "total_cost_npv_cny": total_cost, "candidates": [_candidate(x) for x in report["candidates"]], "chart": _chart(report, "S3_pv_wind"), "chart_recommended": _chart(report, recommendation_id), "carbon_price_scenarios": [{"carbon_price_cny_per_t": None, "label": "不计碳收益", "source": None, "candidate_carbon": {x["scenario_id"]: x["carbon"] for x in report["candidates"]}}, {"carbon_price_cny_per_t": REFERENCE_CARBON_PRICE_CNY_PER_T, "label": "公开报告参考情景，不代表可成交", "source": REFERENCE_CARBON_PRICE_SOURCE, "candidate_carbon": ref_carbon}], "tariff_sensitivities": sensitivity, "not_provided": ["只计空调用电，不含照明、插座、生产工艺和建筑总表负荷", "报价、电价、寿命和碳价为用户情景或公开档案情景", "官方广州档案为2021-10公布的广州五市一般工商业不满1kV表，套用2024天气不是2024实际账单", "屋顶承重、消防间距、并网审批待现场确认", "不代表现场精度、经核证减排量、采购建议或碳市场资格"]}
    case["case_hash"] = _sha(case)
    return case


def _round_viewer(package: Dict[str, Any]) -> Dict[str, Any]:
    viewer = json.loads(json.dumps(package, ensure_ascii=False))
    for case in viewer["cases"]:
        case["chart"] = _compact_chart(case["chart"])
        case["chart_recommended"] = _compact_chart(case["chart_recommended"])
    viewer["display_contract"].update({"hourly_columns": ["timestamps", "load_kwh", "pv_generation_kwh", "wind_generation_kwh", "self_use_kwh", "grid_import_kwh", "curtailment_kwh"], "hourly_display_decimals": 4, "full_precision_results": "operation_planning/results/phase2b_carbon_5090/replay_cases_v4.json", "chart_recommended_from_report": True, "main_tariff": OFFICIAL_TARIFF_ID, "sensitivity_tariffs": ["user_constant:0.66", "user_constant:1.20"]})
    return viewer


def main() -> int:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_commit = _source()
    weather = load_weather("guangzhou", 2024)
    pv_weather = load_pv_weather("guangzhou", 2024)
    if list(weather["time"]) != list(pv_weather["time"]):
        raise AssertionError("负荷与风光天气时间轴不一致")
    one = RoomSpec(area_m2=35, orientation="north", window_wall_ratio=0.1, insulation_u_w_m2k=0.3, people_count=2, equipment_gain_w=100, equipment_count=6, units_per_room=6, room_count=1)
    three = RoomSpec(area_m2=35, orientation="north", window_wall_ratio=0.1, insulation_u_w_m2k=0.3, people_count=2, equipment_gain_w=100, equipment_count=6, units_per_room=6, room_count=3)
    undersized = RoomSpec(equipment_count=1, units_per_room=1, room_count=1)
    two = RoomSpec(equipment_count=2, units_per_room=2, room_count=1)
    cases = [
        _case("primary_not_worth_it", "主案例A：小型35㎡、广州官方分时电价下不安装更合算", "primary_not_worth_it", one, weather, pv_weather, source_commit, roof=35, building={"floors": 1, "rooms_per_floor": 1, "roof_area_m2": 35, "roof_area_basis": "single-floor footprint; usable area is input condition"}),
        _case("primary_worth_it", "主案例B：同一广州天气、40间公共建筑房间", "primary_worth_it", RoomSpec(**{**asdict(one), "room_count": 40}), weather, pv_weather, source_commit, roof=350, pv_capacity=20, budget=300000, building={"floors": 4, "rooms_per_floor": 10, "room_count": 40, "roof_area_m2": 350, "roof_area_basis": "10 rooms × 35m² single-floor footprint; four floors; roof not multiplied"}),
        _case("primary_adequate_three_rooms", "房间口径：三间同类房间项目负荷", "primary_no_service_gap", three, weather, pv_weather, source_commit),
        _case("comparison_undersized_one_unit", "口径对照：默认一台设备的服务缺口", "undersized_comparison", undersized, weather, pv_weather, source_commit),
        _case("comparison_two_unit_reference", "口径对照：每间两台设备", "two_unit_reference", two, weather, pv_weather, source_commit),
        _case("variant_budget_insufficient", "状态变体：预算不足", "state_variant", one, weather, pv_weather, source_commit, budget=30000, variant_reason="风机与风光组合超过预算；保留预算内候选"),
        _case("variant_missing_pv_quote", "状态变体：缺少光伏报价", "state_variant", one, weather, pv_weather, source_commit, pv_complete=False, variant_reason="光伏物理结果保留，经济字段未决；不证明S0最优"),
        _case("variant_roof_area_insufficient", "状态变体：屋顶面积不足", "state_variant", one, weather, pv_weather, source_commit, roof=1, variant_reason="2kWp超过可用屋顶上限，PV相关候选排除"),
        _case("tier_small", "小档：35㎡公共建筑办公室", "tier_small", one, weather, pv_weather, source_commit, roof=35, building={"floors": 1, "rooms_per_floor": 1, "roof_area_m2": 35, "roof_area_basis": "single-floor footprint"}),
        _case("tier_medium", "中档：四层公共建筑40间同类房间", "tier_medium", RoomSpec(**{**asdict(one), "room_count": 40}), weather, pv_weather, source_commit, roof=350, pv_capacity=20, budget=300000, building={"floors": 4, "rooms_per_floor": 10, "room_count": 40, "roof_area_m2": 350, "roof_area_basis": "single-floor footprint; roof not multiplied by floors"}),
        _case("tier_large", "大档：工业厂房内空调分区代理（不含生产工艺负荷）", "tier_large", RoomSpec(**{**asdict(one), "room_count": 100}), weather, pv_weather, source_commit, roof=5000, pv_capacity=100, wind_count=1, budget=500000, storage_capacities=[0, 50, 100, 200, 500], building={"floors": 1, "conditioned_zones": 100, "zone_area_m2": 35, "roof_area_m2": 5000, "roof_area_basis": "single-floor factory roof; site confirmation required", "scope": "air-conditioned zones only"}, feasibility={"status": "bounded_proxy_feasible", "conclusion": "可计算为厂房空调分区代理；不代表全厂能源方案", "why": "当前热湿模型只覆盖同类房间冷却负荷，缺少生产设备、工艺、照明和真实厂房机组数据", "alternative_case_id": "tier_large_conditioned_zones", "not_modelled": ["生产工艺负荷", "照明与插座", "VRF/冷水机组部分负荷性能", "厂房实测校准"]}),
    ]
    package = {"format_version": "5090-carbon-replay-v4", "description": "阶段二B v4：广州官方工商业峰平谷档案主口径、0.66/1.20恒价敏感性、小中大三档、碳价情景、S3与推荐方案双曲线；v3保留不覆盖。", "source": {"source_commit": source_commit, "calculation_version": "phase2b-carbon-5090-v4", "weather_hash": pv_weather.get("hash"), "mode": "fixed_replay_only", "machine_role": "5090"}, "main_tariff": {"tariff_id": OFFICIAL_TARIFF_ID, "application": "current_tariff_on_reference_weather", "source_url": "https://fgw.gz.gov.cn/ztzl/gzsfzggwzdlyxxgkzl/ys/content/post_9497778.html", "note": "官方广州五市2021-10电价表；以明确情景套用于2024参考天气，非2024实际账单"}, "tiers": {"small": "tier_small", "medium": "tier_medium", "large": "tier_large"}, "cases": cases, "display_contract": {"numbers_from_data": True, "carbon_fields_from_backend": True, "annual_offset_is_comparison_only": True, "storage_is_ideal_upper_bound_only": True, "old_replays_immutable": True}}
    OUT.mkdir(parents=True, exist_ok=True)
    full = OUT / "replay_cases_v4.json"
    full.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    viewer = _round_viewer(package)
    VIEWER_OUT.parent.mkdir(parents=True, exist_ok=True)
    VIEWER_OUT.write_text(json.dumps(viewer, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"status": "passed", "source_commit": source_commit, "started_utc": started, "ended_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "machine_role": "5090", "case_count": len(cases), "case_summaries": [{"case_id": c["case_id"], "room_count": c["room_count"], "units_per_room": c["units_per_room"], "service_status": c["service_quality"]["status"], "recommendation": c["recommendation"], "chart_scenario_id": c["chart"]["scenario_id"], "chart_recommended_scenario_id": c["chart_recommended"]["scenario_id"], "case_hash": c["case_hash"]} for c in cases], "package_file_sha256": _file_sha(full), "viewer_file_sha256": _file_sha(VIEWER_OUT), "package_sha256": _sha(package), "viewer_sha256": _sha(viewer), "viewer_path": "docs/handoff/replay_viewer/replay_cases_v4.json", "previous_replay_preserved": "replay_cases_v3.json"}
    (OUT / "run_manifest_v4.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
