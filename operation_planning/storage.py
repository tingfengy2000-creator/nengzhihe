"""Ideal, non-economic storage upper bound for hourly matching.

This is deliberately a counterfactual dispatch bound.  It charges only from
otherwise-curtailed generation and discharges only to the same interval's
load deficit.  It has no price, degradation, replacement, or sizing
recommendation semantics.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


STORAGE_NOTE = (
    "ideal dispatch upper bound; excludes battery cost, degradation and "
    "replacement; not a storage recommendation"
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
    When export is enabled the upper bound is intentionally not calculated;
    the contract is for the no-export case only.
    """
    if allow_export:
        return {"status": "not_applicable", "note": STORAGE_NOTE, "reason": "仅对allow_export=false计算"}
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
        initial_curtailment = sum(curtailment)
        # The ordinary match's curtailment is the authoritative counterfactual
        # supply. Numerical tolerance protects the readable conservation row.
        charged_total = sum(charged)
        recovered_total = sum(recovered)
        remaining_total = sum(remaining)
        expected_remaining = max(0.0, initial_curtailment - charged_total)
        if abs(remaining_total - expected_remaining) > 1e-8:
            raise AssertionError("储能弃电守恒失败")
        result = {
            "capacity_kwh": capacity,
            "power_limit_kw": power_limit_kw,
            "round_trip_efficiency": float(round_trip_efficiency),
            "initial_soc_kwh": 0.0,
            "final_soc_kwh": soc,
            "recovered_kwh_year1": recovered_total,
            "charged_kwh_year1": charged_total,
            "remaining_curtailment_kwh_year1": remaining_total,
            "grid_import_kwh_year1": sum(imports),
            "additional_avoided_kgco2_year1": None,
            "conservation": {
                "curtailment_error_kwh": remaining_total - expected_remaining,
                "soc_change_kwh": soc,
                "charge_input_times_eta_kwh": charged_total * eta_one_way,
                "discharge_output_kwh": recovered_total,
                "passed": recovered_total <= charged_total * float(round_trip_efficiency) + 1e-9 and soc >= -1e-9 and soc <= capacity + 1e-9,
            },
            "note": STORAGE_NOTE,
        }
        results.append(result)
    return {"status": "calculated", "allow_export": False, "note": STORAGE_NOTE, "candidates": results}


def storage_input_from_match(match: Mapping[str, Any], *, generation_key: str = "total_generation_kwh") -> Dict[str, Any]:
    rows = list(match.get("intervals", []))
    return {
        "timestamps": [row.get("timestamp") for row in rows],
        "interval_seconds": [row.get("interval_seconds") for row in rows],
        "load_kwh": [row.get("load_kwh") for row in rows],
        "generation_kwh": [row.get(generation_key, row.get("total_generation_kwh", row.get("pv_generation_kwh", 0.0))) for row in rows],
        "self_use_kwh": [row.get("self_use_kwh", 0.0) for row in rows],
        "grid_import_kwh": [row.get("grid_import_kwh", 0.0) for row in rows],
        "curtailment_kwh": [row.get("curtailment_kwh", 0.0) for row in rows],
    }
