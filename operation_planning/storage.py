"""Surplus-energy add-on calculations.

The ordinary PV/wind candidates and their recommendation are deliberately
unchanged.  This module exposes two independent *what-if* paths from the same
no-storage surplus: an ideal battery upper bound and a coarse grid-export
estimate.  Neither path is a fifth generation scheme or a recommendation
engine.  Numeric values are calculated here; the UI only renders the result.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


STORAGE_NOTE = (
    "ideal dispatch upper bound; excludes battery degradation and temperature "
    "effects, peak/off-peak arbitrage and optimization; not a storage recommendation"
)

EXPORT_NOTE = (
    "coarse surplus-export estimate; grid interconnection, tariff and "
    "settlement require local utility approval"
)


def _finite_nonnegative(values: Sequence[Any], name: str, n: int) -> List[float]:
    if values is None or len(values) != n:
        raise ValueError(f"{name}缺失或长度不一致")
    out: List[float] = []
    for raw in values:
        if isinstance(raw, bool):
            raise ValueError(f"{name}含非数值")
        value = float(raw)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name}含缺测、非有限或负值")
        out.append(value)
    return out


def ideal_storage_upper_bound(
    intervals: Mapping[str, Sequence[Any]],
    *,
    capacities_kwh: Iterable[float],
    round_trip_efficiency: float = 0.90,
    allow_export: bool = False,
) -> Dict[str, Any]:
    """Return ideal dispatch results for each requested battery capacity.

    ``intervals`` contains kWh values after the ordinary no-storage match.
    Storage is calculated even when export is enabled: the two paths are
    independent counterfactuals and both start from ``generation-self_use``.
    This avoids silently treating exported surplus as if it did not exist.
    """
    timestamps = list(intervals.get("timestamps", []))
    seconds = [int(x) for x in intervals.get("interval_seconds", [])]
    n = len(seconds)
    if n == 0:
        raise ValueError("储能上限需要至少一个时间区间")
    if timestamps and len(timestamps) != n:
        raise ValueError("储能时间轴长度不一致")
    load = _finite_nonnegative(intervals.get("load_kwh", []), "负荷电量", n)
    generation = _finite_nonnegative(intervals.get("generation_kwh", intervals.get("total_generation_kwh", [])), "发电电量", n)
    self_use = _finite_nonnegative(intervals.get("self_use_kwh", []), "自用电量", n)
    grid_import = _finite_nonnegative(intervals.get("grid_import_kwh", []), "购电电量", n)
    curtailment = _finite_nonnegative(intervals.get("curtailment_kwh", []), "弃电量", n)
    if not math.isfinite(float(round_trip_efficiency)) or not 0 < float(round_trip_efficiency) <= 1:
        raise ValueError("往返效率必须在(0,1]")
    eta_one_way = math.sqrt(float(round_trip_efficiency))
    results: List[Dict[str, Any]] = []
    for raw_capacity in capacities_kwh:
        capacity = float(raw_capacity)
        if not math.isfinite(capacity) or capacity < 0:
            raise ValueError("储能容量必须是非负有限数")
        power_limit_kw = capacity / 2.0
        soc = 0.0
        recovered: List[float] = []
        charged: List[float] = []
        remaining: List[float] = []
        imports: List[float] = []
        for idx, sec in enumerate(seconds):
            hours = float(sec) / 3600.0
            power_bound = power_limit_kw * hours
            direct = min(load[idx], generation[idx])
            surplus = max(0.0, generation[idx] - direct)
            deficit = max(0.0, load[idx] - direct)
            # With allow_export=True, ordinary ``curtailment`` can be zero
            # because the same surplus was exported.  The independent battery
            # path still sees the physical surplus.  Only the load balance is
            # authoritative for this check.
            if abs(deficit - grid_import[idx]) > 1e-7 or direct > generation[idx] + 1e-7:
                raise ValueError("储能输入必须来自同一无储能匹配的弃电与购电")
            # Charge from curtailment only. Input energy is reported as
            # charged_kwh; internal SOC receives the one-way efficiency.
            charge_in = min(surplus, power_bound, max(0.0, (capacity - soc) / eta_one_way)) if capacity > 0 else 0.0
            soc += charge_in * eta_one_way
            discharge = min(deficit, power_bound, soc * eta_one_way) if capacity > 0 else 0.0
            soc -= discharge / eta_one_way
            charged.append(charge_in)
            recovered.append(discharge)
            remaining.append(max(0.0, surplus - charge_in))
            imports.append(max(0.0, deficit - discharge))
        initial_surplus = sum(max(0.0, generation[i] - self_use[i]) for i in range(n))
        # ``remaining_curtailment`` is retained for API compatibility.  It is
        # the remaining physical surplus in this independent path, including
        # energy that the ordinary export path would have sent to the grid.
        charged_total = sum(charged)
        recovered_total = sum(recovered)
        remaining_total = sum(remaining)
        expected_remaining = max(0.0, initial_surplus - charged_total)
        if abs(remaining_total - expected_remaining) > 1e-8:
            raise AssertionError("储能弃电守恒失败")
        expected_soc = charged_total * eta_one_way - recovered_total / eta_one_way
        soc_balance_error = soc - expected_soc
        result = {
            "capacity_kwh": capacity,
            "power_limit_kw": power_limit_kw,
            "round_trip_efficiency": float(round_trip_efficiency),
            "initial_soc_kwh": 0.0,
            "final_soc_kwh": soc,
            "recovered_kwh_year1": recovered_total,
            "charged_kwh_year1": charged_total,
            "remaining_curtailment_kwh_year1": remaining_total,
            "remaining_surplus_kwh_year1": remaining_total,
            "grid_import_kwh_year1": sum(imports),
            "additional_avoided_kgco2_year1": None,
            "conservation": {
                "curtailment_error_kwh": remaining_total - expected_remaining,
                "surplus_error_kwh": remaining_total - expected_remaining,
                "soc_change_kwh": soc,
                "charge_input_times_eta_kwh": charged_total * eta_one_way,
                "discharge_output_kwh": recovered_total,
                "soc_balance_error_kwh": soc_balance_error,
                "passed": abs(soc_balance_error) <= 1e-8 and recovered_total <= charged_total * float(round_trip_efficiency) + 1e-9 and soc >= -1e-9 and soc <= capacity + 1e-9,
            },
            "note": STORAGE_NOTE,
        }
        results.append(result)
    return {"status": "calculated", "allow_export": bool(allow_export), "note": STORAGE_NOTE, "candidates": results}


def storage_input_from_match(match: Mapping[str, Any], *, generation_key: str = "total_generation_kwh", import_prices: Optional[Sequence[Any]] = None) -> Dict[str, Any]:
    rows = list(match.get("intervals", []))
    if rows:
        result = {
            "timestamps": [row.get("timestamp") for row in rows],
            "interval_seconds": [row.get("interval_seconds") for row in rows],
            "load_kwh": [row.get("load_kwh") for row in rows],
            "generation_kwh": [row.get(generation_key, row.get("total_generation_kwh", row.get("pv_generation_kwh", 0.0))) for row in rows],
            "self_use_kwh": [row.get("self_use_kwh", 0.0) for row in rows],
            "grid_import_kwh": [row.get("grid_import_kwh", 0.0) for row in rows],
            "curtailment_kwh": [row.get("curtailment_kwh", 0.0) for row in rows],
        }
    else:
        # PV ``match_load`` stores arrays under interval_kwh rather than rows.
        arrays = match.get("interval_kwh") or {}
        result = {
            "timestamps": list(arrays.get("timestamps", [])),
            "interval_seconds": list(match.get("interval_seconds", [])),
            "load_kwh": list(arrays.get("load", [])),
            "generation_kwh": list(arrays.get("pv_generation", arrays.get("generation", []))),
            "self_use_kwh": list(arrays.get("self_use", [])),
            "grid_import_kwh": list(arrays.get("grid_import", [])),
            "curtailment_kwh": list(arrays.get("curtailment", [])),
        }
    if import_prices is not None:
        result["import_prices_cny_per_kwh"] = list(import_prices)
    return result


def _quote_number(quote: Mapping[str, Any], key: str) -> Optional[float]:
    value = quote.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"storage.quote.{key}必须是非负有限数")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"storage.quote.{key}必须是非负有限数")
    return value


def _storage_economics(
    upper: Mapping[str, Any],
    intervals: Mapping[str, Sequence[Any]],
    *,
    quote: Optional[Mapping[str, Any]],
    import_prices: Optional[Sequence[Any]],
    study_years: int,
) -> Dict[str, Any]:
    """Attach simple, undiscounted economics to ideal dispatch rows."""
    years = int(study_years)
    if years < 1:
        raise ValueError("storage.study_years必须是正整数")
    prices = None
    if import_prices is not None:
        prices = _finite_nonnegative(import_prices, "储能分时购电价", len(intervals.get("load_kwh", [])))
    elif intervals.get("import_prices_cny_per_kwh") is not None:
        prices = _finite_nonnegative(intervals.get("import_prices_cny_per_kwh"), "储能分时购电价", len(intervals.get("load_kwh", [])))
    q = dict(quote or {})
    parsed = {key: _quote_number(q, key) for key in ("cny_per_kwh", "installation_cny", "installation_cny_per_kwh", "maintenance_cny_per_year")}
    life_raw = q.get("life_years")
    life = None if life_raw is None else int(life_raw)
    if life is not None and life < 1:
        raise ValueError("storage.quote.life_years必须是正整数")
    missing = [key for key, value in parsed.items() if key not in {"installation_cny", "installation_cny_per_kwh"} and value is None]
    if parsed["installation_cny"] is None and parsed["installation_cny_per_kwh"] is None:
        missing.append("installation_cny_or_installation_cny_per_kwh")
    if life is None:
        missing.append("life_years")
    result_rows: List[Dict[str, Any]] = []
    for row in upper.get("candidates", []):
        capacity = float(row["capacity_kwh"])
        recovered = float(row.get("recovered_kwh_year1", 0.0))
        replacements = 0.0
        total_spend = None
        if prices is None:
            annual_saving = None
        else:
            # Dispatch output is aligned with the source interval order.  A
            # compact per-interval recovered series is not retained by the
            # upper-bound API, so recompute its value using a second one-row
            # run only when prices are supplied.  The upper-bound totals stay
            # authoritative for physical values.
            annual_saving = _recovered_value_from_trace(intervals, capacity, float(row.get("round_trip_efficiency", 0.90)), prices)
        if capacity <= 1e-12:
            economics_status = "complete"
            capex = 0.0
            annual_saving = 0.0
            annual_net = 0.0
            period_net = 0.0
            total_spend = 0.0
            payback = None
            payback_reason = "容量为0，不安装储能"
        elif missing or prices is None:
            economics_status = "incomplete"
            capex = None
            annual_net = None
            period_net = None
            payback = None
            payback_reason = "缺少储能报价或分时购电价"
        else:
            economics_status = "complete"
            installation_fixed = parsed["installation_cny"]
            installation_variable = parsed["installation_cny_per_kwh"]
            installation_cost = float(installation_fixed) if installation_fixed is not None else capacity * float(installation_variable)
            capex = capacity * float(parsed["cny_per_kwh"]) + installation_cost
            annual_net = float(annual_saving) - float(parsed["maintenance_cny_per_year"])
            # A replacement is needed only when another operating year remains;
            # a battery that reaches the research-period endpoint is not bought
            # again solely at the endpoint.
            replacements = sum(capex for year in range(life, years, life)) if life else 0.0
            total_spend = capex + float(parsed["maintenance_cny_per_year"]) * years + replacements
            period_net = float(annual_net) * years - capex - replacements
            payback = capex / annual_net if annual_net > 0 and capex > 0 and capex / annual_net <= life else None
            payback_reason = None if payback is not None else ("年净收益不为正" if annual_net <= 0 else "回本年限超过电池寿命")
        generation = sum(_finite_nonnegative(intervals.get("generation_kwh", []), "发电量", len(intervals.get("load_kwh", []))))
        direct_self = sum(_finite_nonnegative(intervals.get("self_use_kwh", []), "自用电量", len(intervals.get("load_kwh", []))))
        before_rate = direct_self / generation if generation > 1e-12 else None
        after_rate = min(1.0, (direct_self + recovered) / generation) if generation > 1e-12 else None
        result_rows.append({**row, "economics_status": economics_status, "initial_investment_cny": capex, "installation_cny": parsed["installation_cny"], "installation_cny_per_kwh": parsed["installation_cny_per_kwh"], "annual_bill_saving_cny": annual_saving, "annual_saving_cny": annual_saving, "annual_net_benefit_cny": annual_net, "annual_net_saving_cny": annual_net, "study_period_total_cost_cny": total_spend, "study_period_total_spend_cny": total_spend, "study_period_net_benefit_cny": period_net, "simple_payback_years": payback, "payback_years": payback, "payback_status": payback_reason, "replacement_count": 0 if life is None else sum(1 for year in range(life, years, life)), "self_consumption_rate_before": before_rate, "self_consumption_rate_after": after_rate, "self_consumption_rate_delta": None if before_rate is None or after_rate is None else after_rate - before_rate, "quote_source": q.get("source"), "quote_source_url": q.get("source_url"), "quote_source_note": q.get("source_note"), "economics_note": "研究期内净收益为不折现粗算；寿命到期且研究期仍继续时按同一初始投入更换，未计衰减与温度影响。"})
    complete = [r for r in result_rows if r["economics_status"] == "complete"]
    complete_nonzero = [r for r in complete if float(r["capacity_kwh"]) > 0]
    recommendation = None
    rec_note = "缺少报价或分时购电价，不能判断储能是否值得安装"
    if complete_nonzero and all(float(r.get("study_period_net_benefit_cny") or 0.0) <= 0 for r in complete_nonzero):
        recommendation = 0.0
        rec_note = "按当前报价不建议装储能"
    elif complete_nonzero:
        recommendation = max(complete, key=lambda r: float(r.get("study_period_net_benefit_cny") or 0.0))["capacity_kwh"]
        rec_note = "附加储能粗算中研究期净收益最高；不改变主方案推荐"
    return {"status": "calculated", "study_years": years, "candidates": result_rows, "recommended_capacity_kwh": recommendation, "recommendation_note": rec_note, "economics_basis": "年末不折现；按放电所在小时分时购电价节省；不进入四方案推荐"}


def _recovered_value_from_trace(intervals: Mapping[str, Sequence[Any]], capacity: float, eta: float, prices: Sequence[float]) -> float:
    """Replay dispatch to value recovered energy at its actual import price."""
    loads = _finite_nonnegative(intervals.get("load_kwh", []), "负荷电量", len(intervals.get("load_kwh", [])))
    generation = _finite_nonnegative(intervals.get("generation_kwh", []), "发电量", len(loads))
    secs = [int(x) for x in intervals.get("interval_seconds", [])]
    if len(secs) != len(loads) or len(prices) != len(loads):
        raise ValueError("储能计价时间序列长度不一致")
    eta_one = math.sqrt(float(eta)); soc = 0.0; value = 0.0
    for load, gen, sec, price in zip(loads, generation, secs, prices):
        direct = min(load, gen); surplus = max(0.0, gen - direct); deficit = max(0.0, load - direct); bound = capacity / 2.0 * sec / 3600.0
        charge = min(surplus, bound, max(0.0, (capacity - soc) / eta_one)) if capacity > 0 else 0.0
        soc += charge * eta_one
        discharge = min(deficit, bound, soc * eta_one) if capacity > 0 else 0.0
        soc -= discharge / eta_one
        value += discharge * float(price)
    return value


def _export_economics(intervals: Mapping[str, Sequence[Any]], *, export: Optional[Mapping[str, Any]], study_years: int) -> Dict[str, Any]:
    loads = _finite_nonnegative(intervals.get("load_kwh", []), "负荷电量", len(intervals.get("load_kwh", [])))
    generation = _finite_nonnegative(intervals.get("generation_kwh", []), "发电量", len(loads))
    self_use = _finite_nonnegative(intervals.get("self_use_kwh", []), "自用电量", len(loads))
    surplus = sum(max(0.0, g - s) for g, s in zip(generation, self_use))
    req = dict(export or {}); price = _quote_number(req, "price_cny_per_kwh")
    connection_missing = req.get("connection_cny") is None
    connection_raw = 0.0 if connection_missing else req.get("connection_cny"); connection = _quote_number({"connection_cny": connection_raw}, "connection_cny")
    years = int(study_years)
    annual_revenue = None if price is None else surplus * price
    study_revenue = None if price is None else surplus * price * years
    row = {"surplus_kwh_year1": surplus, "sold_kwh_year1": surplus, "annual_sell_kwh": surplus, "price_cny_per_kwh": price, "connection_cny": connection, "connection_cost_assumed_zero": connection_missing, "connection_note": "未填写并网投入，按0元粗算" if connection_missing else "采用用户填写的并网投入", "source": req.get("source"), "source_url": req.get("source_url"), "source_note": req.get("source_note"), "economics_status": "complete" if price is not None else "incomplete", "annual_revenue_cny": annual_revenue, "annual_income_cny": annual_revenue, "study_period_revenue_cny": study_revenue, "study_period_income_cny": study_revenue, "simple_payback_years": None if price is None or price <= 0 or connection <= 0 else connection / (surplus * price) if surplus > 0 else None, "payback_status": None if price is not None and price > 0 and connection > 0 and surplus > 0 else ("无并网投入" if connection == 0 else "缺少上网电价或没有可卖余电"), "note": EXPORT_NOTE}
    return {"status": "calculated", "study_years": years, "path": row, "options": [{"price_cny_per_kwh": price, "source": req.get("source")}]}


def surplus_paths_from_match(
    intervals: Mapping[str, Sequence[Any]],
    *,
    capacities_kwh: Iterable[float],
    round_trip_efficiency: float = 0.90,
    allow_export: bool = False,
    storage_quote: Optional[Mapping[str, Any]] = None,
    export: Optional[Mapping[str, Any]] = None,
    import_prices: Optional[Sequence[Any]] = None,
    study_years: int = 10,
) -> Dict[str, Any]:
    """Build the additive ``surplus_paths`` response contract."""
    upper = ideal_storage_upper_bound(intervals, capacities_kwh=capacities_kwh, round_trip_efficiency=round_trip_efficiency, allow_export=allow_export)
    upper = _storage_economics(upper, intervals, quote=storage_quote, import_prices=import_prices, study_years=study_years)
    export_result = _export_economics(intervals, export=export, study_years=study_years)
    generation = _finite_nonnegative(intervals.get("generation_kwh", []), "发电量", len(intervals.get("load_kwh", [])))
    self_use = _finite_nonnegative(intervals.get("self_use_kwh", []), "自用电量", len(intervals.get("load_kwh", [])))
    surplus = sum(max(0.0, g - s) for g, s in zip(generation, self_use))
    return {"surplus_kwh_year1": surplus, "storage": upper, "export": export_result, "note": "储能与卖电从同一份无储能物理余电独立计算，二者不是联合优化；不改变S0–S3和主推荐。"}
