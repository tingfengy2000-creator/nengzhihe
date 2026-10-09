"""Paired localhost model-parse evaluation; no simulation is run here.

The frozen corpus reuses the exact round21 current_task HTTP payloads.  Each
sentence is called once per phase, sequentially, without rule fallbacks.
Only short model/parse objects and their hashes are saved, never hourly data.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def build_corpus(path: Path):
    if path.exists():
        raise SystemExit("Frozen corpus exists; do not replace it")
    old = json.loads((ROOT / "operation_planning/results/round21_local_5090/task_records.json").read_text(encoding="utf-8"))
    expected = {
        "01_units": {"room.units_per_room": 3},
        "02_catalog": {"room.equipment_id": "midea_gaia12"},
        "04_budget": {"hybrid.budget_cny": 180000},
        "05_hours": {"room.start_hour": 18, "room.end_hour": 22},
        "06_export": {"hybrid.allow_export": False},
        "07_pv": {"pv.capacity_kwp": 2},
        "08_wind": {"hybrid.wind.turbine_count": 0},
        "09_escalation": {"hybrid.tariff_escalation_rate": .03},
        "10_storage": {"storage.quote.cny_per_kwh": 600, "storage.capacities_kwh": [0, 5, 10]},
        "13_pv_units": {"pv.capacity_kwp": 2},
        "14_wind_words": {"hybrid.wind.turbine_count": 0},
    }
    cases = []
    for item in old["latest_by_sentence"]:
        filename, line = item["parse_trace"].rsplit(":", 1)
        event = json.loads((ROOT / filename).read_text(encoding="utf-8").splitlines()[int(line) - 1])
        assert event["request"]["request"] == item["request"]
        kind = "edit" if item["id"] in expected else "clarification" if item["id"] == "12_question" else "unsupported"
        cases.append({"id": item["id"], "request": item["request"], "current_task": event["request"]["current_task"],
                      "expected_kind": kind, "expected_changes": expected.get(item["id"], {}),
                      "origin": item["parse_trace"], "historical_round21_status": item["parse_response"]["status"],
                      "historical_round21_adopted": item["adopted"]})
    additions = [
        ("15_no_wind", "不要风机了", "edit", {"hybrid.wind.turbine_count": 0}),
        ("16_two_wind", "装两台风机", "out_of_range", {"hybrid.wind.turbine_count": 2}),
        ("17_pv5", "光伏装 5kWp", "edit", {"pv.capacity_kwp": 5}),
        ("18_budget6", "预算改为6万", "edit", {"hybrid.budget_cny": 60000}),
    ]
    for case_id, request, kind, changes in additions:
        cases.append({"id": case_id, "request": request, "current_task": deepcopy(cases[0]["current_task"]),
                      "expected_kind": kind, "expected_changes": changes, "origin": "section22_new_sentence"})
    write_json(path, {"protocol": "round22-paired-parse-v1", "scope": "read-only parsing and task patch validation, not adopted-and-calculated browser success",
                      "attempts_per_case_per_phase": 1, "retry": False, "rule_fallback": False,
                      "cases": cases, "frozen_note": "WindScenario and shared schema only support turbine_count 0/1; two turbines must remain rejected. No physical model changes."})


def apply_changes(task, changes):
    out = deepcopy(task)
    for item in changes:
        parts = item["field"].split(".")
        target = out
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = item["to"]
    return out


def score(case, response):
    changes = {i["field"]: i["to"] for i in response.get("changes", [])}
    if "hybrid.pv_capacity_kwp" in changes:
        changes["pv.capacity_kwp"] = changes.pop("hybrid.pv_capacity_kwp")
    if case["expected_kind"] == "edit":
        return response.get("status") == "ok" and changes == case["expected_changes"] and not response.get("unsupported")
    if case["expected_kind"] == "clarification":
        return response.get("status") == "needs_clarification" and not changes and bool(response.get("question"))
    if case["expected_kind"] == "unsupported":
        return response.get("status") == "ok" and not changes and bool(response.get("unsupported"))
    return response.get("status") == "failed" and not changes


def run(corpus_path: Path, output: Path, phase: str, port: int):
    from operation_planning import agent_parse, app
    if output.exists():
        raise SystemExit("Output already exists; use a fresh directory")
    output.mkdir(parents=True)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True).strip()
    started = datetime.now(timezone.utc).isoformat()
    records = []
    raw_calls = []
    original = agent_parse._model_parse

    def observed(config, request, task):
        call = {"request": request, "model_id": config["model_id"]}
        raw_calls.append(call)
        try:
            call["raw"] = original(config, request, task)
            return call["raw"]
        except Exception as exc:
            call["error"] = str(exc)
            raise
    agent_parse._model_parse = observed
    server = ThreadingHTTPServer(("127.0.0.1", port), app.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base_url = f"http://127.0.0.1:{port}"
    try:
        with opener.open(base_url + "/api/operation/agent/status", timeout=3) as r:
            model_status = json.load(r)
        if not model_status.get("available"):
            raise RuntimeError("Local model is unavailable; no substitute run is allowed")
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        for case in corpus["cases"]:
            request = {"request": case["request"], "current_task": case["current_task"]}
            encoded = json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")
            start = time.perf_counter()
            with opener.open(urllib.request.Request(base_url + "/api/operation/agent/parse", data=encoded,
                              headers={"Content-Type": "application/json"}), timeout=22) as response:
                raw_response = response.read()
                http_status = response.status
            result = json.loads(raw_response)
            row = {"id": case["id"], "request": case["request"], "request_sha256": digest(encoded),
                   "http_status": http_status, "response": result, "response_sha256": digest(raw_response),
                   "model_call": raw_calls[-1] if raw_calls and raw_calls[-1]["request"] == case["request"] else None,
                   "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
                   "expected_kind": case["expected_kind"], "expected_changes": case["expected_changes"],
                   "expectation_met": score(case, result), "task_patch": result.get("changes", []) if result.get("status") == "ok" else []}
            records.append(row)
            write_json(output / "cases.json", records)
            print(f"{phase} {case['id']} {result['status']} expectation={row['expectation_met']} {row['elapsed_ms']}ms", flush=True)
    finally:
        server.shutdown()
        server.server_close()
        agent_parse._model_parse = original
    manifest = {"run_id": output.name, "phase": phase, "source_commit": source, "workspace_status": status,
                "parser_sha256": digest((ROOT / "operation_planning/agent_parse.py").read_bytes()),
                "corpus_sha256": digest(corpus_path.read_bytes()), "start_utc": started,
                "end_utc": datetime.now(timezone.utc).isoformat(), "model_status": model_status,
                "model_config_sha256": digest(agent_parse.CONFIG_PATH.read_bytes()),
                "model_sampling": {"temperature": 0, "seed": 20260930, "max_tokens": 512, "thinking": False},
                "attempts_per_sentence": 1, "rule_fallback": False, "numerical_calculation_invocations": 0,
                "command": ["python", "-X", "utf8", "-m", "scripts.round22_parse_evaluation", "run", "--corpus", str(corpus_path),
                            "--output", str(output), "--phase", phase, "--port", str(port)],
                "cases_sha256": digest((output / "cases.json").read_bytes()),
                "summary": {"all": len(records), "correct_edits": sum(r["expectation_met"] and r["expected_kind"] == "edit" for r in records),
                            "supported_edit_tasks": sum(r["expected_kind"] == "edit" for r in records),
                            "all_expectations_met": sum(r["expectation_met"] for r in records)},
                "exit_status": "completed"}
    write_json(output / "run_manifest.json", manifest)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["freeze", "run"])
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--phase", choices=["before", "after"])
    p.add_argument("--port", type=int, default=18770)
    args = p.parse_args()
    if args.action == "freeze":
        build_corpus(args.corpus)
    else:
        run(args.corpus, args.output, args.phase, args.port)


if __name__ == "__main__":
    main()
