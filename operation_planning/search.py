"""Deterministic bounded plan generation and FMU evaluation."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Dict, Iterable, List, Sequence

from .boptest_adapter import LocalBestestAirFMUAdapter
from .schemas import DecisionReport, PlanSegment, PlanSpec, SimulationResult, TaskSpec, stable_hash


BASE = Path(__file__).resolve().parent
PRICE_FILES = {
    "constant": BASE / "vendor" / "project1-boptest" / "testcases" / "bestest_air" / "models" / "Resources" / "electricity_prices_constant.csv",
    "dynamic": BASE / "vendor" / "project1-boptest" / "testcases" / "bestest_air" / "models" / "Resources" / "electricity_prices_dynamic.csv",
    "highly_dynamic": BASE / "vendor" / "project1-boptest" / "testcases" / "bestest_air" / "models" / "Resources" / "electricity_prices_highly_dynamic.csv",
}


def _read_prices(path: Path) -> List[tuple[int, float]]:
    lines = [line for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    rows = list(csv.DictReader(lines))
    if not rows:
        raise ValueError(f"价格文件为空：{path}")
    time_key = next((key for key in rows[0] if key and key.strip().lower() == "time"), None)
    price_key = next((key for key in rows[0] if key and "price" in key.lower()), None)
    if not time_key or not price_key:
        raise ValueError(f"价格文件缺少 time/price 列：{path}")
    return [(int(float(row[time_key])), float(row[price_key])) for row in rows]


def _price_at(seconds: float, prices: Sequence[tuple[int, float]]) -> float:
    year = 365 * 86400
    local = int(seconds) % year
    candidate = prices[0][1]
    for stamp, value in prices:
        if stamp > local:
            break
        candidate = value
    return candidate


def _segments(kind: str, duration: int = 0, cooling: float = 24.0) -> List[PlanSegment]:
    if kind == "baseline":
        return []
    if kind == "pre_cool":
        return [PlanSegment(8 * 60 - duration, 8 * 60, cooling, 15.0, f"营业前预冷 {duration} 分钟")]
    if kind == "setpoint_shift":
        return [PlanSegment(8 * 60, 18 * 60, cooling, 21.0, f"营业时段冷却设定 {cooling:.1f}°C")]
    if kind == "pre_cool_and_shift":
        return [
            PlanSegment(8 * 60 - duration, 8 * 60, cooling - 1.0, 15.0, f"营业前预冷 {duration} 分钟"),
            PlanSegment(8 * 60, 18 * 60, cooling, 21.0, f"营业时段冷却设定 {cooling:.1f}°C"),
        ]
    raise ValueError(f"未知方案类型：{kind}")


def generate_plans(task: TaskSpec) -> List[PlanSpec]:
    """Generate the frozen grid; the upper bound is 36 candidates."""
    choices: List[PlanSpec] = [PlanSpec("baseline", "baseline", _segments("baseline"), task.objective, task.price_profile)]
    # This grid is pre-registered before formal runs.  It is deliberately
    # small enough to audit and never expands during a run.
    for duration in (30, 60, 90, 120):
        for cooling in (22.0, 23.0):
            choices.append(PlanSpec(f"pre_cool_{duration}_{cooling:g}", "pre_cool", _segments("pre_cool", duration, cooling), task.objective, task.price_profile))
    for cooling in (23.0, 23.5, 24.0):
        choices.append(PlanSpec(f"shift_{cooling:g}", "setpoint_shift", _segments("setpoint_shift", 0, cooling), task.objective, task.price_profile))
    for duration in (60, 120):
        for cooling in (23.0, 23.5):
            choices.append(PlanSpec(f"combo_{duration}_{cooling:g}", "pre_cool_and_shift", _segments("pre_cool_and_shift", duration, cooling), task.objective, task.price_profile))
    return choices[: min(int(task.max_candidates), 36)]


class PlanEvaluator:
    def __init__(self, adapter: LocalBestestAirFMUAdapter | None = None, result_dir: Path | None = None):
        self.adapter = adapter or LocalBestestAirFMUAdapter()
        self.result_dir = result_dir or (BASE / "results" / "runs")
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.prices = {name: _read_prices(path) for name, path in PRICE_FILES.items() if path.exists()}

    def _cache_key(self, task: TaskSpec, plan: PlanSpec) -> str:
        return stable_hash({
            "testcase": task.testcase,
            "version": task.testcase_version,
            "commit": task.model_commit,
            "fmu_sha256": self.adapter.fmu_sha256,
            "simulation_day": task.simulation_day,
            "physical_schedule": plan.to_dict(),
            "step_seconds": self.adapter.step_seconds,
            "business": [task.business_start_hour, task.business_end_hour, task.lower_temp_c, task.upper_temp_c, task.tolerance_c],
            "recovery_hours": task.recovery_hours,
        })

    def evaluate(self, task: TaskSpec, plan: PlanSpec) -> SimulationResult:
        errors = task.validate()
        if errors:
            raise ValueError("; ".join(errors))
        cache_key = self._cache_key(task, plan)
        cache_path = self.result_dir / f"{cache_key}.json"
        if cache_path.exists():
            cached = SimulationResult(**json.loads(cache_path.read_text(encoding="utf-8")))
            # Cache identity is physical-input based.  Rebind the logical
            # task/plan identity on replay so a previous demo task can never
            # leak its name into a new report.
            cached.task_id = task.task_id
            cached.result_id = f"{task.task_id}:{plan.plan_id}"
            return cached
        raw = self.adapter.run(task.to_dict(), plan.to_dict())
        start, end = raw["target_period"]
        prices = self.prices.get(task.price_profile, self.prices.get("constant", []))
        electric = raw["electric_power_w"]
        times = raw["time_seconds"]
        target_mask = [start <= float(t) <= end for t in times]
        energy = sum(max(0.0, float(p)) for p, flag in zip(electric, target_mask) if flag) * raw["step_seconds"] / 3600000.0
        cost = sum(max(0.0, float(p)) * _price_at(float(t), prices) for p, t, flag in zip(electric, times, target_mask) if flag) * raw["step_seconds"] / 3600000.0
        raw["custom_metrics"]["target_electric_kwh"] = energy
        raw["custom_metrics"]["target_cost_usd"] = cost
        feasible = bool(raw["custom_metrics"].get("target_feasible", False))
        reasons: List[str] = []
        if not feasible:
            reasons.append("营业时段存在超过温度容差的点")
        result = SimulationResult(
            result_id=f"{task.task_id}:{plan.plan_id}",
            task_id=task.task_id,
            plan_id=plan.plan_id,
            testcase=task.testcase,
            testcase_version=task.testcase_version,
            simulation_day=task.simulation_day,
            step_seconds=int(raw["step_seconds"]),
            target_period=tuple(raw["target_period"]),
            recovery_period=tuple(raw["recovery_period"]),
            time_seconds=raw["time_seconds"],
            temperature_c=raw["temperature_c"],
            electric_power_w=raw["electric_power_w"],
            heating_power_w=raw["heating_power_w"],
            kpis=raw["kpis"],
            custom_metrics=raw["custom_metrics"],
            feasible=feasible,
            rejection_reasons=reasons,
            runtime_seconds=float(raw["runtime_seconds"]),
            cache_key=cache_key,
            evidence={"adapter": self.adapter.provenance(), "plan": plan.to_dict(), "price_profile": task.price_profile},
        )
        cache_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    def search(self, task: TaskSpec, plans: Iterable[PlanSpec] | None = None, trace: List[Dict[str, Any]] | None = None) -> DecisionReport:
        plans = list(plans or generate_plans(task))
        if len(plans) > 36:
            raise ValueError("候选方案超过 36 上限")
        candidates: List[Dict[str, Any]] = []
        for plan in plans:
            started = time.perf_counter()
            try:
                result = self.evaluate(task, plan)
                metric = result.custom_metrics.get("target_cost_usd") if task.objective == "cost" else result.custom_metrics.get("target_electric_kwh")
                candidates.append({
                    "plan": plan.to_dict(),
                    "result": result.to_dict(),
                    "objective_value_unrounded": float(metric),
                    "elapsed_seconds": time.perf_counter() - started,
                    "status": "feasible" if result.feasible else "infeasible",
                })
            except Exception as exc:
                candidates.append({"plan": plan.to_dict(), "status": "error", "error": str(exc), "elapsed_seconds": time.perf_counter() - started})
        valid = [c for c in candidates if c.get("status") in ("feasible", "infeasible")]
        feasible = [c for c in valid if c["status"] == "feasible"]
        ordered = sorted(valid, key=lambda c: (0 if c["status"] == "feasible" else 1, c.get("objective_value_unrounded", float("inf")), c["plan"]["plan_id"]))
        recommended = ordered[0]["plan"]["plan_id"] if feasible else None
        reason = "已按可行性优先、再按目标值排序" if recommended else "候选方案均未满足硬约束，保留失败原因并请求用户调整条件"
        return DecisionReport(
            task=task.to_dict(),
            candidates=ordered,
            feasible=bool(feasible),
            recommended_plan_id=recommended,
            recommendation_reason=reason,
            unresolved_requirements=[] if recommended else ["请放宽营业温度带、调整预冷窗口或补充可用运行时段后重新试算"],
            agent_trace=trace or [],
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
        )
