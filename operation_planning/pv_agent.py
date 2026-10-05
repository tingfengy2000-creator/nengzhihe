"""Bounded local-model orchestration for the phase-two PV task.

The model may interpret a requested change and advance a fixed, auditable
workflow.  Every numerical result is produced by the Python PV tools.  A
model failure is returned as a failure; it is never counted as a deterministic
fallback success.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List

from .pv import PVScenario, generate_candidates, generate_pv, match_load, run_pv_planning, scenario_from_dict, _price_vectors
from .thermal_model import RoomSpec, simulate_room
from .weather import load_pv_weather, load_weather

CONFIG_PATH = Path(__file__).resolve().parents[1] / "runtime" / "local_model_config.json"
PV_TOOLS = ["interpret_request", "validate_task", "read_load_context", "check_weather_inputs", "generate_candidates", "compute_pv_generation", "match_load_hourly", "calculate_lifecycle", "prepare_report"]
ALLOWED_MODIFICATIONS = {"budget_cny", "roof_area_m2", "usable_fraction", "start_hour", "end_hour", "import_price_cny_per_kwh", "export_price_cny_per_kwh", "allow_export", "quote", "study_years"}


class PVPlanningAgent:
    def __init__(self, max_rounds: int = 12):
        self.max_rounds = max_rounds

    def _model(self, messages: List[Dict[str, Any]], allowed: List[str]) -> Dict[str, Any]:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")); endpoint = config["base_url"].rstrip("/")
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.path != "/v1":
            raise RuntimeError("仅允许本地 loopback 模型端点")
        schema = {"type": "object", "properties": {"action": {"type": "string", "enum": allowed}, "arguments": {"type": "object"}, "message": {"type": "string"}}, "required": ["action", "arguments", "message"], "additionalProperties": False}
        payload = {"model": config["model_id"], "messages": messages, "temperature": 0, "seed": config.get("seed", 20260930), "max_tokens": min(512, max(320, int(config.get("max_tokens", 192)))), "stream": False, "chat_template_kwargs": {"enable_thinking": False}, "response_format": {"type": "json_schema", "json_schema": {"name": "pv_tool_call", "strict": True, "schema": schema}}}
        req = urllib.request.Request(endpoint + "/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=int(config.get("timeout_seconds", 90))) as response:
            body = response.read().decode("utf-8")
        parsed_body = json.loads(body)
        if parsed_body.get("model") != config["model_id"]:
            raise RuntimeError("模型身份与本地配置不一致")
        choice = parsed_body["choices"][0]
        if choice.get("finish_reason") == "length":
            raise RuntimeError("模型输出超长")
        action = json.loads(choice["message"]["content"])
        if set(action) != {"action", "arguments", "message"} or action["action"] not in allowed or not isinstance(action["arguments"], dict):
            raise RuntimeError("模型工具调用不符合结构")
        return action

    @staticmethod
    def _request_changes(request: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Extract only bounded, user-visible changes; never infer a result."""
        changes = {k: v for k, v in arguments.items() if k in ALLOWED_MODIFICATIONS}
        budgets = [float(x) for x in re.findall(r"预算(?:改为|调整为|设为)\s*([0-9]+(?:\.[0-9]+)?)", request)]
        if len(set(budgets)) > 1:
            raise ValueError("请求中出现多个不同预算，需要先澄清")
        if budgets:
            changes["budget_cny"] = budgets[-1]
        roof = re.search(r"(?:屋顶|可安装面积)(?:改为|调整为|设为)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:平方米|平米|m2|㎡)?", request, re.I)
        if roof: changes["roof_area_m2"] = float(roof.group(1))
        price = re.search(r"(?:购电|电价)(?:改为|调整为|设为)\s*([0-9]+(?:\.[0-9]+)?)", request)
        if price: changes["import_price_cny_per_kwh"] = float(price.group(1))
        quote_fields = {
            "组件": "module_cny_per_kwp", "逆变器": "inverter_cny_per_kwp", "支架": "structure_cny_per_kwp", "施工": "installation_cny_per_kwp", "接入": "grid_connection_cny", "维护": "maintenance_cny_per_kwp_year"
        }
        for label, field in quote_fields.items():
            match = re.search(rf"{label}(?:报价|单价)(?:改为|调整为|设为)\s*([0-9]+(?:\.[0-9]+)?)", request)
            if match:
                changes.setdefault("quote", {})[field] = float(match.group(1))
        if "使用时段改到晚上" in request or "晚间使用" in request:
            changes["start_hour"], changes["end_hour"] = 18, 22
        period = re.search(r"使用时段(?:改为|调整为|设为)\s*(\d{1,2})\s*[-至到]\s*(\d{1,2})\s*点", request)
        if period:
            changes["start_hour"], changes["end_hour"] = int(period.group(1)), int(period.group(2))
        if "允许外送" in request or "开启外送" in request:
            changes["allow_export"] = True
        if "不允许外送" in request or "关闭外送" in request:
            changes["allow_export"] = False
        return changes

    @staticmethod
    def _apply_changes(base: Dict[str, Any], changes: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(base); result["pv"] = dict(result.get("pv") or {}); result["room"] = dict(result.get("room") or {}); quote = dict(result["pv"].get("quote") or {})
        for key, value in changes.items():
            if key == "quote" and isinstance(value, dict): quote.update(value)
            elif key in {"start_hour", "end_hour"}: result["room"][key] = int(value)
            elif key in ALLOWED_MODIFICATIONS: result["pv"][key] = value
        if quote: result["pv"]["quote"] = quote
        return result

    def _tool(self, name: str, state: Dict[str, Any], arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "interpret_request":
            changes = self._request_changes(state["request"], arguments); state["changes"] = changes; state["payload"] = self._apply_changes(state["payload"], changes)
            return {"modifications": changes, "validated_against": sorted(ALLOWED_MODIFICATIONS), "numeric_source": "request parser plus model arguments; no recommendation computed"}
        if name == "validate_task":
            payload = state["payload"]; raw = payload.get("pv") or {}; room_raw = payload.get("room") or {}; state["room"] = RoomSpec(**{k: v for k, v in room_raw.items() if k in RoomSpec.__dataclass_fields__}); state["scenario"] = scenario_from_dict(raw, site_id=state["site_id"], year=state["year"])
            if state["scenario"].allow_export and state["scenario"].export_price_cny_per_kwh is None:
                state["needs_clarification"] = "已开启外送但缺少外送电价；请选择不计经济收益或提供价格"
                return {"status": "needs_clarification", "question": state["needs_clarification"]}
            return {"status": "validated", "scenario": {"budget_cny": state["scenario"].budget_cny, "roof_area_m2": state["scenario"].roof_area_m2, "allow_export": state["scenario"].allow_export}}
        if name == "read_load_context":
            state["load_weather"] = state["payload"].get("weather") or load_weather(state["site_id"], state["year"]); state["pv_weather"] = state["payload"].get("pv_weather") or load_pv_weather(state["site_id"], state["year"]); state["load_result"] = simulate_room(state["load_weather"], state["room"])
            return {"load_kwh": state["load_result"].get("summary", {}).get("electric_kwh"), "service": state["load_result"].get("summary", {})}
        if name == "check_weather_inputs":
            if state["load_result"]["load_series"]["timestamps"] != state["pv_weather"]["time"]: raise ValueError("负荷和光伏天气时间轴不一致")
            return {"source_file": state["pv_weather"].get("source_file"), "hash": state["pv_weather"].get("hash"), "aligned_records": len(state["pv_weather"].get("time", []))}
        if name == "generate_candidates":
            state["capacities"], state["candidate_notes"] = generate_candidates(state["scenario"]); return {"capacities_kwp": state["capacities"], "notes": state["candidate_notes"]}
        if name == "compute_pv_generation":
            intervals = state["load_result"]["load_series"]["interval_seconds"]; weather = dict(state["pv_weather"]); weather["interval_seconds"] = intervals; state["weather_for_pv"] = weather; state["generations"] = {str(cap): generate_pv(weather, cap, state["scenario"]) for cap in state["capacities"]}; return {"generation_kwh": {cap: sum(g.pv_ac_power_w[i] * g.interval_seconds[i] / 3_600_000 for i in range(len(g.pv_ac_power_w))) for cap, g in state["generations"].items()}}
        if name == "match_load_hourly":
            prices, tariff = _price_vectors(state["scenario"], state["load_result"]["load_series"]["timestamps"]); export_prices = ([state["scenario"].export_price_cny_per_kwh] * len(prices) if state["scenario"].export_price_cny_per_kwh is not None else None); state["matches"] = {cap: match_load(state["load_result"]["load_series"], gen, allow_export=state["scenario"].allow_export, export_limit_kw=state["scenario"].export_limit_kw, import_prices=prices, export_prices=export_prices) for cap, gen in state["generations"].items()}; state["prices"] = prices; state["export_prices"] = export_prices; return {"tariff": tariff, "grid_import_kwh": {cap: m["summary"]["grid_import_kwh"] for cap, m in state["matches"].items()}}
        if name == "calculate_lifecycle":
            state["report"] = run_pv_planning(state["load_result"], state["weather_for_pv"], state["scenario"], include_selected_series=True); return {"recommendation": state["report"].get("recommendation"), "candidate_count": len(state["report"].get("candidates", [])), "numeric_source": "run_pv_planning deterministic tool"}
        if name == "prepare_report":
            if not state.get("report"): raise ValueError("尚未完成生命周期计算")
            state["report"]["agent_task"] = {"request": state["request"], "modifications": state.get("changes", {}), "workflow": "request→validate→weather/load→candidates→generation→matching→lifecycle"}; return {"status": "report_ready", "recommendation": state["report"].get("recommendation")}
        raise ValueError(f"未知工具：{name}")

    def run(self, user_request: str, task: Dict[str, Any]) -> Dict[str, Any]:
        state: Dict[str, Any] = {"request": user_request, "payload": dict(task), "site_id": str(task.get("site_id", "guangzhou")), "year": int(task.get("year", 2024)), "trace": []}; messages = [{"role": "system", "content": "你是能智核光伏任务执行助手。按顺序选择工具。第一轮 interpret_request 必须把用户修改写入 arguments（例如预算改为6000时返回 budget_cny:6000）；后续工具按需使用空对象。不得给推荐数字，数字来自Python工具。缺少关键经济输入时保留物理结果并提出澄清。"}, {"role": "user", "content": json.dumps({"request": user_request, "task": {"site_id": state["site_id"], "year": state["year"], "pv": task.get("pv", {}), "room": task.get("room", {})}, "allowed_tools": PV_TOOLS}, ensure_ascii=False)}]
        for i in range(min(self.max_rounds, len(PV_TOOLS))):
            started = time.perf_counter(); allowed = [PV_TOOLS[i]]
            try:
                action = self._model(messages, allowed); result = self._tool(action["action"], state, action.get("arguments", {})); entry = {"round": i + 1, "action": action["action"], "arguments": action.get("arguments", {}), "message": action.get("message", ""), "result": result, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "model": "local_configured_model"}; state["trace"].append(entry)
                messages.extend([{ "role": "assistant", "content": json.dumps(action, ensure_ascii=False)}, {"role": "tool", "name": action["action"], "content": json.dumps(result, ensure_ascii=False, default=str)}])
                if result.get("status") == "needs_clarification": return {"status": "needs_clarification", "question": result["question"], "trace": state["trace"]}
                if action["action"] == "prepare_report": return {"status": "success", "report": state["report"], "trace": state["trace"], "message": "本地模型完成了真实的任务修改与工具序列；数字来自确定性计算工具。"}
                messages.append({"role": "user", "content": f"{action['action']} 已完成。请调用下一阶段 {PV_TOOLS[i + 1]}。arguments 可为空，只有用户修改才需要填写。"})
            except Exception as exc:
                state["trace"].append({"round": i + 1, "action": None, "error": f"{type(exc).__name__}: {exc}", "latency_ms": round((time.perf_counter() - started) * 1000, 2)})
                return {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "trace": state["trace"], "message": "模型协同失败；没有用确定性路径冒充Agent成功。"}
        return {"status": "failed", "error": "超过最大模型轮数", "trace": state["trace"]}
