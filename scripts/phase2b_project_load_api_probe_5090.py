"""Short HTTP contract probe for the PV and Hybrid API project-load boundary.

The three-row input is intentionally a contract sample, not an annual-plan
demonstration.  The full-year evidence is produced by the companion replay.
"""
from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
import subprocess
import threading
import urllib.request

from operation_planning.app import Handler
from operation_planning.thermal_model import RoomSpec, simulate_room


def _post(server: ThreadingHTTPServer, path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    load_weather = {
        "time": ["2024-07-15T08:00", "2024-07-15T09:00", "2024-07-15T10:00"],
        "hourly": {
            "temperature_2m": [30.0, 30.0, 30.0],
            "relative_humidity_2m": [70.0, 70.0, 70.0],
            "surface_pressure": [1010.0, 1010.0, 1010.0],
            "shortwave_radiation": [300.0, 300.0, 300.0],
        },
    }
    pv_weather = {
        "time": list(load_weather["time"]),
        "hourly": {
            **load_weather["hourly"],
            "direct_normal_irradiance": [0.0, 0.0, 0.0],
            "diffuse_radiation": [0.0, 0.0, 0.0],
            "wind_speed_10m": [10.0, 10.0, 10.0],
        },
    }
    room = {"equipment_count": 2, "units_per_room": 2, "room_count": 3}
    base = {"room": room, "weather": load_weather, "pv_weather": pv_weather}
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        pv = _post(server, "/api/operation/pv/run", {**base, "pv": {"roof_area_m2": 50, "requested_capacities_kwp": [0], "quote": {}}})
        hybrid = _post(server, "/api/operation/hybrid/run", {**base, "pv": {"roof_area_m2": 50, "quote": {}}, "hybrid": {"pv_capacity_kwp": 0, "wind": {"turbine_count": 0}, "pv_quote": {}, "wind_quote": {}, "study_years": 1}})
    finally:
        server.shutdown()
        thread.join()

    one = simulate_room(load_weather, RoomSpec(equipment_count=2, units_per_room=2, room_count=1))
    expected = 3 * float(one["summary"]["electric_kwh"])
    pv_load = float(pv["report"]["load_context"]["electric_load_kwh"])
    hybrid_load = float(hybrid["report"]["load_context"]["electric_load_kwh"])
    pv_s0 = pv["report"]["candidates"][0]
    hybrid_s0 = next(x for x in hybrid["report"]["candidates"] if x["scenario_id"] == "S0_grid")
    for name, value in (("PV API load", pv_load), ("Hybrid API load", hybrid_load), ("PV API S0 import", float(pv_s0["grid_import_kwh"])), ("Hybrid API S0 import", float(hybrid_s0["grid_import_kwh"]))):
        if abs(value - expected) > 1e-9:
            raise AssertionError(f"{name} != expected project load: {value} != {expected}")
    result = {"status": "passed", "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "sample_type": "short API contract probe; not an annual-plan demonstration", "rows": 3, "expected_project_load_kwh": expected, "pv": {"status": pv["status"], "load_context_kwh": pv_load, "s0_grid_import_kwh": pv_s0["grid_import_kwh"], "scope": pv["report"]["load_context"]["project_load_context"]}, "hybrid": {"status": hybrid["status"], "load_context_kwh": hybrid_load, "s0_grid_import_kwh": hybrid_s0["grid_import_kwh"], "scope": hybrid["report"]["load_context"]["project_load_context"]}}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
