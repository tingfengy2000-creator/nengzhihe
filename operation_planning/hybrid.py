"""Same-condition grid/PV/wind/hybrid comparison for phase two B."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, List, Optional, Sequence

from .pv import PVScenario, PVQuote, generate_pv, _intervals, _price_vectors
from .wind import WindScenario, WindQuote, WindTurbineProfile, generate_wind

def _safe_intervals(times: Sequence[str], provided: Optional[Sequence[int]]) -> List[int]:
    """Allow a one-interval arithmetic fixture while keeping real axes strict."""
    if len(times) == 1:
        if provided is None or len(provided) != 1 or int(provided[0]) <= 0: raise ValueError("单区间必须显式提供正的interval_seconds")
        return [int(provided[0])]
    return _intervals(times, provided)

@dataclass
class HybridScenario:
    site_id: str = "guangzhou"
    year: int = 2024
    pv_capacity_kwp: float = 2.0
    wind: WindScenario = field(default_factory=WindScenario)
    budget_cny: Optional[float] = None
    allow_export: bool = False
    export_limit_kw: Optional[float] = None
    import_price_cny_per_kwh: float = 0.66
    export_price_cny_per_kwh: Optional[float] = None
    study_years: int = 10
    discount_rate: float = 0.0
    pv_annual_degradation: float = 0.005
    pv_quote: PVQuote = field(default_factory=PVQuote)
    wind_quote: WindQuote = field(default_factory=WindQuote)

    def __post_init__(self) -> None:
        if self.pv_capacity_kwp < 0: raise ValueError("光伏容量不能为负")
        if self.budget_cny is not None and self.budget_cny < 0: raise ValueError("预算不能为负")
        if self.study_years < 1: raise ValueError("研究期必须为正")

def _quote_cost(q: Any, count: int, fields: Sequence[str]) -> Optional[float]:
    if count == 0: return 0.0
    vals=[getattr(q,f,None) for f in fields]
    if any(v is None for v in vals): return None
    return float(count)*sum(float(v) for v in vals)

def match_hybrid(load_series: Dict[str, Any], pv_generation: Dict[str, Any], wind_generation: Dict[str, Any], *, allow_export: bool=False, export_limit_kw: Optional[float]=None, import_prices: Optional[Sequence[float]]=None, export_prices: Optional[Sequence[float]]=None) -> Dict[str, Any]:
    lt=list(load_series.get("timestamps", [])); pt=list(pv_generation.get("timestamps", [])); wt=list(wind_generation.get("timestamps", []))
    if lt != pt or lt != wt: raise ValueError("负荷、光伏和风电必须使用同一时间轴")
    ints=_safe_intervals(lt, load_series.get("interval_seconds"));
    if ints != _safe_intervals(pt, pv_generation.get("interval_seconds")) or ints != _safe_intervals(wt, wind_generation.get("interval_seconds")): raise ValueError("负荷、光伏和风电时间间隔不一致")
    lp=load_series.get("electric_power_w",[]); pp=pv_generation.get("pv_ac_power_w",[]); wp=wind_generation.get("wind_power_w",[])
    if not (len(lp)==len(pp)==len(wp)==len(ints)): raise ValueError("供需序列长度不一致")
    if import_prices is not None and len(import_prices)!=len(lp): raise ValueError("购电价格长度不一致")
    if export_prices is not None and len(export_prices)!=len(lp): raise ValueError("外送价格长度不一致")
    rows=[]; sums={k:0.0 for k in ("load_kwh","pv_generation_kwh","wind_generation_kwh","total_generation_kwh","self_use_kwh","grid_import_kwh","grid_export_kwh","curtailment_kwh","import_cost_cny","export_income_cny")}
    for i,sec in enumerate(ints):
        l=float(lp[i])*sec/3_600_000; p=float(pp[i])*sec/3_600_000; w=float(wp[i])*sec/3_600_000; total=p+w; self_use=min(l,total); surplus=max(0.0,total-self_use)
        exp=min(surplus,float(export_limit_kw)*sec/3600) if allow_export and export_limit_kw is not None else (surplus if allow_export else 0.0); cur=surplus-exp; imp=l-self_use
        pv_self=self_use*(p/total) if total>0 else 0.0; wind_self=self_use-pv_self
        row={"timestamp":lt[i],"interval_seconds":sec,"load_kwh":l,"pv_generation_kwh":p,"wind_generation_kwh":w,"total_generation_kwh":total,"self_use_kwh":self_use,"self_use_pv_kwh":pv_self,"self_use_wind_kwh":wind_self,"grid_import_kwh":imp,"grid_export_kwh":exp,"curtailment_kwh":cur}
        if import_prices is not None: row["import_cost_cny"]=imp*float(import_prices[i]); sums["import_cost_cny"]+=row["import_cost_cny"]
        if export_prices is not None: row["export_income_cny"]=exp*float(export_prices[i]); sums["export_income_cny"]+=row["export_income_cny"]
        rows.append(row)
        for k,v in (("load_kwh",l),("pv_generation_kwh",p),("wind_generation_kwh",w),("total_generation_kwh",total),("self_use_kwh",self_use),("grid_import_kwh",imp),("grid_export_kwh",exp),("curtailment_kwh",cur)): sums[k]+=v
    if abs(sums["load_kwh"]-sums["self_use_kwh"]-sums["grid_import_kwh"])>1e-7: raise AssertionError("负荷守恒失败")
    if abs(sums["total_generation_kwh"]-sums["self_use_kwh"]-sums["grid_export_kwh"]-sums["curtailment_kwh"])>1e-7: raise AssertionError("风光发电守恒失败")
    sums["self_consumption_rate"]=sums["self_use_kwh"]/sums["total_generation_kwh"] if sums["total_generation_kwh"]>1e-12 else None; sums["load_coverage_rate"]=sums["self_use_kwh"]/sums["load_kwh"] if sums["load_kwh"]>1e-12 else None
    return {"summary":sums,"intervals":rows,"export_policy":{"allow_export":allow_export,"limit_kw":export_limit_kw}}

def _lifecycle(match: Dict[str,Any], baseline: Dict[str,Any], scenario: HybridScenario, *, pv_on: bool, wind_on: bool, load_series: Dict[str,Any], pv_generation: Dict[str,Any], wind_generation: Dict[str,Any], import_prices: Sequence[float], export_prices: Optional[Sequence[float]]) -> Dict[str,Any]:
    pq, wq=scenario.pv_quote,scenario.wind_quote
    pcost=_quote_cost(pq,1,["module_cny_per_kwp","inverter_cny_per_kwp","structure_cny_per_kwp","installation_cny_per_kwp"])
    if pv_on and pcost is not None: pcost*=scenario.pv_capacity_kwp
    elif not pv_on: pcost=0.0
    wcost=_quote_cost(wq,1,["turbine_cny","tower_cny","foundation_cny","installation_cny"])
    connection = 0.0
    if pv_on and wind_on:
        connection = max(float(pq.grid_connection_cny or 0), float(wq.grid_connection_cny or 0))
    elif pv_on:
        connection = float(pq.grid_connection_cny or 0)
    elif wind_on:
        connection = float(wq.grid_connection_cny or 0)
    if not wind_on:
        wcost=0.0
    capex=None if (pv_on and pcost is None) or (wind_on and wcost is None) else float(pcost or 0)+float(wcost or 0)+connection
    missing=[]
    if pv_on:
        for f in ["module_cny_per_kwp","inverter_cny_per_kwp","structure_cny_per_kwp","installation_cny_per_kwp","grid_connection_cny","maintenance_cny_per_kwp_year"]:
            if getattr(pq,f,None) is None: missing.append("pv_"+f)
    if wind_on:
        for f in ["turbine_cny","tower_cny","foundation_cny","installation_cny","grid_connection_cny","maintenance_cny_per_year"]:
            if getattr(wq,f,None) is None: missing.append("wind_"+f)
    if scenario.allow_export and scenario.export_price_cny_per_kwh is None: missing.append("export_price_cny_per_kwh")
    if missing: return {"status":"incomplete","missing":missing,"capex_cny":capex}
    rows=[]; npv=0.0; pv_deg=1.0
    base_imp=float(baseline["summary"]["import_cost_cny"])
    for year in range(1,scenario.study_years+1):
        # Recreate the hourly balance each year. Only PV output degrades; wind
        # stays at its explicit availability assumption because no certified
        # annual degradation rule was supplied.
        pg=dict(pv_generation); pg["pv_ac_power_w"]=[float(x)*pv_deg for x in pv_generation.get("pv_ac_power_w",[])] if pv_on else [0.0]*len(load_series.get("timestamps",[]))
        wg=wind_generation if wind_on else {**wind_generation,"wind_power_w":[0.0]*len(load_series.get("timestamps",[]))}
        ym=match_hybrid(load_series,pg,wg,allow_export=scenario.allow_export,export_limit_kw=scenario.export_limit_kw,import_prices=import_prices,export_prices=export_prices)
        imp=float(ym["summary"].get("import_cost_cny",0.0)); export_income=float(ym["summary"].get("export_income_cny",0.0))
        maint=(float(pq.maintenance_cny_per_kwp_year or 0)*scenario.pv_capacity_kwp if pv_on else 0)+(float(wq.maintenance_cny_per_year or 0) if wind_on else 0)
        replacement=0.0
        if pv_on and pq.inverter_replacement_year==year: replacement+=float(pcost or 0)*float(pq.inverter_replacement_fraction)
        if wind_on and wq.replacement_year==year: replacement+=float(wcost or 0)*float(wq.replacement_fraction)
        residual=0.0
        if year==scenario.study_years: residual=(float(pcost or 0)*float(pq.residual_fraction) if pv_on else 0)+(float(wcost or 0)*float(wq.residual_fraction) if wind_on else 0)
        cash=-(capex or 0) if year==1 else 0.0; cash-=maint+replacement; cash+=base_imp-imp+export_income+residual
        discounted=cash/((1+scenario.discount_rate)**(year-1)); npv+=discounted
        rows.append({"year":year,"grid_import_cost_cny":imp,"export_income_cny":export_income,"maintenance_cny":maint,"replacement_cny":replacement,"residual_cny":residual,"net_cashflow_cny":cash,"discounted_cny":discounted})
        pv_deg*=1-float(scenario.pv_annual_degradation)
    total_grid=sum(float(r["grid_import_cost_cny"]) for r in rows); total_export=sum(float(r["export_income_cny"]) for r in rows); total_maint=sum(float(r["maintenance_cny"]) for r in rows); total_repl=sum(float(r["replacement_cny"]) for r in rows); total_residual=sum(float(r["residual_cny"]) for r in rows)
    return {"status":"complete","capex_cny":capex,"npv_cny":npv,"yearly":rows,"baseline_import_cost_cny":base_imp,"total_grid_import_cost_cny":total_grid,"total_export_income_cny":total_export,"total_maintenance_cny":total_maint,"total_replacement_cny":total_repl,"total_residual_cny":total_residual,"total_lifecycle_spend_cny":float(capex or 0)+total_grid-total_export+total_maint+total_repl-total_residual,"simple_payback_years":None}

def run_hybrid_planning(load_result: Dict[str,Any], weather: Dict[str,Any], pv_scenario: PVScenario, hybrid: HybridScenario, profile: Optional[WindTurbineProfile]=None, *, include_hourly: bool=True) -> Dict[str,Any]:
    load=load_result.get("load_series") or {}; times=list(load.get("timestamps",[]));
    if times != list(weather.get("time",[])): raise ValueError("负荷和风光天气不在同一时间区间")
    intervals=_intervals(times, load.get("interval_seconds")); weather=dict(weather); weather["interval_seconds"]=intervals; profile=profile or WindTurbineProfile.from_file()
    prices, tariff_meta=_price_vectors(pv_scenario,times,intervals); export_prices=[hybrid.export_price_cny_per_kwh]*len(times) if hybrid.export_price_cny_per_kwh is not None else None
    pv0=asdict(generate_pv(weather,0.0,pv_scenario)); pv=asdict(generate_pv(weather,hybrid.pv_capacity_kwp,pv_scenario)); wind=generate_wind(weather,profile,hybrid.wind); wind0=dict(wind); wind0["wind_power_w"]=[0.0]*len(times); wind0["wind_energy_kwh"]=[0.0]*len(times); wind0["metadata"]={**wind["metadata"],"turbine_count":0}
    combos=[("S0_grid",False,False), ("S1_pv",True,False),("S2_wind",False,True),("S3_pv_wind",True,True)]
    candidates=[]; baseline=None
    for sid,pv_on,wind_on in combos:
        pg=pv if pv_on else pv0; wg=wind if wind_on else wind0; m=match_hybrid(load,pg,wg,allow_export=hybrid.allow_export,export_limit_kw=hybrid.export_limit_kw,import_prices=prices,export_prices=export_prices); baseline=baseline or m
        econ=_lifecycle(m,baseline,hybrid,pv_on=pv_on,wind_on=wind_on,load_series=load,pv_generation=pg,wind_generation=wg,import_prices=prices,export_prices=export_prices)
        budget_ok = hybrid.budget_cny is None or econ.get("capex_cny") is None or float(econ.get("capex_cny",0)) <= float(hybrid.budget_cny)
        row={"scenario_id":sid,"pv_capacity_kwp":hybrid.pv_capacity_kwp if pv_on else 0.0,"wind_turbine_count":hybrid.wind.turbine_count if wind_on else 0,"generation_kwh":m["summary"]["total_generation_kwh"],"pv_generation_kwh":m["summary"]["pv_generation_kwh"],"wind_generation_kwh":m["summary"]["wind_generation_kwh"],"self_use_kwh":m["summary"]["self_use_kwh"],"grid_import_kwh":m["summary"]["grid_import_kwh"],"grid_export_kwh":m["summary"]["grid_export_kwh"],"curtailment_kwh":m["summary"]["curtailment_kwh"],"load_coverage_rate":m["summary"]["load_coverage_rate"],"economics":econ,"budget_ok":budget_ok,"wind_metadata":wind["metadata"]}
        if include_hourly: row["hourly"]={"timestamps":times,"interval_seconds":intervals,"load_kwh":[r["load_kwh"] for r in m["intervals"]],"pv_generation_kwh":[r["pv_generation_kwh"] for r in m["intervals"]],"wind_generation_kwh":[r["wind_generation_kwh"] for r in m["intervals"]],"self_use_kwh":[r["self_use_kwh"] for r in m["intervals"]],"grid_import_kwh":[r["grid_import_kwh"] for r in m["intervals"]],"grid_export_kwh":[r["grid_export_kwh"] for r in m["intervals"]],"curtailment_kwh":[r["curtailment_kwh"] for r in m["intervals"]],"wind_speed_hub_m_s":wind["wind_speed_hub_m_s"] if wind_on else [0.0]*len(times)}
        candidates.append(row)
    complete=[x for x in candidates if x["economics"].get("status")=="complete" and x.get("budget_ok",True)]
    rec=max(complete,key=lambda x: float(x["economics"].get("npv_cny",-math.inf))) if complete else None
    service=load_result.get("summary",{}); gaps={k:float(service.get(k,0) or 0) for k in ("capacity_shortfall_hours","unmet_temp_degree_hours","unmet_rh_percent_hours")}; has_gap=any(v>1e-9 for v in gaps.values())
    return {"status":"success","calculation_version":"phase2b-wind-v1","scenario":asdict(hybrid),"tariff":tariff_meta,"profile":asdict(profile),"load_context":{"electric_load_kwh":baseline["summary"]["load_kwh"],"service_quality":{"status":"service_gap" if has_gap else "within_modeled_scope","gaps":gaps,"scope":load.get("service_scope"),"note":"存在服务缺口时不代表同等服务水平下的投资最优。" if has_gap else "未校准的城市级空调负荷情景。"}},"weather_provenance":{"source_file":weather.get("source_file"),"hash":weather.get("hash"),"context":weather.get("context"),"normalization":weather.get("weather_normalization"),"wind_input":"reuse normalized 10m wind_speed_10m; instantaneous interval-start semantics"},"baseline":baseline["summary"],"candidates":candidates,"recommendation":{"status":"conditional" if rec else "not_available","scenario_id":rec["scenario_id"] if rec else None,"reason":"在同一负荷、天气、电价和用户成本情景下，有限四方案中研究期NPV最高；不是全局优化，也不是工程审批。" if rec else "非零方案报价或外送价格不完整，不能作经济推荐。"},"notes":["S0=只购电，S1=仅光伏，S2=仅风电，S3=风光组合；同一小时级负荷与天气。","风机档案为SWCC认证系统输出，含报告列出的接口和逆变器；未额外扣逆变器损失。","风电场址、障碍物、噪声、并网和实测风况仍待现场确认。","当前负荷仅为第一阶段未校准城市级空调情景。"]}
