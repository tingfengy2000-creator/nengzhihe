"""Same-condition grid/PV/wind/hybrid comparison for phase two B.

The module deliberately keeps the four-plan comparison small, but makes the
economic and admissibility rules explicit. Physics is calculated once per
candidate; cost rows use the shared t=0/year-end convention from
``economics.py``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import math
from typing import Any, Dict, List, Optional, Sequence

from .economics import discounted_cashflow_npv, discounted_year_end, inverter_replacement_cost
from .pv import PVScenario, PVQuote, generate_pv, scenario_from_dict as pv_scenario_from_dict, _intervals, _price_vectors, DEFAULT_KWP_PER_M2
from .wind import WindScenario, WindQuote, WindTurbineProfile, generate_wind
from .project_load import require_project_load, project_load_context


def _safe_intervals(times: Sequence[str], provided: Optional[Sequence[int]]) -> List[int]:
    """Allow a one-interval arithmetic fixture while keeping real axes strict."""
    if len(times) == 1:
        if provided is None or len(provided) != 1 or int(provided[0]) <= 0:
            raise ValueError("单区间必须显式提供正的interval_seconds")
        return [int(provided[0])]
    return _intervals(times, provided)


def _finite_nonnegative(values: Sequence[Any], name: str, n: int) -> List[float]:
    if values is None or len(values) != n:
        raise ValueError(f"{name}缺失或长度不一致")
    out: List[float] = []
    for raw in values:
        if isinstance(raw, bool):
            raise ValueError(f"{name}含非数值")
        try:
            value = float(raw)
        except Exception as exc:
            raise ValueError(f"{name}含非数值") from exc
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name}含缺测、非有限或负值")
        out.append(value)
    return out


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
    # For a combined project this must be a project-level quote or an
    # explicitly confirmed inclusion. It is never inferred with max().
    shared_connection_cny: Optional[float] = None

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.pv_capacity_kwp)) or self.pv_capacity_kwp < 0:
            raise ValueError("光伏容量必须是非负有限数")
        if self.budget_cny is not None and (not math.isfinite(float(self.budget_cny)) or self.budget_cny < 0):
            raise ValueError("预算必须是非负有限数")
        if self.export_limit_kw is not None and (not math.isfinite(float(self.export_limit_kw)) or self.export_limit_kw < 0):
            raise ValueError("外送功率上限必须是非负有限数")
        if not math.isfinite(float(self.import_price_cny_per_kwh)) or self.import_price_cny_per_kwh < 0:
            raise ValueError("购电价必须是非负有限数")
        if self.export_price_cny_per_kwh is not None and (not math.isfinite(float(self.export_price_cny_per_kwh)) or self.export_price_cny_per_kwh < 0):
            raise ValueError("外送价必须是非负有限数")
        if self.study_years < 1 or not 0 <= float(self.discount_rate) < 1 or not 0 <= float(self.pv_annual_degradation) < 1:
            raise ValueError("研究年限、折现率或光伏衰减率无效")
        if self.shared_connection_cny is not None and (not math.isfinite(float(self.shared_connection_cny)) or self.shared_connection_cny < 0):
            raise ValueError("共享接入费必须是非负有限数")


def hybrid_task_from_dict(payload: Dict[str, Any], *, site_id: Optional[str] = None, year: Optional[int] = None) -> tuple[PVScenario, HybridScenario]:
    """Build the single authoritative hybrid task used by API and Agent."""
    site = str(site_id or payload.get("site_id", "guangzhou")); yr = int(year if year is not None else payload.get("year", 2024))
    pv_raw = payload.get("pv") or {}; hraw = payload.get("hybrid") or {}
    pv = pv_scenario_from_dict(pv_raw, site_id=site, year=yr)
    wind = WindScenario(**{k: v for k, v in (hraw.get("wind") or {}).items() if k in WindScenario.__dataclass_fields__})
    pv_quote = PVQuote(**{k: v for k, v in (hraw.get("pv_quote") or pv_raw.get("quote") or {}).items() if k in PVQuote.__dataclass_fields__})
    wind_quote = WindQuote(**{k: v for k, v in (hraw.get("wind_quote") or {}).items() if k in WindQuote.__dataclass_fields__})
    hvals = {k: v for k, v in hraw.items() if k in HybridScenario.__dataclass_fields__ and k not in {"wind", "pv_quote", "wind_quote"}}
    hvals.update({"site_id": site, "year": yr, "wind": wind, "pv_quote": pv_quote, "wind_quote": wind_quote})
    hvals.setdefault("import_price_cny_per_kwh", pv.import_price_cny_per_kwh)
    return pv, HybridScenario(**hvals)


def _quote_cost(q: Any, count: int, fields: Sequence[str]) -> Optional[float]:
    if count == 0:
        return 0.0
    vals = [getattr(q, field, None) for field in fields]
    if any(value is None for value in vals):
        return None
    numbers = [float(value) for value in vals]
    if any(not math.isfinite(value) or value < 0 for value in numbers):
        raise ValueError("报价必须是非负有限数")
    return float(count) * sum(numbers)


def match_hybrid(load_series: Dict[str, Any], pv_generation: Dict[str, Any], wind_generation: Dict[str, Any], *, allow_export: bool = False, export_limit_kw: Optional[float] = None, import_prices: Optional[Sequence[float]] = None, export_prices: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    lt = list(load_series.get("timestamps", [])); pt = list(pv_generation.get("timestamps", [])); wt = list(wind_generation.get("timestamps", []))
    if lt != pt or lt != wt:
        raise ValueError("负荷、光伏和风电必须使用同一时间轴")
    if allow_export and export_limit_kw is not None and (not math.isfinite(float(export_limit_kw)) or float(export_limit_kw) < 0):
        raise ValueError("外送功率上限必须是非负有限数")
    ints = _safe_intervals(lt, load_series.get("interval_seconds"))
    if ints != _safe_intervals(pt, pv_generation.get("interval_seconds")) or ints != _safe_intervals(wt, wind_generation.get("interval_seconds")):
        raise ValueError("负荷、光伏和风电时间间隔不一致")
    lp = _finite_nonnegative(load_series.get("electric_power_w", []), "负荷功率", len(lt)); pp = _finite_nonnegative(pv_generation.get("pv_ac_power_w", []), "光伏交流功率", len(lt)); wp = _finite_nonnegative(wind_generation.get("wind_power_w", []), "风电功率", len(lt))
    imp_values = None if import_prices is None else _finite_nonnegative(import_prices, "购电价格", len(lt)); exp_values = None if export_prices is None else _finite_nonnegative(export_prices, "外送价格", len(lt))
    rows: List[Dict[str, Any]] = []; sums = {key: 0.0 for key in ("load_kwh", "pv_generation_kwh", "wind_generation_kwh", "total_generation_kwh", "self_use_kwh", "grid_import_kwh", "grid_export_kwh", "curtailment_kwh", "import_cost_cny", "export_income_cny")}
    for i, sec in enumerate(ints):
        l = lp[i] * sec / 3_600_000.0; p = pp[i] * sec / 3_600_000.0; w = wp[i] * sec / 3_600_000.0; total = p + w; self_use = min(l, total); surplus = max(0.0, total - self_use)
        exp = min(surplus, float(export_limit_kw) * sec / 3600.0) if allow_export and export_limit_kw is not None else (surplus if allow_export else 0.0); cur = surplus - exp; imp = l - self_use
        pv_self = self_use * (p / total) if total > 0 else 0.0; wind_self = self_use - pv_self
        row = {"timestamp": lt[i], "interval_seconds": sec, "load_kwh": l, "pv_generation_kwh": p, "wind_generation_kwh": w, "total_generation_kwh": total, "self_use_kwh": self_use, "self_use_pv_kwh": pv_self, "self_use_wind_kwh": wind_self, "grid_import_kwh": imp, "grid_export_kwh": exp, "curtailment_kwh": cur}
        if imp_values is not None: row["import_cost_cny"] = imp * imp_values[i]; sums["import_cost_cny"] += row["import_cost_cny"]
        if exp_values is not None: row["export_income_cny"] = exp * exp_values[i]; sums["export_income_cny"] += row["export_income_cny"]
        rows.append(row)
        for key, value in (("load_kwh", l), ("pv_generation_kwh", p), ("wind_generation_kwh", w), ("total_generation_kwh", total), ("self_use_kwh", self_use), ("grid_import_kwh", imp), ("grid_export_kwh", exp), ("curtailment_kwh", cur)): sums[key] += value
    if abs(sums["load_kwh"] - sums["self_use_kwh"] - sums["grid_import_kwh"]) > 1e-7: raise AssertionError("负荷守恒失败")
    if abs(sums["total_generation_kwh"] - sums["self_use_kwh"] - sums["grid_export_kwh"] - sums["curtailment_kwh"]) > 1e-7: raise AssertionError("风光发电守恒失败")
    sums["self_consumption_rate"] = sums["self_use_kwh"] / sums["total_generation_kwh"] if sums["total_generation_kwh"] > 1e-12 else None; sums["load_coverage_rate"] = sums["self_use_kwh"] / sums["load_kwh"] if sums["load_kwh"] > 1e-12 else None
    return {"summary": sums, "intervals": rows, "export_policy": {"allow_export": allow_export, "limit_kw": export_limit_kw}}


def _connection_cost(scenario: HybridScenario, pv_on: bool, wind_on: bool, missing: List[str]) -> float:
    pq, wq = scenario.pv_quote, scenario.wind_quote
    if pv_on and wind_on:
        if scenario.shared_connection_cny is not None: return float(scenario.shared_connection_cny)
        if pq.grid_connection_cny == 0 and wq.grid_connection_cny == 0: return 0.0
        missing.append("shared_connection_cny"); return 0.0
    if pv_on:
        if pq.grid_connection_cny is None: missing.append("pv_grid_connection_cny"); return 0.0
        return float(pq.grid_connection_cny)
    if wind_on:
        if wq.grid_connection_cny is None: missing.append("wind_grid_connection_cny"); return 0.0
        return float(wq.grid_connection_cny)
    return 0.0


def _lifecycle(match: Dict[str, Any], baseline: Dict[str, Any], scenario: HybridScenario, *, pv_on: bool, wind_on: bool, load_series: Dict[str, Any], pv_generation: Dict[str, Any], wind_generation: Dict[str, Any], import_prices: Sequence[float], export_prices: Optional[Sequence[float]]) -> Dict[str, Any]:
    pv_on = pv_on and scenario.pv_capacity_kwp > 1e-12
    wind_on = wind_on and scenario.wind.turbine_count > 0
    pq, wq = scenario.pv_quote, scenario.wind_quote; missing: List[str] = []
    pv_assets = _quote_cost(pq, int(pv_on), ["module_cny_per_kwp", "inverter_cny_per_kwp", "structure_cny_per_kwp", "installation_cny_per_kwp"])
    wind_assets = _quote_cost(wq, int(wind_on), ["turbine_cny", "tower_cny", "foundation_cny", "installation_cny"])
    if pv_on:
        if pv_assets is None: missing.extend(["pv_" + field for field in ("module_cny_per_kwp", "inverter_cny_per_kwp", "structure_cny_per_kwp", "installation_cny_per_kwp") if getattr(pq, field) is None])
        else: pv_assets *= scenario.pv_capacity_kwp
        if pq.grid_connection_cny is None: missing.append("pv_grid_connection_cny")
        if pq.maintenance_cny_per_kwp_year is None: missing.append("pv_maintenance_cny_per_kwp_year")
    else: pv_assets = 0.0
    if wind_on:
        if wind_assets is None: missing.extend(["wind_" + field for field in ("turbine_cny", "tower_cny", "foundation_cny", "installation_cny") if getattr(wq, field) is None])
        if wq.grid_connection_cny is None: missing.append("wind_grid_connection_cny")
        if wq.maintenance_cny_per_year is None: missing.append("wind_maintenance_cny_per_year")
    else: wind_assets = 0.0
    connection = _connection_cost(scenario, pv_on, wind_on, missing)
    if (pv_on or wind_on) and scenario.allow_export and scenario.export_price_cny_per_kwh is None: missing.append("export_price_cny_per_kwh")
    capital_missing = [key for key in missing if "maintenance" not in key and key != "export_price_cny_per_kwh"]
    capex = None if capital_missing else float(pv_assets or 0) + float(wind_assets or 0) + connection
    base_imp = float(baseline["summary"].get("import_cost_cny", 0.0))
    if missing:
        return {"status": "incomplete", "missing": sorted(set(missing)), "capex_cny": capex, "yearly": [], "npv_cny": None, "total_cost_npv_cny": None, "incremental_npv_vs_s0_cny": None}
    rows: List[Dict[str, Any]] = [{"year": 0, "grid_import_cost_cny": 0.0, "export_income_cny": 0.0, "maintenance_cny": 0.0, "replacement_cny": 0.0, "residual_cny": 0.0, "capex_cny": capex, "net_cashflow_cny": -capex, "discounted_cny": -capex}]; year_end_cash: List[float] = []; pv_deg = 1.0
    for year in range(1, scenario.study_years + 1):
        pg = dict(pv_generation); pg["pv_ac_power_w"] = [float(value) * pv_deg for value in pv_generation.get("pv_ac_power_w", [])] if pv_on else [0.0] * len(load_series.get("timestamps", [])); wg = wind_generation if wind_on else {**wind_generation, "wind_power_w": [0.0] * len(load_series.get("timestamps", []))}
        ym = match_hybrid(load_series, pg, wg, allow_export=scenario.allow_export, export_limit_kw=scenario.export_limit_kw, import_prices=import_prices, export_prices=export_prices); imp = float(ym["summary"].get("import_cost_cny", 0.0)); export_income = float(ym["summary"].get("export_income_cny", 0.0))
        maint = (float(pq.maintenance_cny_per_kwp_year or 0) * scenario.pv_capacity_kwp if pv_on else 0.0) + (float(wq.maintenance_cny_per_year or 0) if wind_on else 0.0); replacement = 0.0
        if pv_on and pq.inverter_replacement_year and year == int(pq.inverter_replacement_year): replacement += inverter_replacement_cost(scenario.pv_capacity_kwp, pq.inverter_cny_per_kwp, pq.inverter_replacement_fraction)
        if wind_on and wq.replacement_year and year == int(wq.replacement_year): replacement += float(wq.turbine_cny or 0.0) * float(wq.replacement_fraction)
        residual = 0.0 if year != scenario.study_years else (float(pv_assets or 0.0) * float(pq.residual_fraction) if pv_on else 0.0) + (float(wind_assets or 0.0) * float(wq.residual_fraction) if wind_on else 0.0)
        cash = -(imp + maint + replacement) + export_income + residual; year_end_cash.append(cash)
        rows.append({"year": year, "grid_import_cost_cny": imp, "export_income_cny": export_income, "maintenance_cny": maint, "replacement_cny": replacement, "residual_cny": residual, "capex_cny": 0.0, "net_cashflow_cny": cash, "discounted_cny": discounted_year_end(cash, year, scenario.discount_rate), "grid_import_kwh": ym["summary"]["grid_import_kwh"], "grid_export_kwh": ym["summary"]["grid_export_kwh"], "curtailment_kwh": ym["summary"]["curtailment_kwh"]}); pv_deg *= 1.0 - float(scenario.pv_annual_degradation)
    net_npv = discounted_cashflow_npv(capex, year_end_cash, scenario.discount_rate); baseline_npv = discounted_cashflow_npv(0.0, [-base_imp] * int(scenario.study_years), scenario.discount_rate)
    total_grid = sum(float(row["grid_import_cost_cny"]) for row in rows[1:]); total_export = sum(float(row["export_income_cny"]) for row in rows[1:]); total_maint = sum(float(row["maintenance_cny"]) for row in rows[1:]); total_repl = sum(float(row["replacement_cny"]) for row in rows[1:]); total_residual = sum(float(row["residual_cny"]) for row in rows[1:]); annual_saving = base_imp - float(rows[1]["grid_import_cost_cny"]) - float(rows[1]["maintenance_cny"]) + float(rows[1]["export_income_cny"]) if len(rows) > 1 else None
    return {"status": "complete", "capex_cny": capex, "npv_cny": net_npv, "total_cost_npv_cny": -net_npv, "incremental_npv_vs_s0_cny": net_npv - baseline_npv, "yearly": rows, "baseline_import_cost_cny": base_imp, "total_grid_import_cost_cny": total_grid, "total_export_income_cny": total_export, "total_maintenance_cny": total_maint, "total_replacement_cny": total_repl, "total_residual_cny": total_residual, "total_lifecycle_spend_cny": float(capex) + total_grid - total_export + total_maint + total_repl - total_residual, "annual_saving_after_maintenance_cny": annual_saving, "simple_payback_years": float(capex) / annual_saving if annual_saving and annual_saving > 0 else None, "cashflow_convention": "capex at t=0; operating and residual values at year end"}


def run_hybrid_planning(load_result: Dict[str, Any], weather: Dict[str, Any], pv_scenario: PVScenario, hybrid: HybridScenario, profile: Optional[WindTurbineProfile] = None, *, include_hourly: bool = True) -> Dict[str, Any]:
    require_project_load(load_result)
    load = load_result.get("load_series") or {}; times = list(load.get("timestamps", []))
    if times != list(weather.get("time", [])): raise ValueError("负荷和风光天气不在同一时间区间")
    intervals = _intervals(times, load.get("interval_seconds")); weather = dict(weather); weather["interval_seconds"] = intervals; profile = profile or WindTurbineProfile.from_file()
    authoritative_pv = replace(pv_scenario, import_price_cny_per_kwh=hybrid.import_price_cny_per_kwh, allow_export=hybrid.allow_export, export_limit_kw=hybrid.export_limit_kw); prices, tariff_meta = _price_vectors(authoritative_pv, times, intervals); export_prices = [float(hybrid.export_price_cny_per_kwh)] * len(times) if hybrid.export_price_cny_per_kwh is not None else None
    pv0 = asdict(generate_pv(weather, 0.0, authoritative_pv)); pv = asdict(generate_pv(weather, hybrid.pv_capacity_kwp, authoritative_pv)); wind = generate_wind(weather, profile, hybrid.wind); wind0 = dict(wind); wind0["wind_power_w"] = [0.0] * len(times); wind0["wind_energy_kwh"] = [0.0] * len(times); wind0["metadata"] = {**wind["metadata"], "turbine_count": 0}
    combos = [("S0_grid", False, False), ("S1_pv", True, False), ("S2_wind", False, True), ("S3_pv_wind", True, True)]; candidates: List[Dict[str, Any]] = []; baseline: Optional[Dict[str, Any]] = None; roof_limit = pv_scenario.roof_area_m2 * pv_scenario.usable_fraction * DEFAULT_KWP_PER_M2
    for sid, pv_on, wind_on in combos:
        pg = pv if pv_on else pv0; wg = wind if wind_on else wind0; matched = match_hybrid(load, pg, wg, allow_export=hybrid.allow_export, export_limit_kw=hybrid.export_limit_kw, import_prices=prices, export_prices=export_prices); baseline = baseline or matched; econ = _lifecycle(matched, baseline, hybrid, pv_on=pv_on, wind_on=(wind_on and hybrid.wind.turbine_count > 0), load_series=load, pv_generation=pg, wind_generation=wg, import_prices=prices, export_prices=export_prices)
        constraint_reasons: List[str] = []
        if pv_on and hybrid.pv_capacity_kwp > roof_limit + 1e-9: constraint_reasons.append(f"光伏容量{hybrid.pv_capacity_kwp:g}kWp超过可用屋顶上限{roof_limit:g}kWp")
        if hybrid.budget_cny is not None and econ.get("capex_cny") is not None and float(econ["capex_cny"]) > float(hybrid.budget_cny) + 1e-9: constraint_reasons.append(f"初始投入超过预算{hybrid.budget_cny:g}元")
        budget_ok = hybrid.budget_cny is None or (econ.get("capex_cny") is not None and float(econ["capex_cny"]) <= float(hybrid.budget_cny) + 1e-9); status = "not_applicable" if any("屋顶" in reason for reason in constraint_reasons) else ("over_budget" if constraint_reasons else ("incomplete_quote" if econ.get("status") != "complete" else "feasible"))
        row = {"scenario_id": sid, "pv_capacity_kwp": hybrid.pv_capacity_kwp if pv_on else 0.0, "wind_turbine_count": hybrid.wind.turbine_count if wind_on else 0, "generation_kwh": matched["summary"]["total_generation_kwh"], "pv_generation_kwh": matched["summary"]["pv_generation_kwh"], "wind_generation_kwh": matched["summary"]["wind_generation_kwh"], "self_use_kwh": matched["summary"]["self_use_kwh"], "grid_import_kwh": matched["summary"]["grid_import_kwh"], "grid_export_kwh": matched["summary"]["grid_export_kwh"], "curtailment_kwh": matched["summary"]["curtailment_kwh"], "load_coverage_rate": matched["summary"]["load_coverage_rate"], "economics": econ, "budget_ok": budget_ok, "constraint_status": status, "constraint_reasons": constraint_reasons, "wind_metadata": wind["metadata"]}
        if include_hourly: row["hourly"] = {"timestamps": times, "interval_seconds": intervals, "load_kwh": [r["load_kwh"] for r in matched["intervals"]], "pv_generation_kwh": [r["pv_generation_kwh"] for r in matched["intervals"]], "wind_generation_kwh": [r["wind_generation_kwh"] for r in matched["intervals"]], "self_use_kwh": [r["self_use_kwh"] for r in matched["intervals"]], "grid_import_kwh": [r["grid_import_kwh"] for r in matched["intervals"]], "grid_export_kwh": [r["grid_export_kwh"] for r in matched["intervals"]], "curtailment_kwh": [r["curtailment_kwh"] for r in matched["intervals"]], "wind_speed_hub_m_s": wind["wind_speed_hub_m_s"] if wind_on else [0.0] * len(times)}
        candidates.append(row)
    # Known hard exclusions do not block a decision among the survivors.
    # Unknown potentially feasible candidates do: report only verified subset.
    seen = {}
    for candidate in candidates:
        key = (candidate["pv_capacity_kwp"], candidate["wind_turbine_count"])
        if key in seen:
            candidate["equivalent_to"] = seen[key]
            candidate["admission_status"] = "equivalent"
        else:
            seen[key] = candidate["scenario_id"]
            candidate["equivalent_to"] = None
            if candidate["constraint_status"] in {"not_applicable", "over_budget"}:
                candidate["admission_status"] = "excluded"
            elif candidate["economics"]["status"] != "complete":
                candidate["admission_status"] = "unknown"
            else:
                candidate["admission_status"] = "eligible"
    eligible = [x for x in candidates if x["admission_status"] == "eligible"]
    unknown = [x for x in candidates if x["admission_status"] == "unknown"]
    excluded = [x for x in candidates if x["admission_status"] == "excluded"]
    subset = max(eligible, key=lambda x: float(x["economics"]["incremental_npv_vs_s0_cny"])) if eligible else None
    status = "conditional" if subset and not unknown else ("conditional_subset" if subset and any(x["scenario_id"] != "S0_grid" for x in eligible) else "not_available")
    recommendation = {"status": status, "scenario_id": subset["scenario_id"] if status != "not_available" and subset else None,
        "complete_subset_best_scenario_id": subset["scenario_id"] if subset else None,
        "all_candidates_conclusion": "unresolved" if unknown else "resolved_with_exclusions",
        "eligible_scenario_ids": [x["scenario_id"] for x in eligible], "excluded_scenario_ids": [x["scenario_id"] for x in excluded],
        "unknown_scenario_ids": [x["scenario_id"] for x in unknown],
        "reason": ("已知硬约束不满足的候选已排除；在其余已核实可行且计价完整的有限候选中按相对S0增量NPV比较。" if not unknown else
                   "仅能给出已核实子集内最优；仍有可能适用但报价/必要条件未知的候选，全候选结论未定，不能称它们已被其他方案击败。")}
    service = load_result.get("summary", {}); gaps = {key: float(service.get(key, 0) or 0) for key in ("capacity_shortfall_hours", "unmet_temp_degree_hours", "unmet_rh_percent_hours")}; has_gap = any(value > 1e-9 for value in gaps.values())
    return {"status": "success", "calculation_version": "phase2b-semantics-5090-v1", "scenario": asdict(hybrid), "tariff": tariff_meta, "profile": asdict(profile), "load_context": {"electric_load_kwh": baseline["summary"]["load_kwh"], "room_count": load.get("room_count"), "units_per_room": load.get("units_per_room"), "project_aggregation": load.get("project_aggregation"), "service_quality": {"status": "service_gap" if has_gap else "within_modeled_scope", "gaps": gaps, "scope": load.get("service_scope"), "note": "存在服务缺口时不代表同等服务水平下的投资最优。" if has_gap else "未校准的城市级空调负荷情景。"}, "project_load_context": project_load_context(load_result)}, "weather_provenance": {"source_file": weather.get("source_file"), "hash": weather.get("hash"), "context": weather.get("context"), "normalization": weather.get("weather_normalization"), "wind_input": "reuse normalized 10m wind_speed_10m; instantaneous interval-start semantics"}, "baseline": baseline["summary"], "candidate_constraints": {"pv_capacity_limit_kwp": roof_limit, "roof_area_m2": pv_scenario.roof_area_m2, "usable_fraction": pv_scenario.usable_fraction, "budget_cny": hybrid.budget_cny, "shared_connection_cny": hybrid.shared_connection_cny}, "candidates": candidates, "recommendation": recommendation, "notes": ["S0=只购电，S1=仅光伏，S2=仅风电，S3=风光组合；同一小时级负荷与天气。", "经济字段区分total_cost_npv_cny与incremental_npv_vs_s0_cny；初始投入在t=0。", "组合接入费只采用shared_connection_cny或两个组件报价均明确为0，不再自动取max。", "风机档案为SWCC认证系统输出；当地温度/气压未参与风电输出修正。", "当前负荷仅为第一阶段未校准城市级空调情景。"]}
