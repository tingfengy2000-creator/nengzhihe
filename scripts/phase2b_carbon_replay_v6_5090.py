"""Generate v6 replay cases through the public HTTP API.

The v6 package is intentionally produced by POSTing each tier (or fixed
variant) request to ``/api/operation/hybrid/run``.  The tier request carries
the complete bounded capacity list and consumes the endpoint's returned sweep.
It therefore exercises the same validation and calculation path used by the
product, rather than importing calculation functions directly.  The server
must already be running (usually with
``python -m operation_planning.app``); ``--base-url`` can point at another
loopback port for an isolated run.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from operation_planning.thermal_model import RoomSpec

OUT = ROOT / "operation_planning" / "results" / "phase2b_carbon_5090"
VIEWER_OUT = ROOT / "docs" / "handoff" / "replay_viewer" / "replay_cases_v6.json"
API_DEFAULT = "http://127.0.0.1:18765"
TARIFF_ID = "guangzhou_industrial_lt1kv_202610"
TARIFF_URL = "https://energydc.cn/policy/guangdong/2026-09/ffdcada5-baab-11f1-959b-ce30ac533824"
WEATHER_REL = "operation_planning/data/weather_pv/guangzhou_2024.json"


def _sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _quotes(pv_complete: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    pv = ({
        "module_cny_per_kwp": 1800, "inverter_cny_per_kwp": 600,
        "structure_cny_per_kwp": 500, "installation_cny_per_kwp": 800,
        "grid_connection_cny": 0, "maintenance_cny_per_kwp_year": 30,
        "inverter_replacement_year": 12, "inverter_replacement_fraction": 0.15,
        "residual_fraction": 0.05,
    } if pv_complete else {})
    wind = {
        "turbine_cny": 45000, "tower_cny": 15000, "foundation_cny": 10000,
        "installation_cny": 12000, "grid_connection_cny": 0,
        "maintenance_cny_per_year": 1200, "residual_fraction": 0.05,
    }
    return pv, wind


def _request_payload(room: RoomSpec, *, cap: float, requested: Sequence[float],
                     roof: float, budget: Optional[float], pv_complete: bool,
                     wind_count: int, study_years: int = 10,
                     fixed_capacity: Optional[float] = None) -> dict[str, Any]:
    pv_quote, wind_quote = _quotes(pv_complete)
    payload = {
        "site_id": "guangzhou", "year": 2024, "room": asdict(room),
        "pv": {
            "roof_area_m2": roof, "usable_fraction": 0.8,
            "requested_capacities_kwp": [float(x) for x in requested],
            "pv_capacity_kwp": float(cap), "quote": pv_quote,
            "tariff_id": TARIFF_ID,
            "tariff_application": "current_tariff_on_reference_weather",
            "study_years": study_years, "allow_export": False,
        },
        "hybrid": {
            "pv_capacity_kwp": float(cap), "budget_cny": budget,
            "allow_export": False, "study_years": study_years,
            "import_price_cny_per_kwh": 0.66,
            "pv_quote": pv_quote, "wind_quote": wind_quote,
            "wind": {"site_id": "guangzhou", "year": 2024,
                      "turbine_count": int(wind_count), "hub_height_m": 9,
                      "source_height_m": 10, "hellman_exponent": 0.14},
        },
        "carbon": {"carbon_price_cny_per_t": None},
        "storage": {"capacities_kwh": [0, 5, 10, 20, 50], "round_trip_efficiency": 0.90},
    }
    if fixed_capacity is not None:
        payload["pv"]["fixed_capacity_kwp"] = float(fixed_capacity)
    return payload


def _http_post(base_url: str, payload: dict[str, Any], timeout: int = 600) -> tuple[dict[str, Any], float, int]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(base_url.rstrip("/") + "/api/operation/hybrid/run", data=body,
                  headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    started = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as response:
            status = int(response.status)
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except Exception:
            data = {"error": str(exc)}
        status = int(exc.code)
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"无法连接实时计算接口 {base_url}: {exc}") from exc
    elapsed = (time.perf_counter() - started) * 1000.0
    if status < 200 or status >= 300 or data.get("status") == "failed":
        raise RuntimeError(f"实时接口返回HTTP {status}: {data.get('error') or data}")
    report = data.get("report")
    if not isinstance(report, dict):
        raise RuntimeError("实时接口响应缺少 report 对象")
    return report, elapsed, status


def _candidate(item: dict[str, Any]) -> dict[str, Any]:
    econ = item.get("economics") or {}
    return {"scenario_id": item.get("scenario_id"), "pv_capacity_kwp": item.get("pv_capacity_kwp"), "wind_turbine_count": item.get("wind_turbine_count"), "generation_kwh": item.get("generation_kwh"), "pv_generation_kwh": item.get("pv_generation_kwh"), "wind_generation_kwh": item.get("wind_generation_kwh"), "self_use_kwh": item.get("self_use_kwh"), "grid_import_kwh": item.get("grid_import_kwh"), "grid_export_kwh": item.get("grid_export_kwh"), "curtailment_kwh": item.get("curtailment_kwh"), "load_coverage_rate": item.get("load_coverage_rate"), "constraint_status": item.get("constraint_status"), "constraint_reasons": item.get("constraint_reasons"), "admission_status": item.get("admission_status"), "equivalent_to": item.get("equivalent_to"), "economics_status": econ.get("status"), "capex_cny": econ.get("capex_cny"), "npv_cny": econ.get("npv_cny"), "total_cost_npv_cny": econ.get("total_cost_npv_cny"), "incremental_npv_vs_s0_cny": econ.get("incremental_npv_vs_s0_cny"), "economics": {"study_years": econ.get("study_years"), "yearly": econ.get("yearly"), "cashflow_convention": econ.get("cashflow_convention")}, "carbon": item.get("carbon"), "annual_offset_estimate": item.get("annual_offset_estimate"), "storage_upper_bound": item.get("storage_upper_bound"), "hourly": item.get("hourly")}


def _find(report: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    return next(x for x in report.get("candidates", []) if x.get("scenario_id") == scenario_id)


def _chart(report: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    item = _find(report, scenario_id)
    return {"scenario_id": scenario_id, **(item.get("hourly") or {})}


def _compact_chart(chart: dict[str, Any]) -> dict[str, Any]:
    fields = ("timestamps", "load_kwh", "pv_generation_kwh", "wind_generation_kwh", "self_use_kwh", "grid_import_kwh", "curtailment_kwh")
    out: dict[str, Any] = {"scenario_id": chart.get("scenario_id")}
    for key in fields:
        values = chart.get(key)
        out[key] = [round(float(v), 4) if isinstance(v, (int, float)) and not isinstance(v, bool) else v for v in values] if isinstance(values, list) else values
    if any(abs(float(v)) > 1e-12 for v in (chart.get("grid_export_kwh") or [])):
        out["grid_export_kwh"] = [round(float(v), 4) for v in chart["grid_export_kwh"]]
    return out


def _safe_rate(num: Any, den: Any) -> Optional[float]:
    try:
        d = float(den)
        return None if d <= 0 else float(num) / d
    except (TypeError, ValueError):
        return None


def _sweep_row(report: dict[str, Any], cap: float) -> dict[str, Any]:
    s1 = _find(report, "S1_pv")
    econ = s1.get("economics") or {}
    carbon = s1.get("carbon") or {}
    generation = float(s1.get("pv_generation_kwh") or s1.get("generation_kwh") or 0.0)
    self_use = float(s1.get("self_use_kwh") or 0.0)
    curtail = float(s1.get("curtailment_kwh") or 0.0)
    return {"requested_capacity_kwp": float(cap), "scenario_id": "S1_pv", "total_cost_npv_cny": econ.get("total_cost_npv_cny"), "incremental_npv_vs_s0_cny": econ.get("incremental_npv_vs_s0_cny"), "capex_cny": econ.get("capex_cny"), "economics_status": econ.get("status"), "admission_status": s1.get("admission_status"), "constraint_status": s1.get("constraint_status"), "constraint_reasons": s1.get("constraint_reasons"), "generation_kwh": generation, "self_use_kwh": self_use, "grid_import_kwh": s1.get("grid_import_kwh"), "curtailment_kwh": curtail, "self_use_rate": _safe_rate(self_use, generation), "waste_rate": _safe_rate(curtail, generation), "avoided_tco2_study_period": carbon.get("avoided_tco2_study_period"), "cost_per_tco2_cny": carbon.get("cost_per_tco2_cny")}


def _api_sweep_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize the compact sweep row returned by hybrid/run."""
    generation = row.get("generation_kwh")
    self_use = row.get("self_use_kwh")
    curtail = row.get("curtailment_kwh")
    return {"requested_capacity_kwp": row.get("requested_capacity_kwp"), "scenario_id": "S1_pv", "total_cost_npv_cny": row.get("total_cost_npv_cny"), "incremental_npv_vs_s0_cny": row.get("incremental_npv_vs_s0_cny"), "capex_cny": (row.get("economics") or {}).get("capex_cny"), "economics_status": (row.get("economics") or {}).get("status", row.get("economics_status")), "admission_status": row.get("admission_status"), "constraint_status": row.get("status") or row.get("constraint_status"), "constraint_reasons": row.get("constraint_reasons"), "generation_kwh": generation, "self_use_kwh": self_use, "grid_import_kwh": row.get("grid_import_kwh"), "curtailment_kwh": curtail, "self_use_rate": row.get("self_use_rate", row.get("self_consumption_rate", _safe_rate(self_use, generation))), "waste_rate": row.get("waste_rate", _safe_rate(curtail, generation)), "avoided_tco2_study_period": (row.get("carbon") or {}).get("avoided_tco2_study_period"), "cost_per_tco2_cny": (row.get("carbon") or {}).get("cost_per_tco2_cny")}


def _choose(rows: Sequence[dict[str, Any]]) -> tuple[float, str]:
    eligible = [r for r in rows if float(r["requested_capacity_kwp"]) > 0 and r.get("admission_status") == "eligible" and r.get("economics_status") in {"complete", "feasible"} and r.get("incremental_npv_vs_s0_cny") is not None]
    if not eligible:
        return 0.0, "没有完整计价且满足约束的非零容量，保留0kWp"
    best = max(eligible, key=lambda r: float(r["incremental_npv_vs_s0_cny"]))
    if float(best["incremental_npv_vs_s0_cny"]) <= 0:
        return 0.0, "可计价非零容量的增量NPV均不为正，推荐0kWp"
    return float(best["requested_capacity_kwp"]), "在满足约束且完整计价的PV-only容量中选择增量NPV最高者"


def _case(base_url: str, *, case_id: str, label: str, role: str, room: RoomSpec, capacities: Sequence[float], roof: float, budget: Optional[float], pv_complete: bool = True, wind_count: int = 1, building: Optional[dict[str, Any]] = None, variant_reason: Optional[str] = None, feasibility: Optional[dict[str, Any]] = None, fixed_cap: Optional[float] = None, aliases: Optional[list[str]] = None) -> dict[str, Any]:
    traces: list[dict[str, Any]] = []
    reports: dict[float, dict[str, Any]] = {}
    requested = [float(x) for x in capacities]
    call_caps = [float(fixed_cap)] if fixed_cap is not None else [0.0]
    for cap in call_caps:
        # A normal tier lets the endpoint execute the complete bounded sweep
        # in one real request; variants deliberately use one fixed capacity.
        payload = _request_payload(room, cap=cap, requested=requested, roof=roof, budget=budget, pv_complete=pv_complete, wind_count=wind_count, fixed_capacity=fixed_cap)
        report, elapsed, status = _http_post(base_url, payload)
        reports[cap] = report
        traces.append({"capacity_kwp": cap, "elapsed_ms": round(elapsed, 3), "http_status": status, "request_sha256": _sha(payload), "response_sha256": _sha(report), "endpoint": "/api/operation/hybrid/run"})
    if fixed_cap is not None:
        rows = [_sweep_row(reports[float(fixed_cap)], float(fixed_cap))]
        selected_cap, basis = float(fixed_cap), "状态变体按12.1固定1kWp主方案"
        selected = reports[selected_cap]
    else:
        selected = reports[0.0]
        rows = [_api_sweep_row(row) for row in (selected.get("pv_capacity_sweep") or [])]
        if not rows:
            rows = [_sweep_row(selected, 0.0)]
        selected_cap = float(selected.get("recommended_pv_capacity_kwp", 0.0))
        if not any(float(row.get("requested_capacity_kwp", -1)) == selected_cap for row in rows):
            selected_cap, basis = _choose(rows)
        else:
            basis = selected.get("recommendation_basis") or "由实时接口在满足约束且完整计价的PV候选中按增量NPV选择"
    recommendation_id = "S1_pv" if fixed_cap is not None else ((selected.get("recommendation") or {}).get("scenario_id") or "S0_grid")
    input_payload = _request_payload(room, cap=selected_cap, requested=requested, roof=roof, budget=budget, pv_complete=pv_complete, wind_count=wind_count, fixed_capacity=fixed_cap)
    context = selected.get("load_context") or {}
    main_input = {"site_id": "guangzhou", "year": 2024, "room": asdict(room), "building": building or {}, "pv_capacity_kwp": selected_cap, "requested_capacities_kwp": requested, "recommended_pv_capacity_kwp": selected_cap, "roof_area_m2": roof, "budget_cny": budget, "tariff_id": TARIFF_ID, "tariff_application": "current_tariff_on_reference_weather", "allow_export": False, "wind_turbine_count": wind_count, "pv_quote": input_payload["pv"].get("quote"), "wind_quote": input_payload["hybrid"].get("wind_quote"), "hub_height_m": input_payload["hybrid"]["wind"].get("hub_height_m"), "hellman_exponent": input_payload["hybrid"]["wind"].get("hellman_exponent"), "carbon": input_payload["carbon"], "storage": input_payload["storage"], "request_sha256": _sha(input_payload)}
    candidates = [_candidate(x) for x in selected.get("candidates", [])]
    total_cost = {x.get("scenario_id"): (x.get("economics") or {}).get("total_cost_npv_cny") for x in selected.get("candidates", [])}
    case = {"case_id": case_id, "label": label, "demo_role": role, "aliases": aliases or [], "variant_reason": variant_reason, "feasibility": feasibility, "source": {"source_commit": _source(), "calculation_version": selected.get("calculation_version") or "phase2b-carbon-api", "mode": "http_api_replay", "endpoint": "/api/operation/hybrid/run", "base_url": base_url}, "input": main_input, "request": input_payload, "http_trace": traces, "weather": {"source": WEATHER_REL, "provenance": selected.get("weather_provenance"), "context": (selected.get("weather_provenance") or {}).get("context")}, "load_context": context, "project_load_contract": selected.get("project_load_contract") or context.get("project_load_contract") or context.get("project_load_context"), "room_count": room.room_count, "units_per_room": room.units_per_room, "service_quality": context.get("service_quality"), "carbon_context": selected.get("carbon_context"), "recommendation": selected.get("recommendation"), "pv_recommendation": {"recommended_capacity_kwp": selected_cap, "basis": basis, "selected_capacity_row": next((r for r in rows if float(r["requested_capacity_kwp"]) == selected_cap), None)}, "total_cost_npv_cny": total_cost, "candidates": candidates, "pv_capacity_sweep": rows, "chart": _chart(selected, "S3_pv_wind"), "chart_recommended": _chart(selected, recommendation_id), "carbon": {x.get("scenario_id"): x.get("carbon") for x in selected.get("candidates", [])}, "annual_offset_estimate": {x.get("scenario_id"): x.get("annual_offset_estimate") for x in selected.get("candidates", [])}, "storage_upper_bound": {x.get("scenario_id"): x.get("storage_upper_bound") for x in selected.get("candidates", [])}, "not_provided": ["只计当前空调负荷，不含照明、插座、生产工艺和建筑总表负荷", "报价与月度代理购电档案是用户确认/公开情景，不是现场账单", "车间大档为有界空调分区代理，不代表全厂"], "case_hash": None}
    case["case_hash"] = _sha(case)
    return case


def build(base_url: str) -> dict[str, Any]:
    one = RoomSpec(area_m2=35, orientation="north", window_wall_ratio=0.1, insulation_u_w_m2k=0.3, people_count=2, equipment_gain_w=100, equipment_count=6, units_per_room=6, room_count=1)
    # Medium tier deliberately changes temporal use rather than scaling the small tier.
    medium = RoomSpec(area_m2=70, height_m=3.6, orientation="north", window_wall_ratio=0.1, insulation_u_w_m2k=0.3, people_count=8, equipment_gain_w=300, equipment_count=8, units_per_room=8, room_count=20, weekdays_only=False, start_hour=9, end_hour=21)
    large = RoomSpec(area_m2=250, height_m=6, orientation="north", window_wall_ratio=0.1, insulation_u_w_m2k=0.3, people_count=20, equipment_gain_w=3000, weekdays_only=False, start_hour=8, end_hour=20, equipment_count=14, units_per_room=14, room_count=6)
    large_building = {"floors": 1, "conditioned_zones": 6, "zone_area_m2": 250, "total_conditioned_area_m2": 1500, "roof_area_m2": 2000, "daily_operation": "08:00-20:00 every day", "scope": "air-conditioned workshop zones only"}
    large_feasibility = {"status": "bounded_proxy_feasible", "conclusion": "可计算为厂房空调分区代理，不代表全厂", "parameter_basis": ["6区×250㎡、层高6m、20人/区、设备显热3kW/区、每天08:00-20:00", "每区14台为当前热湿模型范围内满足服务状态的最小整数扫描值，非工程选型"], "not_modelled": ["生产工艺、照明、插座、VRF/冷水机组和实测校准"]}
    cases = [
        _case(base_url, case_id="tier_small", label="小档：35㎡办公房间", role="tier_small", room=one, capacities=[0, 1, 2, 5.6], roof=35, budget=90000, aliases=["primary_not_worth_it"]),
        _case(base_url, case_id="tier_medium", label="中档：每天09:00-21:00开放的图书馆阅读区", role="tier_medium", room=medium, capacities=[0, 10, 20, 40, 80], roof=350, budget=600000, building={"building_type": "library", "floors": 4, "rooms_per_floor": 5, "conditioned_zones": 20, "zone_area_m2": 70, "total_conditioned_area_m2": 1400, "roof_area_m2": 350, "roof_area_basis": "single-floor footprint; not multiplied by floors", "daily_operation": "09:00-21:00 every day", "basis": "用户情景；不代表实测图书馆"}, aliases=["primary_worth_it"]),
        _case(base_url, case_id="tier_large", label="大档：工业厂房空调分区有界代理", role="tier_large", room=large, capacities=[0, 20, 50, 100, 200, 320], roof=2000, budget=1500000, building=large_building, feasibility=large_feasibility),
        _case(base_url, case_id="variant_budget_insufficient", label="状态变体：预算不足（固定1kWp）", role="state_variant", room=one, capacities=[1], fixed_cap=1, roof=35, budget=30000, variant_reason="预算约束变更；主卡固定1kWp以显示预算状态"),
        _case(base_url, case_id="variant_missing_pv_quote", label="状态变体：缺少光伏报价（固定1kWp）", role="state_variant", room=one, capacities=[1], fixed_cap=1, roof=35, budget=90000, pv_complete=False, variant_reason="主卡固定1kWp；物理结果保留，经济报价状态为unknown"),
        _case(base_url, case_id="variant_roof_area_insufficient", label="状态变体：屋顶面积不足（固定1kWp）", role="state_variant", room=one, capacities=[1], fixed_cap=1, roof=1, budget=90000, variant_reason="主卡固定1kWp；1㎡屋顶导致光伏候选excluded"),
    ]
    return {"format_version": "5090-carbon-replay-v6", "description": "v6由实时HTTP hybrid/run生成；三档为示例，用户输入实时计算为主；中档改为每日09:00-21:00建筑；状态变体固定1kWp。v5及早期回放保留。", "source": {"source_commit": _source(), "calculation_version": "phase2b-carbon-5090-v6-http", "mode": "http_api_replay", "machine_role": "5090", "api_base_url": base_url}, "main_tariff": {"tariff_id": TARIFF_ID, "source_url": TARIFF_URL, "application": "current_tariff_on_reference_weather", "provisional": True}, "tiers": {"small": "tier_small", "medium": "tier_medium", "large": "tier_large"}, "state_variants": ["variant_budget_insufficient", "variant_missing_pv_quote", "variant_roof_area_insufficient"], "cases": cases, "display_contract": {"numbers_from_http_response": True, "user_input_is_primary": True, "capacity_selection_basis": "PV-only eligible complete candidate with maximum incremental NPV; variants fixed at 1kWp", "old_replays_immutable": True}}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=API_DEFAULT)
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    package = build(args.base_url)
    OUT.mkdir(parents=True, exist_ok=True)
    full = OUT / "replay_cases_v6.json"
    full.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    viewer = json.loads(json.dumps(package, ensure_ascii=False))
    for case in viewer["cases"]:
        case["chart"] = _compact_chart(case["chart"])
        case["chart_recommended"] = _compact_chart(case["chart_recommended"])
    viewer["display_contract"].update({"full_precision_results": "operation_planning/results/phase2b_carbon_5090/replay_cases_v6.json", "hourly_display_decimals": 4})
    VIEWER_OUT.parent.mkdir(parents=True, exist_ok=True)
    VIEWER_OUT.write_text(json.dumps(viewer, ensure_ascii=False, indent=2), encoding="utf-8")
    traces = [t for c in package["cases"] for t in c["http_trace"]]
    manifest = {"status": "passed", "source_commit": package["source"]["source_commit"], "started_utc": started, "ended_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "machine_role": "5090", "api_base_url": args.base_url, "case_count": len(package["cases"]), "http_call_count": len(traces), "http_elapsed_ms": {"total": round(sum(t["elapsed_ms"] for t in traces), 3), "mean": round(sum(t["elapsed_ms"] for t in traces) / len(traces), 3), "max": round(max(t["elapsed_ms"] for t in traces), 3)}, "case_summaries": [{"case_id": c["case_id"], "recommended_pv_capacity_kwp": c["pv_recommendation"]["recommended_capacity_kwp"], "service_quality": c.get("service_quality"), "http_calls": len(c["http_trace"]), "case_hash": c["case_hash"]} for c in package["cases"]], "package_file_sha256": _file_sha(full), "viewer_file_sha256": _file_sha(VIEWER_OUT), "viewer_path": "docs/handoff/replay_viewer/replay_cases_v6.json", "previous_replays_preserved": ["replay_cases_v5.json", "replay_cases_v4.json", "replay_cases_v3.json"]}
    (OUT / "run_manifest_v6.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

