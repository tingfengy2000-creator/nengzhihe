"""Run one reproducible real local-FMU operation-planning case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from operation_planning.boptest_adapter import LocalBestestAirFMUAdapter
from operation_planning.schemas import TaskSpec
from operation_planning.search import PlanEvaluator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", type=int, default=153)
    parser.add_argument("--max-candidates", type=int, default=2)
    parser.add_argument("--step-seconds", type=int, default=1800)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    task = TaskSpec(task_id=f"demo-day-{args.day}", simulation_day=args.day, max_candidates=args.max_candidates)
    evaluator = PlanEvaluator(LocalBestestAirFMUAdapter(step_seconds=args.step_seconds))
    report = evaluator.search(task)
    text = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
