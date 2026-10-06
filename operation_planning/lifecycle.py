"""Auditable air-conditioner lifecycle and tariff aggregation.

The thermal trace is for one room and already contains ``units_per_room``.
Lifecycle aggregation therefore applies ``room_count`` to energy exactly once,
while quote multiplication follows an explicit quote scope.  The old
``quantity`` argument remains as a compatibility alias for room_count and is
reported as such in the result; new API requests should use the named fields.
"""
from __future__ import annotations

from datetime import date, datetime, time
import math
from typing import Any, Dict, Optional

from .tariffs import TariffProfile, integrate_power


def _finite(value: Any, name: str, *, nonnegative: bool = False) -> float:
    number = float(value)
    if not math.isfinite(number) or (nonnegative and number < 0):
        qualifier = "非负" if nonnegative else "有效"
        raise ValueError(f"{name} 必须为有限且{qualifier}数")
    return number


def _calendar_date(value: str | date | None, fallback: str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value or fallback)[:10])


def _timeline_seconds(timestamp: str, calendar_start: date) -> float:
    parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    # Billing profiles are local-calendar profiles. Keep the clock fields and
    # compare on a naive local timeline rather than silently converting zones.
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    origin = datetime.combine(calendar_start, time.min)
    return (parsed - origin).total_seconds()


def _tariff_cost(rows: list[dict], tariff: TariffProfile, calendar_start: date) -> float:
    """Use tariffs.integrate_power while keeping a monthly result breakdown."""
    if not rows:
        return 0.0
    times: list[float] = []
    powers: list[float] = []
    for row in rows:
        start = _timeline_seconds(str(row["timestamp"]), calendar_start)
        interval = _finite(row.get("interval_seconds", 3600.0), "负荷时间间隔")
        if interval <= 0:
            raise ValueError("负荷序列包含无效时间间隔")
        power = _finite(row.get("electric_power_w", 0.0), "空调功率", nonnegative=True)
        # Duplicate each endpoint so every source interval is constant-power.
        # Price boundaries, midnight and custom boundaries are split by the
        # shared tariffs.integrate_power implementation.
        times.extend([start, start + interval])
        powers.extend([power, power])
    return integrate_power(times, powers, tariff, calendar_start, min(times), max(times), timeline_origin=0.0)[0]


def monthly_detail(
    rows: list[dict],
    price_cny_per_kwh: Optional[float] = None,
    quantity: int = 1,
    *,
    tariff_profile: Optional[TariffProfile] = None,
    calendar_start: str | date | None = None,
) -> Dict[str, Dict[str, float]]:
    """Aggregate one-room rows by month and apply one explicit price source."""
    if tariff_profile is not None and price_cny_per_kwh is not None:
        raise ValueError("恒价与TariffProfile不能同时提供")
    if tariff_profile is None and price_cny_per_kwh is None:
        raise ValueError("逐月电费需要恒价或完整TariffProfile；缺失价格不能静默当作0")
    if int(quantity) < 1:
        raise ValueError("房间数量必须至少为1")
    quantity = int(quantity)
    constant_price = None if price_cny_per_kwh is None else _finite(price_cny_per_kwh, "恒价", nonnegative=True)
    if not rows:
        return {}
    first_timestamp = str(rows[0]["timestamp"])
    billing_start = _calendar_date(calendar_start, first_timestamp)
    result: Dict[str, Dict[str, float]] = {}
    groups: Dict[str, list[dict]] = {}
    for row in rows:
        month = str(row["timestamp"])[:7]
        groups.setdefault(month, []).append(row)
        dt = _finite(row.get("interval_seconds", 3600.0), "负荷时间间隔")
        if dt <= 0:
            raise ValueError("负荷序列包含无效时间间隔")
        power = _finite(row.get("electric_power_w", 0.0), "空调功率", nonnegative=True)
        cooling = _finite(row.get("delivered_cooling_w", 0.0), "制冷功率", nonnegative=True)
        latent = _finite(row.get("delivered_latent_w", row.get("latent_load_w", 0.0)), "潜热功率", nonnegative=True)
        day = result.setdefault(month, {"electric_kwh": 0.0, "cooling_kwh": 0.0, "latent_kwh": 0.0, "cost_cny": 0.0, "hours": 0.0})
        factor = dt / 3_600_000.0 * quantity
        day["electric_kwh"] += power * factor
        day["cooling_kwh"] += cooling * factor
        day["latent_kwh"] += latent * factor
        day["hours"] += dt / 3600.0
        if constant_price is not None:
            day["cost_cny"] += power * factor * constant_price
    if tariff_profile is not None:
        for month, month_rows in groups.items():
            result[month]["cost_cny"] = _tariff_cost(month_rows, tariff_profile, billing_start) * quantity
    return result


def life_cycle_cost(
    result: Dict[str, Any],
    study_years: int = 10,
    price_cny_per_kwh: Optional[float] = None,
    quantity: int = 1,
    discount_rate: float = 0.0,
    transport_cny: float = 0.0,
    replacement_install_cny: Optional[float] = None,
    residual_cny: float = 0.0,
    equipment_price_cny: Optional[float] = None,
    installation_cny: Optional[float] = None,
    maintenance_cny_per_year: Optional[float] = None,
    *,
    room_count: Optional[int] = None,
    units_per_room: Optional[int] = None,
    expected_life_years: Optional[int] = None,
    warranty_years: Optional[int] = None,
    quote_scope: str = "per_unit",
    tariff_profile: Optional[TariffProfile] = None,
    calendar_start: str | date | None = None,
) -> Dict[str, Any]:
    """Return a lifecycle ledger with explicit room, quote and life semantics."""
    if study_years < 1 or study_years > 30:
        raise ValueError("研究期必须在1..30年")
    discount_rate = _finite(discount_rate, "折现率", nonnegative=True)
    if discount_rate >= 1:
        raise ValueError("折现率必须在0..1之间")
    if tariff_profile is None and price_cny_per_kwh is None:
        raise ValueError("长期电费需要恒价或TariffProfile情景")
    if tariff_profile is not None and price_cny_per_kwh is not None:
        raise ValueError("恒价与TariffProfile不能同时提供")

    room = result.get("room", {}) or {}
    inferred_units = int(room.get("units_per_room", room.get("equipment_count", 1)))
    if room_count is None:
        room_count = int(quantity)
        quantity_semantics = "legacy_quantity_as_room_count"
    else:
        room_count = int(room_count)
        quantity_semantics = "explicit_room_count"
        if int(quantity) != 1 and int(quantity) != room_count:
            raise ValueError("quantity 与 room_count 不一致；请只提供 room_count")
    if room_count < 1:
        raise ValueError("room_count 必须至少为1")
    if units_per_room is None:
        units_per_room = inferred_units
    else:
        units_per_room = int(units_per_room)
        if units_per_room != inferred_units:
            raise ValueError("units_per_room 与热模型结果不一致；不能重新乘用电量")
    if units_per_room < 1:
        raise ValueError("units_per_room 必须至少为1")
    quote_scope = str(quote_scope)
    if quote_scope not in {"per_unit", "per_room", "project"}:
        raise ValueError("quote_scope 必须为 per_unit、per_room 或 project")
    quote_quantity = {"per_unit": room_count * units_per_room, "per_room": room_count, "project": 1}[quote_scope]

    eq = result["equipment"]
    rows = result["rows"]
    equipment = equipment_price_cny if equipment_price_cny is not None else eq.get("price_cny")
    installation = installation_cny if installation_cny is not None else eq.get("installation_cny")
    maintenance = maintenance_cny_per_year if maintenance_cny_per_year is not None else eq.get("maintenance_cny_per_year")
    missing = [name for name, value in (("设备报价", equipment), ("安装报价", installation), ("维护报价", maintenance)) if value is None]
    for name, value in (("设备报价", equipment), ("安装报价", installation), ("维护报价", maintenance)):
        if value is not None:
            _finite(value, name, nonnegative=True)
    if transport_cny < 0 or residual_cny < 0:
        raise ValueError("共享费用和残值不能为负")

    monthly = monthly_detail(rows, price_cny_per_kwh, room_count, tariff_profile=tariff_profile, calendar_start=calendar_start)
    annual_electricity = sum(x["cost_cny"] for x in monthly.values())
    price_metadata: Dict[str, Any] = {
        "price_assumption_cny_per_kwh": price_cny_per_kwh,
        "price_assumption_label": "用户/参考情景，非未来电价预测" if price_cny_per_kwh is not None else "TariffProfile按区间切分；需确认有效期与评价日映射",
    }
    if tariff_profile is not None:
        price_metadata.update({"tariff_id": tariff_profile.tariff_id, "tariff_version": tariff_profile.version, "tariff_effective_start": tariff_profile.effective_start, "tariff_effective_end": tariff_profile.effective_end})
    if missing:
        return {"monthly": monthly, "yearly": [], "lifecycle": {"status": "incomplete_quote", "missing": missing, "room_count": room_count, "units_per_room": units_per_room, "quote_scope": quote_scope, "quote_quantity": quote_quantity, "quantity_semantics": quantity_semantics, "study_years": study_years, **price_metadata}}

    equipment_total = float(equipment) * quote_quantity
    installation_total = float(installation) * quote_quantity
    maintenance_total = float(maintenance) * quote_quantity
    life = int(expected_life_years if expected_life_years is not None else (eq.get("expected_life_years") or study_years))
    if life < 1 or life > 100:
        raise ValueError("预计使用寿命必须在1..100年")
    if warranty_years is not None:
        warranty_years = int(warranty_years)
        if warranty_years < 0 or warranty_years > 100:
            raise ValueError("保修期必须在0..100年")
    replacement = 0.0
    replacement_events = []
    if life < study_years:
        replacement_install_total = installation_total if replacement_install_cny is None else _finite(replacement_install_cny, "更换安装费用", nonnegative=True)
        year = life
        while year < study_years:
            amount = equipment_total + replacement_install_total
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
    lifecycle = {
        "status": "complete", "study_years": study_years, "expected_life_years": life,
        "expected_life_source": "user_scenario_override" if expected_life_years is not None else "equipment_catalog_default",
        "warranty_years": warranty_years, "discount_rate": discount_rate,
        "initial_cny": initial, "equipment_cny": equipment_total, "installation_cny": installation_total,
        "electricity_pv_cny": pv_electricity, "maintenance_pv_cny": pv_maintenance,
        "replacement_pv_cny": replacement, "residual_cny": residual_cny, "total_pv_cny": total,
        "replacement_events": replacement_events, "room_count": room_count, "units_per_room": units_per_room,
        "quote_scope": quote_scope, "quote_quantity": quote_quantity, "quantity_semantics": quantity_semantics,
        "energy_scope": "单房间热模型已包含units_per_room；总用电仅按room_count聚合",
        **price_metadata, "electricity_scope": "重复参考年；需多年份输入才能报告年际成本",
    }
    return {"monthly": monthly, "yearly": yearly, "lifecycle": lifecycle}
