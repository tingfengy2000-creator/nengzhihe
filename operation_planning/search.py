"""Deterministic bounded plan generation and FMU evaluation."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Dict, Iterable, List, Sequence
from datetime import date, timedelta

from .boptest_adapter import LocalBestestAirFMUAdapter
from .schemas import DecisionReport, PlanSegment, PlanSpec, SimulationResult, TaskSpec, stable_hash
from .tariffs import integrate_power, profile, profile_public_dict, tariff_hash


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


def _trapezoid(values: Sequence[float], times: Sequence[float]) -> float:
    """Small dependency-free trapezoid integrator for the Windows service."""
    return sum((float(a) + float(b)) * (float(tb) - float(ta)) / 2.0 for a, b, ta, tb in zip(values, values[1:], times, times[1:]))


def _segments(task: TaskSpec, kind: str, duration: int = 0, cooling: float = 24.0) -> List[PlanSegment]:
    start = int(task.business_start_hour) * 60
    end = int(task.business_end_hour) * 60
    if kind == "baseline":
        return []
    if kind == "pre_cool":
        return [PlanSegment(max(0, start - duration), start, cooling, 15.0, f"营业前预冷 {duration} 分钟")]
    if kind == "setpoint_shift":
        return [PlanSegment(start, end, cooling, 21.0, f"营业时段冷却设定 {cooling:.1f}°C")]
    if kind == "pre_cool_and_shift":
        return [
            PlanSegment(max(0, start - duration), start, cooling - 1.0, 15.0, f"营业前预冷 {duration} 分钟"),
            PlanSegment(start, end, cooling, 21.0, f"营业时段冷却设定 {cooling:.1f}°C"),
        ]
    raise ValueError(f"未知方案类型：{kind}")


def generate_plans(task: TaskSpec) -> List[PlanSpec]:
    """Generate a bounded, category-balanced candidate set.

    The strategy is versioned independently from the historical frozen scores;
    truncation no longer fills the budget with pre-cool-only candidates.
    """
    choices: List[PlanSpec] = [PlanSpec("baseline", "baseline", _segments(task, "baseline"), task.objective, task.price_profile)]
    pre = [
        PlanSpec(f"pre_cool_{duration}_{cooling:g}", "pre_cool", _segments(task, "pre_cool", duration, cooling), task.objective, task.price_profile, "balanced_v2")
        for duration in (30, 60, 90, 120) for cooling in (22.0, 23.0)
    ]
    shifts = [
        PlanSpec(f"shift_{cooling:g}", "setpoint_shift", _segments(task, "setpoint_shift", 0, cooling), task.objective, task.price_profile, "balanced_v2")
        for cooling in (23.0, 23.5, 24.0)
    ]
    combos = [
        PlanSpec(f"combo_{duration}_{cooling:g}", "pre_cool_and_shift", _segments(task, "pre_cool_and_shift", duration, cooling), task.objective, task.price_profile, "balanced_v2")
        for duration in (60, 120) for cooling in (23.0, 23.5)
    ]
    # Round-robin categories, preserving deterministic order and exposing the
    # actual comparison range in the report.
    pools = [pre, shifts, combos]
    while any(pools):
        for pool in pools:
            if pool:
                choices.append(pool.pop(0))
    return choices[: min(int(task.max_candidates), 36)]


class PlanEvaluator:
    def __init__(self, adapter: LocalBestestAirFMUAdapter | None = None, result_dir: Path | None = None):
        self.adapter = adapter or LocalBestestAirFMUAdapter()
        self.result_dir = result_dir or (BASE / "results" / "runs")
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.physical_dir = BASE / "results" / "physical_cache"
        self.physical_dir.mkdir(parents=True, exist_ok=True)
        self.prices = {name: _read_prices(path) for name, path in PRICE_FILES.items() if path.exists()}
        self.progress_callback = None
        self.cancel_callback = None

    def _physical_key(self, task: TaskSpec, plan: PlanSpec) -> str:
        return stable_hash({
            "testcase": task.testcase,
            "version": task.testcase_version,
            "commit": task.model_commit,
            "fmu_sha256": self.adapter.fmu_sha256,
            "runner_contract": "official_baseline_or_initialized_override_day_modulo_v5",
            "simulation_day": task.simulation_day,
            "physical_schedule": {"kind": plan.kind, "segments": [asdict(s) for s in plan.segments]},
            "step_seconds": self.adapter.step_seconds,
            "business": [task.business_start_hour, task.business_end_hour],
            "recovery_hours": task.recovery_hours,
            "occupancy_profile": task.occupancy_profile,
            "internal_gains_profile": task.internal_gains_profile,
        })

    def _cache_key(self, task: TaskSpec, plan: PlanSpec, physical_key: str) -> str:
        tariff = self._tariff(task)
        return stable_hash({
            "physical_key": physical_key,
            "constraints": [task.lower_temp_c, task.upper_temp_c, task.tolerance_c],
            "objective": task.objective,
            "tariff_id": task.tariff_id,
            "tariff_hash": tariff_hash(tariff) if tariff else task.price_profile,
            "calendar": task.tariff_calendar_date,
            "evaluation": "piecewise_rate_v2",
        })

    def _tariff(self, task: TaskSpec):
        if task.tariff_id in ("boptest_dynamic", "boptest_constant", "boptest_highly_dynamic"):
            return None
        return profile(task.tariff_id, task.custom_tariff)

    def _calendar_start(self, task: TaskSpec) -> date:
        if not task.tariff_calendar_date:
            raise ValueError("地区电价情景必须明确计费日历日期")
        return date.fromisoformat(task.tariff_calendar_date)

    def _costs(self, task: TaskSpec, raw: Dict[str, Any]) -> Dict[str, Any]:
        start, end = raw["target_period"]
        times = [float(x) for x in raw["time_seconds"]]
        if any(x is None for x in raw["electric_power_w"]):
            raise ValueError("功率序列存在缺测，不能把缺测静默当作0")
        power = [max(0.0, float(x)) for x in raw["electric_power_w"]]
        target_times = [t for t in times if start <= t <= end]
        target_power = [p for t, p in zip(times, power) if start <= t <= end]
        energy = float(_trapezoid(target_power, target_times) / 3600000.0) if len(target_times) >= 2 else 0.0
        tariff = self._tariff(task)
        if tariff:
            calendar = self._calendar_start(task)
            target_cost, by_period = integrate_power(times, power, tariff, calendar, float(start), float(end), timeline_origin=float(start))
            recovery_end = float(raw["recovery_period"][1])
            recovery_cost, recovery_periods = integrate_power(times, power, tariff, calendar, float(end), recovery_end, timeline_origin=float(start))
            return {
                "target_electric_kwh": energy,
                "target_cost_cny": target_cost,
                "recovery_cost_cny": recovery_cost,
                "total_cost_cny": target_cost + recovery_cost,
                "cost_currency": "CNY",
                "cost_unit": "CNY",
                "cost_period": "目标日 / 共同恢复段 / 合计",
                "cost_scope": "本模型冷却设备+风机电功率；不含建筑总表、需量/容量和燃气供热",
                "tariff_id": task.tariff_id,
                "tariff_period_costs": by_period,
                "recovery_period_costs": recovery_periods,
            }
        prices = self.prices.get(task.price_profile, self.prices.get("constant", []))
        selected_cost_values = [max(0.0, float(p)) * _price_at(float(t), prices) for p, t in zip(power, times) if start <= t <= end]
        cost = float(_trapezoid(selected_cost_values, target_times) / 3600000.0) if len(target_times) >= 2 else 0.0
        return {"target_electric_kwh": energy, "target_cost_usd": cost, "cost_currency": "USD", "cost_unit": "USD", "cost_period": "目标日", "cost_scope": "BOPTEST价格文件对应的模型电功率", "tariff_id": task.tariff_id}

    def evaluate(self, task: TaskSpec, plan: PlanSpec) -> SimulationResult:
        errors = task.validate()
        if errors:
            raise ValueError("; ".join(errors))
        physical_key = self._physical_key(task, plan)
        cache_key = self._cache_key(task, plan, physical_key)
        cache_path = self.result_dir / f"{cache_key}.json"
        if cache_path.exists():
            cached = SimulationResult(**json.loads(cache_path.read_text(encoding="utf-8")))
            # Cache identity is physical-input based.  Rebind the logical
            # task/plan identity on replay so a previous demo task can never
            # leak its name into a new report.
            cached.task_id = task.task_id
            cached.result_id = f"{task.task_id}:{plan.plan_id}"
            return cached
        physical_path = self.physical_dir / f"{physical_key}.json"
        if physical_path.exists():
            raw = json.loads(physical_path.read_text(encoding="utf-8"))
            raw["cache_reused"] = True
        else:
            raw = self.adapter.run(task.to_dict(), plan.to_dict())
            physical_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        start, end = raw["target_period"]
        electric = raw["electric_power_w"]
        times = raw["time_seconds"]
        target_mask = [start <= float(t) <= end for t in times]
        selected_energy_times = [float(t) for t, flag in zip(times, target_mask) if flag]
        selected_energy_values = [max(0.0, float(p)) for p, flag in zip(electric, target_mask) if flag]
        energy = float(_trapezoid(selected_energy_values, selected_energy_times) / 3600000.0) if len(selected_energy_times) >= 2 else 0.0
        raw["custom_metrics"].update(self._costs(task, raw))
        raw["custom_metrics"]["target_electric_kwh"] = energy
        # Re-evaluate constraints from the current task against the physical
        # trajectory.  The physical cache may be shared by scenarios with
        # different temperature bands; trusting a cached feasibility flag
        # would leak the old task's conclusion.
        tolerance = float(task.tolerance_c)
        target_points = [(float(t), float(temp)) for t, temp in zip(times, raw["temperature_c"]) if start <= float(t) <= end]
        strict_degree_hours = 0.0
        violations = 0
        for (ta, va), (tb, vb) in zip(target_points, target_points[1:]):
            dt_hours = max(0.0, tb - ta) / 3600.0
            strict_degree_hours += max(0.0, task.lower_temp_c - min(va, vb), max(va, vb) - task.upper_temp_c) * dt_hours
            if va < task.lower_temp_c - tolerance or va > task.upper_temp_c + tolerance or vb < task.lower_temp_c - tolerance or vb > task.upper_temp_c + tolerance:
                violations += 1
        feasible = bool(target_points) and violations == 0
        raw["custom_metrics"]["target_feasible"] = feasible
        raw["custom_metrics"]["occupied_strict_degree_hours"] = strict_degree_hours
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
            evidence={"adapter": self.adapter.provenance(), "plan": plan.to_dict(), "price_profile": task.price_profile, "tariff": profile_public_dict(self._tariff(task)) if self._tariff(task) else {"id": task.tariff_id, "mode": "BOPTEST"}, "physical_cache_key": physical_key},
            control_schedule=raw.get("control_schedule", {}),
        )
        cache_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    def search(self, task: TaskSpec, plans: Iterable[PlanSpec] | None = None, trace: List[Dict[str, Any]] | None = None) -> DecisionReport:
        plans = list(plans or generate_plans(task))
        if len(plans) > 36:
            raise ValueError("候选方案超过 36 上限")
        candidates: List[Dict[str, Any]] = []
        for index, plan in enumerate(plans, 1):
            if self.cancel_callback and self.cancel_callback():
                break
            if self.progress_callback:
                self.progress_callback({"type": "candidate_started", "completed": index - 1, "total": len(plans), "plan_id": plan.plan_id})
            started = time.perf_counter()
            try:
                result = self.evaluate(task, plan)
                metric_key = ("total_cost_cny" if task.objective == "cost" and task.tariff_id not in ("boptest_dynamic", "boptest_constant", "boptest_highly_dynamic") else "target_cost_usd") if task.objective == "cost" else "target_electric_kwh"
                metric = result.custom_metrics.get(metric_key)
                candidates.append({
                    "plan": plan.to_dict(),
                    "result": result.to_dict(),
                    "objective_value_unrounded": float(metric) if metric is not None else None,
                    "metric_key": metric_key,
                    "elapsed_seconds": time.perf_counter() - started,
                    "status": "feasible" if result.feasible else "infeasible",
                })
            except Exception as exc:
                candidates.append({"plan": plan.to_dict(), "status": "error", "error": str(exc), "elapsed_seconds": time.perf_counter() - started})
            if self.progress_callback:
                self.progress_callback({"type": "candidate_completed", "completed": len(candidates), "total": len(plans), "plan_id": plan.plan_id, "status": candidates[-1].get("status")})
        valid = [c for c in candidates if c.get("status") in ("feasible", "infeasible")]
        feasible = [c for c in valid if c["status"] == "feasible"]
        ordered = sorted(valid, key=lambda c: (0 if c["status"] == "feasible" else 1, c.get("objective_value_unrounded") if c.get("objective_value_unrounded") is not None else float("inf"), c["plan"]["plan_id"]))
        recommended = ordered[0]["plan"]["plan_id"] if feasible else None
        reason = "已按可行性优先、再按目标值排序" if recommended else "候选方案均未满足硬约束，保留失败原因并请求用户调整条件"
        return DecisionReport(
            task=task.to_dict(),
            candidates=ordered,
            feasible=bool(feasible),
            recommended_plan_id=recommended,
            recommendation_reason=reason + f"；本次比较范围：{len(plans)} 个候选，策略 balanced_v2",
            unresolved_requirements=[] if recommended else ["请放宽营业温度带、调整预冷窗口或补充可用运行时段后重新试算"],
            agent_trace=trace or [],
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
        )
