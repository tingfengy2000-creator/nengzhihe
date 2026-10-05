"""Phase-two photovoltaic generation, hourly matching and lifecycle comparison.

The module keeps PV physics, load matching and economics separate.  All energy
balances are computed from the same timestamp and interval vectors; no annual
energy offset is used.  pvlib is used for solar position, POA irradiance,
cell temperature, DC and inverter calculations with explicit inputs.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
import pvlib
from pvlib import irradiance, temperature, pvsystem, inverter


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
    azimuth_open_meteo_deg: float = 0.0  # Open-Meteo: 0 south, -90 east, 90 west.
    shading_loss_fraction: float = 0.0
    system_loss_fraction: float = DEFAULT_SYSTEM_LOSS
    availability: float = DEFAULT_AVAILABILITY
    inverter_ratio: float = 0.85
    budget_cny: Optional[float] = None
    allow_export: bool = False
    export_limit_kw: Optional[float] = None
    import_price_cny_per_kwh: float = 0.66
    export_price_cny_per_kwh: Optional[float] = None
    study_years: int = 10
    discount_rate: float = 0.0
    annual_degradation: float = 0.005
    quote: PVQuote = None  # type: ignore[assignment]
    candidate_step_kwp: float = 1.0
    requested_capacities_kwp: Optional[List[float]] = None

    def __post_init__(self) -> None:
        if self.quote is None:
            self.quote = PVQuote()
        if self.roof_area_m2 <= 0 or not 0 < self.usable_fraction <= 1:
            raise ValueError("可安装屋顶面积与可用比例必须为正，且比例不超过1")
        if not 0 <= self.tilt_deg <= 90:
            raise ValueError("倾角必须在0至90度")
        if not 0 <= self.system_loss_fraction < 1 or not 0 < self.availability <= 1:
            raise ValueError("损失率或可用率无效")
        if self.study_years < 1 or self.candidate_step_kwp <= 0:
            raise ValueError("研究年限与容量步长必须有效")
        if self.budget_cny is not None and self.budget_cny < 0:
            raise ValueError("预算不能为负")
        if self.export_limit_kw is not None and self.export_limit_kw < 0:
            raise ValueError("外送功率上限不能为负")
        if self.export_price_cny_per_kwh is not None and self.export_price_cny_per_kwh < 0:
            raise ValueError("外送电价不能为负")
        if self.quote.residual_fraction < 0 or self.quote.residual_fraction > 1:
            raise ValueError("残值比例必须在0至1")


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


def _open_meteo_azimuth_to_pvlib(value: float) -> float:
    # pvlib: 0=N, 90=E, 180=S, 270=W. Open-Meteo UI: 0=S, -90=E, 90=W.
    return (180.0 - float(value)) % 360.0


def _times_index(times: Sequence[str], timezone: str) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(times)
    if idx.tz is None:
        idx = idx.tz_localize(timezone)
    else:
        idx = idx.tz_convert(timezone)
    return idx


def _intervals(times: Sequence[str], provided: Optional[Sequence[int]] = None) -> List[int]:
    if provided is not None:
        values = [int(x) for x in provided]
        if len(values) != len(times) or any(x <= 0 for x in values):
            raise ValueError("PV时间间隔长度或数值无效")
        return values
    if len(times) < 2:
        raise ValueError("PV时间序列至少需要两个时刻")
    out = []
    for a, b in zip(times, times[1:]):
        dt = (datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds()
        if dt >= 0:
            dt = -dt
        if dt <= 0 or dt > 3 * 3600:
            raise ValueError(f"PV时间轴间隔无效：{a} -> {b}")
        out.append(int(dt))
    out.append(out[-1])
    return out


def _as_float(values: Sequence[Any], name: str, n: int) -> List[float]:
    if len(values) != n or any(v is None for v in values):
        raise ValueError(f"光伏天气变量缺失或长度不一致：{name}")
    return [max(0.0, float(v)) for v in values]


def generate_pv(weather: Dict[str, Any], capacity_kwp: float, scenario: PVScenario) -> GenerationSeries:
    if capacity_kwp < 0:
        raise ValueError("装机容量不能为负")
    times = list(weather.get("time", [])); h = weather.get("hourly", {})
    n = len(times)
    if n < 2:
        raise ValueError("光伏天气序列太短")
    intervals = _intervals(times, weather.get("interval_seconds"))
    timezone = str((weather.get("context") or {}).get("site", {}).get("timezone", "Asia/Shanghai"))
    lat = float((weather.get("context") or {}).get("site", {}).get("latitude", weather.get("latitude", 0.0)))
    lon = float((weather.get("context") or {}).get("site", {}).get("longitude", weather.get("longitude", 0.0)))
    ghi = _as_float(h.get("shortwave_radiation", []), "shortwave_radiation/GHI", n)
    dni = _as_float(h.get("direct_normal_irradiance", []), "direct_normal_irradiance/DNI", n)
    dhi = _as_float(h.get("diffuse_radiation", []), "diffuse_radiation/DHI", n)
    temp_air = [float(v) for v in h.get("temperature_2m", [])]
    wind_kmh = [float(v) for v in h.get("wind_speed_10m", [])]
    if len(temp_air) != n or len(wind_kmh) != n or any(v is None for v in temp_air + wind_kmh):
        raise ValueError("光伏天气需要完整温度与10米风速")
    idx = _times_index(times, timezone)
    loc = pvlib.location.Location(lat, lon, tz=timezone)
    solar = loc.get_solarposition(idx)
    pvlib_azimuth = _open_meteo_azimuth_to_pvlib(scenario.azimuth_open_meteo_deg)
    poa = irradiance.get_total_irradiance(
        surface_tilt=float(scenario.tilt_deg),
        surface_azimuth=pvlib_azimuth,
        solar_zenith=solar["zenith"],
        solar_azimuth=solar["azimuth"],
        dni=pd.Series(dni, index=idx),
        ghi=pd.Series(ghi, index=idx),
        dhi=pd.Series(dhi, index=idx),
        albedo=DEFAULT_ALBEDO,
    )
    poa_global = pd.Series(poa["poa_global"], index=idx).clip(lower=0.0)
    wind_ms = pd.Series(wind_kmh, index=idx) / 3.6
    temp_cell = temperature.sapm_cell(
        poa_global=poa_global,
        temp_air=pd.Series(temp_air, index=idx),
        wind_speed=wind_ms,
        a=-3.56,
        b=-0.0750,
        deltaT=3.0,
    )
    if capacity_kwp == 0:
        dc = pd.Series(0.0, index=idx)
        ac = pd.Series(0.0, index=idx)
    else:
        pdc0_w = float(capacity_kwp) * 1000.0
        inv_kw = max(0.001, pdc0_w * float(scenario.inverter_ratio) / 1000.0)
        dc = pvsystem.pvwatts_dc(poa_global, temp_cell, pdc0=pdc0_w, gamma_pdc=DEFAULT_GAMMA_PDC).clip(lower=0.0)
        ac = inverter.pvwatts(dc, pdc0=inv_kw * 1000.0, eta_inv_nom=DEFAULT_INVERTER_EFFICIENCY, eta_inv_ref=0.9637).clip(lower=0.0)
        # Apply array/shading/system availability once, after inverter clipping.
        ac = ac * max(0.0, 1.0 - float(scenario.shading_loss_fraction)) * max(0.0, 1.0 - float(scenario.system_loss_fraction)) * float(scenario.availability)
    metadata = {
        "pvlib_version": PVLIB_VERSION,
        "solar_position": "pvlib Location.get_solarposition",
        "transposition": "pvlib irradiance.get_total_irradiance; isotropic diffuse with albedo 0.20",
        "temperature_model": "pvlib SAPM cell temperature, explicit -3.56/-0.075/3.0 and 10m wind converted km/h→m/s",
        "dc_model": "pvlib PVWatts DC, gamma_pdc=-0.0035/C",
        "inverter_model": "pvlib PVWatts inverter, explicit 0.96 nominal efficiency and ratio",
        "azimuth_input_convention": "Open-Meteo 0 south/-90 east/90 west; converted to pvlib 0 north/90 east/180 south/270 west",
        "radiation_semantics": "GHI/DNI/DHI are preceding-hour means; output is interval energy using each timestamp's explicit duration",
        "loss_application": "shading, system loss and availability applied once after inverter clipping",
        "capacity_kwp": float(capacity_kwp),
        "inverter_ratio": float(scenario.inverter_ratio),
    }
    return GenerationSeries(
        timestamps=times,
        interval_seconds=intervals,
        pv_dc_power_w=[round(float(v), 8) for v in dc.tolist()],
        pv_ac_power_w=[round(float(v), 8) for v in ac.tolist()],
        ghi_w_m2=ghi, dni_w_m2=dni, dhi_w_m2=dhi,
        poa_w_m2=[round(float(v), 8) for v in poa_global.tolist()],
        cell_temp_c=[round(float(v), 8) for v in temp_cell.tolist()],
        source=str(weather.get("source_file", "weather")), model="pvlib.PVWatts",
        metadata=metadata,
    )


def _energy(power_w: float, seconds: int) -> float:
    return max(0.0, float(power_w)) * float(seconds) / 3_600_000.0


def match_load(load_series: Dict[str, Any], generation: GenerationSeries, *, allow_export: bool = False, export_limit_kw: Optional[float] = None) -> Dict[str, Any]:
    lt = list(load_series.get("timestamps", [])); gt = generation.timestamps
    if lt != gt:
        raise ValueError("负荷与光伏时间戳不一致，拒绝跨时段或年度错配")
    li = [int(x) for x in load_series.get("interval_seconds", [])]
    gi = generation.interval_seconds
    if li != gi:
        raise ValueError("负荷与光伏时间间隔不一致")
    lp = load_series.get("electric_power_w", [])
    gp = generation.pv_ac_power_w
    if len(lp) != len(gp):
        raise ValueError("负荷与光伏序列长度不一致")
    load_kwh=[]; pv_kwh=[]; self_use=[]; imports=[]; exports=[]; curtail=[]
    for load_w, pv_w, sec in zip(lp, gp, li):
        l = _energy(float(load_w), sec); p = _energy(float(pv_w), sec)
        s = min(l, p); surplus = max(0.0, p - s)
        if allow_export:
            limit = surplus if export_limit_kw is None else min(surplus, max(0.0, float(export_limit_kw)) * sec / 3600.0)
        else:
            limit = 0.0
        load_kwh.append(l); pv_kwh.append(p); self_use.append(s); imports.append(max(0.0, l-s)); exports.append(limit); curtail.append(max(0.0, surplus-limit))
    sums={"load_kwh":sum(load_kwh),"pv_generation_kwh":sum(pv_kwh),"self_use_kwh":sum(self_use),"grid_import_kwh":sum(imports),"grid_export_kwh":sum(exports),"curtailment_kwh":sum(curtail)}
    if abs(sums["load_kwh"] - sums["self_use_kwh"] - sums["grid_import_kwh"]) > 1e-7 or abs(sums["pv_generation_kwh"] - sums["self_use_kwh"] - sums["grid_export_kwh"] - sums["curtailment_kwh"]) > 1e-7:
        raise AssertionError("逐时供需守恒失败")
    sums["self_consumption_rate"] = sums["self_use_kwh"] / sums["pv_generation_kwh"] if sums["pv_generation_kwh"] > 1e-12 else None
    sums["load_coverage_rate"] = sums["self_use_kwh"] / sums["load_kwh"] if sums["load_kwh"] > 1e-12 else None
    monthly={}
    for ts,l,p,s,imp,exp,cur in zip(lt,load_kwh,pv_kwh,self_use,imports,exports,curtail):
        month=str(ts)[:7]; m=monthly.setdefault(month,{"load_kwh":0.0,"pv_generation_kwh":0.0,"self_use_kwh":0.0,"grid_import_kwh":0.0,"grid_export_kwh":0.0,"curtailment_kwh":0.0})
        for k,v in (("load_kwh",l),("pv_generation_kwh",p),("self_use_kwh",s),("grid_import_kwh",imp),("grid_export_kwh",exp),("curtailment_kwh",cur)): m[k]+=v
    return {"summary": sums, "monthly": monthly, "interval_kwh": {"load": load_kwh, "pv_generation": pv_kwh, "self_use": self_use, "grid_import": imports, "grid_export": exports, "curtailment": curtail}, "export_policy": {"allow_export": bool(allow_export), "limit_kw": export_limit_kw}}


def _quote_capex(capacity_kwp: float, quote: PVQuote) -> Optional[float]:
    fields=(quote.module_cny_per_kwp,quote.inverter_cny_per_kwp,quote.structure_cny_per_kwp,quote.installation_cny_per_kwp,quote.grid_connection_cny)
    if any(x is None for x in fields): return None
    return capacity_kwp * sum(float(x) for x in fields[:4]) + float(fields[4])


def lifecycle_compare(match: Dict[str, Any], baseline_match: Dict[str, Any], capacity_kwp: float, scenario: PVScenario) -> Dict[str, Any]:
    quote=scenario.quote; capex=_quote_capex(capacity_kwp,quote)
    missing=[]
    for name,value in (("module_cny_per_kwp",quote.module_cny_per_kwp),("inverter_cny_per_kwp",quote.inverter_cny_per_kwp),("structure_cny_per_kwp",quote.structure_cny_per_kwp),("installation_cny_per_kwp",quote.installation_cny_per_kwp),("grid_connection_cny",quote.grid_connection_cny),("maintenance_cny_per_kwp_year",quote.maintenance_cny_per_kwp_year)):
        if value is None: missing.append(name)
    base_cost=baseline_match["summary"]["grid_import_kwh"] * scenario.import_price_cny_per_kwh
    summary=match["summary"]
    yearly=[]; npv=0.0; cumulative=0.0
    for year in range(0, scenario.study_years + 1):
        if year == 0:
            cash = -float(capex or 0.0); row={"year":0,"grid_import_kwh":0.0,"electricity_cost_cny":0.0,"maintenance_cny":0.0,"replacement_cny":0.0,"export_income_cny":0.0,"capex_cny":float(capex or 0.0),"net_cash_flow_cny":cash}
        else:
            degradation=(1.0-float(scenario.annual_degradation)) ** (year-1)
            imp=summary["grid_import_kwh"] * degradation
            exp=summary["grid_export_kwh"] * degradation
            elec=imp * scenario.import_price_cny_per_kwh
            export_income=exp * (scenario.export_price_cny_per_kwh or 0.0) if scenario.allow_export else 0.0
            maintenance=float(quote.maintenance_cny_per_kwp_year or 0.0) * capacity_kwp
            replacement=0.0
            if quote.inverter_replacement_year and year == int(quote.inverter_replacement_year):
                replacement=capacity_kwp * float(quote.inverter_cny_per_kwp or 0.0) * float(quote.inverter_replacement_fraction)
            residual=0.0
            if year == scenario.study_years:
                residual=float(capex or 0.0) * float(quote.residual_fraction)
            cash=-(elec + maintenance + replacement) + export_income + residual
            row={"year":year,"grid_import_kwh":imp,"pv_generation_kwh":summary["pv_generation_kwh"]*degradation,"self_use_kwh":summary["self_use_kwh"]*degradation,"grid_export_kwh":exp,"curtailment_kwh":summary["curtailment_kwh"]*degradation,"electricity_cost_cny":elec,"maintenance_cny":maintenance,"replacement_cny":replacement,"export_income_cny":export_income,"residual_cny":residual,"capex_cny":0.0,"net_cash_flow_cny":cash}
        cumulative += cash; row["cumulative_cash_flow_cny"]=cumulative; discounted=cash/((1.0+scenario.discount_rate)**year) if scenario.discount_rate > -1 else cash; row["discounted_cash_flow_cny"]=discounted; npv += discounted; yearly.append(row)
    base_life=base_cost*scenario.study_years
    result={"status":"complete" if (not missing or capacity_kwp == 0) else "incomplete_quote","missing_quote_fields":missing,"capex_cny":capex,"baseline_annual_import_cost_cny":base_cost,"pv_annual_import_cost_cny":summary["grid_import_kwh"]*scenario.import_price_cny_per_kwh,"annual_grid_cost_saving_cny":base_cost-summary["grid_import_kwh"]*scenario.import_price_cny_per_kwh,"study_years":scenario.study_years,"npv_cny":npv if not missing or capacity_kwp == 0 else None,"net_present_cost_cny":(-npv) if not missing or capacity_kwp == 0 else None,"yearly":yearly,"quote_source":quote.source,"cost_note":"空调负荷在P0与PV候选中保持相同；购电节省与外送收入分开计算，未重复计入。NPV沿现金流约定为净现金流现值，成本比较使用较大的（较不负的）NPV/较小的净现值成本。"}
    annual_saving=result["annual_grid_cost_saving_cny"] + (summary["grid_export_kwh"] * (scenario.export_price_cny_per_kwh or 0.0) if scenario.allow_export else 0.0) - float(quote.maintenance_cny_per_kwp_year or 0.0)*capacity_kwp
    result["simple_payback_years"] = (float(capex)/annual_saving) if capex is not None and annual_saving > 0 else None
    return result


def _capacity_limit(scenario: PVScenario) -> Tuple[float, List[str]]:
    usable=scenario.roof_area_m2*scenario.usable_fraction
    max_area=usable*DEFAULT_KWP_PER_M2
    notes=[f"可用屋顶面积={usable:.2f}m²；组件面积假设={MODULE_AREA_M2_PER_KWP:.2f}m²/kWp", "屋顶承重、消防间距、并网审批仍待现场确认"]
    quote=scenario.quote
    unit=sum(float(x) for x in (quote.module_cny_per_kwp,quote.inverter_cny_per_kwp,quote.structure_cny_per_kwp,quote.installation_cny_per_kwp) if x is not None)
    if scenario.budget_cny is not None and unit > 0 and quote.grid_connection_cny is not None:
        max_budget=max(0.0, scenario.budget_cny-float(quote.grid_connection_cny))/unit; return min(max_area,max_budget), notes+[f"预算容量上限按已填单价估算={max_budget:.3f}kWp"]
    if scenario.budget_cny is not None: notes.append("预算已输入但报价不完整，不能据预算裁剪容量；经济结论待补报价")
    return max_area,notes


def generate_candidates(scenario: PVScenario) -> Tuple[List[float], List[str]]:
    maximum,notes=_capacity_limit(scenario)
    if scenario.requested_capacities_kwp:
        raw=[float(x) for x in scenario.requested_capacities_kwp]
    else:
        raw=[0.0]; x=scenario.candidate_step_kwp
        while x < maximum - 1e-9:
            raw.append(round(x,6)); x += scenario.candidate_step_kwp
        if maximum > 1e-9: raw.append(round(maximum,6))
    out=sorted({round(max(0.0,min(maximum,x)),6) for x in raw})
    if not out or out[0] != 0.0: out.insert(0,0.0)
    return out,notes


def run_pv_planning(load_result: Dict[str, Any], weather: Dict[str, Any], scenario: PVScenario, include_selected_series: bool = True) -> Dict[str, Any]:
    load=load_result.get("load_series") or {}; lt=list(load.get("timestamps", [])); wt=list(weather.get("time", []))
    if lt != wt: raise ValueError("第一阶段负荷与光伏天气不在同一时间区间，不能联算")
    intervals=[int(x) for x in load.get("interval_seconds", [])]
    if len(intervals)!=len(lt): raise ValueError("负荷时间间隔缺失")
    weather = dict(weather); weather["interval_seconds"] = intervals
    capacities, candidate_notes=generate_candidates(scenario)
    base_generation=generate_pv(weather,0.0,scenario); baseline=match_load(load,base_generation,allow_export=False)
    candidates=[]; selected_key=None
    for capacity in capacities:
        generation=generate_pv(weather,capacity,scenario); matched=match_load(load,generation,allow_export=scenario.allow_export,export_limit_kw=scenario.export_limit_kw)
        economics=lifecycle_compare(matched,baseline,capacity,scenario)
        row={"capacity_kwp":capacity,"generation_kwh":matched["summary"]["pv_generation_kwh"],"self_use_kwh":matched["summary"]["self_use_kwh"],"grid_import_kwh":matched["summary"]["grid_import_kwh"],"grid_export_kwh":matched["summary"]["grid_export_kwh"],"curtailment_kwh":matched["summary"]["curtailment_kwh"],"self_consumption_rate":matched["summary"]["self_consumption_rate"],"load_coverage_rate":matched["summary"]["load_coverage_rate"],"economics":economics,"monthly":matched["monthly"]}
        if include_selected_series: row["hourly"]={"timestamps":generation.timestamps,"load_kwh":matched["interval_kwh"]["load"],"pv_generation_kwh":matched["interval_kwh"]["pv_generation"],"self_use_kwh":matched["interval_kwh"]["self_use"],"grid_import_kwh":matched["interval_kwh"]["grid_import"],"grid_export_kwh":matched["interval_kwh"]["grid_export"],"curtailment_kwh":matched["interval_kwh"]["curtailment"],"cell_temp_c":generation.cell_temp_c}
        candidates.append(row)
    complete=[x for x in candidates if x["economics"]["status"]=="complete"]
    if complete:
        selected=max(complete,key=lambda x: (x["economics"]["npv_cny"] if x["economics"]["npv_cny"] is not None else float("-inf")))
        selected_key=selected["capacity_kwp"]
        recommendation={"status":"conditional","capacity_kwp":selected_key,"reason":"在已填报价、电价、研究年限和历史天气重复假设下，有限候选中净现金流现值最大（净现值成本最小）；不是全局优化，也不是未来保证"}
    else:
        recommendation={"status":"not_available","capacity_kwp":None,"reason":"报价不完整，保留发电与供需结果，不做无条件经济推荐"}
    return {"status":"success","scenario":asdict(scenario),"candidate_constraints":candidate_notes,"load_context":{"source":load.get("source"),"scope":load.get("scope"),"model_version":load.get("model_version"),"equipment_count":load.get("equipment_count"),"service_scope":load.get("service_scope"),"assumptions":load.get("assumptions"),"electric_load_kwh":baseline["summary"]["load_kwh"]},"weather_provenance":{"source_file":weather.get("source_file"),"hash":weather.get("hash"),"context":weather.get("context"),"pv_provenance":weather.get("pv_provenance",{})},"baseline":{"capacity_kwp":0.0,"matching":baseline["summary"],"monthly":baseline["monthly"]},"candidates":candidates,"recommendation":recommendation,"selected_capacity_kwp":selected_key,"notes":["第一阶段空调负荷是未校准城市级情景，不是楼宇精准负荷。", "本轮只评价当前建模空调用电；不含其他电器、储能、风电。", "逐时匹配不等于分钟级波动仿真。"]}
