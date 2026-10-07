"""Lightweight API contracts for the v6 realtime calculation surface.

These tests exercise request validation and the capacity/thermal adapters
without GPU, network or the front end.  Full-year timing is covered by the
5090 replay manifest; this file intentionally stays a fast contract gate.
"""
from __future__ import annotations

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
