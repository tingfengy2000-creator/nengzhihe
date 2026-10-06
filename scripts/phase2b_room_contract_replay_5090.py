"""Generate the 5090 full-year replay after the room-field API fix.

The replay keeps the old one-unit, one-room scenario as a deliberate
"equipment undersized" comparison and adds a capacity-adequate reference
with explicit one-room and three-room project-load contracts.  It is a
read-only data export for 5060; no frontend code is executed here.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from operation_planning.hybrid import HybridScenario, run_hybrid_planning
from operation_planning.pv import PVQuote, PVScenario
from operation_planning.project_load import aggregate_project_load
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.weather import load_pv_weather, load_weather
from operation_planning.wind import WindScenario, WindTurbineProfile, WindQuote


OUT = ROOT / "operation_planning" / "results" / "phase2b_room_contract_replay_5090"
VIEWER_OUT = ROOT / "docs" / "handoff" / "replay_viewer" / "replay_cases_room_contract.json"


def _sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _source() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _quotes() -> tuple[PVQuote, WindQuote]:
    return (
        PVQuote(module_cny_per_kwp=1800, inverter_cny_per_kwp=600, structure_cny_per_kwp=500, installation_cny_per_kwp=800, grid_connection_cny=0, maintenance_cny_per_kwp_year=30),
        WindQuote(turbine_cny=45000, tower_cny=15000, foundation_cny=10000, installation_cny=12000, grid_connection_cny=0, maintenance_cny_per_year=1200),
    )


def _scenario(site: str, year: int, pv_quote: PVQuote) -> tuple[PVScenario, HybridScenario]:
    pv = PVScenario(site_id=site, year=year, roof_area_m2=50, requested_capacities_kwp=[0, 2], quote=pv_quote, import_price_cny_per_kwh=0.66, study_years=10)
    hybrid = HybridScenario(site_id=site, year=year, pv_capacity_kwp=2, wind=WindScenario(site_id=site, year=year, turbine_count=1), budget_cny=90000, allow_export=False, import_price_cny_per_kwh=0.66, study_years=10, pv_quote=pv_quote, wind_quote=_quotes()[1], shared_connection_cny=0)
    return pv, hybrid


def _flat_candidate(item: Dict[str, Any]) -> Dict[str, Any]:
    econ = item.get("economics") or {}
    keys = ("scenario_id", "pv_capacity_kwp", "wind_turbine_count", "generation_kwh", "pv_generation_kwh", "wind_generation_kwh", "self_use_kwh", "grid_import_kwh", "grid_export_kwh", "curtailment_kwh", "load_coverage_rate", "constraint_status", "constraint_reasons", "admission_status", "equivalent_to")
    row = {key: item.get(key) for key in keys}
    row.update({"capex_cny": econ.get("capex_cny"), "npv_cny": econ.get("npv_cny"), "total_cost_npv_cny": econ.get("total_cost_npv_cny"), "incremental_npv_vs_s0_cny": econ.get("incremental_npv_vs_s0_cny"), "economics_status": econ.get("status")})
    return row


def _case(case_id: str, label: str, demo_role: str, room_spec: RoomSpec, weather: Dict[str, Any], pv_weather: Dict[str, Any], source_commit: str) -> Dict[str, Any]:
    single = simulate_room(weather, room_spec)
    project = aggregate_project_load(single)
    pv_quote, _ = _quotes()
    pv_scenario, hybrid_scenario = _scenario("guangzhou", 2024, pv_quote)
    report = run_hybrid_planning(project, pv_weather, pv_scenario, hybrid_scenario, WindTurbineProfile.from_file(), include_hourly=True)
    service = report["load_context"]["service_quality"]
    if demo_role == "primary_no_service_gap" and service["status"] != "within_modeled_scope":
        raise AssertionError(f"primary demo unexpectedly has service gap: {service}")
    if demo_role == "undersized_comparison" and service["status"] != "service_gap":
        raise AssertionError(f"undersized comparison unexpectedly has no service gap: {service}")
    s3 = next(item for item in report["candidates"] if item["scenario_id"] == "S3_pv_wind")
    chart = s3["hourly"]
    weather_context = pv_weather.get("context") or {}
    case = {
        "case_id": case_id,
        "label": label,
        "demo_role": demo_role,
        "source": {"source_commit": source_commit, "calculation_version": report["calculation_version"], "source_result_file": "operation_planning/results/phase2b_room_contract_replay_5090/replay_cases_room_contract.json", "mode": "fixed_replay_only; 5090 full-year calculation"},
        "input": {"site_id": "guangzhou", "year": 2024, "room": asdict(room_spec), "pv_capacity_kwp": 2, "wind_turbine_count": 1, "budget_cny": 90000, "import_price_cny_per_kwh": 0.66, "allow_export": False, "study_years": 10},
        "weather": {"source": "operation_planning/data/weather_pv/guangzhou_2024.json", "hash": pv_weather.get("hash"), "site": weather_context.get("site"), "start": weather_context.get("start"), "end": weather_context.get("end"), "normalization_version": pv_weather.get("weather_normalization", {}).get("version") if isinstance(pv_weather.get("weather_normalization"), dict) else pv_weather.get("weather_normalization")},
        "load_context": {**report["load_context"], "project_load_contract": project.get("project_load_contract"), "single_room_summary": project.get("single_room_summary"), "project_scope": project["load_series"].get("scope")},
        "project_load_contract": project.get("project_load_contract"),
        "room_count": project["load_series"].get("room_count"),
        "units_per_room": project["load_series"].get("units_per_room"),
        "service_quality": service,
        "recommendation": report["recommendation"],
        "candidates": [_flat_candidate(item) for item in report["candidates"]],
        "chart": chart,
        "not_provided": ["不同房间朝向、时段、设备和独立天气未建模", "报价、电价和寿命为用户情景", "不代表现场精度、节能收益或采购建议"],
    }
    case["case_hash"] = _sha(case)
    return case


def main() -> int:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_commit = _source()
    weather = load_weather("guangzhou", 2024)
    pv_weather = load_pv_weather("guangzhou", 2024)
    if list(weather["time"]) != list(pv_weather["time"]):
        raise AssertionError("负荷与风光天气时间轴不一致")

    # Formal primary demo: a deliberately capacity-adequate modeled reference
    # (strong envelope, low internal gains, six units), not a procurement claim.
    adequate_one = RoomSpec(area_m2=35, orientation="north", window_wall_ratio=0.1, insulation_u_w_m2k=0.3, people_count=2, equipment_gain_w=100, equipment_count=6, units_per_room=6, room_count=1)
    adequate_three = RoomSpec(area_m2=35, orientation="north", window_wall_ratio=0.1, insulation_u_w_m2k=0.3, people_count=2, equipment_gain_w=100, equipment_count=6, units_per_room=6, room_count=3)
    undersized = RoomSpec(equipment_count=1, units_per_room=1, room_count=1)
    two_unit_reference = RoomSpec(equipment_count=2, units_per_room=2, room_count=1)
    cases = [
        _case("primary_adequate_one_room", "主演示：容量充足的单房间项目负荷", "primary_no_service_gap", adequate_one, weather, pv_weather, source_commit),
        _case("primary_adequate_three_rooms", "主演示：三间同类房间项目负荷", "primary_no_service_gap", adequate_three, weather, pv_weather, source_commit),
        _case("comparison_undersized_one_unit", "对照：默认一台设备的服务缺口", "undersized_comparison", undersized, weather, pv_weather, source_commit),
        _case("comparison_two_unit_reference", "口径对照：默认房间改为每间两台设备", "two_unit_reference", two_unit_reference, weather, pv_weather, source_commit),
    ]
    package = {"format_version": "5090-project-load-replay-v1", "description": "5090完整年真实回放；主场景为无服务缺口的容量充足模型参考，对照场景保留默认一台设备的服务缺口。", "source": {"source_commit": source_commit, "calculation_version": "phase2b-semantics-5090-v1", "weather_hash": pv_weather.get("hash"), "mode": "fixed_replay_only"}, "cases": cases, "display_contract": {"numbers_from_data": True, "room_fields": ["room_count", "units_per_room", "project_load_contract"], "unknown_new_inputs": "待5090验算", "short_contract_samples_are_not_annual_demos": True}}
    OUT.mkdir(parents=True, exist_ok=True)
    VIEWER_OUT.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "replay_cases_room_contract.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"status": "passed", "source_commit": source_commit, "started_utc": started, "ended_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "case_count": len(cases), "cases": [{"case_id": c["case_id"], "demo_role": c["demo_role"], "room_count": c["room_count"], "units_per_room": c["units_per_room"], "electric_load_kwh": c["load_context"]["electric_load_kwh"], "service_status": c["service_quality"]["status"], "project_load_contract": c["project_load_contract"], "case_hash": c["case_hash"]} for c in cases], "package_sha256": _sha(package), "note": "完整年回放；旧 replay_cases.json 保留为历史固定样例，本文件供5060读取。"}
    (OUT / "run_manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
