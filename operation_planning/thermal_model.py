"""Auditable single-room heat/moisture and DX response model.

This is a bounded lumped model for planning comparisons. It is not a calibrated
building simulation. Psychrometric state updates use PsychroLib; the equipment
catalogue supplies only rated points unless a user provides a curve.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime
import math
from typing import Any, Dict, List
from .equipment import get_equipment
from .psychrometrics import enthalpy_kj_kg, humidity_ratio, relative_humidity_percent

@dataclass
class RoomSpec:
    area_m2: float = 35.0
    height_m: float = 3.0
    orientation: str = "south"
    window_wall_ratio: float = 0.25
    insulation_u_w_m2k: float = 0.75
    people_count: int = 4
    equipment_gain_w: float = 300.0
    ventilation_lps_person: float = 7.0
    infiltration_ach: float = 0.35
    weekdays_only: bool = True
    start_hour: int = 8
    end_hour: int = 18
    indoor_temp_c: float = 26.0
    indoor_rh_percent: float = 60.0
    cooling_setpoint_c: float = 26.0
    rh_setpoint_percent: float = 60.0
    equipment_id: str = "midea_msagbu12_mox201"
    equipment_count: int = 1
    default_shr: float = 0.75


def _active(ts: str, room: RoomSpec) -> bool:
    dt = datetime.fromisoformat(ts)
    return (not room.weekdays_only or dt.weekday() < 5) and room.start_hour <= dt.hour < room.end_hour


def _orientation_factor(orientation: str) -> float:
    return {"south": 1.0, "west": 1.15, "east": 1.10, "north": 0.65}.get(orientation.lower(), 0.90)


def _seconds_between(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()


def _capacity_and_cop(eq: Any, outdoor_c: float, count: int) -> tuple[float, float]:
    # Rated-point adaptation only: kept explicit so a complete manufacturer
    # performance map can replace it without changing the result contract.
    derate = max(0.65, min(1.05, 1.0 - 0.012 * (outdoor_c - 35.0)))
    capacity = float(eq.rated_cooling_kw) * 1000.0 * count * derate
    cop = max(1.8, float(eq.cop) * (1.0 - 0.010 * max(0.0, outdoor_c - 35.0)))
    return capacity, cop


def simulate_room(weather: Dict[str, Any], room: RoomSpec | None = None) -> Dict[str, Any]:
    room = room or RoomSpec()
    if room.area_m2 <= 0 or room.height_m <= 0 or not 0 <= room.window_wall_ratio <= 1:
        raise ValueError("房间面积、高度和窗墙比必须有效")
    if not 0 <= room.start_hour < room.end_hour <= 24:
        raise ValueError("使用时段必须为合法小时")
    if not 0 < room.default_shr <= 1:
        raise ValueError("默认显热比必须在(0,1]")
    eq = get_equipment(room.equipment_id)
    times = weather.get("time", [])
    h = weather.get("hourly", {})
    required = ["temperature_2m", "relative_humidity_2m", "surface_pressure", "shortwave_radiation"]
    if len(times) < 2 or any(len(h.get(v, [])) != len(times) for v in required):
        raise ValueError("天气序列至少需要两个时刻，且温度/RH/气压/辐照长度一致")
    intervals: List[float] = []
    for i in range(len(times) - 1):
        dt = _seconds_between(times[i], times[i + 1])
        if dt <= 0 or dt > 3 * 3600:
            raise ValueError(f"天气时间轴存在无效或过长间隔：{times[i]} -> {times[i+1]}")
        intervals.append(dt)
    intervals.append(intervals[-1])
    rho = 1.2; cp = 1006.0; hfg = 2_450_000.0
    window_area = room.area_m2 * room.window_wall_ratio
    volume = room.area_m2 * room.height_m
    # Effective envelope conductance and thermal mass are building archetype
    # parameters.  They are intentionally conservative references, exposed
    # through the room assumptions rather than presented as a measured site.
    ua = max(20.0, room.area_m2 * (room.insulation_u_w_m2k + 0.45))
    capacitance = max(1_000_000.0, room.area_m2 * 1_200_000.0)
    dry_air_mass = max(1.0, rho * volume)
    pressure0 = float(h["surface_pressure"][0]) * 100.0
    temp = float(room.indoor_temp_c)
    w = humidity_ratio(temp, room.indoor_rh_percent, pressure0)
    target_w = humidity_ratio(room.cooling_setpoint_c, room.rh_setpoint_percent, pressure0)
    shr = float(eq.shr) if eq.shr is not None else float(room.default_shr)
    rows: List[Dict[str, Any]] = []
    totals = {"cooling_kwh": 0.0, "sensible_cooling_kwh": 0.0, "latent_cooling_kwh": 0.0, "electric_kwh": 0.0, "unmet_temp_degree_hours": 0.0, "unmet_rh_percent_hours": 0.0}
    shortfall_hours = 0.0
    for i, ts in enumerate(times):
        if any(h[v][i] is None for v in required):
            raise ValueError(f"天气变量在 {ts} 缺测；长缺口不得静默补零")
        tout = float(h["temperature_2m"][i]); rhout = float(h["relative_humidity_2m"][i]); pressure = float(h["surface_pressure"][i]) * 100.0; solar = max(0.0, float(h["shortwave_radiation"][i]))
        dt_seconds = float(intervals[i]); scheduled = _active(ts, room); people = room.people_count if scheduled else 0
        # This first-stage model is cooling-only.  A scheduled winter hour is
        # retained in the trace, but it cannot be scored as an AC cooling
        # failure or given a fictitious cooling load.
        cooling_active = scheduled and tout >= 18.0 and temp >= room.cooling_setpoint_c
        envelope = ua * (tout - temp)
        solar_gain = solar * window_area * 0.18 * _orientation_factor(room.orientation)
        internal_sensible = people * 75.0 + (room.equipment_gain_w if scheduled else 0.0)
        outdoor_w = humidity_ratio(tout, rhout, pressure)
        ventilation = people * room.ventilation_lps_person / 1000.0 + room.infiltration_ach * volume / 3600.0
        ventilation_sensible = rho * cp * ventilation * (tout - temp)
        uncontrolled_sensible = envelope + solar_gain + internal_sensible + ventilation_sensible
        pull_down = max(0.0, (temp - room.cooling_setpoint_c) * capacitance / dt_seconds) if cooling_active else 0.0
        sensible_load = max(0.0, uncontrolled_sensible) + pull_down if cooling_active else max(0.0, envelope + solar_gain)
        latent_generation_w = max(0.0, people * 55.0 + rho * ventilation * (outdoor_w - w) * hfg) if cooling_active else 0.0
        dehum_need_w = max(0.0, (w - target_w) * dry_air_mass * hfg / dt_seconds) if cooling_active else 0.0
        latent_demand = latent_generation_w + dehum_need_w
        capacity_w, cop = _capacity_and_cop(eq, tout, int(room.equipment_count)) if cooling_active else (0.0, float(eq.cop))
        max_sensible = capacity_w * shr
        max_latent = capacity_w * (1.0 - shr)
        sensible_delivered = min(sensible_load, max_sensible)
        latent_delivered = min(latent_demand, max_latent)
        delivered = sensible_delivered + latent_delivered
        power_w = delivered / cop if cooling_active and delivered > 0 else 0.0
        temp += (envelope + solar_gain + internal_sensible + ventilation_sensible - sensible_delivered) * dt_seconds / capacitance
        w += (latent_generation_w - latent_delivered) * dt_seconds / (dry_air_mass * hfg)
        w = max(0.0001, w)
        indoor_rh = max(0.0, min(120.0, relative_humidity_percent(temp, w, pressure)))
        sensible_unmet = max(0.0, sensible_load - sensible_delivered)
        latent_unmet = max(0.0, latent_demand - latent_delivered)
        if cooling_active:
            shortfall_hours += dt_seconds / 3600.0 if sensible_unmet > 1.0 or latent_unmet > 1.0 else 0.0
            totals["unmet_temp_degree_hours"] += max(0.0, temp - room.cooling_setpoint_c - 0.25) * dt_seconds / 3600.0
            totals["unmet_rh_percent_hours"] += max(0.0, indoor_rh - room.rh_setpoint_percent - 5.0) * dt_seconds / 3600.0
        totals["cooling_kwh"] += delivered * dt_seconds / 3_600_000.0
        totals["sensible_cooling_kwh"] += sensible_delivered * dt_seconds / 3_600_000.0
        totals["latent_cooling_kwh"] += latent_delivered * dt_seconds / 3_600_000.0
        totals["electric_kwh"] += power_w * dt_seconds / 3_600_000.0
        rows.append({"timestamp": ts, "interval_seconds": dt_seconds, "outdoor_temp_c": tout, "outdoor_rh_percent": rhout, "surface_pressure_hpa": pressure / 100.0, "solar_w_m2": solar, "active": scheduled, "cooling_active": cooling_active, "sensible_load_w": sensible_load, "latent_load_w": latent_generation_w, "latent_demand_w": latent_demand, "cooling_load_w": sensible_load + latent_demand, "capacity_w": capacity_w, "delivered_cooling_w": delivered, "delivered_sensible_w": sensible_delivered, "delivered_latent_w": latent_delivered, "sensible_unmet_w": sensible_unmet, "latent_unmet_w": latent_unmet, "electric_power_w": power_w, "indoor_temp_c": temp, "indoor_rh_percent": indoor_rh, "outdoor_enthalpy_kj_kg": enthalpy_kj_kg(tout, outdoor_w), "humidity_ratio_outdoor": outdoor_w, "humidity_ratio_indoor": w})
    active_hours = sum(x["interval_seconds"] for x in rows if x["active"]) / 3600.0
    cooling_hours = sum(x["interval_seconds"] for x in rows if x["cooling_active"]) / 3600.0
    load_series = {"timestamps": [x["timestamp"] for x in rows], "interval_seconds": [int(x["interval_seconds"]) for x in rows], "electric_power_w": [x["electric_power_w"] for x in rows], "cooling_load_w": [x["cooling_load_w"] for x in rows], "latent_load_w": [x["latent_load_w"] for x in rows], "source": "single-room lumped heat-moisture model", "scope": "one-room; equipment count included"}
    totals.update({"capacity_shortfall_hours": shortfall_hours, "active_hours": active_hours, "cooling_season_hours": cooling_hours})
    return {"room": asdict(room), "equipment": asdict(eq), "rows": rows, "load_series": load_series, "summary": {**totals, "source": "bounded single-room lumped model; reference consistency only, not measured-building validation", "shr_source": "manufacturer value when published; otherwise editable default reference assumption", "performance_source": "rated point with explicit temperature derate; no complete part-load map"}}
