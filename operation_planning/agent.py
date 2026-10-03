"""One local-model tool-feedback agent for operation planning.

The model chooses an allow-listed tool on every round.  All calculations and
physical simulation remain in Python; invalid model output is an explicit
agent failure and is never silently replaced by a deterministic script.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import time
from typing import Any, Callable, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

from .boptest_adapter import LocalBestestAirFMUAdapter
from .schemas import PlanSegment, PlanSpec, TaskSpec
from .search import PlanEvaluator


CONFIG_PATH = Path(__file__).resolve().parents[1] / "runtime" / "local_model_config.json"
TOOLS = ["get_case_context", "validate_task", "evaluate_plan", "search_plans", "get_violation_details", "compare_results", "prepare_report"]


class OperationPlanningAgent:
    def __init__(self, evaluator: PlanEvaluator | None = None, max_rounds: int = 8):
        self.evaluator = evaluator or PlanEvaluator()
        self.max_rounds = max_rounds
        self.adapter = self.evaluator.adapter

    def _model(self, messages: List[Dict[str, Any]], allowed_tools: Optional[List[str]] = None) -> Dict[str, Any]:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        allowed_tools = allowed_tools or TOOLS
        endpoint = config["base_url"].rstrip("/")
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.path != "/v1":
            raise RuntimeError("仅允许本地 loopback 模型端点")
        schema = {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": allowed_tools},
                "arguments": {"type": "object"},
                "message": {"type": "string"},
            },
            "required": ["action", "arguments", "message"],
            "additionalProperties": False,
        }
        payload = {
            "model": config["model_id"],
            "messages": messages,
            "temperature": 0,
            "seed": config.get("seed", 20260930),
            # The local config is intentionally conservative for evidence
            # actions; operation planning needs room for a short structured
            # tool call, but never more than one bounded call per round.
            "max_tokens": min(512, max(320, int(config.get("max_tokens", 192)))),
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"name": "operation_tool_call", "strict": True, "schema": schema}},
        }
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
        content = choice["message"]["content"]
        action = json.loads(content)
        if set(action) != {"action", "arguments", "message"} or action["action"] not in TOOLS or not isinstance(action["arguments"], dict):
            raise RuntimeError("模型工具调用不符合结构")
        return action

    def _tool(self, name: str, args: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        if name == "get_case_context":
            return {"provenance": self.adapter.provenance(), "measurements": self.adapter.get_measurements(), "inputs": self.adapter.get_inputs(), "forecast": self.adapter.get_forecast_points()}
        if name == "validate_task":
            task = dict(state["task"])
            prior_conflict = state.get("constraint_conflict")
            if not prior_conflict and task.get("requested_upper_temp_c") is not None and float(task["requested_upper_temp_c"]) > float(task.get("upper_temp_c", 24.0)) + float(task.get("tolerance_c", 0.25)) and task.get("constraint_notes"):
                prior_conflict = "用户要求的温度区间与当前硬温度带冲突；搜索只按硬温度带执行并返回可行替代方案。"
            # Natural-language range fields are accepted only as a parsing
            # aid; the actual range is stored as explicit numeric TaskSpec
            # fields and the hard safety band remains unchanged.
            occupied_room = args.get("occupied_room")
            if isinstance(occupied_room, str):
                nums = re.findall(r"-?\d+(?:\.\d+)?", occupied_room)
                if len(nums) >= 2:
                    task["requested_lower_temp_c"] = float(nums[0])
                    task["requested_upper_temp_c"] = float(nums[1])
            if isinstance(args.get("conflict_resolution"), str):
                task["constraint_notes"] = args["conflict_resolution"]
            known = set(task) | {"occupied_room", "conflict_resolution", "request"}
            unknown = sorted(k for k in args if k not in known)
            # Once a user explicitly declares a hard conflict, later model
            # retries cannot overwrite the hard band with the requested band.
            # This prevents a second validation round from erasing the very
            # conflict that must be shown to the operator.
            blocked_updates = {"lower_temp_c", "upper_temp_c"} if prior_conflict else set()
            task.update({k: v for k, v in args.items() if k in task and k not in blocked_updates})
            candidate = TaskSpec(**task)
            errors = candidate.validate()
            if unknown:
                errors.append("模型提出了未映射字段：" + ", ".join(unknown) + "；请改为 TaskSpec 的明确数值字段")
            state["task"] = candidate.to_dict()
            state["task_valid"] = not errors
            conflict = None
            if candidate.requested_upper_temp_c is not None and candidate.requested_upper_temp_c > candidate.upper_temp_c + candidate.tolerance_c:
                conflict = "用户要求的温度上限高于当前硬上限；搜索只按硬上限执行，不自动放宽。"
            if candidate.requested_lower_temp_c is not None and candidate.requested_lower_temp_c > candidate.upper_temp_c + candidate.tolerance_c:
                conflict = "用户要求的温度区间与当前硬温度带冲突；搜索只按硬温度带执行并返回可行替代方案。"
            conflict = conflict or prior_conflict
            state["constraint_conflict"] = conflict
            return {"valid": not errors, "errors": errors, "constraint_conflict": conflict, "task": state["task"]}
        if name == "evaluate_plan":
            plan_data = args.get("plan") or {}
            segments = [PlanSegment(**segment) for segment in plan_data.get("segments", [])]
            plan = PlanSpec(plan_data.get("plan_id", "agent_plan"), plan_data.get("kind", "agent"), segments, state["task"].get("objective", "cost"), state["task"].get("price_profile", "dynamic"), "agent_requested")
            result = self.evaluator.evaluate(TaskSpec(**state["task"]), plan)
            state.setdefault("results", {})[result.result_id] = result.to_dict()
            return {"result_id": result.result_id, "feasible": result.feasible, "metrics": result.custom_metrics, "rejection_reasons": result.rejection_reasons}
        if name == "search_plans":
            if not state.get("task_valid"):
                return {"error": "TaskSpec 尚未通过 validate_task；不得在条件无效时搜索"}
            report = self.evaluator.search(TaskSpec(**state["task"]), trace=state["trace"])
            if state.get("constraint_conflict"):
                report.unresolved_requirements.insert(0, state["constraint_conflict"])
                report.recommendation_reason += "；已保留用户要求与硬约束的冲突"
            state["report"] = report.to_dict()
            state["results"] = {c["result"]["result_id"]: c["result"] for c in report.candidates if c.get("result")}
            return {"feasible": report.feasible, "recommended_plan_id": report.recommended_plan_id, "candidate_count": len(report.candidates), "unresolved_requirements": report.unresolved_requirements}
        if name == "get_violation_details":
            result_id = args.get("result_id")
            result = state.get("results", {}).get(result_id)
            if not result:
                return {"error": "result_id 不存在于当前会话"}
            return {"result_id": result_id, "metrics": result["custom_metrics"], "rejection_reasons": result["rejection_reasons"], "evidence": result["evidence"]}
        if name == "compare_results":
            ids = args.get("result_ids", [])
            return {"results": [{"result_id": rid, "feasible": state.get("results", {}).get(rid, {}).get("feasible"), "metrics": state.get("results", {}).get(rid, {}).get("custom_metrics", {})} for rid in ids]}
        if name == "prepare_report":
            if "report" not in state:
                return {"error": "请先 search_plans"}
            state["done"] = True
            return {"report_ready": True, "recommended_plan_id": state["report"].get("recommended_plan_id"), "feasible": state["report"].get("feasible")}
        raise RuntimeError(f"不允许的工具：{name}")

    @staticmethod
    def _request_hints(text: str, task: Dict[str, Any]) -> None:
        """Normalize an explicitly stated temperature range before the loop.

        This is a bounded input normalizer, not an answer generator.  It keeps
        Chinese and English requirement changes from becoming unknown model
        fields, while the model still has to validate and search through tools.
        """
        range_match = re.search(r"(?:室温|温度|room\s*temperature|temperature)[^\d]{0,16}(\d+(?:\.\d+)?)\s*(?:到|至|to|and|[-~])\s*(\d+(?:\.\d+)?)", text, re.I)
        if not range_match:
            range_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:到|至|to|and|[-~])\s*(\d+(?:\.\d+)?)\s*(?:摄氏|°?C|degrees?)", text, re.I)
        if not range_match:
            return
        low, high = float(range_match.group(1)), float(range_match.group(2))
        task["requested_lower_temp_c"] = low
        task["requested_upper_temp_c"] = high
        conflict_words = ("不能超过", "不超过", "硬约束", "not exceed", "hard constraint", "must not")
        conflict = any(word.lower() in text.lower() for word in conflict_words)
        if conflict:
            task["constraint_notes"] = "自然语言中同时出现请求温度带与硬上限，保留两者并由工具报告冲突"
        else:
            task["lower_temp_c"] = low
            task["upper_temp_c"] = high

    def run(self, user_request: str, task_defaults: Optional[TaskSpec] = None) -> Dict[str, Any]:
        defaults = task_defaults or TaskSpec(task_id=f"agent-{int(time.time())}")
        initial_task = {**defaults.to_dict(), "user_request": user_request}
        self._request_hints(user_request, initial_task)
        state: Dict[str, Any] = {"task": initial_task, "trace": [], "results": {}}
        system = (
            "你是能智核运行方案试算助手。每轮只选一个工具并等待工具结果。"
            "先选 get_case_context，再选 validate_task（arguments 只写用户明确改变的字段），"
            "再选 search_plans（arguments 必须是空对象），最后选 prepare_report。"
            "不要复制 TaskSpec 全部字段，不要编造天气、功率、费用或节能；无解时保留无解，不能放宽硬约束。"
            "只输出结构化工具调用，不输出思维过程。"
        )
        compact_defaults = {
            "task_id": state["task"]["task_id"],
            "simulation_day": state["task"]["simulation_day"],
            "business_start_hour": state["task"]["business_start_hour"],
            "business_end_hour": state["task"]["business_end_hour"],
            "lower_temp_c": state["task"]["lower_temp_c"],
            "upper_temp_c": state["task"]["upper_temp_c"],
            "objective": state["task"]["objective"],
            "price_profile": state["task"]["price_profile"],
            "max_candidates": state["task"]["max_candidates"],
        }
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({"request": user_request, "task_defaults": compact_defaults, "allowed_tools": TOOLS}, ensure_ascii=False)},
        ]
        for round_index in range(self.max_rounds):
            started = time.perf_counter()
            try:
                successful_actions = [x.get("action") for x in state["trace"] if x.get("action")]
                if not successful_actions:
                    allowed_now = ["get_case_context"]
                else:
                    previous = successful_actions[-1]
                    if previous == "get_case_context":
                        allowed_now = ["validate_task"]
                    elif previous == "validate_task":
                        allowed_now = ["search_plans"] if state.get("task_valid") else ["validate_task"]
                    elif previous == "search_plans":
                        allowed_now = ["prepare_report"]
                    else:
                        allowed_now = TOOLS
                action = self._model(messages, allowed_now)
                tool_name = action["action"]
                tool_result = self._tool(tool_name, action.get("arguments", {}), state)
                trace_entry = {"round": round_index + 1, "action": tool_name, "arguments": action.get("arguments", {}), "message": action.get("message", ""), "result": tool_result, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "model": "local_configured_model"}
                state["trace"].append(trace_entry)
                messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
                messages.append({"role": "tool", "name": tool_name, "content": json.dumps(tool_result, ensure_ascii=False, default=str)})
                if tool_name == "get_case_context":
                    messages.append({"role": "user", "content": "上下文已返回。下一轮请只调用 validate_task，arguments 只写需要改变的数值字段；不要复制 request。"})
                elif tool_name == "validate_task" and tool_result.get("valid"):
                    messages.append({"role": "user", "content": "条件已校验。下一轮请只调用 search_plans，arguments 必须为空对象。"})
                elif tool_name == "search_plans":
                    messages.append({"role": "user", "content": "方案搜索已完成。下一轮请只调用 prepare_report，arguments 必须为空对象。"})
                if state.get("done"):
                    report = dict(state["report"])
                    report["agent_trace"] = state["trace"]
                    return {"status": "success", "report": report, "trace": state["trace"]}
            except Exception as exc:
                state["trace"].append({"round": round_index + 1, "action": None, "error": f"{type(exc).__name__}: {exc}", "latency_ms": round((time.perf_counter() - started) * 1000, 2)})
                if round_index + 1 < self.max_rounds:
                    messages.append({"role": "user", "content": "上一次输出未通过结构校验。请只返回一个允许的 JSON 工具调用，当前阶段优先 prepare_report；arguments 使用空对象。"})
                    continue
                return {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "trace": state["trace"], "task": state["task"]}
        return {"status": "failed", "error": f"超过最大模型轮数 {self.max_rounds}", "trace": state["trace"], "task": state["task"]}

    def run_one_shot(self, user_request: str, task_defaults: Optional[TaskSpec] = None) -> Dict[str, Any]:
        """B1 control: one local-model parse, then the same deterministic engine.

        There is no tool feedback in this condition.  A malformed parse is
        reported as a parse failure rather than repaired by the program.
        """
        task = task_defaults or TaskSpec(task_id=f"one-shot-{int(time.time())}")
        compact = {"task_id": task.task_id, "simulation_day": task.simulation_day, "business_start_hour": task.business_start_hour, "business_end_hour": task.business_end_hour, "lower_temp_c": task.lower_temp_c, "upper_temp_c": task.upper_temp_c, "objective": task.objective, "price_profile": task.price_profile, "max_candidates": task.max_candidates}
        messages = [
            {"role": "system", "content": "只做一次自然语言条件解析。请选择 validate_task，arguments 只含可执行的 TaskSpec 数值字段；不要调用其他工具，不要复制全部字段。"},
            {"role": "user", "content": json.dumps({"request": user_request, "task_defaults": compact}, ensure_ascii=False)},
        ]
        started = time.perf_counter()
        try:
            action = self._model(messages)
            if action["action"] != "validate_task":
                return {"status": "parse_failed", "reason": "one-shot model did not select validate_task", "action": action, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
            initial_task = {**task.to_dict(), "user_request": user_request}
            self._request_hints(user_request, initial_task)
            state = {"task": initial_task, "task_valid": False, "trace": [], "results": {}}
            validation = self._tool("validate_task", action.get("arguments", {}), state)
            if not validation.get("valid"):
                return {"status": "parse_failed", "reason": validation.get("errors"), "action": action, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
            report = self.evaluator.search(TaskSpec(**state["task"]))
            return {"status": "success", "report": report.to_dict(), "action": action, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
        except Exception as exc:
            return {"status": "parse_failed", "reason": f"{type(exc).__name__}: {exc}", "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
