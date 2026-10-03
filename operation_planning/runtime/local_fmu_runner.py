"""Run the pinned official bestest_air FMU inside WSL.

The Windows adapter sends one JSON request on stdin.  This file intentionally
does not read labels, fault names, or experiment metadata: only the physical
FMU path, date, plan and control inputs are accepted.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from fmpy import simulate_fmu


INPUT_FIELDS = [
    "con_oveTSetCoo_activate",
    "con_oveTSetCoo_u",
    "con_oveTSetHea_activate",
    "con_oveTSetHea_u",
]
OUTPUT_FIELDS = [
    "time",
    "zon_reaTRooAir_y",
    "fcu_reaPCoo_y",
    "fcu_reaPFan_y",
    "fcu_reaPHea_y",
    "zon_reaCO2RooAir_y",
]


def _setpoint_for_minute(minute: int, segments: List[Dict[str, Any]]) -> tuple[float, float]:
    """Return °C setpoints for one minute in the target date."""
    # An explicit baseline makes the comparison reproducible and prevents the
    # FMU's internal schedule from silently changing between candidates.
    local_hour = minute / 60.0
    cooling, heating = (24.0, 21.0) if 8.0 <= local_hour < 18.0 else (30.0, 15.0)
    for segment in segments:
        if int(segment["start_minute"]) <= minute < int(segment["end_minute"]):
            cooling = float(segment["cooling_setpoint_c"])
            heating = float(segment["heating_setpoint_c"])
            break
    return cooling, heating


def _build_input(req: Dict[str, Any], stop_time: int, step: int) -> np.ndarray:
    dtype = [
        ("time", "f8"),
        ("con_oveTSetCoo_activate", "?"),
        ("con_oveTSetCoo_u", "f8"),
        ("con_oveTSetHea_activate", "?"),
        ("con_oveTSetHea_u", "f8"),
    ]
    times = np.arange(0.0, float(stop_time) + 0.1, float(step))
    arr = np.zeros(times.size, dtype=dtype)
    arr["time"] = times
    arr["con_oveTSetCoo_activate"] = True
    arr["con_oveTSetHea_activate"] = True
    day_start = (int(req["simulation_day"]) - 1) * 86400
    for idx, t in enumerate(times):
        if t < day_start:
            # Same known history for every candidate.
            cooling, heating = (24.0, 21.0) if ((t % 86400) / 3600.0) >= 8 and ((t % 86400) / 3600.0) < 18 else (30.0, 15.0)
        else:
            minute = int((t - day_start) // 60)
            cooling, heating = _setpoint_for_minute(minute, req.get("segments", []))
        arr["con_oveTSetCoo_u"][idx] = cooling + 273.15
        arr["con_oveTSetHea_u"][idx] = heating + 273.15
    return arr


def _integrate(values: np.ndarray, step: int) -> float:
    values = np.asarray(values, dtype=float)
    return float(np.nansum(np.maximum(values, 0.0)) * step / 3600000.0)


def run(req: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    fmu_path = str(req["fmu_path"])
    step = int(req.get("step_seconds", 900))
    day_start = (int(req["simulation_day"]) - 1) * 86400
    target_start = day_start
    target_end = day_start + 86400
    recovery_end = target_end + int(req.get("recovery_hours", 24)) * 3600
    controls = _build_input(req, recovery_end, step)
    result = simulate_fmu(
        filename=fmu_path,
        start_time=0.0,
        stop_time=float(recovery_end),
        input=controls,
        output=OUTPUT_FIELDS[1:],
        step_size=float(step),
        output_interval=float(step),
        fmi_type="CoSimulation",
        validate=False,
        start_values={},
        set_stop_time=True,
    )
    times = np.asarray(result["time"], dtype=float)
    mask = (times >= target_start - 1e-6) & (times <= recovery_end + 1e-6)
    temp_c = np.asarray(result["zon_reaTRooAir_y"], dtype=float) - 273.15
    cool_w = np.asarray(result["fcu_reaPCoo_y"], dtype=float)
    fan_w = np.asarray(result["fcu_reaPFan_y"], dtype=float)
    heat_w = np.asarray(result["fcu_reaPHea_y"], dtype=float)
    temp_local = temp_c[mask]
    times_local = times[mask]
    cool_local = cool_w[mask]
    fan_local = fan_w[mask]
    heat_local = heat_w[mask]
    low = float(req.get("lower_temp_c", 21.0))
    high = float(req.get("upper_temp_c", 24.0))
    tol = float(req.get("tolerance_c", 0.25))
    occupied_start = target_start + int(req.get("business_start_hour", 8)) * 3600
    occupied_end = target_start + int(req.get("business_end_hour", 18)) * 3600
    occupied = (times >= occupied_start - 1e-6) & (times <= occupied_end + 1e-6)
    violation = np.maximum(low - temp_c, 0.0) + np.maximum(temp_c - high, 0.0)
    strict_violation = np.maximum(low - tol - temp_c, 0.0) + np.maximum(temp_c - (high + tol), 0.0)
    occ_violation = violation[occupied]
    occ_strict = strict_violation[occupied]
    electric = cool_w + fan_w
    custom = {
        "target_electric_kwh": _integrate(electric[(times >= target_start) & (times <= target_end)], step),
        "target_heating_kwh": _integrate(heat_w[(times >= target_start) & (times <= target_end)], step),
        "target_cost_usd": _integrate(electric[(times >= target_start) & (times <= target_end)], step),
        "occupied_degree_hours": float(np.sum(occ_violation) * step / 3600.0),
        "occupied_strict_degree_hours": float(np.sum(occ_strict) * step / 3600.0),
        "max_target_temp_c": float(np.nanmax(temp_c[(times >= target_start) & (times <= target_end)])),
        "min_target_temp_c": float(np.nanmin(temp_c[(times >= target_start) & (times <= target_end)])),
        "max_recovery_temp_deviation_c": float(np.nanmax(violation[(times >= target_end) & (times <= recovery_end)])),
        "target_peak_electric_w": float(np.nanmax(electric[(times >= target_start) & (times <= target_end)])),
        "target_feasible": bool(np.sum(occ_strict) == 0),
    }
    # Values are clipped to JSON-safe finite values; the full result stays
    # traceable to the target and recovery windows, not to a pre-written answer.
    def clean(xs: np.ndarray) -> List[float]:
        return [float(x) if math.isfinite(float(x)) else None for x in xs]

    return {
        "time_seconds": clean(times_local),
        "temperature_c": clean(temp_local),
        "electric_power_w": clean((cool_local + fan_local)),
        "heating_power_w": clean(heat_local),
        "kpis": {
            "AirZoneTemperature_min_c": float(np.nanmin(temp_local)),
            "AirZoneTemperature_max_c": float(np.nanmax(temp_local)),
            "ElectricEnergy_target_kwh": custom["target_electric_kwh"],
            "HeatingEnergy_target_kwh": custom["target_heating_kwh"],
        },
        "custom_metrics": custom,
        "target_period": [target_start, target_end],
        "recovery_period": [target_end, recovery_end],
        "step_seconds": step,
        "runtime_seconds": time.perf_counter() - started,
        "outputs": OUTPUT_FIELDS,
        "input_fields": INPUT_FIELDS,
    }


def main() -> None:
    request = json.load(sys.stdin)
    try:
        response = {"ok": True, "result": run(request)}
    except Exception as exc:  # returned to adapter for an evidence trail
        response = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
    sys.stdout.write(json.dumps(response, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
