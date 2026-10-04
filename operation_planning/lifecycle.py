"""Cost aggregation for first-stage equipment comparison.

Electricity is a repeated reference-year scenario unless the caller supplies a
separate weather-year series. Missing purchase or installation quotes remain
missing and prevent a complete lifecycle total; they are never treated as zero.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, Optional


def monthly_detail(rows: list[dict], price_cny_per_kwh: Optional[float] = None, quantity: int = 1) -> Dict[str, Dict[str, float]]:
    if price_cny_per_kwh is None:
        raise ValueError("逐月电费需要完整年度价格情景；缺失价格不能静默当作0")
    if quantity < 1:
        raise ValueError("数量必须至少为1")
    result: Dict[str, Dict[str, float]] = {}
    for row in rows:
        month = str(row["timestamp"])[:7]
        dt = float(row.get("interval_seconds", 3600.0))
        if dt <= 0:
            raise ValueError("负荷序列包含无效时间间隔")
        day = result.setdefault(month, {"electric_kwh": 0.0, "cooling_kwh": 0.0, "latent_kwh": 0.0, "cost_cny": 0.0, "hours": 0.0})
        factor = dt / 3600000.0 * quantity
        day["electric_kwh"] += float(row.get("electric_power_w", 0.0)) * factor
        day["cooling_kwh"] += float(row.get("delivered_cooling_w", 0.0)) * factor
        day["latent_kwh"] += float(row.get("delivered_latent_w", row.get("latent_load_w", 0.0))) * factor
        day["cost_cny"] += float(row.get("electric_power_w", 0.0)) * factor * float(price_cny_per_kwh)
        day["hours"] += dt / 3600.0
    return result


def life_cycle_cost(result: Dict[str, Any], study_years: int = 10, price_cny_per_kwh: Optional[float] = None, quantity: int = 1, discount_rate: float = 0.0, transport_cny: float = 0.0, replacement_install_cny: Optional[float] = None, residual_cny: float = 0.0, equipment_price_cny: Optional[float] = None, installation_cny: Optional[float] = None, maintenance_cny_per_year: Optional[float] = None) -> Dict[str, Any]:
    if study_years < 1 or study_years > 30:
        raise ValueError("研究期必须在1..30年")
    if not 0 <= discount_rate < 1:
        raise ValueError("折现率必须在0..1之间")
    eq = result["equipment"]
    rows = result["rows"]
    if price_cny_per_kwh is None:
        raise ValueError("长期电费需要用户确认可覆盖研究期的价格情景")
    equipment = equipment_price_cny if equipment_price_cny is not None else eq.get("price_cny")
    installation = installation_cny if installation_cny is not None else eq.get("installation_cny")
    maintenance = maintenance_cny_per_year if maintenance_cny_per_year is not None else eq.get("maintenance_cny_per_year")
    missing = [name for name, value in (("设备报价", equipment), ("安装报价", installation), ("维护报价", maintenance)) if value is None]
    if missing:
        return {"monthly": monthly_detail(rows, price_cny_per_kwh, quantity), "yearly": [], "lifecycle": {"status": "incomplete_quote", "missing": missing, "price_assumption_cny_per_kwh": price_cny_per_kwh}}
    monthly = monthly_detail(rows, price_cny_per_kwh, quantity)
    annual_electricity = sum(x["cost_cny"] for x in monthly.values())
    equipment_total = float(equipment) * quantity
    installation_total = float(installation) * quantity
    maintenance_total = float(maintenance) * quantity
    life = int(eq.get("expected_life_years") or study_years)
    replacement = 0.0; replacement_events = []
    if life < study_years:
        replacement_install_cny = installation_total if replacement_install_cny is None else float(replacement_install_cny)
        year = life
        while year < study_years:
            amount = equipment_total + replacement_install_cny
            replacement += amount / ((1.0 + discount_rate) ** year)
            replacement_events.append({"year": year, "amount_cny": amount})
            year += life
    pv_electricity = sum(annual_electricity / ((1.0 + discount_rate) ** year) for year in range(1, study_years + 1))
    pv_maintenance = sum(maintenance_total / ((1.0 + discount_rate) ** year) for year in range(1, study_years + 1))
    initial = equipment_total + installation_total + float(transport_cny)
    total = initial + pv_electricity + pv_maintenance + replacement - float(residual_cny) / ((1.0 + discount_rate) ** study_years)
    yearly = []
    for year in range(0, study_years + 1):
        repl = sum(x["amount_cny"] for x in replacement_events if x["year"] == year)
        yearly.append({"year": year, "electricity_cny": 0.0 if year == 0 else annual_electricity, "maintenance_cny": 0.0 if year == 0 else maintenance_total, "replacement_cny": repl, "cash_out_cny": initial if year == 0 else annual_electricity + maintenance_total + repl})
    return {"monthly": monthly, "yearly": yearly, "lifecycle": {"status": "complete", "study_years": study_years, "discount_rate": discount_rate, "initial_cny": initial, "equipment_cny": equipment_total, "installation_cny": installation_total, "electricity_pv_cny": pv_electricity, "maintenance_pv_cny": pv_maintenance, "replacement_pv_cny": replacement, "residual_cny": residual_cny, "total_pv_cny": total, "replacement_events": replacement_events, "price_assumption_cny_per_kwh": price_cny_per_kwh, "price_assumption_label": "用户/参考情景，非未来电价预测", "electricity_scope": "重复参考年；需多年份输入才能报告年际成本"}}