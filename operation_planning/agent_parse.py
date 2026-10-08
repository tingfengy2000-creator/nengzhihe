"""Small, read-only local-model interface for interpreting user changes.

This module deliberately stops before any thermal, PV, wind, tariff or cost
calculation.  It validates the model's proposed field changes against the
same bounded task vocabulary used by the planning APIs and returns a compact
review object for the UI.
"""
from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .equipment import catalogue
from .task_changes import MODIFICATION_SCHEMA, validate_modifications


CONFIG_PATH = Path(__file__).resolve().parents[1] / "runtime" / "local_model_config.json"
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}

# The parse endpoint exposes a flat change list, while the existing planning
# APIs consume this nested schema.  Keeping this list here prevents a model
# from inventing a field that a subsequent planning request cannot validate.
FIELD_RULES: dict[str, dict[str, Any]] = {
    "room.units_per_room": {"kind": "integer", "minimum": 1, "label": "每间空调台数"},
    "room.room_count": {"kind": "integer", "minimum": 1, "label": "同类房间数"},
    "room.start_hour": {"kind": "integer", "minimum": 0, "maximum": 23, "label": "使用开始时间"},
    "room.end_hour": {"kind": "integer", "minimum": 1, "maximum": 24, "label": "使用结束时间"},
    "room.area_m2": {"kind": "number", "minimum": 0, "exclusive_minimum": True, "label": "房间面积"},
    "room.equipment_id": {"kind": "equipment", "label": "空调型号"},
    "hybrid.budget_cny": {"kind": "number", "minimum": 0, "label": "预算"},
    "hybrid.budget_multiplier": {"kind": "number", "minimum": 0, "label": "预算相对调整"},
    "hybrid.pv_capacity_kwp": {"kind": "number", "minimum": 0, "label": "光伏容量"},
    # The public hybrid request keeps the user-facing capacity under ``pv``;
    # the normalized planning object also has ``hybrid.pv_capacity_kwp``.
    # Both are read-only parse aliases and are never sent to a calculator.
    "pv.capacity_kwp": {"kind": "number", "minimum": 0, "label": "光伏容量"},
    "hybrid.allow_export": {"kind": "boolean", "label": "多余电量卖给电网"},
    "hybrid.import_price_cny_per_kwh": {"kind": "number", "minimum": 0, "label": "购电价格"},
    "hybrid.export_price_cny_per_kwh": {"kind": "nullable_number", "minimum": 0, "label": "外送电价"},
    "hybrid.tariff_escalation_rate": {"kind": "number", "minimum": -0.05, "maximum": 0.10, "label": "电价年涨幅"},
    "hybrid.wind.turbine_count": {"kind": "integer", "minimum": 0, "maximum": 1, "label": "风机台数"},
    "storage.quote.cny_per_kwh": {"kind": "number", "minimum": 0, "label": "储能单价"},
    "storage.capacities_kwh": {"kind": "number_list", "minimum": 0, "label": "储能容量列表"},
}


def _read_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError("未找到本地模型配置")
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # pragma: no cover - malformed deployment config
        raise ValueError("本地模型配置无效") from exc
    endpoint = str(config.get("base_url", "")).rstrip("/")
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in _LOOPBACK or parsed.path != "/v1":
        raise ValueError("本地模型端点必须是loopback的/v1服务")
    if not config.get("model_id"):
        raise ValueError("本地模型配置缺少模型标识")
    config["_endpoint"] = endpoint
    return config


def local_model_status() -> dict[str, Any]:
    """Probe only the local endpoint and never disclose machine/model paths."""
    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        config = _read_config()
    except FileNotFoundError:
        return {"available": False, "mode": "local_model", "label": "本地大模型", "checked_at": checked_at, "reason": "未找到本地模型配置"}
    except ValueError as exc:
        return {"available": False, "mode": "local_model", "label": "本地大模型", "checked_at": checked_at, "reason": str(exc)}
    request = urllib.request.Request(config["_endpoint"] + "/models", method="GET")
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=2.0) as response:
            if int(getattr(response, "status", 200)) >= 400:
                raise urllib.error.HTTPError(request.full_url, int(response.status), "probe failed", response.headers, None)
            response.read(4096)
        return {"available": True, "mode": "local_model", "label": "本地大模型", "checked_at": checked_at, "reason": None}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {"available": False, "mode": "local_model", "label": "本地大模型", "checked_at": checked_at, "reason": "本地模型未启动"}


def _get_path(obj: dict[str, Any], path: str) -> Any:
    value: Any = obj
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _equipment_ids() -> set[str]:
    return {str(item.get("equipment_id")) for item in catalogue() if item.get("equipment_id")}


def _validate_value(field: str, value: Any) -> None:
    rule = FIELD_RULES[field]
    kind = rule["kind"]
    if kind == "equipment":
        if not isinstance(value, str) or value not in _equipment_ids():
            raise ValueError("设备型号不在当前公开目录中")
        return
    if kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{field}必须为布尔值")
        return
    if kind == "nullable_number" and value is None:
        return
    if kind == "number_list":
        if not isinstance(value, list) or not value:
            raise ValueError(f"{field}必须是非空数值列表")
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)) or float(item) < float(rule.get("minimum", 0)):
                raise ValueError(f"{field}必须是非负有限数值列表")
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{field}必须为有限数值")
    if rule.get("exclusive_minimum") and value <= rule["minimum"]:
        raise ValueError(f"{field}必须大于{rule['minimum']}")
    if not rule.get("exclusive_minimum") and value < rule.get("minimum", 0):
        raise ValueError(f"{field}不能为负数")
    if "maximum" in rule and value > rule["maximum"]:
        raise ValueError(f"{field}超出范围")
    if kind == "integer" and int(value) != value:
        raise ValueError(f"{field}必须为整数")


def _nested_changes(changes: list[dict[str, Any]]) -> dict[str, Any]:
    nested: dict[str, Any] = {}
    for item in changes:
        field, value = item["field"], item["to"]
        parts = field.split(".")
        group = parts[0]
        target = nested.setdefault(group, {})
        for part in parts[1:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    # Validate all fields shared with the planning schema.  equipment_id is
    # intentionally checked above because it is a catalogue selection, not a
    # thermal numeric parameter in task_changes.py.
    common: dict[str, dict[str, Any]] = {}
    for group, values in nested.items():
        if group not in {"room", "hybrid"} or not isinstance(values, dict):
            continue
        allowed: dict[str, Any] = {}
        for key, value in values.items():
            full = f"{group}.{key}"
            if full in FIELD_RULES and key != "equipment_id":
                allowed[key] = value
            elif isinstance(value, dict):
                nested_allowed = {child: child_value for child, child_value in value.items() if f"{full}.{child}" in FIELD_RULES}
                if nested_allowed:
                    allowed[key] = nested_allowed
        if allowed:
            common[group] = allowed
    common = {g: vals for g, vals in common.items() if vals}
    if common:
        validate_modifications(common)
    return nested


def _normalise_changes(raw: Any, current_task: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError("模型返回的changes必须是数组")
    out: list[dict[str, Any]] = []
    seen: dict[str, Any] = {}
    for item in raw:
        if not isinstance(item, dict) or set(item) - {"field", "to", "label", "from"} or not {"field", "to"} <= set(item):
            raise ValueError("模型返回的修改项结构无效")
        field = str(item["field"])
        if field not in FIELD_RULES:
            raise ValueError(f"不支持的修改字段：{field}")
        value = item["to"]
        _validate_value(field, value)
        if field in seen and seen[field] != value:
            raise ValueError(f"同一字段出现冲突修改：{field}")
        seen[field] = value
        source_from = _get_path(current_task, field)
        # A model may echo the current value, but it cannot invent the old
        # value.  Always use the request's current_task as the authoritative
        # ``from`` value in the review object.
        out.append({"field": field, "from": source_from, "to": value,
                    "label": str(item.get("label") or FIELD_RULES[field]["label"])})
    _nested_changes(out)

    # A relative budget is a user instruction, but the review card should
    # expose the one effective field that the jobs API will receive.  Resolve
    # it once from the current form value; this is interpretation, not a plan
    # or cost calculation.  Reject inconsistent absolute+relative output.
    relative = next((item for item in out if item["field"] == "hybrid.budget_multiplier"), None)
    absolute = next((item for item in out if item["field"] == "hybrid.budget_cny"), None)
    if relative is not None:
        current_budget = _get_path(current_task, "hybrid.budget_cny")
        if isinstance(current_budget, bool) or not isinstance(current_budget, (int, float)) or not math.isfinite(float(current_budget)):
            raise ValueError("原预算未知，不能执行相对预算修改")
        effective = round(float(current_budget) * float(relative["to"]), 2)
        if absolute is not None and not math.isclose(float(absolute["to"]), effective, rel_tol=1e-8, abs_tol=0.01):
            raise ValueError("预算绝对值与相对修改结果不一致，请确认")
        out = [item for item in out if item["field"] not in {"hybrid.budget_multiplier", "hybrid.budget_cny"}]
        out.append({"field": "hybrid.budget_cny", "from": current_budget, "to": effective, "label": "预算"})
    return out


_FIELD_HINTS = {
    "room.units_per_room": ("台", "每间", "设备数量", "空调数量"),
    "room.room_count": ("房间", "办公室", "间"),
    "room.start_hour": ("时段", "时间", "点", "到", "开始", "晚上", "上午", "早上", ":"),
    "room.end_hour": ("时段", "时间", "点", "到", "结束", "晚上", "上午", "早上", ":"),
    "room.area_m2": ("面积", "平方米", "㎡", "m²", "m2"),
    "room.equipment_id": ("型号", "设备", "空调", "换成", "更换"),
    "hybrid.budget_cny": ("预算", "元", "万元", "万", "花费", "成本"),
    "hybrid.budget_multiplier": ("预算", "翻倍", "减少", "下调", "增加", "提高", "一半", "三分之一"),
    "hybrid.pv_capacity_kwp": ("光伏", "kWp", "kwp", "千瓦", "容量"),
    "pv.capacity_kwp": ("光伏", "kWp", "kwp", "千瓦", "容量"),
    "hybrid.allow_export": ("卖电", "外送", "上网", "余电"),
    "hybrid.import_price_cny_per_kwh": ("购电价", "电价", "每度", "元/kWh"),
    "hybrid.export_price_cny_per_kwh": ("卖电价", "外送价", "上网电价"),
    "hybrid.tariff_escalation_rate": ("电价", "涨幅", "增长率", "每年"),
    "hybrid.wind.turbine_count": ("风机", "风电", "台"),
    "storage.quote.cny_per_kwh": ("储能", "电池", "储能单价", "元/kWh"),
    "storage.capacities_kwh": ("储能", "电池", "容量列表", "kWh"),
}


def _assert_request_supports_changes(request_text: str, changes: list[dict[str, Any]]) -> None:
    """Reject model hallucinations such as inventing a budget for “加电池”."""
    text = request_text.lower()
    for item in changes:
        field = item["field"]
        if not any(str(hint).lower() in text for hint in _FIELD_HINTS[field]):
            raise ValueError(f"模型修改了用户未提及的字段：{field}")


def _unsupported_brand_notes(request_text: str) -> list[str]:
    # The public catalogue currently contains Midea and Daikin references.
    # Keep an explicit note for common brands that are not represented rather
    # than allowing a model to substitute an arbitrary catalogue item.
    notes = []
    for brand in ("格力", "海尔", "三菱", "奥克斯", "志高"):
        if brand in request_text and any(token in request_text for token in ("换", "型号", "空调", "设备")):
            notes.append(f'“{brand}”：设备目录中没有该品牌型号')
    return notes


def _unsupported_feature_notes(request_text: str) -> list[str]:
    notes = []
    for term, label in (("储能套利", "储能峰谷套利"), ("峰谷套利", "峰谷套利"), ("保证回本", "回本保证"), ("其他电器", "其他电器")):
        if term in request_text:
            notes.append(f"“{label}”：本接口不承诺自动套利或收益保证")
    return notes


def _collapse_budget_changes(changes: list[dict[str, Any]], current_task: dict[str, Any]) -> list[dict[str, Any]]:
    """Represent a relative budget edit as one absolute suggestion.

    This is only interpretation arithmetic; no planning or cost calculation
    is performed.  If absolute and relative forms disagree, the caller asks
    the user to confirm instead of choosing one silently.
    """
    budget = [item for item in changes if item["field"] in {"hybrid.budget_cny", "hybrid.budget_multiplier"}]
    if not budget:
        return changes
    absolute = next((item for item in budget if item["field"] == "hybrid.budget_cny"), None)
    multiplier = next((item for item in budget if item["field"] == "hybrid.budget_multiplier"), None)
    if multiplier is None:
        return changes
    original = _get_path(current_task, "hybrid.budget_cny")
    if not isinstance(original, (int, float)) or isinstance(original, bool):
        raise ValueError("原预算未知，不能解释相对预算修改")
    # Keep ordinary currency inputs readable after a model emits a decimal
    # multiplier such as 1.6666666666666663.
    relative = round(float(original) * float(multiplier["to"]), 2)
    if absolute is not None and not math.isclose(float(absolute["to"]), relative, rel_tol=1e-8, abs_tol=.01):
        raise ValueError("预算绝对值与相对修改结果不一致，请确认")
    target = float(absolute["to"]) if absolute is not None else relative
    replacement = {"field": "hybrid.budget_cny", "from": original, "to": target, "label": "预算"}
    return [item for item in changes if item["field"] not in {"hybrid.budget_cny", "hybrid.budget_multiplier"}] + [replacement]


def _budget_language_conflict(request_text: str, current_task: dict[str, Any], changes: list[dict[str, Any]]) -> str | None:
    """Check an absolute-plus-relative budget sentence without computing a plan."""
    original = _get_path(current_task, "hybrid.budget_cny")
    target = next((item.get("to") for item in changes if item.get("field") == "hybrid.budget_cny"), None)
    if not isinstance(original, (int, float)) or not isinstance(target, (int, float)):
        return None
    multiplier = None
    if "减少三分之一" in request_text or "下调三分之一" in request_text:
        multiplier = 2 / 3
    elif "减少一半" in request_text or "下调一半" in request_text or "减少50%" in request_text:
        multiplier = .5
    elif "预算翻倍" in request_text or "预算加倍" in request_text:
        multiplier = 2.0
    if multiplier is None:
        return None
    if not math.isclose(float(target), float(original) * multiplier, rel_tol=1e-8, abs_tol=.01):
        return "预算绝对值与相对修改结果不一致，请确认采用哪个预算"
    return None


def _model_parse(config: dict[str, Any], request_text: str, current_task: dict[str, Any]) -> dict[str, Any]:
    fields = {key: {k: v for k, v in value.items() if k != "kind"} for key, value in FIELD_RULES.items()}
    system = (
        "你是能智核的只读任务理解器。只把用户原话解释成修改建议，不做任何热湿、发电、匹配、费用或推荐计算。"
        "只允许使用给定字段；不支持的内容写入unsupported，不能静默丢弃。数字只能来自用户原话或相对修改；"
        "预算相对修改可返回budget_multiplier；如果请求只有‘降低一些/适当增加’而没有数值或比例，必须question追问，不能把当前值当新值。"
        "时间范围‘18:00到22:00’必须同时返回room.start_hour=18和room.end_hour=22，不能只返回一端。只返回JSON对象changes、unsupported、question。"
    )
    user = json.dumps({"request": request_text, "current_task": current_task, "allowed_fields": fields,
                       "equipment_options": sorted(_equipment_ids())}, ensure_ascii=False)
    schema = {"type": "object", "properties": {
        "changes": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string"}, "to": {}, "label": {"type": "string"}},
            "required": ["field", "to"], "additionalProperties": False}},
        "unsupported": {"type": "array", "items": {"type": "string"}},
        "question": {"type": ["string", "null"]}},
        "required": ["changes", "unsupported", "question"], "additionalProperties": False}
    body = {"model": config["model_id"], "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0, "seed": config.get("seed", 20260930), "max_tokens": 512, "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"name": "agent_parse", "strict": True, "schema": schema}}}
    req = urllib.request.Request(config["_endpoint"] + "/chat/completions", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    timeout = min(float(config.get("timeout_seconds", 10)), 10.0)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("model") != config["model_id"]:
        raise ValueError("模型身份与本地配置不一致")
    content = payload.get("choices", [{}])[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise ValueError("模型未返回结构化理解结果")
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("模型输出不是有效JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("模型输出结构无效")
    if not isinstance(result.get("unsupported", []), list) or any(not isinstance(x, str) for x in result.get("unsupported", [])):
        raise ValueError("unsupported字段无效")
    return result


def parse_agent_request(request_text: str, current_task: dict[str, Any]) -> dict[str, Any]:
    """Interpret one sentence; never invokes a planning/calculation function."""
    started = time.perf_counter()
    elapsed = lambda: round((time.perf_counter() - started) * 1000.0, 2)
    if not isinstance(request_text, str) or not request_text.strip():
        return {"status": "failed", "changes": [], "unsupported": [], "question": None, "reason": "request必须是非空文本", "model": "local_model", "latency_ms": elapsed()}
    if not isinstance(current_task, dict):
        return {"status": "failed", "changes": [], "unsupported": [], "question": None, "reason": "current_task必须是对象", "model": "local_model", "latency_ms": elapsed()}
    try:
        config = _read_config()
    except FileNotFoundError:
        return {"status": "unavailable", "changes": [], "unsupported": [], "question": None, "reason": "未找到本地模型配置", "model": "local_model", "latency_ms": elapsed()}
    except ValueError as exc:
        return {"status": "unavailable", "changes": [], "unsupported": [], "question": None, "reason": str(exc), "model": "local_model", "latency_ms": elapsed()}
    try:
        raw = _model_parse(config, request_text, current_task)
        unsupported = [str(x) for x in raw.get("unsupported", [])]
        feature_notes = _unsupported_brand_notes(request_text) + _unsupported_feature_notes(request_text)
        unsupported.extend(note for note in feature_notes if note not in unsupported)
        # When the whole request is outside the supported vocabulary, retain
        # the transparent unsupported result even if the small model emitted a
        # stray malformed default field.  Mixed requests still go through the
        # strict validator below and cannot silently drop supported edits.
        has_supported_hint = any(str(h).lower() in request_text.lower() for hints in _FIELD_HINTS.values() for h in hints)
        if feature_notes and not has_supported_hint:
            changes = []
        else:
            changes = _normalise_changes(raw.get("changes", []), current_task)
        # For a request that is entirely outside this read-only vocabulary,
        # return a transparent unsupported result even if the model echoed a
        # stray default field.  It is never applied to a task.
        if unsupported and not has_supported_hint:
            changes = []
        else:
            _assert_request_supports_changes(request_text, changes)
        changes = _collapse_budget_changes(changes, current_task)
        conflict = _budget_language_conflict(request_text, current_task, changes)
        if conflict:
            return {"status": "needs_clarification", "changes": [], "unsupported": unsupported,
                    "question": conflict, "reason": conflict, "model": "local_model", "latency_ms": elapsed()}
        for note in _unsupported_brand_notes(request_text):
            # A model suggestion for an unavailable brand is not a valid
            # catalogue change.  Report it as unsupported rather than
            # silently applying a different model.
            changes = [item for item in changes if item["field"] != "room.equipment_id"]
        question = raw.get("question")
        if question is not None and not isinstance(question, str):
            raise ValueError("question字段无效")
        if isinstance(question, str) and not question.strip():
            question = None
        vague_period = ("晚上使用" in request_text or "晚上用" in request_text) and not any(ch.isdigit() for ch in request_text)
        if vague_period:
            changes = []
            question = "请给出晚上使用时段的开始和结束时间，例如18:00到22:00。"
        # An explicit request may already match the form (e.g. "关闭卖电"
        # while export is off).  Equality is not evidence of ambiguity.  Keep
        # the bounded proposal; genuine vague amounts are checked below.
        # Small local guard for vague natural-language amounts.  The model is
        # still the source of the interpretation; this only prevents an
        # unchanged value from being presented as a successful modification.
        vague_budget = any(token in request_text for token in ("预算调低一些", "预算降低一些", "预算减少一些", "预算增加一些", "预算提高一些", "预算适当"))
        if vague_budget and any(item["field"] == "hybrid.budget_cny" and item["to"] == item["from"] for item in changes):
            changes = []
            question = "预算要调整为多少元，或减少/增加多少比例？"
        status = "needs_clarification" if question else "ok"
        return {"status": status, "changes": changes, "unsupported": unsupported, "question": question,
                "model": "local_model", "latency_ms": elapsed()}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"status": "unavailable", "changes": [], "unsupported": [], "question": None, "reason": "本地模型未启动", "model": "local_model", "latency_ms": elapsed()}
    except Exception as exc:
        reason = str(exc) or "模型输出不合法"
        return {"status": "failed", "changes": [], "unsupported": [], "question": None, "reason": reason,
                "model": "local_model", "latency_ms": elapsed()}
