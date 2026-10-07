"""Short, GPU-independent contracts for physical-only typical previews.

Fixtures are expressly not annual demonstration evidence.  The annual
preview/replay equivalence and timing are saved by the 5090 evidence runner.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import operation_planning.app as app
from operation_planning.hybrid import match_hybrid
from operation_planning.project_load import aggregate_project_load
from operation_planning.pv import generate_pv
from operation_planning.thermal_model import simulate_room
from operation_planning.wind import generate_wind, WindTurbineProfile
from dataclasses import asdict


def _fixture(start: datetime = datetime(2024, 7, 15), hours: int = 168):
    times = [(start + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(hours)]
    hourly = {"time": times,
        "temperature_2m": [30.0 + (i % 24) / 10 for i in range(hours)],
        "relative_humidity_2m": [70.0] * hours,
        "surface_pressure": [1010.0] * hours,
        "shortwave_radiation": [max(0.0, 400.0 - abs((i % 24) - 12) * 70) for i in range(hours)],
        "direct_normal_irradiance": [max(0.0, 350.0 - abs((i % 24) - 12) * 65) for i in range(hours)],
        "diffuse_radiation": [50.0 if 7 <= i % 24 <= 17 else 0.0 for i in range(hours)],
        "wind_speed_10m": [10.0] * hours, "wind_direction_10m": [180.0] * hours}
    return {"time": times, "hourly": hourly, "interval_seconds": [3600] * hours,
            "context": {"site": {"timezone": "Asia/Shanghai", "latitude": 23.1291, "longitude": 113.2644}},
            "hash": "short-preview-contract-fixture"}


def _payload(weather):
    return {"site_id": "guangzhou", "year": 2024,
        "room": {"area_m2": 35, "equipment_id": "midea_msagbu12_mox201", "equipment_count": 2,
                 "units_per_room": 2, "room_count": 3, "weekdays_only": False},
        "weather": weather, "pv_weather": weather,
        "preview": {"period": "typical_week", "month": 7},
        "pv": {"roof_area_m2": 35, "quote": {}},
        "hybrid": {"pv_capacity_kwp": 1, "wind": {"turbine_count": 0},
                   "budget_cny": 1, "allow_export": False}}


def test_preview_selection_rule():
    times = _fixture(datetime(2024, 1, 1), 8784)["time"]
    indices, window = app._preview_period_indices(times, "typical_week", "summer", 7)
    assert len(indices) == 168 and window["start"] == "2024-07-15T00:00"
    assert window["end_exclusive"] == "2024-07-22T00:00"
    month_indices, month = app._preview_period_indices(times, "typical_month", "winter", 2)
    assert len(month_indices) == 696 and month["start"] == "2024-02-01T00:00"
    assert month["end_exclusive"] == "2024-03-01T00:00"
    for bad in (0, 13):
        try:
            app._preview_period_indices(times, "month", "summer", bad)
        except ValueError as exc:
            assert "preview.month" in str(exc)
        else:
            raise AssertionError("invalid month was accepted")


def test_preview_is_physical_only_and_matches_same_rows():
    weather = _fixture()
    payload = _payload(weather)
    result = app._hybrid_preview(payload)
    room, _, _ = app._thermal_inputs(payload)
    load = aggregate_project_load(simulate_room(weather, room))
    pv_scenario, hybrid = app.hybrid_task_from_dict(payload, site_id="guangzhou", year=2024)
    pv = asdict(generate_pv(weather, hybrid.pv_capacity_kwp, pv_scenario))
    wind = generate_wind(weather, WindTurbineProfile.from_file(), hybrid.wind)
    expected = match_hybrid(load["load_series"], pv, wind, allow_export=False)
    s3 = next(row for row in result["candidates"] if row["scenario_id"] == "S3_pv_wind")
    assert s3["summary"] == expected["summary"]
    assert s3["intervals"] == expected["intervals"]
    assert result["economics"]["status"] == "not_calculated"
    assert all(row["economics"]["status"] == "not_calculated" for row in result["candidates"])
    assert all("import_cost_cny" not in row for row in s3["intervals"])
    assert "recommendation" not in result and "carbon" not in s3
    assert result["load_context"]["annual_extrapolation"] is False
    assert result["project_load_contract"]["room_count"] == 3
    changed = deepcopy(payload)
    changed["hybrid"].update({"import_price_cny_per_kwh": 999, "budget_cny": 1000000})
    assert app._hybrid_preview(changed)["candidates"] == result["candidates"]


def test_preview_http_and_chinese_error():
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        body = _payload(_fixture())
        req = Request(base + "/api/operation/hybrid/preview", data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())
            assert response.status == 200 and result["status"] == "success"
        body["preview"]["month"] = 13
        req = Request(base + "/api/operation/hybrid/preview", data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
        try:
            urlopen(req, timeout=30)
        except HTTPError as exc:
            result = json.loads(exc.read().decode())
            assert exc.code == 400 and "preview.month" in result["message"]
        else:
            raise AssertionError("invalid month returned success")
    finally:
        server.shutdown(); server.server_close()


if __name__ == "__main__":
    test_preview_selection_rule()
    test_preview_is_physical_only_and_matches_same_rows()
    test_preview_http_and_chinese_error()
    print("preview contracts: 3 passed")
