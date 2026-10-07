"""Auditable single-room heat/moisture and DX response model.

This is a bounded lumped model for planning comparisons. It is not a calibrated
building simulation. Psychrometric state updates use PsychroLib; the equipment
catalogue supplies only rated points unless a user provides a curve.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
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
    # A bounded start-up pre-cooling window models the common practice of
    # starting the unit before occupancy.  It is deliberately explicit in
    # the room contract: the energy used during this window is retained in
    # the load, while service adequacy is scored only during occupancy.
    pre_cool_minutes: int = 60
    # Effective thermal capacitance per floor area.  100 kJ/(m²·K) is an
    # explicit lightweight-office reference assumption; it is not a measured
    # building value and remains user-overridable for a calibrated study.
    thermal_mass_kj_per_m2: float = 100.0
    equipment_id: str = "midea_msagbu12_mox201"
    # ``equipment_count`` is retained as the phase-one compatibility field.
    # New callers should use ``units_per_room`` and ``room_count`` explicitly.
    equipment_count: int | None = 1
    room_count: int = 1
    units_per_room: int | None = None
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


def _normalise_room_counts(room: RoomSpec) -> RoomSpec:
    """Resolve legacy equipment_count without multiplying room energy twice.

    The physical trace is always for one room.  ``units_per_room`` changes the
    capacity inside that trace; ``room_count`` is applied once by project_load
    for supply matching or lifecycle for cost aggregation.  Supplying both legacy and new fields with different values
    is rejected instead of silently guessing what ``equipment_count`` meant.
    """
    legacy = room.equipment_count
    units = room.units_per_room
    if units is None:
        units = 1 if legacy is None else int(legacy)
    elif legacy not in (None, 1, int(units)):
        raise ValueError("equipment_count 与 units_per_room 不一致；请只保留一个台数口径")
    room_count = int(room.room_count)
    units = int(units)
    if room_count < 1 or units < 1:
        raise ValueError("room_count 与 units_per_room 必须至少为1")
    if legacy is not None and int(legacy) < 1:
        raise ValueError("equipment_count 必须至少为1")
    return replace(room, equipment_count=units, units_per_room=units, room_count=room_count)


def simulate_room(weather: Dict[str, Any], room: RoomSpec | None = None) -> Dict[str, Any]:
    room = _normalise_room_counts(room or RoomSpec())
    if room.area_m2 <= 0 or room.height_m <= 0 or not 0 <= room.window_wall_ratio <= 1:
        raise ValueError("房间面积、高度和窗墙比必须有效")
    if not 0 <= room.start_hour < room.end_hour <= 24:
        raise ValueError("使用时段必须为合法小时")
    if not isinstance(room.pre_cool_minutes, int) or not 0 <= room.pre_cool_minutes <= 180:
        raise ValueError("pre_cool_minutes 必须是0到180之间的整数")
    if not math.isfinite(float(room.thermal_mass_kj_per_m2)) or not 50.0 <= float(room.thermal_mass_kj_per_m2) <= 2_000.0:
        raise ValueError("thermal_mass_kj_per_m2 必须在50到2000之间")
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
    capacitance = max(1_000_000.0, room.area_m2 * float(room.thermal_mass_kj_per_m2) * 1_000.0)
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
        values = [float(h[v][i]) for v in required]
        if any(not math.isfinite(value) for value in values):
            raise ValueError(f"天气变量在 {ts} 含 NaN 或非有限值；不得静默补零")
        if values[1] < 0 or values[1] > 100 or values[2] <= 0 or values[3] < 0:
            raise ValueError(f"天气变量在 {ts} 超出物理输入范围")
        tout, rhout, pressure_hpa, solar = values
        pressure = pressure_hpa * 100.0
        dt_seconds = float(intervals[i]); scheduled = _active(ts, room)
        # Pre-cooling is allowed before occupancy, but never carries people
        # or equipment gains.  The weather interval is still charged to the
        # electrical load, and any remaining startup shortfall is excluded
        # from the occupancy service score below.
        dt = datetime.fromisoformat(ts)
        pre_start = room.start_hour * 60 - int(room.pre_cool_minutes)
        minute_of_day = dt.hour * 60 + dt.minute
        precooling = (
            room.pre_cool_minutes > 0
            and not scheduled
            and pre_start <= minute_of_day < room.start_hour * 60
            and (not room.weekdays_only or dt.weekday() < 5)
        )
        operating = scheduled or precooling
        people = room.people_count if scheduled else 0
        # This first-stage model is cooling-only.  A scheduled winter hour is
        # retained in the trace, but it cannot be scored as an AC cooling
        # failure or given a fictitious cooling load.
        cooling_active = operating and tout >= 18.0 and temp >= room.cooling_setpoint_c
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
            # ``cooling_active`` also covers pre-cooling.  Only occupied
            # intervals are service checks; pre-cooling still contributes to
            # energy and state evolution but cannot be reported as an
            # occupancy shortfall.
            if scheduled:
                shortfall_hours += dt_seconds / 3600.0 if sensible_unmet > 1.0 or latent_unmet > 1.0 else 0.0
                totals["unmet_temp_degree_hours"] += max(0.0, temp - room.cooling_setpoint_c - 0.25) * dt_seconds / 3600.0
                totals["unmet_rh_percent_hours"] += max(0.0, indoor_rh - room.rh_setpoint_percent - 5.0) * dt_seconds / 3600.0
        totals["cooling_kwh"] += delivered * dt_seconds / 3_600_000.0
        totals["sensible_cooling_kwh"] += sensible_delivered * dt_seconds / 3_600_000.0
        totals["latent_cooling_kwh"] += latent_delivered * dt_seconds / 3_600_000.0
        totals["electric_kwh"] += power_w * dt_seconds / 3_600_000.0
        rows.append({"timestamp": ts, "interval_seconds": dt_seconds, "outdoor_temp_c": tout, "outdoor_rh_percent": rhout, "surface_pressure_hpa": pressure / 100.0, "solar_w_m2": solar, "active": scheduled, "pre_cooling": precooling, "cooling_active": cooling_active, "sensible_load_w": sensible_load, "latent_load_w": latent_generation_w, "latent_demand_w": latent_demand, "cooling_load_w": sensible_load + latent_demand, "capacity_w": capacity_w, "delivered_cooling_w": delivered, "delivered_sensible_w": sensible_delivered, "delivered_latent_w": latent_delivered, "sensible_unmet_w": sensible_unmet, "latent_unmet_w": latent_unmet, "electric_power_w": power_w, "indoor_temp_c": temp, "indoor_rh_percent": indoor_rh, "outdoor_enthalpy_kj_kg": enthalpy_kj_kg(tout, outdoor_w), "humidity_ratio_outdoor": outdoor_w, "humidity_ratio_indoor": w})
    active_hours = sum(x["interval_seconds"] for x in rows if x["active"]) / 3600.0
    cooling_hours = sum(x["interval_seconds"] for x in rows if x["cooling_active"] and x["active"]) / 3600.0
    pre_cooling_hours = sum(x["interval_seconds"] for x in rows if x.get("pre_cooling")) / 3600.0
    load_series = {"timestamps": [x["timestamp"] for x in rows], "interval_seconds": [int(x["interval_seconds"]) for x in rows], "electric_power_w": [x["electric_power_w"] for x in rows], "cooling_load_w": [x["cooling_load_w"] for x in rows], "latent_load_w": [x["latent_load_w"] for x in rows], "active": [bool(x["active"]) for x in rows], "cooling_active": [bool(x["cooling_active"]) for x in rows], "pre_cooling": [bool(x.get("pre_cooling")) for x in rows], "temperature_unmet_degree_hours": [max(0.0, x["indoor_temp_c"] - room.cooling_setpoint_c) * x["interval_seconds"] / 3600.0 if x["cooling_active"] and x["active"] else 0.0 for x in rows], "rh_unmet_percent_hours": [max(0.0, x["indoor_rh_percent"] - room.rh_setpoint_percent) * x["interval_seconds"] / 3600.0 if x["cooling_active"] and x["active"] else 0.0 for x in rows], "capacity_shortfall_w": [max(0.0, x["sensible_unmet_w"] + x["latent_unmet_w"]) if x["active"] and x["cooling_active"] else 0.0 for x in rows], "source": "single-room lumped heat-moisture model", "scope": "one-room; units_per_room included; room_count applied once by project_load / lifecycle", "equipment_count": int(room.equipment_count), "room_count": int(room.room_count), "units_per_room": int(room.units_per_room), "model_version": "thermal_model_phase1_v3_pre_cool_lightweight_mass", "assumptions": ["city-scale hourly reference weather", "cooling-only; no heating load", "bounded 60-minute pre-cooling before occupancy; energy included in load; service scored only in occupied intervals", "effective thermal mass 100 kJ/(m²·K) is an editable lightweight-office reference, not measured calibration", "rated-point temperature derate; no complete part-load map", "SHR defaults to editable reference when manufacturer value is absent"], "adequacy_rule": {"name": "occupied_hours_only_with_bounded_precooling", "pre_cool_minutes": int(room.pre_cool_minutes), "service_metrics_exclude_precooling": True, "thermal_mass_kj_per_m2": float(room.thermal_mass_kj_per_m2), "description": "允许营业前预冷；预冷电量计入负荷，但冷量不足和温湿度服务指标仅在使用时段判定。有效热容为轻质办公参考假设，可由用户覆盖。"}, "service_scope": "cooling_only", "weather_provenance": {"source_file": weather.get("source_file"), "boundary_file": weather.get("boundary_file"), "hash": weather.get("hash"), "normalization": weather.get("weather_normalization")}}
    totals.update({"capacity_shortfall_hours": shortfall_hours, "active_hours": active_hours, "cooling_season_hours": cooling_hours, "pre_cooling_hours": pre_cooling_hours})
    return {"room": asdict(room), "equipment": asdict(eq), "rows": rows, "load_series": load_series, "summary": {**totals, "source": "bounded single-room lumped model; reference consistency only, not measured-building validation", "shr_source": "manufacturer value when published; otherwise editable default reference assumption", "performance_source": "rated point with explicit temperature derate; no complete part-load map"}}
