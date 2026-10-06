"""Project-level aggregation of the existing single-room load trace.

The heat/moisture model intentionally remains a one-room model.  This module
only performs the declared same-room aggregation needed by PV and wind/PV
matching; it does not create new rooms, orientations, schedules or equipment
models.  The adapter is idempotent so an Agent and an API route cannot apply
room_count twice.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Dict


ENERGY_SUMMARY_FIELDS = ("cooling_kwh", "sensible_cooling_kwh", "latent_cooling_kwh", "electric_kwh")
POWER_SERIES_FIELDS = ("electric_power_w", "cooling_load_w", "latent_load_w", "capacity_shortfall_w")


def _count(load_result: Dict[str, Any]) -> int:
    series = load_result.get("load_series") or {}
    room = load_result.get("room") or {}
    raw = series.get("room_count", room.get("room_count", 1))
    try:
        value = int(raw)
    except Exception as exc:
        raise ValueError("room_count 必须是正整数") from exc
    if value < 1:
        raise ValueError("room_count 必须是正整数")
    return value


def _already_project(series: Dict[str, Any]) -> bool:
    aggregation = series.get("project_aggregation") or {}
    return aggregation.get("level") == "project" or str(series.get("scope", "")).startswith("project;")


def aggregate_project_load(load_result: Dict[str, Any]) -> Dict[str, Any]:
    """Return a project-load view without changing the one-room evidence.

    Energy and power fields are multiplied once by room_count.  Duration or
    degree-hour quality metrics remain per-room because identical rooms share
    the same weather/schedule; the scope and source are explicit in the
    returned contract.
    """
    if not isinstance(load_result, dict) or not isinstance(load_result.get("load_series"), dict):
        raise ValueError("缺少可聚合的单房间load_series")
    source = load_result["load_series"]
    if _already_project(source):
        return load_result
    room_count = _count(load_result)
    result = deepcopy(load_result)
    series = result["load_series"]
    source_scope = str(series.get("scope", "one-room single-room trace"))
    for field in POWER_SERIES_FIELDS:
        values = series.get(field)
        if values is None:
            continue
        if len(values) != len(series.get("timestamps", [])):
            raise ValueError(f"单房间负荷字段长度不一致：{field}")
        scaled = []
        for raw in values:
            value = float(raw)
            if not math.isfinite(value):
                raise ValueError(f"单房间负荷含非有限值：{field}")
            scaled.append(value * room_count)
        series[field] = scaled
    summary = dict(result.get("summary") or {})
    result["single_room_summary"] = dict(summary)
    for field in ENERGY_SUMMARY_FIELDS:
        if field in summary:
            value = float(summary[field])
            if not math.isfinite(value):
                raise ValueError(f"单房间汇总含非有限值：{field}")
            summary[field] = value * room_count
    result["summary"] = summary
    series["scope"] = "project; same-room aggregation of single-room trace"
    series["project_aggregation"] = {
        "level": "project",
        "room_count": room_count,
        "source_scope": source_scope,
        "rule": "single-room units_per_room already included; multiply project load by room_count once",
    }
    series["project_room_count"] = room_count
    series["single_room_scope"] = source_scope
    result["project_load_contract"] = {
        "scope": "project",
        "room_count": room_count,
        "units_per_room": series.get("units_per_room", (result.get("room") or {}).get("units_per_room", (result.get("room") or {}).get("equipment_count", 1))),
        "source": "operation_planning.project_load.aggregate_project_load",
        "single_room_preserved": True,
    }
    return result


def project_load_context(load_result: Dict[str, Any]) -> Dict[str, Any]:
    """Small serializable context for UI/API evidence, without duplicating rows."""
    series = load_result.get("load_series") or {}
    summary = load_result.get("summary") or {}
    aggregation = series.get("project_aggregation") or {}
    return {
        "scope": series.get("scope"),
        "room_count": aggregation.get("room_count", series.get("room_count", 1)),
        "units_per_room": series.get("units_per_room", (load_result.get("room") or {}).get("units_per_room", (load_result.get("room") or {}).get("equipment_count", 1))),
        "electric_load_kwh": summary.get("electric_kwh"),
        "source": "single-room thermal trace aggregated once by room_count",
        "source_scope": aggregation.get("source_scope", series.get("scope")),
        "single_room_preserved": bool(load_result.get("single_room_summary")) or not _already_project(series),
    }


def require_project_load(load_result: Dict[str, Any]) -> None:
    """Reject an unadapted multi-room trace at direct PV/Hybrid tool entry."""
    series = load_result.get("load_series") or {}
    if _count(load_result) > 1 and not _already_project(series):
        raise ValueError("多房间风光联算需要先经过aggregate_project_load；拒绝按一间房静默计算")
