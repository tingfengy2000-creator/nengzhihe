"""Shared, explicit cash-flow conventions for PV and hybrid planning.

All investment outlays occur at t=0.  Operating cash flows are attached to
the end of their stated year and discounted with that year number.  Keeping
this convention in one module prevents the PV and hybrid engines from
silently using different NPV definitions.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence


def discounted_cashflow_npv(
    initial_outlay_cny: float,
    year_end_cashflows_cny: Sequence[float],
    discount_rate: float,
) -> float:
    """Return net cash-flow NPV with capex at t=0.

    ``initial_outlay_cny`` is a positive cost, while year-end values are net
    cash flows (positive savings/income, negative costs).  For example,
    105 paid now and 110 received at year end at 10% gives -5.
    """
    initial = float(initial_outlay_cny)
    rate = float(discount_rate)
    if not math.isfinite(initial) or initial < 0:
        raise ValueError("初始投入必须是非负有限数")
    if not math.isfinite(rate) or not 0 <= rate < 1:
        raise ValueError("折现率必须在[0,1)内")
    total = -initial
    for year, cash in enumerate(year_end_cashflows_cny, 1):
        value = float(cash)
        if not math.isfinite(value):
            raise ValueError("现金流不能含非有限值")
        total += value / ((1.0 + rate) ** year)
    return float(round(total, 12))


def discounted_year_end(value: float, year: int, discount_rate: float) -> float:
    """Discount one year-end amount using the shared year convention."""
    if year < 1:
        raise ValueError("年末现金流年份必须从1开始")
    amount = float(value)
    rate = float(discount_rate)
    if not math.isfinite(amount) or not math.isfinite(rate) or not 0 <= rate < 1:
        raise ValueError("现金流或折现率无效")
    return amount / ((1.0 + rate) ** int(year))


def present_value_of_costs(
    initial_cost_cny: float,
    year_end_costs_cny: Sequence[float],
    year_end_income_cny: Optional[Sequence[float]],
    discount_rate: float,
) -> float:
    """Return positive present value of costs net of income/residual value."""
    income = list(year_end_income_cny or [0.0] * len(year_end_costs_cny))
    if len(income) != len(year_end_costs_cny):
        raise ValueError("成本与收入年份长度不一致")
    net = [-(float(cost)) + float(value) for cost, value in zip(year_end_costs_cny, income)]
    return float(-discounted_cashflow_npv(initial_cost_cny, net, discount_rate))


def inverter_replacement_cost(capacity_kwp: float, inverter_cny_per_kwp: Optional[float], fraction: float) -> float:
    """Replacement is a fraction of the inverter quote only."""
    cap = float(capacity_kwp)
    if cap <= 1e-12:
        return 0.0
    if inverter_cny_per_kwp is None:
        raise ValueError("缺少逆变器单价")
    value = cap * float(inverter_cny_per_kwp) * float(fraction)
    if not math.isfinite(value) or value < 0:
        raise ValueError("逆变器更换费用无效")
    return float(value)
