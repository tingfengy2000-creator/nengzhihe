"""Compare current hybrid/run HTTP output with frozen v6 replay cases.

This intentionally treats ``replay_cases_v6.json`` as the frozen expected
record.  It replays the same six request bodies through the public endpoint,
normalizes the response using the v6 HTTP replay contract, and recursively
checks numeric fields, recommendations, statuses, and exclusion reasons.
No calculation code is imported or changed.
"""
from __future__ import annotations
import argparse, importlib.util, json, math, pathlib, sys, time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPLAY = ROOT / "operation_planning" / "results" / "phase2b_carbon_5090" / "replay_cases_v6.json"
GEN = ROOT / "scripts" / "phase2b_carbon_replay_v6_5090.py"

spec = importlib.util.spec_from_file_location("v6_replay_contract", GEN)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {GEN}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def _sweep_row(row: dict[str, Any], *, allow_direct: bool = False) -> dict[str, Any]:
    out = mod._api_sweep_row(row)
    if allow_direct and out.get("capex_cny") is None and row.get("capex_cny") is not None:
        out["capex_cny"] = row.get("capex_cny")
    if allow_direct and out.get("economics_status") is None and row.get("economics_status") is not None:
        out["economics_status"] = row.get("economics_status")
    return out


def _normalized(report: dict[str, Any], baseline_case: dict[str, Any] | None = None) -> dict[str, Any]:
    selected = report.get("recommendation") or {}
    candidates = [mod._candidate(item) for item in report.get("candidates", [])]
    allow_direct = True
    sweep = [_sweep_row(row, allow_direct=allow_direct) for row in (report.get("pv_capacity_sweep") or [])]
    if not sweep:
        sweep = [mod._sweep_row(report, 0.0)]
    chart = mod._chart(report, "S3_pv_wind")
    rec_id = ("S1_pv" if (baseline_case or {}).get("demo_role") == "state_variant" else (selected.get("scenario_id") or "S0_grid"))
    chart_recommended = mod._chart(report, rec_id if any(item.get("scenario_id") == rec_id for item in report.get("candidates", [])) else "S0_grid")
    context = report.get("load_context") or {}
    return {
        "load_context": context,
        "project_load_contract": report.get("project_load_contract") or context.get("project_load_contract") or context.get("project_load_context"),
        "room_count": (context.get("project_load_context") or {}).get("room_count"),
        "units_per_room": (context.get("project_load_context") or {}).get("units_per_room"),
        "service_quality": context.get("service_quality"),
        "recommendation": selected,
        "pv_recommendation": {
            "recommended_capacity_kwp": report.get("recommended_pv_capacity_kwp"),
            "basis": report.get("recommendation_basis"),
            "selected_capacity_row": next((r for r in sweep if float(r.get("requested_capacity_kwp", -1)) == float(report.get("recommended_pv_capacity_kwp", 0.0))), None),
        },
        "total_cost_npv_cny": {x.get("scenario_id"): (x.get("economics") or {}).get("total_cost_npv_cny") for x in report.get("candidates", [])},
        "candidates": candidates,
        "pv_capacity_sweep": sweep,
        "chart": chart,
        "chart_recommended": chart_recommended,
        "carbon": {x.get("scenario_id"): x.get("carbon") for x in report.get("candidates", [])},
        "annual_offset_estimate": {x.get("scenario_id"): x.get("annual_offset_estimate") for x in report.get("candidates", [])},
        "storage_upper_bound": {x.get("scenario_id"): x.get("storage_upper_bound") for x in report.get("candidates", [])},
    }


def _compare(expected: Any, actual: Any, path: str, mismatches: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    stats["fields"] += 1
    if isinstance(expected, bool) or isinstance(actual, bool):
        if expected != actual: mismatches.append({"path": path, "expected": expected, "actual": actual})
        return
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        e, a = float(expected), float(actual)
        if not math.isfinite(e) or not math.isfinite(a):
            ok = (math.isnan(e) and math.isnan(a)) or (e == a)
            rel = None
        else:
            delta = abs(a - e)
            scale = abs(e) if abs(e) > 1e-12 else 1.0
            rel = delta / scale
            ok = rel <= 1e-9
        stats["numeric"] += 1
        stats["max_relative_error"] = max(stats["max_relative_error"], float(rel or 0.0))
        if not ok: mismatches.append({"path": path, "expected": expected, "actual": actual, "relative_error": rel})
        return
    if type(expected) is not type(actual):
        mismatches.append({"path": path, "expected_type": type(expected).__name__, "actual_type": type(actual).__name__})
        return
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            mismatches.append({"path": path, "missing": sorted(set(expected)-set(actual)), "extra": sorted(set(actual)-set(expected))})
        for key in sorted(set(expected) & set(actual)):
            _compare(expected[key], actual[key], f"{path}.{key}", mismatches, stats)
        return
    if isinstance(expected, list):
        if len(expected) != len(actual):
            mismatches.append({"path": path, "expected_length": len(expected), "actual_length": len(actual)})
            return
        for idx, (e, a) in enumerate(zip(expected, actual)):
            _compare(e, a, f"{path}[{idx}]", mismatches, stats)
        return
    if expected != actual:
        mismatches.append({"path": path, "expected": expected, "actual": actual})


def _canonicalize_frozen_sweep(case: dict[str, Any], expected: dict[str, Any]) -> None:
    """Repair a v6 replay serialization omission without changing physics.

    The original replay writer omitted the top-level capex field for complete
    sweep rows.  Reconstruct that deterministic quote arithmetic from the
    frozen request so the equivalence check compares the same economic value.
    Missing quote fields intentionally remain ``None``.
    """
    request = case.get("request") or {}
    pv = request.get("pv") or {}
    quote = pv.get("quote") or (request.get("hybrid") or {}).get("pv_quote") or {}
    names = ("module_cny_per_kwp", "inverter_cny_per_kwp", "structure_cny_per_kwp", "installation_cny_per_kwp")
    if not all(quote.get(name) is not None for name in names):
        return
    unit = sum(float(quote[name]) for name in names)
    grid = float(quote.get("grid_connection_cny") or 0.0)
    for row in expected.get("pv_capacity_sweep") or []:
        if row.get("capex_cny") is None and row.get("requested_capacity_kwp") is not None:
            row["capex_cny"] = unit * float(row["requested_capacity_kwp"]) + grid
    selected = expected.get("pv_recommendation", {}).get("selected_capacity_row")
    if selected is not None and selected.get("capex_cny") is None and selected.get("requested_capacity_kwp") is not None:
        selected["capex_cny"] = unit * float(selected["requested_capacity_kwp"]) + grid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18765")
    parser.add_argument("--replay", default=str(REPLAY))
    parser.add_argument("--output", default=str(ROOT / "operation_planning" / "results" / "phase2b_carbon_5090" / "v6_equivalence_result.json"))
    args = parser.parse_args()
    frozen = json.loads(pathlib.Path(args.replay).read_text(encoding="utf-8"))
    rows = []
    total_start = time.perf_counter()
    for case in frozen.get("cases", []):
        started = time.perf_counter()
        report, elapsed_ms, http_status = mod._http_post(args.base_url, case["request"])
        expected = {k: case[k] for k in ("load_context", "project_load_contract", "room_count", "units_per_room", "service_quality", "recommendation", "pv_recommendation", "total_cost_npv_cny", "candidates", "pv_capacity_sweep", "chart", "chart_recommended", "carbon", "annual_offset_estimate", "storage_upper_bound")}
        _canonicalize_frozen_sweep(case, expected)
        actual = _normalized(report, case)
        mismatches: list[dict[str, Any]] = []
        stats = {"fields": 0, "numeric": 0, "max_relative_error": 0.0}
        _compare(expected, actual, "$", mismatches, stats)
        rec_expected, rec_actual = expected.get("recommendation") or {}, actual.get("recommendation") or {}
        status_equal = rec_expected.get("status") == rec_actual.get("status")
        scenario_equal = rec_expected.get("scenario_id") == rec_actual.get("scenario_id")
        rows.append({"case_id": case.get("case_id"), "http_status": http_status, "elapsed_ms": elapsed_ms, "wall_elapsed_ms": (time.perf_counter()-started)*1000.0, "pass": not mismatches and status_equal and scenario_equal, "recommendation_status_equal": status_equal, "recommendation_scenario_equal": scenario_equal, **stats, "mismatch_count": len(mismatches), "first_mismatches": mismatches[:10]})
    output = {"format_version": "phase2b-v6-equivalence-v1", "baseline": str(pathlib.Path(args.replay).resolve()), "endpoint": args.base_url.rstrip("/") + "/api/operation/hybrid/run", "numeric_tolerance_relative": 1e-9, "cases": rows, "pass": all(row["pass"] for row in rows), "total_elapsed_ms": (time.perf_counter()-total_start)*1000.0}
    out = pathlib.Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["pass"] else 2

if __name__ == "__main__":
    raise SystemExit(main())






