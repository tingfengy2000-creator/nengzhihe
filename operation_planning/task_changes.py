"""One bounded modification schema for hybrid API, rules and local model.

No unrecognized field is silently ignored. Absolute and relative budget
representations are compared against the original budget, then applied once.
"""
from __future__ import annotations
import copy
import math
import re
from typing import Any, Dict


class ModificationConflict(ValueError):
    pass


ROOM_PROPERTIES = {"start_hour": {"type": "integer", "minimum": 0, "maximum": 23},
                   "end_hour": {"type": "integer", "minimum": 1, "maximum": 24},
                   "room_count": {"type": "integer", "minimum": 1},
                   "units_per_room": {"type": "integer", "minimum": 1},
                   "area_m2": {"type": "number", "exclusiveMinimum": 0}}
WIND_PROPERTIES = {"turbine_count": {"type": "integer", "enum": [0, 1]},
                   "hub_height_m": {"type": "number", "exclusiveMinimum": 0},
                   "hub_height_max_m": {"type": "number", "exclusiveMinimum": 0}}
HYBRID_PROPERTIES = {name: {"type": "number", "minimum": 0} for name in
                     ("budget_cny", "budget_multiplier", "pv_capacity_kwp", "import_price_cny_per_kwh")}
HYBRID_PROPERTIES["tariff_escalation_rate"] = {"type": "number", "minimum": -0.05, "maximum": 0.10}
HYBRID_PROPERTIES.update({"allow_export": {"type": "boolean"},
                          "export_price_cny_per_kwh": {"type": ["number", "null"], "minimum": 0},
                          "wind": {"type": "object", "properties": WIND_PROPERTIES, "additionalProperties": False}})
MODIFICATION_SCHEMA = {"type": "object", "properties": {
    "room": {"type": "object", "properties": ROOM_PROPERTIES, "additionalProperties": False},
    "hybrid": {"type": "object", "properties": HYBRID_PROPERTIES, "additionalProperties": False}},
    "additionalProperties": False}


def validate_modifications(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("修改必须是对象")
    if set(raw) - {"room", "hybrid"}:
        raise ValueError("不支持的修改字段：" + ",".join(sorted(set(raw) - {"room", "hybrid"})))
    out = copy.deepcopy(raw)
    for group, allowed in (("room", ROOM_PROPERTIES), ("hybrid", HYBRID_PROPERTIES)):
        values = out.get(group, {})
        if not isinstance(values, dict) or set(values) - set(allowed):
            raise ValueError(f"{group}含不支持的修改字段")
        for name, value in values.items():
            if name == "wind":
                if not isinstance(value, dict) or set(value) - set(WIND_PROPERTIES):
                    raise ValueError("hybrid.wind含不支持的修改字段")
                checks = value.items()
            else:
                checks = [(name, value)]
            for key, number in checks:
                if key == "allow_export":
                    if not isinstance(number, bool): raise ValueError("allow_export必须为布尔值")
                    continue
                if key == "export_price_cny_per_kwh" and number is None: continue
                if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number):
                    raise ValueError(f"{key}必须为有限数值，不能使用公式字符串")
                if (number < 0 and key != "tariff_escalation_rate") or (key in {"hub_height_m", "hub_height_max_m", "area_m2"} and number <= 0):
                    raise ValueError(f"{key}超出有效范围")
                if key in {"start_hour", "end_hour", "turbine_count", "room_count", "units_per_room"} and int(number) != number:
                    raise ValueError(f"{key}必须为整数")
                if key == "turbine_count" and number not in (0, 1): raise ValueError("只支持0或1台风机")
                if key == "tariff_escalation_rate" and not -0.05 <= number <= 0.10: raise ValueError("tariff_escalation_rate必须在-0.05至0.10之间")
                if key == "start_hour" and number > 23: raise ValueError("start_hour超出范围")
                if key == "end_hour" and not 1 <= number <= 24: raise ValueError("end_hour超出范围")
                if key in {"room_count", "units_per_room"} and number < 1: raise ValueError(f"{key}必须至少为1")
    return out


def rule_modifications(request: str) -> Dict[str, Any]:
    """Limited transparent helpers; they emit the same schema as the model."""
    h: Dict[str, Any] = {}; room: Dict[str, Any] = {}; wind: Dict[str, Any] = {}
    m = re.search(r"预算(?:改为|调整为|设为)\s*([0-9]+(?:\.[0-9]+)?)", request)
    if m: h["budget_cny"] = float(m.group(1))
    if re.search(r"预算\s*(?:减少|下调)\s*三分之一", request): h["budget_multiplier"] = 2 / 3
    if re.search(r"预算\s*(?:减少|下调)\s*一半", request): h["budget_multiplier"] = .5
    m = re.search(r"电价(?:年涨幅|涨幅|增长率)(?:改为|调整为|设为)?\s*(-?\d+(?:\.\d+)?)\s*%?", request)
    if m:
        raw_rate = float(m.group(1)); h["tariff_escalation_rate"] = raw_rate / 100.0 if abs(raw_rate) > 1 else raw_rate
    m = re.search(r"(?:塔架|轮毂|高度)最多\s*([0-9]+(?:\.[0-9]+)?)\s*米", request)
    if m: wind["hub_height_max_m"] = float(m.group(1))
    m = re.search(r"(?:塔架|轮毂|高度)(?:改为|调整为|设为)\s*([0-9]+(?:\.[0-9]+)?)\s*米", request)
    if m: wind["hub_height_m"] = float(m.group(1))
    if "允许外送" in request: h["allow_export"] = True
    if "不允许外送" in request: h["allow_export"] = False
    if "没有卖电价格" in request or "缺少外送价" in request: h["export_price_cny_per_kwh"] = None
    if "使用时段改到晚上" in request: room.update(start_hour=18, end_hour=22)
    m = re.search(r"使用时段(?:改为|改成|调整为|设为)\s*(\d{1,2})(?::?\d{2})?\s*点?\s*[-至到—–]\s*(\d{1,2})(?::?\d{2})?\s*点?", request)
    if m: room.update(start_hour=int(m.group(1)), end_hour=int(m.group(2)))
    m = re.search(r"(?:房间数|房间数量|有)\s*(?:改为|调整为|设为)?\s*(\d+)\s*间", request)
    if not m: m = re.search(r"(?:改为|调整为|设为)?\s*(\d+)\s*间(?:房间|办公室|同类房间)?", request)
    if m: room["room_count"] = int(m.group(1))
    m = re.search(r"每间\s*(?:配置|安装|有)?\s*(\d+)\s*台(?:空调|设备)?", request)
    if m: room["units_per_room"] = int(m.group(1))
    if wind: h["wind"] = wind
    return {**({"room": room} if room else {}), **({"hybrid": h} if h else {})}


def merge_modifications(model: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, Any]:
    out = validate_modifications(model)
    for group, vals in validate_modifications(rules).items():
        target = out.setdefault(group, {})
        for key, value in vals.items():
            if key == "wind":
                nested = target.setdefault(key, {})
                for field, v in value.items():
                    if field in nested and nested[field] != v: raise ModificationConflict(f"{group}.{key}.{field}的模型和规则修改冲突")
                    nested[field] = v
            else:
                if key in target and target[key] != value: raise ModificationConflict(f"{group}.{key}的模型和规则修改冲突")
                target[key] = value
    return out


def apply_modifications(base: Dict[str, Any], raw: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    changes = validate_modifications(raw); out = copy.deepcopy(base)
    h = changes.get("hybrid", {}); original = (base.get("hybrid") or {}).get("budget_cny")
    absolute, multiplier = h.get("budget_cny"), h.get("budget_multiplier")
    if multiplier is not None:
        if original is None: raise ModificationConflict("原预算未知，不能执行相对预算修改")
        relative = float(original) * float(multiplier)
        if absolute is not None and not math.isclose(float(absolute), relative, rel_tol=1e-8, abs_tol=.01):
            raise ModificationConflict(f"预算绝对值{absolute:g}与相对修改结果{relative:g}不一致，请确认")
        absolute = relative
    normalized = copy.deepcopy(changes)
    if absolute is not None:
        normalized.setdefault("hybrid", {})["budget_cny"] = float(absolute)
    normalized.get("hybrid", {}).pop("budget_multiplier", None)
    for group, values in normalized.items():
        target = out.setdefault(group, {})
        for key, value in values.items():
            if key == "wind": target.setdefault("wind", {}).update(value)
            else: target[key] = value
    # RoomSpec retains equipment_count for backwards compatibility. Keep it
    # synchronized when a user changes the canonical units_per_room field.
    if "units_per_room" in normalized.get("room", {}) and "equipment_count" in (out.get("room") or {}):
        out["room"]["equipment_count"] = normalized["room"]["units_per_room"]
    room = out.get("room") or {}
    if room.get("start_hour", 8) >= room.get("end_hour", 18):
        raise ValueError("使用结束时间必须大于开始时间（本版不支持跨午夜使用时段）")
    return out, normalized
