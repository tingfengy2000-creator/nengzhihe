"""Electricity-carbon metrics for the phase-two planning reports.

The module contains no physical-model code.  It only resolves a versioned
grid-average factor and derives auditable carbon and annual-offset metrics
from already matched load/generation results.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


FACTOR_PATH = Path(__file__).resolve().parent / "data" / "carbon" / "emission_factors.json"
FACTOR_SOURCE_URL_2023 = "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/t20251231_1139517.html"
FACTOR_ATTACHMENT_URL_2023 = "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/W020251231726284332528.pdf"
FACTOR_SOURCE_URL_2022 = "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202412/t20241226_1099413.html"
REFERENCE_CARBON_PRICE_CNY_PER_T = 97.49
REFERENCE_CARBON_PRICE_SOURCE = {
    "title": "全国碳市场发展报告（2025）",
    "issuer": "生态环境部",
    "date": "2025-09",
    "basis": "报告记载2024年年底全国碳市场综合价格收盘价97.49元/吨",
    "url": "https://www.mee.gov.cn/ywgz/ydqhbh/wsqtkz/202509/W020250927515316322073.pdf",
}


def carbon_price_scenarios() -> list[Dict[str, Any]]:
    """Return explicitly labelled carbon-price scenarios for option UIs.

    These are user-selectable sensitivity inputs only.  They are deliberately
    kept separate from the emission-factor registry and never affect the main
    energy/economic recommendation.
    """
    return [{
        "carbon_price_cny_per_t": REFERENCE_CARBON_PRICE_CNY_PER_T,
        "value_cny_per_t": REFERENCE_CARBON_PRICE_CNY_PER_T,
        "source": REFERENCE_CARBON_PRICE_SOURCE["title"],
        "source_title": REFERENCE_CARBON_PRICE_SOURCE["title"],
        "source_url": REFERENCE_CARBON_PRICE_SOURCE["url"],
        "date": REFERENCE_CARBON_PRICE_SOURCE["date"],
        "note": "仅为情景，资格未核实；不代表可成交、CCER或地方碳普惠收益。",
        "qualification": "unverified_scenario",
    }]


def load_factors() -> list[Dict[str, Any]]:
    raw = json.loads(FACTOR_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("factors"), list):
        raise ValueError("排放因子文件结构无效")
    return [dict(row) for row in raw["factors"]]


def factor_catalog() -> Dict[str, Any]:
    return {
        "status": "verified_source_registry",
        "unit": "kgCO2/kWh",
        "default_selection": "site province latest year with basis=电力平均",
        "factors": load_factors(),
        "carbon_price_scenarios": carbon_price_scenarios(),
        "notes": [
            "电网平均因子用于情景估算，不是经核证的减排量。",
            "未计入光伏、风机制造、运输和回收的隐含排放。",
        ],
    }


def _site_region(site_id: str) -> Optional[str]:
    key = str(site_id or "").lower()
    if "beijing" in key or key in {"bj", "北京"}:
        return "北京"
    if "harbin" in key or key in {"hrb", "哈尔滨", "黑龙江"}:
        return "黑龙江"
    if "guangzhou" in key or key in {"gz", "广州", "广东"}:
        return "广东"
    return None


def resolve_factor(site_id: str, factor_id: Optional[str] = None) -> Dict[str, Any]:
    factors = load_factors()
    by_id = {str(row.get("factor_id")): row for row in factors}
    if factor_id:
        if factor_id not in by_id:
            raise ValueError(f"未知排放因子：{factor_id}")
        selected = by_id[factor_id]
    else:
        region = _site_region(site_id)
        candidates = [
            row for row in factors
            if row.get("basis") == "电力平均" and row.get("scope") == "省" and row.get("region") == region
        ]
        if not candidates:
            candidates = [row for row in factors if row.get("factor_id") == "grid_avg_national_2023"]
        selected = max(candidates, key=lambda row: int(row.get("data_year", 0)))
    return dict(selected)


def normalize_request(site_id: str, raw: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if raw is not None and not isinstance(raw, Mapping):
        raise ValueError("carbon必须是对象")
    request = dict(raw or {})
    if set(request) - {"factor_id", "carbon_price_cny_per_t"}:
        raise ValueError("carbon含未支持参数")
    factor_id = request.get("factor_id")
    price = request.get("carbon_price_cny_per_t")
    if price is not None:
        if isinstance(price, bool):
            raise ValueError("碳价必须是非负有限数")
        try:
            price = float(price)
        except Exception as exc:
            raise ValueError("碳价必须是非负有限数") from exc
        if not math.isfinite(price) or price < 0:
            raise ValueError("碳价必须是非负有限数")
    factor = resolve_factor(site_id, None if factor_id in (None, "") else str(factor_id))
    return {"factor": factor, "carbon_price_cny_per_t": price}


def context(site_id: str, raw: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    request = normalize_request(site_id, raw)
    comparison = resolve_factor(site_id, "grid_avg_national_2023")
    price = request["carbon_price_cny_per_t"]
    return {
        "factor": request["factor"],
        "comparison_factor": comparison,
        "carbon_price_cny_per_t": price,
        "carbon_price_note": (
            "未提供碳价；不计算碳收益情景。"
            if price is None
            else ("公开报告参考价情景，不代表本项目可成交、CCER或地方碳普惠资格。"
                  if abs(float(price) - REFERENCE_CARBON_PRICE_CNY_PER_T) < 1e-9
                  else "用户提供的碳价情景；不代表可成交、CCER或地方碳普惠资格。")
        ),
        "carbon_price_source": REFERENCE_CARBON_PRICE_SOURCE if price is not None and abs(float(price) - REFERENCE_CARBON_PRICE_CNY_PER_T) < 1e-9 else None,
        "cashflow_note": "碳收益总额不折现；碳收益现值在每年末按与费用相同折现率折现。研究期固定使用所选历史排放因子，不预测未来电网。碳收益不进入原费用推荐。",
        "scope_notes": [
            "基于电网平均排放因子的情景估算，不是经核证的减排量。",
            "不包含光伏、风机制造、运输、回收的隐含排放。",
            "只有当时用上的自发电替代电网电；弃电不计入自用减碳。",
            "外送电量单独列示，不并入avoided_kgco2。",
        ],
    }


def _number(value: Any, default: float = 0.0) -> float:
    number = float(default if value is None else value)
    if not math.isfinite(number):
        raise ValueError("碳计算输入含非有限值")
    return number


def _discounted(values: Sequence[float], rate: float) -> float:
    return sum(float(value) / ((1.0 + float(rate)) ** year) for year, value in enumerate(values, 1))


def candidate_carbon(
    *,
    site_id: str,
    request: Optional[Mapping[str, Any]],
    baseline_match: Mapping[str, Any],
    candidate_match: Mapping[str, Any],
    yearly_matches: Sequence[Mapping[str, Any]],
    economics: Mapping[str, Any],
    annual_generation_kwh: float,
    annual_load_kwh: float,
    annual_import_price_cny_per_kwh: float,
) -> Dict[str, Any]:
    """Derive carbon metrics from first-year and yearly matched results."""
    ctx = context(site_id, request)
    factor = _number(ctx["factor"]["value_kgco2_per_kwh"])
    price = ctx["carbon_price_cny_per_t"]
    base_summary = baseline_match.get("summary", {})
    cand_summary = candidate_match.get("summary", {})
    base_import = _number(base_summary.get("grid_import_kwh"))
    cand_import = _number(cand_summary.get("grid_import_kwh"))
    self_use = _number(cand_summary.get("self_use_kwh"))
    avoided_year1 = (base_import - cand_import) * factor
    # Matching conservation is the authoritative check; retain a small
    # tolerance for floating-point totals and expose the discrepancy.
    conservation_error = avoided_year1 - self_use * factor
    rows = list(yearly_matches)
    avoided_years: list[float] = []
    yearly_evidence = []
    rate = _number(economics.get("discount_rate", 0.0))
    for year, item in enumerate(rows, 1):
        summary = item.get("summary", item)
        avoided = (base_import - _number(summary.get("grid_import_kwh"))) * factor
        error = avoided - _number(summary.get("self_use_kwh")) * factor
        if abs(error) > 1e-7:
            raise AssertionError("逐年自用减碳守恒失败")
        avoided_years.append(avoided)
        yearly_evidence.append({"year": year, "grid_emissions_kgco2": _number(summary.get("grid_import_kwh")) * factor, "avoided_kgco2": avoided, "self_use_kwh": _number(summary.get("self_use_kwh")), "grid_import_kwh": _number(summary.get("grid_import_kwh")), "total_generation_kwh": _number(summary.get("total_generation_kwh", summary.get("pv_generation_kwh"))), "exported_kwh": _number(summary.get("grid_export_kwh")), "curtailed_kwh": _number(summary.get("curtailment_kwh")), "conservation_error_kgco2": error, "carbon_revenue_cny": None if price is None else avoided / 1000 * price, "carbon_revenue_present_value_cny": None if price is None else avoided / 1000 * price / ((1 + rate) ** year)})
    avoided_t = sum(avoided_years) / 1000.0
    exported = _number(cand_summary.get("grid_export_kwh"))
    curtailed = _number(cand_summary.get("curtailment_kwh"))
    generation = _number(cand_summary.get("total_generation_kwh", cand_summary.get("pv_generation_kwh", annual_generation_kwh)))
    incomplete = economics.get("status") not in {"complete", "feasible"}
    incremental = economics.get("incremental_npv_vs_s0_cny")
    cost_per_t = None
    cost_status = "incomplete_cost" if incomplete else "zero_avoided"
    if not incomplete and incremental is not None and avoided_t > 1e-12:
        cost_per_t = -_number(incremental) / avoided_t
        cost_status = "calculated_from_incremental_npv_vs_s0"
    revenue = None if price is None else avoided_t * float(price)
    revenue_pv = None if price is None else _discounted(avoided_years, rate) / 1000.0 * float(price)
    with_carbon = None if incomplete or incremental is None or revenue_pv is None else _number(incremental) + revenue_pv
    base_cost = _number(base_summary.get("import_cost_cny"), base_import * annual_import_price_cny_per_kwh)
    avg_price = base_cost / annual_load_kwh if annual_load_kwh > 1e-12 else _number(annual_import_price_cny_per_kwh)
    covered = min(max(0.0, _number(annual_generation_kwh)), max(0.0, _number(annual_load_kwh)))
    claimed_saving = covered * avg_price
    annual_offset_npv = None
    if not incomplete and economics.get("capex_cny") is not None:
        yearly = {int(row["year"]): row for row in (economics.get("yearly") or [])}
        claimed_cash: list[float] = []
        for year, physical in enumerate(yearly_evidence, 1):
            claimed_covered = min(physical["total_generation_kwh"], max(0.0, annual_load_kwh))
            row = yearly[year]
            claimed_import_cost = max(0.0, base_cost - claimed_covered * avg_price)
            claimed_cash.append(
                -claimed_import_cost
                - _number(row.get("maintenance_cny"))
                - _number(row.get("replacement_cny"))
                + _number(row.get("residual_cny"))
            )
        if claimed_cash:
            from .economics import discounted_cashflow_npv
            claimed_npv = discounted_cashflow_npv(_number(economics.get("capex_cny")), claimed_cash, rate)
            baseline_npv = discounted_cashflow_npv(0.0, [-base_cost] * len(claimed_cash), rate)
            annual_offset_npv = claimed_npv - baseline_npv
    return {
        "grid_emissions_kgco2_year1": cand_import * factor,
        "avoided_kgco2_year1": avoided_year1,
        "avoided_tco2_study_period": avoided_t,
        "curtailed_kwh_year1": curtailed,
        "curtailed_share": curtailed / generation if generation > 1e-12 else None,
        "exported_kwh_year1": exported,
        "export_avoided_kgco2_year1": exported * factor,
        "cost_per_tco2_cny": cost_per_t,
        "cost_per_tco2_status": cost_status,
        "carbon_revenue_cny_study_period": revenue,
        "carbon_revenue_present_value_cny": revenue_pv,
        "incremental_npv_with_carbon_cny": with_carbon,
        "yearly": yearly_evidence,
        "national_comparison": {"factor_id": ctx["comparison_factor"]["factor_id"], "grid_emissions_kgco2_year1": cand_import * ctx["comparison_factor"]["value_kgco2_per_kwh"], "avoided_kgco2_year1": self_use * ctx["comparison_factor"]["value_kgco2_per_kwh"]},
        "eligibility": "unverified",
        "eligibility_note": "小规模项目参与CCER/碳普惠需符合方法学与备案，本作品未核实。",
        "conservation_check": {"avoided_minus_self_use_kgco2": conservation_error, "passed": abs(conservation_error) <= 1e-7},
        "annual_offset_estimate": {
            "covered_kwh": covered,
            "claimed_coverage_rate": covered / annual_load_kwh if annual_load_kwh > 1e-12 else None,
            "claimed_avoided_kgco2": covered * factor,
            "claimed_bill_saving_cny_year1": claimed_saving,
            "claimed_incremental_npv_vs_s0_cny": annual_offset_npv,
            "electricity_price_basis": "baseline annual import bill / annual load; load-weighted mean for TOU",
            "effective_price_cny_per_kwh": avg_price,
            "export_policy": "annual net offset only; no export revenue added again",
            "participates_in_recommendation": False,
            "method": "annual net offset; ignores hourly timing; for comparison only",
        },
    }
