"""Auditable photovoltaic generation, load matching and lifecycle comparison.

Weather values from Open-Meteo are preceding-hour averages. They are attached
to explicit timestamp intervals; pvlib solar position is evaluated at each
interval midpoint and no annual energy offset is used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
import pvlib
from pvlib import irradiance, inverter, pvsystem, temperature
from .economics import discounted_cashflow_npv, discounted_year_end, inverter_replacement_cost
from .project_load import require_project_load, project_load_context
from .carbon import candidate_carbon, context as carbon_context

PVLIB_VERSION = getattr(pvlib, "__version__", "unknown")
MODULE_AREA_M2_PER_KWP = 5.0
DEFAULT_ALBEDO = 0.20
DEFAULT_SYSTEM_LOSS = 0.14
DEFAULT_AVAILABILITY = 0.99
DEFAULT_GAMMA_PDC = -0.0035
DEFAULT_INVERTER_EFFICIENCY = 0.96
DEFAULT_KWP_PER_M2 = 1.0 / MODULE_AREA_M2_PER_KWP


@dataclass
class PVQuote:
    module_cny_per_kwp: Optional[float] = None
    inverter_cny_per_kwp: Optional[float] = None
    structure_cny_per_kwp: Optional[float] = None
    installation_cny_per_kwp: Optional[float] = None
    grid_connection_cny: Optional[float] = None
    maintenance_cny_per_kwp_year: Optional[float] = None
    inverter_replacement_year: Optional[int] = None
    inverter_replacement_fraction: float = 0.0
    residual_fraction: float = 0.0
    source: str = "user scenario; not a verified procurement quote"


@dataclass
class PVScenario:
    site_id: str = "guangzhou"
    year: int = 2024
    roof_area_m2: float = 50.0
    usable_fraction: float = 0.80
    tilt_deg: float = 23.0
    azimuth_open_meteo_deg: float = 0.0  # 0 south, -90 east, 90 west.
    shading_loss_fraction: float = 0.0
    system_loss_fraction: float = DEFAULT_SYSTEM_LOSS
    availability: float = DEFAULT_AVAILABILITY
    inverter_ratio: float = 0.85  # AC inverter rating / DC array kWp.
    budget_cny: Optional[float] = None
    allow_export: bool = False
    export_limit_kw: Optional[float] = None
    import_price_cny_per_kwh: float = 0.66
    export_price_cny_per_kwh: Optional[float] = None
    tariff_id: str = "user_constant"
    custom_tariff: Optional[Dict[str, Any]] = None
    study_years: int = 10
    discount_rate: float = 0.0
    annual_degradation: float = 0.005
    quote: PVQuote = field(default_factory=PVQuote)
    candidate_step_kwp: float = 1.0
    requested_capacities_kwp: Optional[List[float]] = None

    def __post_init__(self) -> None:
        if self.roof_area_m2 <= 0 or not 0 < self.usable_fraction <= 1:
            raise ValueError("可安装屋顶面积与可用比例必须为正，且比例不超过1")
        if not 0 <= self.tilt_deg <= 90:
            raise ValueError("倾角必须在0至90度")
        if not 0 <= self.shading_loss_fraction < 1 or not 0 <= self.system_loss_fraction < 1:
            raise ValueError("遮挡或系统损失率无效")
        if not 0 < self.availability <= 1 or not 0 < self.inverter_ratio <= 2:
            raise ValueError("可用率或逆变器直流配比无效")
        if self.study_years < 1 or self.candidate_step_kwp <= 0:
            raise ValueError("研究年限与容量步长必须有效")
        if self.budget_cny is not None and self.budget_cny < 0:
            raise ValueError("预算不能为负")
        if self.export_limit_kw is not None and self.export_limit_kw < 0:
            raise ValueError("外送功率上限不能为负")
        for name, value in (("import_price_cny_per_kwh", self.import_price_cny_per_kwh), ("export_price_cny_per_kwh", self.export_price_cny_per_kwh)):
            if value is not None and (not math.isfinite(float(value)) or float(value) < 0):
                raise ValueError(f"{name}必须是非负有限数")
        if not 0 <= self.discount_rate < 1:
            raise ValueError("折现率必须在[0,1)内")
        if not 0 <= self.annual_degradation < 1:
            raise ValueError("年衰减率必须在[0,1)内")
        if not 0 <= self.quote.residual_fraction <= 1:
            raise ValueError("残值比例必须在[0,1]内")


@dataclass
class GenerationSeries:
    timestamps: List[str]
    interval_seconds: List[int]
    pv_dc_power_w: List[float]
    pv_ac_power_w: List[float]
    ghi_w_m2: List[float]
    dni_w_m2: List[float]
    dhi_w_m2: List[float]
    poa_w_m2: List[float]
    cell_temp_c: List[float]
    source: str
    model: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def quote_from_dict(raw: Optional[Dict[str, Any]]) -> PVQuote:
    raw = raw or {}
    return PVQuote(**{k: v for k, v in raw.items() if k in PVQuote.__dataclass_fields__})


def scenario_from_dict(raw: Optional[Dict[str, Any]], *, site_id: Optional[str] = None, year: Optional[int] = None) -> PVScenario:
    values = {k: v for k, v in (raw or {}).items() if k in PVScenario.__dataclass_fields__ and k != "quote"}
    if site_id is not None:
        values["site_id"] = site_id
    if year is not None:
        values["year"] = year
    values["quote"] = quote_from_dict((raw or {}).get("quote"))
    return PVScenario(**values)


def _open_meteo_azimuth_to_pvlib(value: float) -> float:
    """Open-Meteo 0=south/-90=east/+90=west -> pvlib 180/90/270."""
    return (180.0 + float(value)) % 360.0


def _time_index(times: Sequence[str]) -> pd.DatetimeIndex:
    if not times:
        raise ValueError("时间序列为空")
    try:
        idx = pd.DatetimeIndex(times)
    except Exception as exc:
        raise ValueError(f"时间戳无法解析：{exc}") from exc
    if idx.isna().any() or idx.has_duplicates:
        raise ValueError("时间轴含无效或重复时间戳")
    return idx


def _times_index(times: Sequence[str], timezone: str) -> pd.DatetimeIndex:
    idx = _time_index(times)
    return idx.tz_localize(timezone) if idx.tz is None else idx.tz_convert(timezone)


def _intervals(times: Sequence[str], provided: Optional[Sequence[int]] = None) -> List[int]:
    """Check actual intervals; values describe [timestamp,timestamp+dt)."""
    idx = _time_index(times)
    if len(idx) < 2:
        raise ValueError("PV时间序列至少需要两个时刻")
    actual = [int((idx[i + 1] - idx[i]).total_seconds()) for i in range(len(idx) - 1)]
    if any(x <= 0 or x > 3 * 3600 for x in actual):
        raise ValueError("PV时间轴存在重复、倒序或超过3小时的间隔")
    expected = actual + [actual[-1]]
    if provided is not None:
        try:
            values = [int(x) for x in provided]
        except Exception as exc:
            raise ValueError("PV时间间隔必须是整数秒") from exc
        if len(values) != len(times) or any(x <= 0 for x in values) or values != expected:
            raise ValueError("声明的时间间隔与真实时间轴不一致")
        return values
    return expected


def _representative_index(times: Sequence[str], intervals: Sequence[int], timezone: str) -> pd.DatetimeIndex:
    starts = _times_index(times, timezone)
    return starts + pd.to_timedelta([int(x) / 2 for x in intervals], unit="s")


def _finite_values(values: Sequence[Any], name: str, n: int, *, nonnegative: bool = False) -> List[float]:
    if values is None or len(values) != n:
        raise ValueError(f"光伏变量缺失或长度不一致：{name}")
    out: List[float] = []
    for value in values:
        if isinstance(value, bool):
            raise ValueError(f"光伏变量不是数值：{name}")
        try:
            number = float(value)
        except Exception as exc:
            raise ValueError(f"光伏变量不是数值：{name}") from exc
        if not math.isfinite(number) or (nonnegative and number < 0):
            raise ValueError(f"光伏变量含缺测、非有限或负值：{name}")
        out.append(number)
    return out


def _as_float(values: Sequence[Any], name: str, n: int) -> List[float]:
    return _finite_values(values, name, n, nonnegative=True)


def generate_pv(weather: Dict[str, Any], capacity_kwp: float, scenario: PVScenario) -> GenerationSeries:
    if not math.isfinite(float(capacity_kwp)) or capacity_kwp < 0:
        raise ValueError("装机容量必须是非负有限数")
    times = list(weather.get("time", [])); hourly = weather.get("hourly", {}) or {}; n = len(times)
    if n < 2:
        raise ValueError("光伏天气序列太短")
    intervals = _intervals(times, weather.get("interval_seconds"))
    context = weather.get("context") or {}; site = context.get("site") or {}
    timezone = str(site.get("timezone", context.get("timezone", "Asia/Shanghai")))
    lat = float(site.get("latitude", weather.get("latitude", 0.0))); lon = float(site.get("longitude", weather.get("longitude", 0.0)))
    ghi = _as_float(hourly.get("shortwave_radiation", []), "shortwave_radiation/GHI", n)
    dni = _as_float(hourly.get("direct_normal_irradiance", []), "direct_normal_irradiance/DNI", n)
    dhi = _as_float(hourly.get("diffuse_radiation", []), "diffuse_radiation/DHI", n)
    temp_air = _finite_values(hourly.get("temperature_2m", []), "temperature_2m", n)
    wind_kmh = _finite_values(hourly.get("wind_speed_10m", []), "wind_speed_10m", n, nonnegative=True)
    start_idx = _times_index(times, timezone); rep_idx = _representative_index(times, intervals, timezone)
    loc = pvlib.location.Location(lat, lon, tz=timezone); solar = loc.get_solarposition(rep_idx)
    pvlib_azimuth = _open_meteo_azimuth_to_pvlib(scenario.azimuth_open_meteo_deg)
    poa = irradiance.get_total_irradiance(surface_tilt=float(scenario.tilt_deg), surface_azimuth=pvlib_azimuth, solar_zenith=solar["zenith"], solar_azimuth=solar["azimuth"], dni=pd.Series(dni, index=rep_idx), ghi=pd.Series(ghi, index=rep_idx), dhi=pd.Series(dhi, index=rep_idx), albedo=DEFAULT_ALBEDO)
    poa_global = pd.Series(poa["poa_global"], index=rep_idx)
    if not all(math.isfinite(float(x)) and float(x) >= 0 for x in poa_global.tolist()):
        raise ValueError("光伏转置结果含缺测或负值")
    temp_cell = temperature.sapm_cell(poa_global=poa_global, temp_air=pd.Series(temp_air, index=rep_idx), wind_speed=pd.Series(wind_kmh, index=rep_idx) / 3.6, a=-3.56, b=-0.0750, deltaT=3.0)
    if capacity_kwp == 0:
        dc = pd.Series(0.0, index=rep_idx); ac = pd.Series(0.0, index=rep_idx)
    else:
        pdc0_w = float(capacity_kwp) * 1000.0; inverter_ac_rated_w = float(capacity_kwp) * float(scenario.inverter_ratio) * 1000.0
        dc = pvsystem.pvwatts_dc(poa_global, temp_cell, pdc0=pdc0_w, gamma_pdc=DEFAULT_GAMMA_PDC)
        # pvlib's PVWatts inverter expects pdc0 at the DC input corresponding
        # to the AC rating: Pac0 = pdc0 * eta_inv_nom.  Passing Pac0 here
        # would clip at Pac0*eta_inv_nom and under-rate the inverter.
        inverter_pdc0_w = inverter_ac_rated_w / DEFAULT_INVERTER_EFFICIENCY
        clipped_ac = inverter.pvwatts(dc, pdc0=inverter_pdc0_w, eta_inv_nom=DEFAULT_INVERTER_EFFICIENCY, eta_inv_ref=0.9637)
        ac = clipped_ac * (1.0 - float(scenario.shading_loss_fraction)) * (1.0 - float(scenario.system_loss_fraction)) * float(scenario.availability)
    if capacity_kwp == 0:
        pdc0_w = 0.0; inverter_ac_rated_w = 0.0; inverter_pdc0_w = 0.0; clipped_ac = pd.Series(0.0, index=rep_idx)
    for label, series in (("pv_dc_power_w", dc), ("pv_ac_power_w", ac), ("cell_temp_c", temp_cell)):
        if not all(math.isfinite(float(x)) for x in series.tolist()):
            raise ValueError(f"光伏计算结果含非有限值：{label}")
    metadata = {"pvlib_version": PVLIB_VERSION, "solar_position": "pvlib Location.get_solarposition at interval midpoint", "transposition": "pvlib irradiance.get_total_irradiance; isotropic diffuse with albedo 0.20", "temperature_model": "pvlib SAPM cell temperature, explicit -3.56/-0.075/3.0 and 10m wind converted km/h→m/s", "dc_model": "pvlib PVWatts DC, pdc0=capacity_kWp*1000 and gamma_pdc=-0.0035/C", "inverter_model": "pvlib PVWatts inverter; pdc0=pac0/eta_inv_nom", "azimuth_input_convention": "Open-Meteo 0 south/-90 east/90 west; converted to pvlib 0 north/90 east/180 south/270 west", "radiation_semantics": "GHI/DNI/DHI are normalized preceding-hour means attached to [interval_start,interval_end); solar position uses the interval midpoint", "interval_start_first": times[0], "interval_end_last": str(start_idx[-1] + pd.to_timedelta(intervals[-1], unit="s")), "representative_time_first": str(rep_idx[0]), "representative_time_last": str(rep_idx[-1]), "interval_seconds_first": intervals[0], "interval_seconds_last": intervals[-1], "loss_application": "shading, system loss and availability applied once after inverter clipping", "capacity_kwp": float(capacity_kwp), "module_dc_rated_w": float(pdc0_w), "inverter_ratio_ac_to_dc": float(scenario.inverter_ratio), "inverter_ac_rated_w": float(inverter_ac_rated_w), "inverter_pdc0_w": float(inverter_pdc0_w), "inverter_eta_inv_nom": DEFAULT_INVERTER_EFFICIENCY, "inverter_output_before_losses_max_w": float(max(clipped_ac.tolist())) if len(clipped_ac) else 0.0, "inverter_output_after_losses_max_w": float(max(ac.tolist())) if len(ac) else 0.0}
    return GenerationSeries(timestamps=times, interval_seconds=intervals, pv_dc_power_w=[round(float(v), 8) for v in dc.tolist()], pv_ac_power_w=[round(float(v), 8) for v in ac.tolist()], ghi_w_m2=ghi, dni_w_m2=dni, dhi_w_m2=dhi, poa_w_m2=[round(float(v), 8) for v in poa_global.tolist()], cell_temp_c=[round(float(v), 8) for v in temp_cell.tolist()], source=str(weather.get("source_file", "weather")), model="pvlib.PVWatts", metadata=metadata)


def _energy(power_w: float, seconds: int) -> float:
    value = float(power_w)
    if not math.isfinite(value) or value < 0 or int(seconds) <= 0:
        raise ValueError("功率或时间间隔含缺测、非有限或负值")
    return value * float(seconds) / 3_600_000.0


def _validate_prices(values: Optional[Sequence[float]], n: int, name: str) -> Optional[List[float]]:
    return None if values is None else _finite_values(values, name, n, nonnegative=True)


def match_load(load_series: Dict[str, Any], generation: GenerationSeries, *, allow_export: bool = False, export_limit_kw: Optional[float] = None, import_prices: Optional[Sequence[float]] = None, export_prices: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    lt = list(load_series.get("timestamps", [])); gt = generation.timestamps
    if lt != gt:
        raise ValueError("负荷与光伏时间戳不一致，拒绝跨时段或年度错配")
    li = _intervals(lt, load_series.get("interval_seconds")); gi = _intervals(gt, generation.interval_seconds)
    if li != gi:
        raise ValueError("负荷与光伏时间间隔不一致")
    lp = load_series.get("electric_power_w", []); gp = generation.pv_ac_power_w
    if len(lp) != len(gp):
        raise ValueError("负荷与光伏序列长度不一致")
    imp_prices = _validate_prices(import_prices, len(lp), "购电价格"); exp_prices = _validate_prices(export_prices, len(lp), "外送价格")
    load_kwh: List[float] = []; pv_kwh: List[float] = []; self_use: List[float] = []; imports: List[float] = []; exports: List[float] = []; curtail: List[float] = []; import_cost: List[float] = []; export_income: List[float] = []
    for i, (load_w, pv_w, sec) in enumerate(zip(lp, gp, li)):
        l = _energy(load_w, sec); p = _energy(pv_w, sec); s = min(l, p); surplus = max(0.0, p - s)
        limit = surplus if allow_export and export_limit_kw is None else (min(surplus, float(export_limit_kw) * sec / 3600.0) if allow_export else 0.0)
        imp = l - s; cur = surplus - limit
        load_kwh.append(l); pv_kwh.append(p); self_use.append(s); imports.append(imp); exports.append(limit); curtail.append(cur)
        if imp_prices is not None: import_cost.append(imp * imp_prices[i])
        if exp_prices is not None: export_income.append(limit * exp_prices[i])
    sums = {"load_kwh": sum(load_kwh), "pv_generation_kwh": sum(pv_kwh), "self_use_kwh": sum(self_use), "grid_import_kwh": sum(imports), "grid_export_kwh": sum(exports), "curtailment_kwh": sum(curtail)}
    if imp_prices is not None: sums["import_cost_cny"] = sum(import_cost)
    if exp_prices is not None: sums["export_income_cny"] = sum(export_income)
    if abs(sums["load_kwh"] - sums["self_use_kwh"] - sums["grid_import_kwh"]) > 1e-7: raise AssertionError("逐时负荷守恒失败")
    if abs(sums["pv_generation_kwh"] - sums["self_use_kwh"] - sums["grid_export_kwh"] - sums["curtailment_kwh"]) > 1e-7: raise AssertionError("逐时光伏守恒失败")
    sums["self_consumption_rate"] = sums["self_use_kwh"] / sums["pv_generation_kwh"] if sums["pv_generation_kwh"] > 1e-12 else None
    sums["load_coverage_rate"] = sums["self_use_kwh"] / sums["load_kwh"] if sums["load_kwh"] > 1e-12 else None
    monthly: Dict[str, Dict[str, float]] = {}
    for ts, l, p, s, imp, exp, cur in zip(lt, load_kwh, pv_kwh, self_use, imports, exports, curtail):
        month = str(ts)[:7]; m = monthly.setdefault(month, {"load_kwh": 0.0, "pv_generation_kwh": 0.0, "self_use_kwh": 0.0, "grid_import_kwh": 0.0, "grid_export_kwh": 0.0, "curtailment_kwh": 0.0})
        for key, value in (("load_kwh", l), ("pv_generation_kwh", p), ("self_use_kwh", s), ("grid_import_kwh", imp), ("grid_export_kwh", exp), ("curtailment_kwh", cur)): m[key] += value
    return {"summary": sums, "monthly": monthly, "interval_kwh": {"load": load_kwh, "pv_generation": pv_kwh, "self_use": self_use, "grid_import": imports, "grid_export": exports, "curtailment": curtail}, "interval_cost_cny": {"import": import_cost, "export": export_income}, "export_policy": {"allow_export": bool(allow_export), "limit_kw": export_limit_kw}}


def _quote_capex(capacity_kwp: float, quote: PVQuote) -> Optional[float]:
    if capacity_kwp <= 1e-12: return 0.0
    fields = (quote.module_cny_per_kwp, quote.inverter_cny_per_kwp, quote.structure_cny_per_kwp, quote.installation_cny_per_kwp, quote.grid_connection_cny)
    if any(x is None for x in fields): return None
    return capacity_kwp * sum(float(x) for x in fields[:4]) + float(fields[4])


def _scaled_generation(generation: GenerationSeries, factor: float) -> GenerationSeries:
    return GenerationSeries(timestamps=list(generation.timestamps), interval_seconds=list(generation.interval_seconds), pv_dc_power_w=list(generation.pv_dc_power_w), pv_ac_power_w=[float(x) * factor for x in generation.pv_ac_power_w], ghi_w_m2=list(generation.ghi_w_m2), dni_w_m2=list(generation.dni_w_m2), dhi_w_m2=list(generation.dhi_w_m2), poa_w_m2=list(generation.poa_w_m2), cell_temp_c=list(generation.cell_temp_c), source=generation.source, model=generation.model, metadata={**generation.metadata, "annual_degradation_factor": factor})


def _match_cost(match: Dict[str, Any], kind: str, price: Optional[float]) -> Optional[float]:
    summary = match.get("summary", {}); key = "import_cost_cny" if kind == "import" else "export_income_cny"
    if key in summary: return float(summary[key])
    if kind == "import" and price is not None: return float(summary.get("grid_import_kwh", 0.0)) * float(price)
    if kind == "export" and price is not None: return float(summary.get("grid_export_kwh", 0.0)) * float(price)
    return None


def lifecycle_compare(match: Dict[str, Any], baseline_match: Dict[str, Any], capacity_kwp: float, scenario: PVScenario, *, load_series: Optional[Dict[str, Any]] = None, generation: Optional[GenerationSeries] = None, import_prices: Optional[Sequence[float]] = None, export_prices: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    """Recompute yearly matching with a fixed load and degraded PV generation."""
    capacity_kwp = float(capacity_kwp); quote = scenario.quote; capex = _quote_capex(capacity_kwp, quote); missing: List[str] = []
    if capacity_kwp > 1e-12:
        for name, value in (("module_cny_per_kwp", quote.module_cny_per_kwp), ("inverter_cny_per_kwp", quote.inverter_cny_per_kwp), ("structure_cny_per_kwp", quote.structure_cny_per_kwp), ("installation_cny_per_kwp", quote.installation_cny_per_kwp), ("grid_connection_cny", quote.grid_connection_cny), ("maintenance_cny_per_kwp_year", quote.maintenance_cny_per_kwp_year)):
            if value is None: missing.append(name)
        if scenario.allow_export and scenario.export_price_cny_per_kwh is None: missing.append("export_price_cny_per_kwh")
    baseline_import_cost = _match_cost(baseline_match, "import", scenario.import_price_cny_per_kwh)
    if baseline_import_cost is None: raise ValueError("缺少基准购电价格，不能计算生命周期成本")
    yearly: List[Dict[str, Any]] = []; cumulative: Optional[float] = 0.0; npv: Optional[float] = None if capex is None else -float(capex)
    for year in range(0, scenario.study_years + 1):
        if year == 0:
            row: Dict[str, Any] = {"year": 0, "grid_import_kwh": 0.0, "pv_generation_kwh": 0.0, "self_use_kwh": 0.0, "grid_export_kwh": 0.0, "curtailment_kwh": 0.0, "electricity_cost_cny": 0.0, "maintenance_cny": 0.0, "replacement_cny": 0.0, "export_income_cny": 0.0, "residual_cny": 0.0, "capex_cny": capex, "net_cash_flow_cny": -capex if capex is not None else None}
        else:
            if capacity_kwp <= 1e-12: annual_match = baseline_match
            elif load_series is not None and generation is not None:
                factor = (1.0 - float(scenario.annual_degradation)) ** (year - 1); annual_match = match_load(load_series, _scaled_generation(generation, factor), allow_export=scenario.allow_export, export_limit_kw=scenario.export_limit_kw, import_prices=import_prices, export_prices=export_prices)
            else: raise ValueError("生命周期逐年重算需要原始负荷与光伏序列")
            summary = annual_match["summary"]; electricity_cost = _match_cost(annual_match, "import", scenario.import_price_cny_per_kwh); export_income = _match_cost(annual_match, "export", scenario.export_price_cny_per_kwh) if scenario.allow_export else 0.0
            maintenance = float(quote.maintenance_cny_per_kwp_year or 0.0) * capacity_kwp if capacity_kwp > 1e-12 else 0.0; replacement = 0.0
            if capacity_kwp > 1e-12 and quote.inverter_replacement_year and year == int(quote.inverter_replacement_year): replacement = inverter_replacement_cost(capacity_kwp, quote.inverter_cny_per_kwp, quote.inverter_replacement_fraction)
            residual = float(capex or 0.0) * float(quote.residual_fraction) if capacity_kwp > 1e-12 and year == scenario.study_years else 0.0
            known_cash = None if electricity_cost is None or export_income is None or (capex is None and capacity_kwp > 1e-12) else -(electricity_cost + maintenance + replacement) + export_income + residual
            row = {"year": year, "grid_import_kwh": summary["grid_import_kwh"], "pv_generation_kwh": summary["pv_generation_kwh"], "self_use_kwh": summary["self_use_kwh"], "grid_export_kwh": summary["grid_export_kwh"], "curtailment_kwh": summary["curtailment_kwh"], "electricity_cost_cny": electricity_cost, "maintenance_cny": maintenance, "replacement_cny": replacement, "export_income_cny": export_income, "residual_cny": residual, "capex_cny": 0.0, "net_cash_flow_cny": known_cash, "load_kwh": summary["load_kwh"], "matching_conservation": {"load_error_kwh": summary["load_kwh"] - summary["self_use_kwh"] - summary["grid_import_kwh"], "pv_error_kwh": summary["pv_generation_kwh"] - summary["self_use_kwh"] - summary["grid_export_kwh"] - summary["curtailment_kwh"]}}
        cash = row.get("net_cash_flow_cny")
        if cash is None: cumulative = None; npv = None
        elif cumulative is not None: cumulative += float(cash)
        if cash is not None and year > 0 and npv is not None: npv += discounted_year_end(float(cash), year, scenario.discount_rate)
        row["cumulative_cash_flow_cny"] = cumulative; row["discounted_cash_flow_cny"] = None if cash is None else float(cash) / ((1.0 + scenario.discount_rate) ** year); yearly.append(row)
    first = yearly[1] if len(yearly) > 1 else yearly[0]; pv_import_cost = first.get("electricity_cost_cny"); pv_export_income = first.get("export_income_cny")
    annual_saving = None if pv_import_cost is None or pv_export_income is None else float(baseline_import_cost) - float(pv_import_cost) + float(pv_export_income) - (float(quote.maintenance_cny_per_kwp_year or 0.0) * capacity_kwp if capacity_kwp > 1e-12 else 0.0)
    net_npv = npv if not missing else None
    baseline_npv = discounted_cashflow_npv(0.0, [-float(baseline_import_cost)] * int(scenario.study_years), scenario.discount_rate)
    incremental_npv = None if net_npv is None else float(net_npv) - baseline_npv
    result = {"status": "complete" if not missing else ("incomplete_economics" if "export_price_cny_per_kwh" in missing else "incomplete_quote"), "missing_quote_fields": [x for x in missing if x != "export_price_cny_per_kwh"], "missing_economic_inputs": list(missing), "capex_cny": capex, "baseline_annual_import_cost_cny": baseline_import_cost, "pv_annual_import_cost_cny": pv_import_cost, "annual_grid_cost_saving_cny": None if pv_import_cost is None else float(baseline_import_cost) - float(pv_import_cost), "annual_export_income_cny": pv_export_income, "annual_saving_after_maintenance_cny": annual_saving, "study_years": scenario.study_years, "discount_rate": scenario.discount_rate, "pv_annual_degradation": scenario.annual_degradation, "npv_cny": net_npv, "total_cost_npv_cny": None if net_npv is None else -float(net_npv), "incremental_npv_vs_s0_cny": incremental_npv, "net_present_cost_cny": None if net_npv is None else -float(net_npv), "yearly": yearly, "quote_source": quote.source, "cost_note": "初始投入在t=0；运行、维护、更换、残值按年末计入并按该年份折现。光伏衰减只作用于发电；每年用固定空调负荷逐时重算自用、购电、外送和弃电。0kWp不承担任何光伏报价项。"}
    result["simple_payback_years"] = float(capex) / annual_saving if capex is not None and annual_saving is not None and annual_saving > 0 else None
    return result


def _capacity_limit(scenario: PVScenario) -> Tuple[float, List[str]]:
    usable = scenario.roof_area_m2 * scenario.usable_fraction; max_area = usable * DEFAULT_KWP_PER_M2; notes = [f"可用屋顶面积={usable:.2f}m²；组件面积假设={MODULE_AREA_M2_PER_KWP:.2f}m²/kWp", "屋顶承重、消防间距、并网审批仍待现场确认"]
    quote = scenario.quote; unit = sum(float(x) for x in (quote.module_cny_per_kwp, quote.inverter_cny_per_kwp, quote.structure_cny_per_kwp, quote.installation_cny_per_kwp) if x is not None)
    if scenario.budget_cny is not None and unit > 0 and quote.grid_connection_cny is not None:
        max_budget = max(0.0, scenario.budget_cny - float(quote.grid_connection_cny)) / unit; return min(max_area, max_budget), notes + [f"预算容量上限按已填单价估算={max_budget:.3f}kWp"]
    if scenario.budget_cny is not None: notes.append("预算已输入但报价不完整，不能据预算裁剪容量；经济结论待补报价")
    return max_area, notes


def generate_candidates(scenario: PVScenario) -> Tuple[List[float], List[str]]:
    maximum, notes = _capacity_limit(scenario)
    if scenario.requested_capacities_kwp: raw = [float(x) for x in scenario.requested_capacities_kwp]
    else:
        raw = [0.0]; value = scenario.candidate_step_kwp
        while value < maximum - 1e-9: raw.append(round(value, 6)); value += scenario.candidate_step_kwp
        if maximum > 1e-9: raw.append(round(maximum, 6))
    out = sorted({round(max(0.0, min(maximum, x)), 6) for x in raw})
    if not out or out[0] != 0.0: out.insert(0, 0.0)
    return out, notes


def _price_vectors(scenario: PVScenario, timestamps: Sequence[str], interval_seconds: Optional[Sequence[int]] = None) -> Tuple[List[float], Dict[str, Any]]:
    if scenario.tariff_id in ("", "user_constant"):
        return [float(scenario.import_price_cny_per_kwh)] * len(timestamps), {"tariff_id": "user_constant", "type": "constant_user_scenario", "price_cny_per_kwh": float(scenario.import_price_cny_per_kwh), "interval_pricing": "constant over each physical interval"}
    from .tariffs import _clock, profile, profile_public_dict, rate_at, validate_profile
    tariff = profile(scenario.tariff_id, scenario.custom_tariff); idx = _time_index(timestamps); intervals = _intervals(timestamps, interval_seconds)
    physical_end = idx[-1] + pd.to_timedelta(int(intervals[-1]), unit="s")
    last_included_date = (physical_end - pd.to_timedelta(1, unit="s")).date()
    days = (last_included_date - idx[0].date()).days + 1; validate_profile(tariff, idx[0].date(), days)
    prices: List[float] = []; examples: List[Dict[str, Any]] = []
    for i, (start, seconds) in enumerate(zip(idx, intervals)):
        end = start + pd.to_timedelta(int(seconds), unit="s"); cuts = {start, end}; cursor = start.normalize()
        while cursor <= end:
            day = cursor.date()
            for item in tariff.periods:
                a = _clock(item["start"]); b = _clock(item["end"]); b = 86400 if b <= a else b
                cuts.add(cursor + pd.to_timedelta(a, unit="s")); cuts.add(cursor + pd.to_timedelta(b, unit="s"))
            cursor += pd.Timedelta(days=1)
        ordered = sorted(x for x in cuts if start <= x <= end); weighted = 0.0; segments: List[Dict[str, Any]] = []
        for left, right in zip(ordered, ordered[1:]):
            span = (right - left).total_seconds()
            if span <= 0: continue
            mid = left + (right - left) / 2; second = int(mid.hour * 3600 + mid.minute * 60 + mid.second)
            name, rate = rate_at(tariff, mid.date(), second); weighted += span * float(rate)
            segments.append({"start": str(left), "end": str(right), "period": name, "price_cny_per_kwh": float(rate), "seconds": span})
        prices.append(weighted / float(seconds))
        if i < 4: examples.append({"interval_start": str(start), "interval_end": str(end), "segments": segments, "weighted_price_cny_per_kwh": prices[-1]})
    meta = profile_public_dict(tariff); meta.update({"interval_pricing": "constant average power; each physical interval split at tariff boundaries", "interval_examples": examples})
    return prices, meta


def _service_context(load_result: Dict[str, Any]) -> Dict[str, Any]:
    summary = load_result.get("summary") or {}; gaps = {key: float(summary.get(key, 0.0) or 0.0) for key in ("capacity_shortfall_hours", "unmet_temp_degree_hours", "unmet_rh_percent_hours")}; has_gap = any(value > 1e-9 for value in gaps.values())
    return {"status": "service_gap" if has_gap else "within_modeled_scope", "scope": (load_result.get("load_series") or {}).get("service_scope", "cooling_only"), "gaps": gaps, "note": "有服务缺口时，候选仍可用于当前负荷情景试算，但不能解释为同等服务水平下的最优投资方案。" if has_gap else "仅代表当前未校准的冷却负荷情景。"}


def _candidate_row(capacity: float, matched: Dict[str, Any], generation: GenerationSeries, economics: Dict[str, Any], include_series: bool) -> Dict[str, Any]:
    summary = matched["summary"]; row: Dict[str, Any] = {"capacity_kwp": capacity, "generation_kwh": summary["pv_generation_kwh"], "self_use_kwh": summary["self_use_kwh"], "grid_import_kwh": summary["grid_import_kwh"], "grid_export_kwh": summary["grid_export_kwh"], "curtailment_kwh": summary["curtailment_kwh"], "self_consumption_rate": summary["self_consumption_rate"], "load_coverage_rate": summary["load_coverage_rate"], "economics": economics, "monthly": matched["monthly"], "generation_metadata": generation.metadata}
    if include_series: row["hourly"] = {"timestamps": generation.timestamps, "interval_seconds": generation.interval_seconds, "load_kwh": matched["interval_kwh"]["load"], "pv_generation_kwh": matched["interval_kwh"]["pv_generation"], "self_use_kwh": matched["interval_kwh"]["self_use"], "grid_import_kwh": matched["interval_kwh"]["grid_import"], "grid_export_kwh": matched["interval_kwh"]["grid_export"], "curtailment_kwh": matched["interval_kwh"]["curtailment"], "pv_dc_power_w": generation.pv_dc_power_w, "pv_ac_power_w": generation.pv_ac_power_w, "poa_w_m2": generation.poa_w_m2, "cell_temp_c": generation.cell_temp_c}
    return row


def run_pv_planning(load_result: Dict[str, Any], weather: Dict[str, Any], scenario: PVScenario, include_selected_series: bool = True, carbon: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    require_project_load(load_result)
    load = load_result.get("load_series") or {}; lt = list(load.get("timestamps", [])); wt = list(weather.get("time", []))
    if lt != wt: raise ValueError("第一阶段负荷与光伏天气不在同一时间区间，不能联算")
    intervals = _intervals(lt, load.get("interval_seconds")); weather = dict(weather); weather["interval_seconds"] = intervals
    capacities, candidate_notes = generate_candidates(scenario); import_prices, tariff_meta = _price_vectors(scenario, lt, intervals); export_prices = ([float(scenario.export_price_cny_per_kwh)] * len(lt) if scenario.export_price_cny_per_kwh is not None else None)
    base_generation = generate_pv(weather, 0.0, scenario); baseline = match_load(load, base_generation, allow_export=False, import_prices=import_prices); candidates: List[Dict[str, Any]] = []
    carbon_ctx = carbon_context(scenario.site_id, carbon)
    for capacity in capacities:
        generation = generate_pv(weather, capacity, scenario); matched = match_load(load, generation, allow_export=scenario.allow_export, export_limit_kw=scenario.export_limit_kw, import_prices=import_prices, export_prices=export_prices); economics = lifecycle_compare(matched, baseline, capacity, scenario, load_series=load, generation=generation, import_prices=import_prices, export_prices=export_prices)
        yearly_matches = [r for r in economics["yearly"] if r["year"] > 0]
        row = _candidate_row(capacity, matched, generation, economics, include_selected_series)
        row["carbon"] = candidate_carbon(site_id=scenario.site_id, request=carbon, baseline_match=baseline, candidate_match=matched, yearly_matches=yearly_matches, economics=economics, annual_generation_kwh=matched["summary"]["pv_generation_kwh"], annual_load_kwh=matched["summary"]["load_kwh"], annual_import_price_cny_per_kwh=scenario.import_price_cny_per_kwh)
        row["annual_offset_estimate"] = row["carbon"].pop("annual_offset_estimate")
        candidates.append(row)
    baseline_candidate = next(x for x in candidates if x["capacity_kwp"] == 0.0); complete_nonzero = [x for x in candidates if x["capacity_kwp"] > 0 and x["economics"]["status"] == "complete"]; selected_key: Optional[float] = None
    if complete_nonzero:
        selected = max([baseline_candidate] + complete_nonzero, key=lambda x: float(x["economics"]["npv_cny"])); selected_key = selected["capacity_kwp"]; recommendation = {"status": "conditional", "capacity_kwp": selected_key, "reason": "在报价、电价、研究年限和历史天气情景均已填写的有限候选中，净现金流现值最大；不是全局优化，也不是未来保证。"}
    else: recommendation = {"status": "not_available", "capacity_kwp": None, "reason": "非零候选缺少完整报价或外送价格，保留物理结果与0kWp基准，不能据此证明不安装最划算。"}
    service = _service_context(load_result)
    if service["status"] == "service_gap": recommendation["service_qualification"] = "当前空调负荷存在服务缺口；该推荐不能称为同等服务水平下的最优投资方案。"
    load_context = {"source": load.get("source"), "scope": load.get("scope"), "model_version": load.get("model_version"), "equipment_count": load.get("equipment_count"), "room_count": load.get("room_count"), "units_per_room": load.get("units_per_room"), "project_aggregation": load.get("project_aggregation"), "service_scope": load.get("service_scope"), "assumptions": load.get("assumptions"), "electric_load_kwh": baseline["summary"]["load_kwh"], "service_quality": service, "project_load_context": project_load_context(load_result)}
    return {"status": "success", "calculation_version": "phase2a-carbon-5090-v1", "scenario": asdict(scenario), "carbon_context": carbon_ctx, "candidate_constraints": candidate_notes, "load_context": load_context, "service_quality": service, "tariff": tariff_meta, "weather_provenance": {"source_file": weather.get("source_file"), "boundary_file": weather.get("boundary_file"), "hash": weather.get("hash"), "context": weather.get("context"), "normalization": weather.get("weather_normalization"), "pv_provenance": weather.get("pv_provenance", {})}, "baseline": {"capacity_kwp": 0.0, "matching": baseline["summary"], "monthly": baseline["monthly"]}, "candidates": candidates, "recommendation": recommendation, "selected_capacity_kwp": selected_key, "notes": ["第一阶段空调负荷是未校准城市级情景，不是楼宇精准负荷。", "本轮只评价当前建模空调用电；不含其他电器、储能、风电。", "逐时匹配不等于分钟级波动仿真。", "光伏候选有限枚举，不称全局最优。", "碳字段只使用当时用上的自发电；年度抵扣为不参与推荐的粗算对照。"]}
