"""Lightweight API contracts for the v6 realtime calculation surface.

These tests exercise request validation and the capacity/thermal adapters
without GPU, network or the front end.  Full-year timing is covered by the
5090 replay manifest; this file intentionally stays a fast contract gate.
"""
from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

from operation_planning.app import _api_error, _capacity_candidates, _thermal_capacity_sweep


def _weather_fixture():
    times = ["2024-07-01T08:00", "2024-07-01T09:00", "2024-07-01T10:00"]
    common = {"temperature_2m": [30, 31, 32], "relative_humidity_2m": [70, 70, 70],
              "surface_pressure": [1010, 1010, 1010], "shortwave_radiation": [200, 400, 600],
              "wind_speed_10m": [10, 10, 10], "wind_direction_10m": [180, 180, 180],
              "direct_normal_irradiance": [300, 500, 700], "diffuse_radiation": [50, 50, 50]}
    return {"time": times, "hourly": common, "context": {"site": {"timezone": "Asia/Shanghai", "latitude": 23.1291, "longitude": 113.2644}}, "hash": "fixture"}


def test_v6_options_and_capacity_validation_contract():
    assert _capacity_candidates({"requested_capacities_kwp": [0, 2, 1, 2]}) == [0.0, 1.0, 2.0]
    auto = _capacity_candidates({"auto_capacity": True, "roof_area_m2": 35, "usable_fraction": 0.8})
    assert auto[0] == 0.0 and auto[-1] > auto[1]
    error = _api_error(ValueError("pv.requested_capacities_kwp 必须是非空数组"))
    assert error["status"] == "failed" and error["field"] == "pv.requested_capacities_kwp"


def test_v6_thermal_capacity_contract():
    import operation_planning.app as app
    original = app.load_weather
    app.load_weather = lambda site, year: _weather_fixture()
    try:
        result = _thermal_capacity_sweep({"site_id": "guangzhou", "year": 2024, "max_units": 3,
            "room": {"area_m2": 35, "equipment_id": "midea_msagbu12_mox201", "room_count": 1,
                     "units_per_room": 1, "equipment_count": 1}})
    finally:
        app.load_weather = original
    assert result["status"] == "success"
    assert [row["units_per_room"] for row in result["candidates"]] == [1, 2, 3]
    assert "minimum_adequate_units_per_room" in result
    assert all("annual_electric_kwh" in row and "capacity_shortfall_hours" in row for row in result["candidates"])


def test_v6_fixed_capacity_preserves_unknown_and_excluded_status():
    import operation_planning.app as app
    base = {"site_id": "guangzhou", "year": 2024,
        "room": {"area_m2": 35, "equipment_id": "midea_msagbu12_mox201", "equipment_count": 1,
                 "units_per_room": 1, "room_count": 1}, "weather": _weather_fixture(),
        "pv_weather": _weather_fixture(), "pv": {"roof_area_m2": 35, "usable_fraction": 0.8,
            "requested_capacities_kwp": [1], "fixed_capacity_kwp": 1, "quote": {}},
        "hybrid": {"pv_capacity_kwp": 1, "budget_cny": 90000, "allow_export": False,
            "wind": {"turbine_count": 0}, "pv_quote": {}, "wind_quote": {}},
        "storage": {"capacities_kwh": [0]}}
    unknown = app._hybrid_capacity_run(base)
    s1 = next(row for row in unknown["candidates"] if row["scenario_id"] == "S1_pv")
    assert unknown["recommended_pv_capacity_kwp"] == 1 and s1["admission_status"] == "unknown"
    excluded_payload = dict(base)
    excluded_payload["pv"] = {**base["pv"], "roof_area_m2": 1}
    excluded = app._hybrid_capacity_run(excluded_payload)
    s1 = next(row for row in excluded["candidates"] if row["scenario_id"] == "S1_pv")
    assert excluded["recommended_pv_capacity_kwp"] == 1 and s1["admission_status"] == "excluded"


def test_v6_async_contract_schema():
    # The HTTP worker returns these exact fields at submit/poll boundaries;
    # keep this test independent from a long full-year calculation.
    accepted = {"status": "queued", "job_id": "abc123", "progress": 0.0}
    polled = {"job_id": "abc123", "status": "running", "progress": 0.5, "events": [], "result": None}
    assert set(("status", "job_id", "progress")) <= accepted.keys()
    assert set(("job_id", "status", "progress", "events", "result")) <= polled.keys()


def test_v6_http_options_thermal_and_async_contract():
    import operation_planning.app as app
    original_weather = app.load_weather
    original_hybrid = app._hybrid_capacity_run
    app.load_weather = lambda site, year: _weather_fixture()
    app._hybrid_capacity_run = lambda payload, progress=None: {"status": "success", "pv_capacity_sweep": [], "candidates": [], "recommended_pv_capacity_kwp": 0.0}
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/api/operation/options") as response:
            options = json.loads(response.read().decode("utf-8")); assert response.status == 200
        assert "equipment_models" in options and "tariffs" in options and "carbon_factors" in options
        body = {"max_units": 2, "room": {"equipment_id": "midea_msagbu12_mox201", "equipment_count": 1, "units_per_room": 1, "room_count": 1}}
        req = Request(base + "/api/operation/thermal/size", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urlopen(req) as response:
            thermal = json.loads(response.read().decode("utf-8")); assert response.status == 200
        assert len(thermal["candidates"]) == 2 and "minimum_adequate_units_per_room" in thermal
        req = Request(base + "/api/operation/hybrid/run", data=json.dumps({"room": {"equipment_id": "midea_msagbu12_mox201"}, "pv": {"requested_capacities_kwp": [0]}}).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urlopen(req) as response:
            hybrid = json.loads(response.read().decode("utf-8")); assert response.status == 200
        assert hybrid["status"] == "success" and "pv_capacity_sweep" in hybrid["report"]
        req = Request(base + "/api/operation/hybrid/jobs", data=json.dumps({"room": {"equipment_id": "midea_msagbu12_mox201"}, "pv": {"requested_capacities_kwp": [0]}}).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urlopen(req) as response:
            accepted = json.loads(response.read().decode("utf-8")); assert response.status == 202
        with urlopen(base + "/api/operation/hybrid/jobs/" + accepted["job_id"]) as response:
            polled = json.loads(response.read().decode("utf-8"))
        assert polled["status"] in {"queued", "running", "done"} and "progress" in polled
    finally:
        server.shutdown(); server.server_close()
        app.load_weather = original_weather; app._hybrid_capacity_run = original_hybrid


def real_short_http_probe() -> dict:
    """Exercise real thermal/PV/wind/matching/economic tools over three hours.

    No calculation function or weather loader is mocked.  Embedded weather
    is a short contractual fixture, explicitly not an annual replay case.
    The independent ephemeral port avoids the 18765 full-year service.
    """
    import operation_planning.app as app
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    records = []

    def request(method, path, payload=None):
        started = time.perf_counter()
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(base_url + path, data=data, headers={"Content-Type": "application/json"}, method=method)
        with urlopen(req, timeout=30) as response:
            status = response.status; output = json.loads(response.read().decode("utf-8"))
        records.append({"method": method, "path": path, "http_status": status,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                        "request": payload, "response": output})
        return output

    pv_quote = {"module_cny_per_kwp": 1800, "inverter_cny_per_kwp": 600,
                "structure_cny_per_kwp": 500, "installation_cny_per_kwp": 800,
                "grid_connection_cny": 0, "maintenance_cny_per_kwp_year": 30,
                "residual_fraction": 0.05}
    payload = {"site_id": "guangzhou", "year": 2024,
        "room": {"area_m2": 35, "equipment_id": "midea_msagbu12_mox201", "equipment_count": 2,
                 "units_per_room": 2, "room_count": 1},
        "weather": _weather_fixture(), "pv_weather": _weather_fixture(),
        "pv": {"roof_area_m2": 35, "usable_fraction": 0.8, "auto_capacity": True, "quote": pv_quote},
        "hybrid": {"wind": {"turbine_count": 0}, "study_years": 2,
                   "budget_cny": 90000, "pv_quote": pv_quote, "shared_connection_cny": 0},
        "storage": {"capacities_kwh": [0], "round_trip_efficiency": 0.90}}

    def wait_job(job_id):
        deadline = time.monotonic() + 30
        snapshots = []
        while time.monotonic() < deadline:
            snapshot = request("GET", "/api/operation/hybrid/jobs/" + job_id)
            snapshots.append(snapshot)
            if snapshot["status"] in {"done", "failed"}:
                return snapshot, snapshots
            time.sleep(0.02)
        raise AssertionError("short HTTP job timed out")

    try:
        options = request("GET", "/api/operation/options")
        verified = next(row for row in options["tariffs"]["tariffs"] if row["tariff_id"] == "guangzhou_industrial_lt1kv_202610")
        assert verified["provisional"] is False and verified["verified"] is True
        assert "guangzhou" in verified["site_ids"]
        assert options["carbon_price_scenarios"][0]["carbon_price_cny_per_t"] == 97.49

        thermal = request("POST", "/api/operation/thermal/size",
                          {"site_id": "guangzhou", "year": 2024, "room": payload["room"],
                           "weather": payload["weather"], "max_units": 2})
        assert len(thermal["candidates"]) == 2

        automatic = request("POST", "/api/operation/hybrid/run", payload)
        sweep = automatic["report"]["pv_capacity_sweep"]
        assert [row["requested_capacity_kwp"] for row in sweep] == [0.0, 1.4, 2.8, 5.6]
        for candidate in automatic["report"]["candidates"]:
            assert len(candidate["hourly"]["timestamps"]) == 3

        fixed = deepcopy(payload); fixed["pv"].pop("auto_capacity")
        fixed["pv"].update({"fixed_capacity_kwp": 1, "requested_capacities_kwp": [1], "quote": {}})
        fixed["hybrid"]["pv_quote"] = {}
        unknown = request("POST", "/api/operation/hybrid/run", fixed)
        s1 = next(row for row in unknown["report"]["candidates"] if row["scenario_id"] == "S1_pv")
        assert s1["pv_capacity_kwp"] == 1 and s1["admission_status"] == "unknown"
        excluded_input = deepcopy(fixed); excluded_input["pv"]["roof_area_m2"] = 1
        excluded = request("POST", "/api/operation/hybrid/run", excluded_input)
        s1 = next(row for row in excluded["report"]["candidates"] if row["scenario_id"] == "S1_pv")
        assert s1["pv_capacity_kwp"] == 1 and s1["admission_status"] == "excluded"

        accepted = request("POST", "/api/operation/hybrid/jobs", payload)
        done, done_snapshots = wait_job(accepted["job_id"])
        assert done["status"] == "done" and done["progress"] == 1
        assert done["result"]["status"] == "success"
        events = [event for event in done["events"] if event["type"] == "capacity_completed"]
        assert len(events) == 4 and [event["completed"] for event in events] == [1, 2, 3, 4]
        assert all(0 <= snapshot["progress"] <= 1 for snapshot in done_snapshots)
        assert [snapshot["progress"] for snapshot in done_snapshots] == sorted(snapshot["progress"] for snapshot in done_snapshots)

        failed_input = deepcopy(payload); failed_input["room"]["equipment_id"] = "unsupported_contract_model"
        failed_accepted = request("POST", "/api/operation/hybrid/jobs", failed_input)
        failed, _ = wait_job(failed_accepted["job_id"])
        assert failed["status"] == "failed" and "未支持的设备型号" in failed["error"]
        assert failed["field"] == "room.equipment_id" and failed["result"]["error"] == failed["error"]
        return {"status": "passed", "fixture_type": "3-hour contract fixture; not annual demonstration",
                "port_strategy": "independent ephemeral loopback port", "calculators_mocked": False,
                "assertions": ["options provisional", "real thermal size", "auto capacities 0/1.4/2.8/5.6 kWp",
                    "fixed 1kWp unknown", "fixed 1kWp excluded", "real async progress/done", "real async failed Chinese message"],
                "records": records}
    finally:
        server.shutdown(); server.server_close()


def test_v6_real_short_http_contract():
    assert real_short_http_probe()["status"] == "passed"
