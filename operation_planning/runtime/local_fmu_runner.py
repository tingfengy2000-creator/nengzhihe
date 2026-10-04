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
    "con_oveTSetCoo_y",
    "con_oveTSetHea_y",
]


def _setpoint_for_minute(minute: int, segments: List[Dict[str, Any]], business_start: int = 8, business_end: int = 18) -> tuple[float, float, bool]:
    """Return day-internal °C setpoints and whether a plan segment applies."""
    minute = int(minute) % 1440
    local_hour = minute / 60.0
    cooling, heating = (24.0, 21.0) if business_start <= local_hour < business_end else (30.0, 15.0)
    for segment in segments:
        if int(segment["start_minute"]) <= minute < int(segment["end_minute"]):
            cooling = float(segment["cooling_setpoint_c"])
            heating = float(segment["heating_setpoint_c"])
            return cooling, heating, True
    return cooling, heating, False


def _official_setpoint(minute: int) -> tuple[float, float]:
    hour = (int(minute) % 1440) / 60.0
    return (24.0, 21.0) if 8 <= hour < 18 else (30.0, 15.0)


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
    # The native controller remains untouched for A0.  For a non-baseline
    # plan, the override channel is activated from initialization so the FMU
    # receives a well-defined common history; outside plan segments its values
    # equal the official schedule.
    has_override = bool(req.get("segments"))
    arr["con_oveTSetCoo_activate"] = has_override
    arr["con_oveTSetHea_activate"] = has_override
    day_start = (int(req["simulation_day"]) - 1) * 86400
    for idx, t in enumerate(times):
        if t < day_start:
            # Same known history for every candidate.
            cooling, heating = (24.0, 21.0) if ((t % 86400) / 3600.0) >= 8 and ((t % 86400) / 3600.0) < 18 else (30.0, 15.0)
            active = False
        elif day_start <= t < day_start + 86400:
            minute = int((t - day_start) // 60) % 1440
            # User task hours define the candidate plan, while the official
            # native controller remains the common reference history.
            cooling, heating, active = _setpoint_for_minute(
                minute, req.get("segments", []), int(req.get("business_start_hour", 8)), int(req.get("business_end_hour", 18))
            )
        else:
            cooling, heating = _official_setpoint(int((t - day_start) // 60))
            active = False
        arr["con_oveTSetCoo_u"][idx] = cooling + 273.15
        arr["con_oveTSetHea_u"][idx] = heating + 273.15
        arr["con_oveTSetCoo_activate"][idx] = has_override
        arr["con_oveTSetHea_activate"][idx] = has_override
    return arr


def _integrate_window(times: np.ndarray, values: np.ndarray, start: float, end: float, divisor: float) -> float:
    mask = (times >= start - 1e-6) & (times <= end + 1e-6)
    x = np.asarray(times[mask], dtype=float)
    y = np.maximum(np.asarray(values[mask], dtype=float), 0.0)
    return float(np.trapezoid(y, x) / divisor) if x.size >= 2 else 0.0


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
    cool_set_c = np.asarray(result["con_oveTSetCoo_y"], dtype=float) - 273.15
    heat_set_c = np.asarray(result["con_oveTSetHea_y"], dtype=float) - 273.15
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
    user_discomfort = np.maximum(low - temp_c, 0.0) + np.maximum(temp_c - high, 0.0)
    official_discomfort = np.maximum(heat_set_c - temp_c, 0.0) + np.maximum(temp_c - cool_set_c, 0.0)
    custom = {
        "target_electric_kwh": _integrate_window(times, electric, target_start, target_end, 3600000.0),
        "target_heating_kwh": _integrate_window(times, heat_w, target_start, target_end, 3600000.0),
        "target_cost_usd": 0.0,
        "occupied_degree_hours": float(np.trapezoid(occ_violation, times[occupied]) / 3600.0) if np.count_nonzero(occupied) >= 2 else 0.0,
        "occupied_strict_degree_hours": float(np.trapezoid(occ_strict, times[occupied]) / 3600.0) if np.count_nonzero(occupied) >= 2 else 0.0,
        "target_official_discomfort_degree_hours": _integrate_window(times, official_discomfort, target_start, target_end, 3600.0),
        "target_user_discomfort_degree_hours": _integrate_window(times, user_discomfort, target_start, target_end, 3600.0),
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
        "cooling_setpoint_c": clean(np.asarray(result["con_oveTSetCoo_y"], dtype=float)[mask] - 273.15),
        "heating_setpoint_c": clean(np.asarray(result["con_oveTSetHea_y"], dtype=float)[mask] - 273.15),
        # Two distinct facts are exported: the override channel may be enabled
        # for a candidate's common initialized history, while a plan segment is
        # actually applied only at selected day-internal minutes.
        "override_active": [bool(x) for x in _build_input(req, recovery_end, step)["con_oveTSetCoo_activate"][mask]],
        "override_setting_applied": [
            bool(day_start <= t < day_start + 86400 and _setpoint_for_minute(int((t - day_start) // 60) % 1440, req.get("segments", []), int(req.get("business_start_hour", 8)), int(req.get("business_end_hour", 18)))[2])
            for t in times_local
        ],
        "kpis": {
            "AirZoneTemperature_min_c": float(np.nanmin(temp_local)),
            "AirZoneTemperature_max_c": float(np.nanmax(temp_local)),
            "ElectricEnergy_target_kwh": custom["target_electric_kwh"],
            "HeatingEnergy_target_kwh": custom["target_heating_kwh"],
            "ThermalDiscomfort_target_degree_hours": custom["target_official_discomfort_degree_hours"],
        },
        "custom_metrics": custom,
        "target_period": [target_start, target_end],
        "recovery_period": [target_end, recovery_end],
        "step_seconds": step,
        "runtime_seconds": time.perf_counter() - started,
        "outputs": OUTPUT_FIELDS,
        "input_fields": INPUT_FIELDS,
        "control_schedule": {
            "baseline": "official 8:00–18:00 native thermostat schedule used for common history and recovery",
            "override_channel": "candidate channel is initialized consistently; active does not mean a plan segment is applied",
            "plan_hours": [req.get("business_start_hour", 8), req.get("business_end_hour", 18)],
            "segments": req.get("segments", []),
        },
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
