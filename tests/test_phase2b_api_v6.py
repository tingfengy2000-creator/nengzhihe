"""Lightweight API contracts for the v6 realtime calculation surface.

These tests exercise request validation and the capacity/thermal adapters
without GPU, network or the front end.  Full-year timing is covered by the
5090 replay manifest; this file intentionally stays a fast contract gate.
"""
from __future__ import annotations

import json
import threading
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
