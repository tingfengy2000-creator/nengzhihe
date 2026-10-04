"""SI psychrometric helpers backed by the vendored PsychroLib 2.5.0.

The wrapper keeps the product contract small while making the source and unit
system explicit. PsychroLib is MIT licensed; see vendor/psychrolib.py and
protocol/first_stage_model.md for provenance.
"""
from __future__ import annotations
from .vendor import psychrolib
psychrolib.SetUnitSystem(psychrolib.SI)

def saturation_pressure_pa(t_c: float) -> float:
    return float(psychrolib.GetSatVapPres(float(t_c)))

def humidity_ratio(t_c: float, rh_percent: float, pressure_pa: float = 101325.0) -> float:
    rh = max(0.0, min(100.0, float(rh_percent))) / 100.0
    return float(psychrolib.GetHumRatioFromRelHum(float(t_c), rh, float(pressure_pa)))

def enthalpy_kj_kg(t_c: float, w: float) -> float:
    return float(psychrolib.GetMoistAirEnthalpy(float(t_c), float(w))) / 1000.0

def dew_point_c(t_c: float, rh_percent: float, pressure_pa: float = 101325.0) -> float:
    rh = max(1.0e-6, min(100.0, float(rh_percent))) / 100.0
    return float(psychrolib.GetTDewPointFromRelHum(float(t_c), rh, float(pressure_pa)))

def wet_bulb_c(t_c: float, rh_percent: float, pressure_pa: float = 101325.0) -> float:
    rh = max(1.0e-6, min(100.0, float(rh_percent))) / 100.0
    return float(psychrolib.GetTWetBulbFromRelHum(float(t_c), rh, float(pressure_pa)))


def relative_humidity_percent(t_c: float, w: float, pressure_pa: float = 101325.0) -> float:
    return float(psychrolib.GetRelHumFromHumRatio(float(t_c), float(w), float(pressure_pa))) * 100.0
