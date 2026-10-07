"""Generate phase-two-B v5 replay: real bounded workshop tier and PV sizing sweeps."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib, json, subprocess, sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.phase2b_carbon_replay_v4_5090 import (
    _quotes, _scenarios, _candidate, _chart, _compact_chart,
    _constant_sensitivity, _carbon_reference,
)
from operation_planning.carbon import REFERENCE_CARBON_PRICE_CNY_PER_T, REFERENCE_CARBON_PRICE_SOURCE
from operation_planning.hybrid import run_hybrid_planning
from operation_planning.project_load import aggregate_project_load
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.weather import load_pv_weather, load_weather
from operation_planning.wind import WindTurbineProfile

OUT = ROOT / "operation_planning" / "results" / "phase2b_carbon_5090"
VIEWER_OUT = ROOT / "docs" / "handoff" / "replay_viewer" / "replay_cases_v5.json"
WEATHER_REL = "operation_planning/data/weather_pv/guangzhou_2024.json"
OFFICIAL_TARIFF_ID = "guangzhou_industrial_lt1kv_202610"
TARIFF_URL = "https://energydc.cn/policy/guangdong/2026-09/ffdcada5-baab-11f1-959b-ce30ac533824"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _source() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _report(project: Dict[str, Any], pv_weather: Dict[str, Any], *, budget: Optional[float], roof: float, pv_complete: bool, cap: float, wind_count: int, study_years: int, include_hourly: bool, storage: Dict[str, Any]):
    pv, hybrid, quote_input = _scenarios(
        budget=budget, roof=roof, pv_complete=pv_complete, pv_capacity=cap,
        wind_count=wind_count, import_price=0.66, study_years=study_years,
        tariff_id=OFFICIAL_TARIFF_ID, tariff_application="current_tariff_on_reference_weather",
    )
    report = run_hybrid_planning(project, pv_weather, pv, hybrid, WindTurbineProfile.from_file(), include_hourly=include_hourly, carbon={"carbon_price_cny_per_t": None}, storage=storage)
    return report, quote_input


def _find(report: Dict[str, Any], scenario_id: str) -> Dict[str, Any]:
    return next(x for x in report["candidates"] if x["scenario_id"] == scenario_id)


def _safe_rate(n: Any, d: Any) -> Optional[float]:
    try:
        den = float(d)
        return None if den <= 0 else float(n) / den
    except (TypeError, ValueError):
        return None


def _capacity_row(report: Dict[str, Any], requested: float) -> Dict[str, Any]:
    s1 = _find(report, "S1_pv")
    econ = s1.get("economics") or {}
    carbon = s1.get("carbon") or {}
    generation = float(s1.get("pv_generation_kwh") or s1.get("generation_kwh") or 0.0)
    self_use = float(s1.get("self_use_kwh") or 0.0)
    curtail = float(s1.get("curtailment_kwh") or 0.0)
    s3 = _find(report, "S3_pv_wind")
    return {
        "requested_capacity_kwp": float(requested),
        "scenario_id": "S1_pv",
        "total_cost_npv_cny": econ.get("total_cost_npv_cny"),
        "incremental_npv_vs_s0_cny": econ.get("incremental_npv_vs_s0_cny"),
        "capex_cny": econ.get("capex_cny"),
        "economics_status": econ.get("status"),
        "admission_status": s1.get("admission_status"),
        "constraint_status": s1.get("constraint_status"),
        "constraint_reasons": s1.get("constraint_reasons"),
        "generation_kwh": generation,
        "self_use_kwh": self_use,
        "grid_import_kwh": s1.get("grid_import_kwh"),
        "curtailment_kwh": curtail,
        "self_use_rate": _safe_rate(self_use, generation),
        "waste_rate": _safe_rate(curtail, generation),
        "avoided_tco2_study_period": carbon.get("avoided_tco2_study_period"),
        "cost_per_tco2_cny": carbon.get("cost_per_tco2_cny"),
        "pv_wind_incremental_npv_vs_s0_cny": (s3.get("economics") or {}).get("incremental_npv_vs_s0_cny"),
        "pv_wind_admission_status": s3.get("admission_status"),
    }


def _select(rows: Sequence[Dict[str, Any]]) -> tuple[float, str]:
    eligible = [r for r in rows if r["requested_capacity_kwp"] > 0 and r.get("admission_status") == "eligible" and r.get("economics_status") in {"complete", "feasible"} and r.get("incremental_npv_vs_s0_cny") is not None]
    if not eligible:
        return 0.0, "没有完整计价且可行的非零光伏候选，保留0kWp"
    best = max(eligible, key=lambda r: float(r["incremental_npv_vs_s0_cny"]))
    if float(best["incremental_npv_vs_s0_cny"]) <= 0:
        return 0.0, "所有可行非零候选相对S0增量现值不为正，推荐0kWp"
    return float(best["requested_capacity_kwp"]), "在完整计价且满足约束的PV-only候选中选择增量NPV最高者"


def _case(case_id: str, label: str, demo_role: str, room_spec: RoomSpec, weather: Dict[str, Any], pv_weather: Dict[str, Any], source_commit: str, *, requested_capacities: Sequence[float], budget: Optional[float] = 90000, roof: float = 35, pv_complete: bool = True, wind_count: int = 1, study_years: int = 10, building: Optional[Dict[str, Any]] = None, variant_reason: Optional[str] = None, storage_capacities: Optional[list[float]] = None, feasibility: Optional[Dict[str, Any]] = None, aliases: Optional[list[str]] = None) -> Dict[str, Any]:
    single = simulate_room(weather, room_spec)
    project = aggregate_project_load(single)
    storage_request = {"capacities_kwh": storage_capacities or ([0, 50, 100, 200, 500] if room_spec.room_count >= 20 else [0, 5, 10, 20, 50]), "round_trip_efficiency": 0.90}
    sweep_reports = []
    sweep_rows = []
    for cap in requested_capacities:
        rep, q = _report(project, pv_weather, budget=budget, roof=roof, pv_complete=pv_complete, cap=float(cap), wind_count=wind_count, study_years=study_years, include_hourly=False, storage=storage_request)
        sweep_reports.append((float(cap), rep, q))
        sweep_rows.append(_capacity_row(rep, float(cap)))
    selected_cap, selection_basis = _select(sweep_rows)
    selected_rep, quote_input = _report(project, pv_weather, budget=budget, roof=roof, pv_complete=pv_complete, cap=selected_cap, wind_count=wind_count, study_years=study_years, include_hourly=True, storage=storage_request)
    recommendation_id = selected_rep.get("recommendation", {}).get("scenario_id") or "S0_grid"
    # The selected PV report is the complete trace; chart_recommended follows the full four-scenario recommendation.
    sensitivity = [_constant_sensitivity(selected_rep, price, name) for price, name in ((0.66, "恒价0.66用户情景"), (1.20, "恒价1.20用户情景"))]
    null_carbon = {x["scenario_id"]: x.get("carbon") for x in selected_rep["candidates"]}
    ref_carbon = {x["scenario_id"]: _carbon_reference(x["carbon"]) for x in selected_rep["candidates"]}
    context = pv_weather.get("context") or {}
    total_cost = {x["scenario_id"]: (x.get("economics") or {}).get("total_cost_npv_cny") for x in selected_rep["candidates"]}
    main_input = {
        "site_id": "guangzhou", "year": 2024, "room": asdict(room_spec),
        "building": building or {"floors": 1, "rooms_per_floor": room_spec.room_count, "roof_area_m2": roof, "roof_area_basis": "explicit site input"},
        "pv_capacity_kwp": selected_cap, "requested_capacities_kwp": [float(x) for x in requested_capacities],
        "recommended_pv_capacity_kwp": selected_cap, "wind_turbine_count": wind_count, "budget_cny": budget,
        "roof_area_m2": roof, "usable_fraction": 0.8,
        "tariff_id": OFFICIAL_TARIFF_ID, "tariff_application": "current_tariff_on_reference_weather",
        "tariff_basis": "2026-10广东电网代理购电工商业公开抄录档案（广州所属珠三角六市）；用现行月度电价评价2024参考天气，不是2024实际账单；原始公告PDF待进一步核验",
        "sensitivity_import_prices_cny_per_kwh": [0.66, 1.20], "allow_export": False, "study_years": study_years,
        "pv_quote": quote_input["pv_quote"], "wind_quote": quote_input["wind_quote"], "hub_height_m": quote_input["hub_height_m"], "hellman_exponent": quote_input["hellman_exponent"],
        "carbon": {"carbon_price_cny_per_t": None}, "carbon_price_reference": {"carbon_price_cny_per_t": REFERENCE_CARBON_PRICE_CNY_PER_T, "source": REFERENCE_CARBON_PRICE_SOURCE}, "storage": storage_request,
    }
    selected_rows = [_candidate(x) for x in selected_rep["candidates"]]
    case = {
        "case_id": case_id, "label": label, "demo_role": demo_role, "aliases": aliases or [], "variant_reason": variant_reason, "feasibility": feasibility,
        "source": {"source_commit": source_commit, "calculation_version": selected_rep["calculation_version"], "source_result_file": "operation_planning/results/phase2b_carbon_5090/replay_cases_v5.json", "mode": "fixed_replay_only; 5090 full-year calculation"},
        "input": main_input,
        "weather": {"source": WEATHER_REL, "hash": pv_weather.get("hash"), "site": context.get("site"), "start": context.get("start"), "end": context.get("end"), "normalization_version": (pv_weather.get("weather_normalization") or {}).get("version")},
        "load_context": {**selected_rep["load_context"], "project_load_contract": project.get("project_load_contract"), "single_room_summary": project.get("single_room_summary"), "project_scope": project["load_series"].get("scope")},
        "project_load_contract": project.get("project_load_contract"), "room_count": project["load_series"].get("room_count"), "units_per_room": project["load_series"].get("units_per_room"), "service_quality": selected_rep["load_context"]["service_quality"],
        "carbon_context": selected_rep["carbon_context"], "recommendation": selected_rep["recommendation"], "pv_recommendation": {"recommended_capacity_kwp": selected_cap, "basis": selection_basis, "selected_candidate": next((r for r in sweep_rows if r["requested_capacity_kwp"] == selected_cap), sweep_rows[0])},
        "total_cost_npv_cny": total_cost, "candidates": selected_rows,
        "pv_capacity_sweep": sweep_rows, "chart": _chart(selected_rep, "S3_pv_wind"), "chart_recommended": _chart(selected_rep, recommendation_id),
        "carbon_price_scenarios": [{"carbon_price_cny_per_t": None, "label": "不计碳收益", "source": None, "candidate_carbon": null_carbon}, {"carbon_price_cny_per_t": REFERENCE_CARBON_PRICE_CNY_PER_T, "label": "公开报告参考情景，不代表可成交", "source": REFERENCE_CARBON_PRICE_SOURCE, "candidate_carbon": ref_carbon}],
        "tariff_sensitivities": sensitivity,
        "not_provided": ["只计空调用电，不含照明、插座、生产工艺和建筑总表负荷", "报价、电价、寿命和碳价为用户情景或公开档案情景", "2026-10主电价是公开抄录的月度代理购电档案，原始公告PDF待核验；不代表2024实际账单", "屋顶承重、消防间距、并网审批待现场确认", "不代表现场精度、经核证减排量、采购建议或碳市场资格"],
    }
    case["case_hash"] = _sha(case)
    return case


def _large_spec() -> tuple[RoomSpec, Dict[str, Any], Dict[str, Any]]:
    room = RoomSpec(area_m2=250, height_m=6, orientation="north", window_wall_ratio=0.1, insulation_u_w_m2k=0.3, people_count=20, equipment_gain_w=3000, weekdays_only=False, start_hour=8, end_hour=20, equipment_count=14, units_per_room=14, room_count=6)
    building = {"floors": 1, "conditioned_zones": 6, "zone_area_m2": 250, "total_conditioned_area_m2": 1500, "roof_area_m2": 2000, "roof_area_basis": "single-floor roof explicit site input; not derived from conditioned area", "scope": "air-conditioned workshop zones only", "daily_operation": "08:00-20:00 every day", "total_units": 84}
    feasibility = {"status": "bounded_proxy_feasible", "conclusion": "可计算为厂房空调分区代理；不代表全厂能源方案", "parameter_basis": ["每区250m²：处于150–300m²车间分区用户情景范围，非实测", "层高6m：轻工/装配车间6–8m量级用户情景", "20人/区：8人/100m²的装配班组用户情景", "设备显热3000W：12W/m²轻工设备情景，不含生产主机/照明/插座", "每天08:00–20:00：模型可支持的全年每日白班近似，不代表两班制或每周6天", "14台/区：本模型扫描得到达到within_modeled_scope的最小整数台数，不是工程选型结论"], "service_check": {"one_zone_14_units": "within_modeled_scope", "capacity_shortfall_hours": 0, "unmet_temp_degree_hours": 0, "unmet_rh_percent_hours": 0}, "not_modelled": ["生产工艺负荷", "照明与插座", "VRF/冷水机组及部分负荷性能", "实际厂房BMS与实测校准", "复杂两班制/每周6天排班"], "alternative_case_id": "tier_large_conditioned_zones"}
    return room, building, feasibility


def main() -> int:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_commit = _source()
    weather = load_weather("guangzhou", 2024)
    pv_weather = load_pv_weather("guangzhou", 2024)
    if list(weather["time"]) != list(pv_weather["time"]):
        raise AssertionError("负荷与风光天气时间轴不一致")
    one = RoomSpec(area_m2=35, orientation="north", window_wall_ratio=0.1, insulation_u_w_m2k=0.3, people_count=2, equipment_gain_w=100, equipment_count=6, units_per_room=6, room_count=1)
    medium = RoomSpec(**{**asdict(one), "room_count": 40})
    large, large_building, large_feasibility = _large_spec()
    cases = [
        _case("tier_small", "小档：35㎡公共建筑办公室", "tier_small", one, weather, pv_weather, source_commit, requested_capacities=[0, 1, 2, 5.6], roof=35, building={"floors": 1, "rooms_per_floor": 1, "roof_area_m2": 35, "roof_area_basis": "single-floor footprint; explicit site input"}, aliases=["primary_not_worth_it"]),
        _case("tier_medium", "中档：四层公共建筑40间同类房间", "tier_medium", medium, weather, pv_weather, source_commit, requested_capacities=[0, 5, 10, 20, 40, 56], roof=350, budget=300000, building={"floors": 4, "rooms_per_floor": 10, "room_count": 40, "roof_area_m2": 350, "roof_area_basis": "single-floor roof; not multiplied by floors"}, aliases=["primary_worth_it"]),
        _case("tier_large", "大档：工业厂房空调分区代理（不含生产工艺负荷）", "tier_large", large, weather, pv_weather, source_commit, requested_capacities=[0, 20, 50, 100, 200, 320], roof=2000, budget=1500000, storage_capacities=[0, 50, 100, 200, 500], building=large_building, feasibility=large_feasibility),
        _case("variant_budget_insufficient", "状态变体：预算不足（小档屋顶口径）", "state_variant", one, weather, pv_weather, source_commit, requested_capacities=[0, 1, 2, 5.6], roof=35, budget=30000, variant_reason="预算约束变更；保留预算内可计价候选，不把排除解释为S0全面最优"),
        _case("variant_missing_pv_quote", "状态变体：缺少光伏报价（小档屋顶口径）", "state_variant", one, weather, pv_weather, source_commit, requested_capacities=[0, 1, 2, 5.6], roof=35, pv_complete=False, variant_reason="光伏物理结果保留，非零报价未知；经济推荐未决"),
        _case("variant_roof_area_insufficient", "状态变体：屋顶面积不足", "state_variant", one, weather, pv_weather, source_commit, requested_capacities=[0, 1, 2], roof=1, variant_reason="可用屋顶1㎡为故意约束变体，非零容量超上限时排除"),
    ]
    package = {"format_version": "5090-carbon-replay-v5", "description": "阶段二B v5：最新广东代理购电月度档案主口径、真实厂房空调分区有界代理、小中大三档PV容量比选、最划算容量与完整四方案结果；v4及更早回放保留不覆盖。", "source": {"source_commit": source_commit, "calculation_version": "phase2b-carbon-5090-v5", "weather_hash": pv_weather.get("hash"), "mode": "fixed_replay_only", "machine_role": "5090"}, "main_tariff": {"tariff_id": OFFICIAL_TARIFF_ID, "application": "current_tariff_on_reference_weather", "source_url": TARIFF_URL, "note": "2026-10广东珠三角六市（含广州）单一制不满1kV代理购电月度价格，公开抄录来源页；用现行电价评价2024参考天气，不是2024实际账单；原始公告PDF待进一步核验", "period_prices_cny_per_kwh": {"valley": 0.32136875, "flat": 0.80066875, "peak": 1.34176875, "super_peak": 1.67036875}}, "tiers": {"small": "tier_small", "medium": "tier_medium", "large": "tier_large"}, "aliases": {"tier_small": ["primary_not_worth_it"], "tier_medium": ["primary_worth_it"], "tier_large": []}, "legacy_omitted_cases": ["primary_adequate_three_rooms", "comparison_undersized_one_unit", "comparison_two_unit_reference"], "cases": cases, "display_contract": {"numbers_from_data": True, "carbon_fields_from_backend": True, "annual_offset_is_comparison_only": True, "storage_is_ideal_upper_bound_only": True, "capacity_sweep_is_pv_only_selection_basis": True, "old_replays_immutable": True, "main_tariff_source": TARIFF_URL}}
    OUT.mkdir(parents=True, exist_ok=True)
    full = OUT / "replay_cases_v5.json"
    full.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    viewer = json.loads(json.dumps(package, ensure_ascii=False))
    for case in viewer["cases"]:
        case["chart"] = _compact_chart(case["chart"])
        case["chart_recommended"] = _compact_chart(case["chart_recommended"])
    viewer["display_contract"].update({"hourly_columns": ["timestamps", "load_kwh", "pv_generation_kwh", "wind_generation_kwh", "self_use_kwh", "grid_import_kwh", "curtailment_kwh"], "hourly_display_decimals": 4, "full_precision_results": "operation_planning/results/phase2b_carbon_5090/replay_cases_v5.json", "chart_recommended_from_report": True, "main_tariff": OFFICIAL_TARIFF_ID, "sensitivity_tariffs": ["user_constant:0.66", "user_constant:1.20"]})
    VIEWER_OUT.parent.mkdir(parents=True, exist_ok=True)
    VIEWER_OUT.write_text(json.dumps(viewer, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"status": "passed", "source_commit": source_commit, "started_utc": started, "ended_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "machine_role": "5090", "case_count": len(cases), "case_summaries": [{"case_id": c["case_id"], "room_count": c["room_count"], "units_per_room": c["units_per_room"], "service_status": c["service_quality"]["status"], "recommended_pv_capacity_kwp": c["pv_recommendation"]["recommended_capacity_kwp"], "recommendation": c["recommendation"], "sweep_count": len(c["pv_capacity_sweep"]), "chart_scenario_id": c["chart"]["scenario_id"], "chart_recommended_scenario_id": c["chart_recommended"]["scenario_id"], "case_hash": c["case_hash"]} for c in cases], "package_file_sha256": _file_sha(full), "viewer_file_sha256": _file_sha(VIEWER_OUT), "package_sha256": _sha(package), "viewer_sha256": _sha(viewer), "viewer_path": "docs/handoff/replay_viewer/replay_cases_v5.json", "previous_replays_preserved": ["replay_cases_v3.json", "replay_cases_v4.json"]}
    (OUT / "run_manifest_v5.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

