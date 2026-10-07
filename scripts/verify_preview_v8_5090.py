"""Verify corrected preview rows against the same annual physical trace."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from operation_planning import app
from operation_planning.hybrid import match_hybrid
from operation_planning.project_load import aggregate_project_load
from operation_planning.pv import generate_pv
from operation_planning.thermal_model import simulate_room
from operation_planning.weather import load_weather, load_pv_weather
from operation_planning.wind import WindTurbineProfile, generate_wind

PREVIEW = ROOT / "operation_planning/results/phase2b_carbon_5090/replay_previews_v7.json"
OUT = ROOT / "operation_planning/results/phase2b_carbon_5090/preview_v8_equivalence.json"


def _rel(got: float, want: float) -> float:
    scale = max(abs(float(want)), 1e-12)
    return abs(float(got) - float(want)) / scale


def main() -> None:
    package = json.loads(PREVIEW.read_text(encoding="utf-8"))
    rows = []
    max_abs = 0.0
    max_rel = 0.0
    fields = ("load_kwh", "pv_generation_kwh", "wind_generation_kwh", "self_use_kwh", "grid_import_kwh", "curtailment_kwh")
    for case in package["cases"]:
        payload = case["request"]
        weather = load_weather(str(payload.get("site_id", "guangzhou")), int(payload.get("year", 2024)))
        indices, _ = app._preview_period_indices(weather["time"], "week", case["season"], int(payload["preview"]["month"]))
        room, _, _ = app._thermal_inputs(payload)
        load = aggregate_project_load(simulate_room(weather, room))
        pv_scenario, hybrid = app.hybrid_task_from_dict(payload, site_id=str(payload.get("site_id", "guangzhou")), year=int(payload.get("year", 2024)))
        pv_weather = load_pv_weather(str(payload.get("site_id", "guangzhou")), int(payload.get("year", 2024)))
        pv = asdict(generate_pv(pv_weather, hybrid.pv_capacity_kwp, pv_scenario))
        wind = generate_wind(pv_weather, WindTurbineProfile.from_file(), hybrid.wind)
        annual = match_hybrid(load["load_series"], pv, wind, allow_export=False)
        selected_load = app._slice_project_load(load, indices)
        expected_service = selected_load["summary"]
        got_response = case["response"]
        got_by_id = {x["scenario_id"]: x for x in got_response["candidates"]}
        scenario_diffs = []
        for scenario_id, expected_candidate in (("S3_pv_wind", annual),):
            got_intervals = got_by_id[scenario_id]["intervals"]
            expected_intervals = [expected_candidate["intervals"][i] for i in indices]
            for got, want in zip(got_intervals, expected_intervals):
                for field in fields:
                    av = float(got[field]); bv = float(want[field])
                    max_abs = max(max_abs, abs(av - bv))
                    max_rel = max(max_rel, _rel(av, bv))
            scenario_diffs.append({"scenario_id": scenario_id, "rows": len(got_intervals)})
        service = got_response["service_quality"]
        service_expected = {"capacity_shortfall_hours": expected_service.get("capacity_shortfall_hours", 0.0), "unmet_temp_degree_hours": expected_service.get("unmet_temp_degree_hours", 0.0), "unmet_rh_percent_hours": expected_service.get("unmet_rh_percent_hours", 0.0)}
        service_actual = {key: service.get(key) for key in service_expected}
        rows.append({"case_id": case["case_id"], "scenario_checks": scenario_diffs, "service_actual": service_actual, "service_expected": service_expected, "service_equal": service_actual == service_expected})
    output = {"format_version": "preview_v8_equivalence", "source_preview": str(PREVIEW.relative_to(ROOT)), "case_count": len(rows), "fields": list(fields), "max_abs_diff": max_abs, "max_relative_error": max_rel, "tolerance": 1e-9, "cases": rows, "pass": max_rel <= 1e-9 and all(row["service_equal"] for row in rows)}
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
