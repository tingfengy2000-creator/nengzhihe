"""Freeze and run the 16-task local-agent comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any, Dict, List

from .agent import OperationPlanningAgent
from .boptest_adapter import LocalBestestAirFMUAdapter
from .schemas import TaskSpec
from .search import PlanEvaluator


BASE = Path(__file__).resolve().parent


def frozen_tasks() -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    groups = [
        ("normal", [153, 177, 193, 209], "请在8点到18点保持21到24摄氏度，优先降低动态电价费用。"),
        ("change", [177, 193, 209, 225], "请把营业时段温度约束改为22到23摄氏度，重新试算并说明变化。"),
        ("failure", [161, 225, 241, 289], "请在8点到18点保持20到20.5摄氏度，若无解请说明缺口。"),
        ("conflict", [153, 177, 193, 209], "请要求营业室温在30到31摄氏度，同时不能超过24摄氏度；如果冲突请给出计算后的替代方案，不要放宽硬约束。"),
    ]
    for category, days, request in groups:
        for index, day in enumerate(days, 1):
            tasks.append({"task_id": f"{category}-{index:02d}", "category": category, "simulation_day": day, "request": request})
    return tasks


def run(output: Path | None = None, step_seconds: int = 900) -> Dict[str, Any]:
    tasks = frozen_tasks()
    evaluator = PlanEvaluator(LocalBestestAirFMUAdapter(step_seconds=step_seconds))
    agent = OperationPlanningAgent(evaluator=evaluator, max_rounds=8)
    records: List[Dict[str, Any]] = []
    for item in tasks:
        task = TaskSpec(task_id=item["task_id"], simulation_day=item["simulation_day"], max_candidates=1)
        b0_started = time.perf_counter()
        b0 = evaluator.search(task)
        b0_record = {"task_id": item["task_id"], "category": item["category"], "day": item["simulation_day"], "engine": "B0_structured_form_same_engine", "status": "success", "feasible": b0.feasible, "elapsed_seconds": time.perf_counter() - b0_started}
        b1 = agent.run_one_shot(item["request"], task)
        b1_record = {"task_id": item["task_id"], "category": item["category"], "day": item["simulation_day"], "engine": "B1_one_shot_local_model", "status": b1.get("status"), "elapsed_seconds": b1.get("latency_ms", 0) / 1000.0, "reason": b1.get("reason")}
        b2 = agent.run(item["request"], task)
        b2_record = {"task_id": item["task_id"], "category": item["category"], "day": item["simulation_day"], "engine": "B2_full_tool_feedback_agent", "status": b2.get("status"), "feasible": b2.get("report", {}).get("feasible"), "unresolved": b2.get("report", {}).get("unresolved_requirements"), "rounds": len(b2.get("trace", [])), "error_rounds": sum(1 for x in b2.get("trace", []) if not x.get("action")), "trace_actions": [x.get("action") for x in b2.get("trace", [])]}
        records.extend([b0_record, b1_record, b2_record])
    payload = {"task_count": len(tasks), "tasks": tasks, "step_seconds": step_seconds, "records": records, "interpretation": "B0/B1/B2 use the same deterministic engine; this measures parsing and bounded tool-loop behavior, not user efficiency. Participants were not simulated."}
    output = output or (BASE / "results" / "experiments" / "agent_comparison.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step-seconds", type=int, default=900)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    p = run(args.output, args.step_seconds)
    print(json.dumps({"task_count": p["task_count"], "record_count": len(p["records"]), "output": str(args.output or BASE / "results" / "experiments" / "agent_comparison.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
