"""Record actual short HTTP interface contracts without touching annual replay.

Run from the repository root using Python on the 5090.  A separate ephemeral
loopback HTTP server is used; port 18765 and all annual results are preserved.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests import test_phase2b_api_v6 as contracts

OUT = ROOT / "operation_planning/results/phase2b_carbon_5090/api_contracts_v6"
EXAMPLES = ROOT / "docs/handoff/api_examples_v6.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact_response(response):
    if "equipment_models" in response:
        return {"status": response["status"], "cities": response["cities"], "years": response["years"],
            "equipment_model_count": len(response["equipment_models"]),
            "tariffs": [{key: row.get(key) for key in ("tariff_id", "verified", "provisional", "verification_status", "source_url")}
                        for row in response["tariffs"]["tariffs"]],
            "carbon_factor_count": len(response["carbon_factors"]["factors"])}
    if "report" in response:
        report = response["report"]
        return {"status": response["status"], "report": {
            "project_load_contract": report.get("project_load_contract"),
            "recommended_pv_capacity_kwp": report.get("recommended_pv_capacity_kwp"),
            "recommendation": report.get("recommendation"),
            "calculation_timing": report.get("calculation_timing"),
            "pv_capacity_sweep": [{key: row.get(key) for key in ("requested_capacity_kwp", "admission_status", "status", "incremental_npv_vs_s0_cny")}
                                   for row in report.get("pv_capacity_sweep", [])],
            "candidates": [{"scenario_id": row["scenario_id"], "pv_capacity_kwp": row["pv_capacity_kwp"],
                "admission_status": row["admission_status"], "constraint_status": row["constraint_status"],
                "generation_kwh": row["generation_kwh"], "self_use_kwh": row["self_use_kwh"],
                "grid_import_kwh": row["grid_import_kwh"],
                "hourly_row_count": len(row.get("hourly", {}).get("timestamps", [])),
                "total_cost_npv_cny": row["economics"].get("total_cost_npv_cny")}
                for row in report.get("candidates", [])]}}
    if "job_id" in response and "result" in response:
        return {key: response.get(key) for key in ("job_id", "status", "progress", "elapsed_ms", "events", "error", "message", "field")}
    return response


def main():
    started = datetime.now(timezone.utc).isoformat()
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    workspace = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines()
    began = time.perf_counter()
    short_checks = []
    for name in ("test_v6_options_and_capacity_validation_contract", "test_v6_thermal_capacity_contract",
                 "test_v6_fixed_capacity_preserves_unknown_and_excluded_status", "test_v6_async_contract_schema",
                 "test_v6_http_options_thermal_and_async_contract"):
        getattr(contracts, name)(); short_checks.append({"test": name, "status": "passed"})
    probe = contracts.real_short_http_probe()
    short_checks.append({"test": "test_v6_real_short_http_contract", "status": probe["status"]})
    OUT.mkdir(parents=True, exist_ok=True)
    evidence = OUT / "http_contract_results.json"
    evidence.write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    examples = []
    for row in probe["records"]:
        response = row["response"]
        # Polling produces many transient snapshots; keep only terminal
        # snapshots and submits in the concise handbook examples.
        if row["method"] == "GET" and "job_id" in response and response["status"] not in {"done", "failed"}:
            continue
        examples.append({"method": row["method"], "path": row["path"], "http_status": row["http_status"],
                         "request": row["request"], "response": compact_response(response),
                         "response_projection": True, "actual_http_elapsed_ms": row["elapsed_ms"]})
    EXAMPLES.write_text(json.dumps({"source_commit": source_commit, "fixture_type": probe["fixture_type"],
        "note": "Actual HTTP request/response projections; no mocked calculators. Short fixture is not an annual demo.",
        "full_response_evidence": "operation_planning/results/phase2b_carbon_5090/api_contracts_v6/http_contract_results.json",
        "examples": examples}, ensure_ascii=False, indent=2), encoding="utf-8")
    deps = {}
    for name in ("pvlib", "numpy", "pandas", "scipy", "windpowerlib"):
        deps[name] = importlib.metadata.version(name)
    manifest = {"run_id": "phase2b-v6-short-http-contracts-5090", "status": "passed", "machine_role": "5090",
        "source_commit": source_commit, "formal_annual_v6_source_commit": "ec8a7cf",
        "source_change_note": "Post-annual-run interface-only change adds explicit provisional option fields and polling error payloads; annual v6 physics/results preserved.",
        "workspace_at_start": workspace, "python": sys.version, "dependencies": deps,
        "command": "python -X utf8 scripts/phase2b_api_contracts_v6_5090.py", "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(), "elapsed_ms": round((time.perf_counter() - began) * 1000, 3),
        "tests": short_checks, "port_strategy": "independent ephemeral loopback port; no port 18765 restart",
        "source_hashes": {str(path.relative_to(ROOT)): sha(path) for path in [ROOT / "operation_planning/app.py", ROOT / "tests/test_phase2b_api_v6.py", Path(__file__)]},
        "output_hashes": {str(path.relative_to(ROOT)): sha(path) for path in [evidence, EXAMPLES]}}
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source_commit": source_commit, "status": "passed", "test_count": len(short_checks),
                      "elapsed_ms": manifest["elapsed_ms"], "examples": len(examples)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
