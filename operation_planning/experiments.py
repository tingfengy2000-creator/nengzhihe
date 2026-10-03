"""Run the frozen operation-planning comparison without changing the grid."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any, Dict, List

from .boptest_adapter import LocalBestestAirFMUAdapter
from .schemas import PlanSegment, PlanSpec, TaskSpec, stable_hash
from .search import PlanEvaluator, generate_plans


BASE = Path(__file__).resolve().parent
FREEZE = BASE / "protocol" / "experiment_freeze.json"


def _fixed_plan(task: TaskSpec) -> PlanSpec:
    return PlanSpec(
        "fixed_precool_60_23",
        "fixed_reasonable",
        [PlanSegment(420, 480, 23.0, 15.0, "固定规则：营业前预冷 60 分钟")],
        task.objective,
        task.price_profile,
        "frozen_fixed_baseline",
    )


def run_comparison(days: List[int], step_seconds: int = 900, max_candidates: int = 6, output: Path | None = None) -> Dict[str, Any]:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    evaluator = PlanEvaluator(LocalBestestAirFMUAdapter(step_seconds=step_seconds))
    records: List[Dict[str, Any]] = []
    for day in days:
        base = TaskSpec(task_id=f"comparison-day-{day}", simulation_day=day, max_candidates=max_candidates)
        for engine, plan in (("A0_official_control", PlanSpec("baseline", "baseline", [], base.objective, base.price_profile, "official_default_schedule")), ("A1_fixed_plan", _fixed_plan(base))):
            started = time.perf_counter()
            result = evaluator.evaluate(base, plan)
            records.append({"group": "development" if day in freeze["development_date_blocks"] else "holdout", "day": day, "engine": engine, "plan_id": plan.plan_id, "result": result.to_dict(), "elapsed_seconds": time.perf_counter() - started})
        search_task = TaskSpec(task_id=f"search-day-{day}", simulation_day=day, max_candidates=max_candidates)
        started = time.perf_counter()
        report = evaluator.search(search_task, plans=generate_plans(search_task)[:max_candidates])
        records.append({"group": "development" if day in freeze["development_date_blocks"] else "holdout", "day": day, "engine": "A2_bounded_search", "report": report.to_dict(), "elapsed_seconds": time.perf_counter() - started})
    payload = {
        "protocol": freeze,
        "protocol_sha256": stable_hash(freeze),
        "adapter": evaluator.adapter.provenance(),
        "step_seconds": step_seconds,
        "date_blocks": {"development": [d for d in days if d in freeze["development_date_blocks"]], "holdout": [d for d in days if d in freeze["formal_holdout_date_blocks"]]},
        "records": records,
        "interpretation": "This is a bounded time-block replay of one official model, not independent buildings or an operational pilot. Feasibility is determined by the frozen temperature constraint; no savings or user-efficiency claim is inferred.",
    }
    output = output or (BASE / "results" / "experiments" / "frozen_comparison.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", default="153,289,161,177,193,209,225,241")
    parser.add_argument("--step-seconds", type=int, default=900)
    parser.add_argument("--max-candidates", type=int, default=6)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run_comparison([int(item) for item in args.days.split(",") if item.strip()], args.step_seconds, args.max_candidates, args.output)
    print(json.dumps({"records": len(payload["records"]), "output": str(args.output or BASE / "results" / "experiments" / "frozen_comparison.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
