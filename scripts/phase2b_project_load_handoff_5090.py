"""5090-only full-year verification for the single-room/project-load boundary.

This is a bounded replay, not a new performance experiment.  It reuses the
locked Guangzhou 2024 weather caches and checks that room_count is applied
once before PV/hybrid matching.  Short cost tests remain contract examples;
this script is the formal full-year replay for the handoff.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from operation_planning.hybrid import HybridScenario, run_hybrid_planning
from operation_planning.lifecycle import life_cycle_cost
from operation_planning.pv import PVQuote, PVScenario, run_pv_planning
from operation_planning.project_load import aggregate_project_load
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.weather import load_pv_weather, load_weather
from operation_planning.wind import WindQuote, WindScenario, WindTurbineProfile


OUT = ROOT / "operation_planning" / "results" / "phase2b_project_load_handoff_5090"


def _sha(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _nvidia() -> str | None:
    try:
        return subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except Exception:
        return None


def _pv_quote() -> PVQuote:
    return PVQuote(
        module_cny_per_kwp=1800,
        inverter_cny_per_kwp=600,
        structure_cny_per_kwp=500,
        installation_cny_per_kwp=800,
        grid_connection_cny=0,
        maintenance_cny_per_kwp_year=30,
    )


def _wind_quote() -> WindQuote:
    return WindQuote(
        turbine_cny=45000,
        tower_cny=15000,
        foundation_cny=10000,
        installation_cny=12000,
        grid_connection_cny=0,
        maintenance_cny_per_year=1200,
    )


def _candidate(report: Dict[str, Any], key: str, field: str = "capacity_kwp") -> Dict[str, Any]:
    for item in report.get("candidates", []):
        if abs(float(item.get(field, item.get("pv_capacity_kwp", 0.0))) - float(key)) < 1e-9:
            return item
    raise AssertionError(f"candidate not found: {key}")


def _assert_close(a: float, b: float, name: str, tol: float = 1e-7) -> None:
    if abs(float(a) - float(b)) > tol:
        raise AssertionError(f"{name}: {a} != {b}")


def main() -> int:
    started = _now()
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    site, year = "guangzhou", 2024
    weather = load_weather(site, year)
    pv_weather = load_pv_weather(site, year)
    if list(weather["time"]) != list(pv_weather["time"]):
        raise AssertionError("空调天气与PV天气时间轴不一致")

    room_one = RoomSpec(equipment_count=2, units_per_room=2, room_count=1)
    room_three = RoomSpec(equipment_count=2, units_per_room=2, room_count=3)
    single = simulate_room(weather, room_one)
    single_three = simulate_room(weather, room_three)
    project_one = aggregate_project_load(single)
    project_three = aggregate_project_load(single_three)
    n = len(project_one["load_series"]["timestamps"])
    if n not in (8760, 8784):
        raise AssertionError(f"unexpected full-year rows: {n}")

    # room_count=1 is an identity; three same rooms scale only the load.
    if project_one["load_series"]["electric_power_w"] != single["load_series"]["electric_power_w"]:
        raise AssertionError("room_count=1 changed the single-room trace")
    for one, three in zip(project_one["load_series"]["electric_power_w"], project_three["load_series"]["electric_power_w"]):
        _assert_close(three, 3.0 * one, "three-room electric power")
    _assert_close(project_three["summary"]["electric_kwh"], 3.0 * project_one["summary"]["electric_kwh"], "three-room annual load")

    pvq = _pv_quote()
    pv_scenario = PVScenario(
        site_id=site,
        year=year,
        roof_area_m2=50,
        requested_capacities_kwp=[0, 2],
        quote=pvq,
        import_price_cny_per_kwh=0.66,
        study_years=10,
    )
    pv_one = run_pv_planning(project_one, pv_weather, pv_scenario, include_selected_series=False)
    pv_three = run_pv_planning(project_three, pv_weather, pv_scenario, include_selected_series=False)
    pv0_one = _candidate(pv_one, 0.0)
    pv0_three = _candidate(pv_three, 0.0)
    pv2_one = _candidate(pv_one, 2.0)
    pv2_three = _candidate(pv_three, 2.0)
    _assert_close(pv_one["load_context"]["electric_load_kwh"], project_one["summary"]["electric_kwh"], "PV one-room load context")
    _assert_close(pv_three["load_context"]["electric_load_kwh"], project_three["summary"]["electric_kwh"], "PV three-room load context")
    _assert_close(pv2_one["generation_kwh"], pv2_three["generation_kwh"], "PV generation unchanged by room count")
    _assert_close(pv0_one["grid_import_kwh"], project_one["summary"]["electric_kwh"], "PV S0 one-room import")
    _assert_close(pv0_three["grid_import_kwh"], project_three["summary"]["electric_kwh"], "PV S0 three-room import")
    for row in (pv0_one, pv0_three, pv2_one, pv2_three):
        # PV reports retain the hourly conservation values in lifecycle rows.
        for year_row in row["economics"]["yearly"][1:]:
            _assert_close(year_row["matching_conservation"]["load_error_kwh"], 0.0, "PV load conservation")
            _assert_close(year_row["matching_conservation"]["pv_error_kwh"], 0.0, "PV generation conservation")

    wind_profile = WindTurbineProfile.from_file()
    windq = _wind_quote()
    hybrid_scenario = HybridScenario(
        site_id=site,
        year=year,
        pv_capacity_kwp=2,
        wind=WindScenario(site_id=site, year=year, turbine_count=1),
        pv_quote=pvq,
        wind_quote=windq,
        shared_connection_cny=0,
        import_price_cny_per_kwh=0.66,
        study_years=10,
    )
    hy_one = run_hybrid_planning(project_one, pv_weather, pv_scenario, hybrid_scenario, wind_profile, include_hourly=False)
    hy_three = run_hybrid_planning(project_three, pv_weather, pv_scenario, hybrid_scenario, wind_profile, include_hourly=False)
    hy_s3_one = next(x for x in hy_one["candidates"] if x["scenario_id"] == "S3_pv_wind")
    hy_s3_three = next(x for x in hy_three["candidates"] if x["scenario_id"] == "S3_pv_wind")
    _assert_close(hy_s3_one["generation_kwh"], hy_s3_three["generation_kwh"], "wind/PV generation unchanged by room count")
    _assert_close(hy_one["load_context"]["electric_load_kwh"], project_one["summary"]["electric_kwh"], "hybrid one-room load context")
    _assert_close(hy_three["load_context"]["electric_load_kwh"], project_three["summary"]["electric_kwh"], "hybrid three-room load context")

    no_generation = HybridScenario(
        site_id=site,
        year=year,
        pv_capacity_kwp=0,
        wind=WindScenario(site_id=site, year=year, turbine_count=0),
        pv_quote=pvq,
        wind_quote=windq,
        shared_connection_cny=0,
        import_price_cny_per_kwh=0.66,
        study_years=10,
    )
    hy0 = run_hybrid_planning(project_three, pv_weather, pv_scenario, no_generation, wind_profile, include_hourly=False)
    hy0_s0 = next(x for x in hy0["candidates"] if x["scenario_id"] == "S0_grid")
    _assert_close(hy0_s0["grid_import_kwh"], project_three["summary"]["electric_kwh"], "hybrid zero-generation import")
    _assert_close(hy0_s0["generation_kwh"], 0.0, "hybrid zero-generation output")

    # The air-cost page uses the same one-room rows and applies room_count once.
    cost = life_cycle_cost(single_three, study_years=1, price_cny_per_kwh=0.66, room_count=3, units_per_room=2, equipment_price_cny=0, installation_cny=0, maintenance_cny_per_year=0)
    cost_load_kwh = sum(float(row["electric_kwh"]) for row in cost["monthly"].values())
    _assert_close(cost_load_kwh, project_three["summary"]["electric_kwh"], "air-cost/project annual load")
    _assert_close(cost_load_kwh, pv_three["load_context"]["electric_load_kwh"], "air-cost/PV annual load")
    _assert_close(cost_load_kwh, hy_three["load_context"]["electric_load_kwh"], "air-cost/hybrid annual load")

    result = {
        "status": "passed",
        "run_id": "phase2b-project-load-5090-guangzhou-2024",
        "source_commit": source_commit,
        "machine_role": "5090",
        "scope": "same-room aggregation only; no different-room physics",
        "weather": {"site_id": site, "year": year, "rows": n, "load_hash": weather.get("hash"), "pv_hash": pv_weather.get("hash"), "load_source": weather.get("source_file"), "pv_source": pv_weather.get("source_file")},
        "room_contract": {
            "one_room": {"room_count": 1, "units_per_room": 2, "single_room_kwh": single["summary"]["electric_kwh"], "project_kwh": project_one["summary"]["electric_kwh"]},
            "three_rooms": {"room_count": 3, "units_per_room": 2, "single_room_kwh": single_three["summary"]["electric_kwh"], "project_kwh": project_three["summary"]["electric_kwh"]},
            "project_to_one_ratio": project_three["summary"]["electric_kwh"] / project_one["summary"]["electric_kwh"],
            "single_room_preserved": bool(project_three.get("single_room_summary")),
            "aggregation_contract": project_three.get("project_load_contract"),
            "project_scope": project_three["load_series"].get("scope"),
            "source_scope": project_three["load_series"].get("single_room_scope"),
        },
        "pv": {"one_room": {"load_kwh": pv_one["load_context"]["electric_load_kwh"], "pv2_generation_kwh": pv2_one["generation_kwh"], "pv0_grid_import_kwh": pv0_one["grid_import_kwh"]}, "three_rooms": {"load_kwh": pv_three["load_context"]["electric_load_kwh"], "pv2_generation_kwh": pv2_three["generation_kwh"], "pv0_grid_import_kwh": pv0_three["grid_import_kwh"]}},
        "hybrid": {"one_room_s3": {"load_kwh": hy_one["load_context"]["electric_load_kwh"], "generation_kwh": hy_s3_one["generation_kwh"], "grid_import_kwh": hy_s3_one["grid_import_kwh"]}, "three_rooms_s3": {"load_kwh": hy_three["load_context"]["electric_load_kwh"], "generation_kwh": hy_s3_three["generation_kwh"], "grid_import_kwh": hy_s3_three["grid_import_kwh"]}, "three_rooms_s0": {"load_kwh": hy0_s0["load_kwh"] if "load_kwh" in hy0_s0 else project_three["summary"]["electric_kwh"], "grid_import_kwh": hy0_s0["grid_import_kwh"], "generation_kwh": hy0_s0["generation_kwh"]}},
        "air_cost": {"annual_load_kwh": cost_load_kwh, "cost_status": cost["lifecycle"]["status"], "room_count": cost["lifecycle"]["room_count"], "units_per_room": cost["lifecycle"]["units_per_room"]},
        "contract_examples": "tests/test_aircost_handoff.py are short contract samples, not annual-plan demonstrations; this file is the formal full-year replay.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "project_load_full_year.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    ended = _now()
    manifest = {
        "run_id": result["run_id"],
        "source_commit": source_commit,
        "machine_role": "5090",
        "hostname": platform.node(),
        "python": sys.version,
        "gpu": _nvidia(),
        "command": "python scripts/phase2b_project_load_handoff_5090.py",
        "started_utc": started,
        "ended_utc": ended,
        "exit_status": 0,
        "weather_hashes": {"load": weather.get("hash"), "pv": pv_weather.get("hash")},
        "output_sha256": _sha(result),
        "short_tests": "contract examples only; not annual-plan demonstrations",
        "formal_replay": "Guangzhou 2024 complete-year normalized weather; no historical experiment rerun",
        "notes": ["Only room_count aggregation is tested; heat/moisture and PV/wind formulas are unchanged.", "Single-room trace, project aggregation and matching outputs are kept distinct.", "No model weights, credentials or private data are included."],
    }
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "source_commit": source_commit, "rows": n, "project_kwh": project_three["summary"]["electric_kwh"], "pv2_generation_kwh": pv2_three["generation_kwh"], "hybrid_s3_generation_kwh": hy_s3_three["generation_kwh"], "output": str(OUT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
