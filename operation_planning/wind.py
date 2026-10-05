"""Auditable small-wind adaptation for the phase-two hybrid calculator."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import hashlib, json, math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
import windpowerlib
from windpowerlib import power_output, wind_speed

WINDPOWERLIB_VERSION = getattr(windpowerlib, "__version__", "unknown")
PROFILE_PATH = Path(__file__).resolve().parent / "data" / "wind_profiles" / "sd6_swcc_11_04.json"

@dataclass
class WindTurbineProfile:
    profile_id: str
    manufacturer: str
    model: str
    source_url: str
    source_sha256: str
    tested_hub_height_m: float
    rotor_diameter_m: float
    reference_density_kg_m3: float
    rated_power_kw: float
    rated_wind_speed_m_s: float
    peak_power_kw: float
    peak_wind_speed_m_s: float
    power_curve: List[List[float]]
    curve_range_m_s: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path = PROFILE_PATH) -> "WindTurbineProfile":
        raw = json.loads(path.read_text(encoding="utf-8"))
        system = raw["system"]
        return cls(profile_id=raw["profile_id"], manufacturer=raw["manufacturer"], model=raw["model"], source_url=raw["source_url"], source_sha256=raw["source_sha256"], tested_hub_height_m=float(system["tested_hub_height_m"]), rotor_diameter_m=float(system["rotor_diameter_m"]), reference_density_kg_m3=float(system["reference_density_kg_m3"]), rated_power_kw=float(system["rated_power_kw"]), rated_wind_speed_m_s=float(system["rated_wind_speed_m_s"]), peak_power_kw=float(system["peak_power_kw"]), peak_wind_speed_m_s=float(system["peak_wind_speed_m_s"]), power_curve=raw["power_curve"], curve_range_m_s=raw["validity"]["curve_range_m_s"], metadata=raw)

    def curve_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.power_curve, sort_keys=True).encode()).hexdigest()

@dataclass
class WindScenario:
    site_id: str = "guangzhou"
    year: int = 2024
    turbine_count: int = 0
    hub_height_m: float = 9.0
    hub_height_max_m: Optional[float] = None
    source_height_m: float = 10.0
    hellman_exponent: float = 0.14
    availability: float = 1.0
    budget_cny: Optional[float] = None
    allow_export: bool = False
    export_limit_kw: Optional[float] = None

    def __post_init__(self) -> None:
        if self.turbine_count not in (0, 1): raise ValueError("首版只支持0或1台完整风机，不支持分数台数")
        if self.hub_height_m <= 0 or self.source_height_m <= 0: raise ValueError("风速高度必须为正")
        if self.hub_height_max_m is not None and (self.hub_height_max_m <= 0 or self.hub_height_m > self.hub_height_max_m): raise ValueError("轮毂高度超过用户给定上限")
        if not 0 <= self.hellman_exponent <= 1: raise ValueError("幂律指数必须在[0,1]")
        if not 0 < self.availability <= 1: raise ValueError("风机可用率必须在(0,1]")
        if self.budget_cny is not None and self.budget_cny < 0: raise ValueError("预算不能为负")

@dataclass
class WindQuote:
    turbine_cny: Optional[float] = None
    tower_cny: Optional[float] = None
    foundation_cny: Optional[float] = None
    installation_cny: Optional[float] = None
    grid_connection_cny: Optional[float] = None
    maintenance_cny_per_year: Optional[float] = None
    replacement_year: Optional[int] = None
    replacement_fraction: float = 0.0
    residual_fraction: float = 0.0
    source: str = "user scenario; not a verified procurement quote"

def profile_from_dict(raw: Optional[Dict[str, Any]]) -> WindTurbineProfile:
    # Only a known public profile is accepted; user-supplied curves need an explicit file adapter.
    return WindTurbineProfile.from_file()

def scenario_from_dict(raw: Optional[Dict[str, Any]], *, site_id: Optional[str] = None, year: Optional[int] = None) -> WindScenario:
    vals = {k: v for k, v in (raw or {}).items() if k in WindScenario.__dataclass_fields__}
    if site_id is not None: vals["site_id"] = site_id
    if year is not None: vals["year"] = year
    return WindScenario(**vals)

def _finite(values: Sequence[Any], name: str, n: int, *, nonnegative: bool = False) -> List[float]:
    if values is None or len(values) != n: raise ValueError(f"风电变量缺失或长度不一致：{name}")
    out=[]
    for x in values:
        try: y=float(x)
        except Exception as exc: raise ValueError(f"风电变量不是数值：{name}") from exc
        if not math.isfinite(y) or (nonnegative and y < 0): raise ValueError(f"风电变量含缺测或非有限值：{name}")
        out.append(y)
    return out

def _intervals(times: Sequence[str], provided: Optional[Sequence[int]]) -> List[int]:
    idx = pd.DatetimeIndex(times)
    if len(idx) < 2 or idx.has_duplicates or not idx.is_monotonic_increasing: raise ValueError("风电时间轴无效")
    actual = [int((idx[i+1]-idx[i]).total_seconds()) for i in range(len(idx)-1)]
    if any(x <= 0 or x > 3*3600 for x in actual): raise ValueError("风电时间间隔无效")
    expected = actual + [actual[-1]]
    if provided is not None and [int(x) for x in provided] != expected: raise ValueError("风电声明时间间隔与真实轴不一致")
    return expected

def generate_wind(weather: Dict[str, Any], profile: WindTurbineProfile, scenario: WindScenario) -> Dict[str, Any]:
    times=list(weather.get("time", [])); n=len(times)
    intervals=_intervals(times, weather.get("interval_seconds"))
    hourly=weather.get("hourly") or {}
    source_kmh=_finite(hourly.get("wind_speed_10m"), "wind_speed_10m", n, nonnegative=True)
    temp=_finite(hourly.get("temperature_2m"), "temperature_2m", n)
    pressure_hpa=_finite(hourly.get("surface_pressure"), "surface_pressure", n, nonnegative=True)
    source_ms=[x/3.6 for x in source_kmh]
    if scenario.turbine_count == 0:
        hub_ms=[0.0]*n; gross=[0.0]*n; out_range=[False]*n; neg_clip=0
    else:
        hub_ms=list(wind_speed.hellman(pd.Series(source_ms), scenario.source_height_m, scenario.hub_height_m, hellman_exponent=scenario.hellman_exponent))
        curve_x=[float(x[0]) for x in profile.power_curve]; curve_y=[float(x[1]) for x in profile.power_curve]
        gross=[]; out_range=[]; neg_clip=0
        for v in hub_ms:
            if v < curve_x[0] or v > curve_x[-1]: out_range.append(True); gross.append(0.0); continue
            out_range.append(False)
            y=float(power_output.power_curve(v, curve_x, curve_y, density_correction=False))
            if y < 0: neg_clip += 1; y=0.0
            gross.append(y)
    net=[max(0.0, float(x)*scenario.availability) for x in gross]
    density=[float(p)*100.0/(287.05*(float(t)+273.15)) for p,t in zip(pressure_hpa,temp)]
    power_kwh=[p*sec/3_600_000 for p,sec in zip(net,intervals)]
    metadata={"windpowerlib_version": WINDPOWERLIB_VERSION, "profile_id": profile.profile_id, "profile_curve_hash": profile.curve_hash(), "source_wind_height_m": scenario.source_height_m, "hub_height_m": scenario.hub_height_m, "hub_height_max_m": scenario.hub_height_max_m, "hellman_exponent": scenario.hellman_exponent, "source_wind_unit": "km/h converted to m/s", "wind_timestamp_semantics": "instantaneous at normalized interval start; no radiation midpoint shift", "reference_density_kg_m3": profile.reference_density_kg_m3, "air_density_kg_m3": density, "density_correction": "none; certified system curve used at reference density, density retained for audit only", "curve_range_m_s": profile.curve_range_m_s, "out_of_curve_range_count": sum(out_range), "out_of_curve_range_policy": "0 W conservative bounded scenario, not physical shutdown claim", "negative_curve_power_clipped_count": neg_clip, "measurement_point": profile.metadata["system"]["measurement_point"], "ac_output_includes_certified_interface_and_inverter": True, "interval_start": times, "interval_end": [str(pd.Timestamp(t)+pd.Timedelta(seconds=s)) for t,s in zip(times,intervals)]}
    return {"timestamps":times,"interval_seconds":intervals,"wind_speed_source_m_s":source_ms,"wind_speed_hub_m_s":[float(x) for x in hub_ms],"air_density_kg_m3":density,"wind_power_w":net,"wind_energy_kwh":power_kwh,"metadata":metadata,"source":weather.get("source_file", "weather_pv")}
