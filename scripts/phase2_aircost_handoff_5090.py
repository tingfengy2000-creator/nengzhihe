"""Run the 5090 air-cost handoff cases through the real HTTP API.

The script starts a temporary loopback server from the current checkout, sends
the same JSON a frontend would send, and saves compact request/response
evidence. It never calls the local model and does not alter historical result
directories.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "operation_planning" / "results" / "phase2b_aircost_handoff_5090"
PORT = 18880


def _post(payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(f"http://127.0.0.1:{PORT}/api/operation/thermal/run", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=180) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        if hasattr(exc, "read"):
            return getattr(exc, "code", 500), json.loads(exc.read().decode("utf-8"))
        raise


def _short_response(data: dict) -> dict:
    result = data.get("result", {})
    cost = data.get("cost", {})
    return {
        "status": data.get("status"),
        "input_contract": data.get("input_contract"),
        "weather_hash": data.get("weather_hash"),
        "room": result.get("room"),
        "summary": result.get("summary"),
        "load_series_contract": {k: result.get("load_series", {}).get(k) for k in ("scope", "equipment_count", "room_count", "units_per_room", "model_version")},
        "cost": cost,
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _weather() -> dict:
    return {
        "context": {"source": "handoff_short_contract", "dataset_kind": "controlled_short_sequence"},
        "hash": "handoff-short-weather-v1",
        "time": ["2024-07-15T08:00", "2024-07-15T08:30", "2024-07-15T09:00"],
        "hourly": {
            "temperature_2m": [30.0, 30.0, 30.0],
            "relative_humidity_2m": [70.0, 70.0, 70.0],
            "surface_pressure": [1010.0, 1010.0, 1010.0],
            "shortwave_radiation": [300.0, 300.0, 300.0],
        },
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    started = datetime.now(timezone.utc).isoformat()
    server = subprocess.Popen([sys.executable, "-c", f"from operation_planning.app import serve; serve(port={PORT})"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(60):
            try:
                request.urlopen(f"http://127.0.0.1:{PORT}/api/operation/health", timeout=2).read()
                break
            except Exception:
                time.sleep(0.25)
        weather = _weather()
        common = {
            "site_id": "handoff_short", "year": 2024, "weather": weather,
            "annual_price_cny_per_kwh": 0.66, "study_years": 10,
            "equipment_quote": {"equipment_price_cny": 3200, "installation_cny": 900, "maintenance_cny_per_year": 0},
        }
        cases = {}
        for case_id, room in (("one_room_two_units", {"equipment_count": 2, "room_count": 1}), ("three_rooms_two_units", {"equipment_count": 2, "room_count": 3})):
            payload = {**common, "room": room}
            status, response = _post(payload)
            cases[case_id] = {"request": payload, "http_status": status, "response": _short_response(response)}
        for life in (8, 12):
            payload = {**common, "room": {"equipment_count": 2, "room_count": 1}, "expected_life_years": life, "warranty_years": 2}
            status, response = _post(payload)
            cases[f"lifetime_{life}_years"] = {"request": payload, "http_status": status, "response": _short_response(response)}
        tariff_payload = {"effective_start": "2024-07-15", "effective_end": "2024-07-15", "periods": [{"name": "peak", "start": "08:00", "end": "08:30", "price": 0.5}, {"name": "flat", "start": "08:30", "end": "24:00", "price": 1.0}, {"name": "flat", "start": "00:00", "end": "08:00", "price": 1.0}]}
        payload = {"site_id": "handoff_short", "year": 2024, "weather": weather, "tariff_id": "custom_user", "custom_tariff": tariff_payload, "tariff_calendar_date": "2024-07-15", "study_years": 1, "room": {"equipment_count": 1, "room_count": 1}, "equipment_quote": {"equipment_price_cny": 0, "installation_cny": 0, "maintenance_cny_per_year": 0}}
        status, response = _post(payload)
        cases["custom_tariff_boundary"] = {"request": payload, "http_status": status, "response": _short_response(response)}

        # Representative full-year task: retain compact, traceable summaries;
        # the old full weather and physical result files remain untouched.
        full_payload = {"site_id": "guangzhou", "year": 2024, "annual_price_cny_per_kwh": 0.66, "study_years": 10, "expected_life_years": 10, "room": {"equipment_count": 2, "room_count": 1}, "equipment_quote": {"equipment_price_cny": 3200, "installation_cny": 900, "maintenance_cny_per_year": 280}}
        status, response = _post(full_payload)
        cases["guangzhou_2024_one_room_two_units_full_weather"] = {"request": full_payload, "http_status": status, "response": _short_response(response), "response_sha256": hashlib.sha256(json.dumps(response, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
        full_three_payload = {**full_payload, "room": {"equipment_count": 2, "room_count": 3}}
        status, response = _post(full_three_payload)
        cases["guangzhou_2024_three_rooms_full_weather"] = {"request": full_three_payload, "http_status": status, "response": _short_response(response), "response_sha256": hashlib.sha256(json.dumps(response, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}

        old = json.loads((ROOT / "operation_planning" / "results" / "regional_product_v2" / "three_demos.json").read_text(encoding="utf-8"))
        old_batch = old["demos"]["03_quote_and_batch"]["batch_quote"]
        (OUT / "batch_quote_legacy_preserved.json").write_text(json.dumps(old_batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        corrected = cases["guangzhou_2024_one_room_two_units_full_weather"]
        (OUT / "batch_quote_corrected.json").write_text(json.dumps(corrected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        corrected_summary = corrected["response"]["summary"]
        (OUT / "batch_quote_diff.json").write_text(json.dumps({"legacy_file": "operation_planning/results/regional_product_v2/three_demos.json", "legacy_initial_cny": old_batch["response"]["cost"]["lifecycle"]["initial_cny"] if "response" in old_batch else old_batch["cost"]["initial_cny"], "corrected_initial_cny": corrected["response"]["cost"]["lifecycle"]["initial_cny"], "legacy_electric_kwh": old_batch["summary"]["electric_kwh"], "corrected_electric_kwh_one_room": corrected_summary["electric_kwh"], "explanation": "旧batch_quote把equipment_count=2同时当作费用数量和用电乘数；修正后单房间物理轨迹已经包含两台设备，费用按逐台报价计2台，room_count只有在同类房间聚合时才乘电量。"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cases["legacy_batch_quote_note"] = {"legacy_initial_cny": old_batch["cost"]["initial_cny"], "legacy_equipment_count": old_batch["room"].get("equipment_count"), "note": "旧记录保留；旧 quantity 同时影响电量与费用，不能作为本轮修正口径"}
        cases_text = json.dumps({"source_commit": source_commit, "calculation_version": "phase2b-aircost-handoff-5090-v1", "cases": cases}, ensure_ascii=False, indent=2) + "\n"
        (OUT / "aircost_api_cases.json").write_text(cases_text, encoding="utf-8")
        (ROOT / "docs" / "handoff" / "replay_viewer" / "aircost_cases.json").write_text(cases_text, encoding="utf-8")
        output_paths = [OUT / name for name in ("aircost_api_cases.json", "batch_quote_legacy_preserved.json", "batch_quote_corrected.json", "batch_quote_diff.json")] + [ROOT / "docs" / "handoff" / "replay_viewer" / "aircost_cases.json"]
        package_versions = {}
        for package in ("numpy", "pandas", "pvlib", "windpowerlib", "requests"):
            try:
                package_versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                package_versions[package] = None
        gpu = "unqueried"
        if shutil.which("nvidia-smi"):
            try:
                gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True, timeout=10).strip()
            except Exception:
                gpu = "nvidia-smi-query-failed"
        manifest = {"run_id": "phase2b-aircost-handoff-5090-20261006", "source_commit": source_commit, "machine_role": "5090", "workspace": str(ROOT), "python": platform.python_version(), "gpu": gpu, "key_dependencies": package_versions, "local_model": {"called": False, "reason": "本轮仅验证确定性空调热湿和成本API"}, "command": "python scripts/phase2_aircost_handoff_5090.py", "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "exit_status": "success", "inputs": {"short_weather_hash": weather["hash"], "guangzhou_normalized_weather_hash": corrected["response"].get("weather_hash"), "quote_and_parameter_hash": hashlib.sha256(json.dumps(full_payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}, "outputs": [{"path": str(path.relative_to(ROOT)), "sha256": _sha(path)} for path in output_paths], "notes": ["仅新增空调成本接口回归；阶段二A/B旧结果未覆盖。", "短序列和广州2024完整天气均通过真实HTTP接口；本地模型未参与。"]}
        (OUT / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
