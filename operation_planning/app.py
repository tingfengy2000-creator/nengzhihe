"""Loopback-only workbench server for the operation-planning product."""

from __future__ import annotations

import csv
from dataclasses import asdict
from copy import deepcopy
from datetime import datetime, timedelta
from html import escape
import io
import json
import math
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse

from .agent import OperationPlanningAgent
from .boptest_adapter import LocalBestestAirFMUAdapter
from .external_physical import summarize as summarize_external_physical
from .schemas import TaskSpec
from .search import PlanEvaluator
from .tariffs import registry, profile as tariff_profile
from .equipment import catalogue
from .weather import available_sites, load_weather, parse_user_csv
from .weather import load_pv_weather
from .thermal_model import RoomSpec, simulate_room
from .lifecycle import life_cycle_cost
from .pv import PVScenario, PVQuote, run_pv_planning, scenario_from_dict, DEFAULT_KWP_PER_M2, generate_pv
from .pv_agent import PVPlanningAgent
from .wind import WindTurbineProfile, WindScenario, WindQuote, generate_wind
from .hybrid import HybridScenario, hybrid_task_from_dict, run_hybrid_planning, match_hybrid
from .hybrid_agent import HybridPlanningAgent
from .project_load import aggregate_project_load, project_load_context
from .carbon import factor_catalog, carbon_price_scenarios
from .agent_parse import local_model_status, parse_agent_request


ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"
# Read-only fixed replay samples for the 5060 UI.  Only these whitelisted
# 5090 files are exposed (exact names, no paths); nothing is copied into ui/
# so evidence cannot drift.  The compact v9 UI cases and v7 typical-week
# previews back the UI's sample mode; v6 stays listed for older reviewers.
REPLAY_DIR = ROOT.parent / "docs" / "handoff" / "replay_viewer"
REPLAY_SAMPLES = frozenset({"replay_cases.json", "aircost_cases.json", "replay_cases_room_contract.json",
                            "replay_cases_v6.json", "replay_previews_v7.json", "replay_cases_ui_v9.json"})
JOBS: dict[str, dict] = {}
LOCK = threading.RLock()
MIME = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".json": "application/json; charset=utf-8", ".csv": "text/csv; charset=utf-8",
}


def _tariff_options() -> dict:
    """Make verification status explicit for the UI option contract."""
    data = registry()
    for item in data.get("tariffs", []):
        item["provisional"] = not bool(item.get("verified"))
        item["verification_status"] = "verified" if item.get("verified") else "provisional"
    return data


def _api_error(exc: Exception, field: str | None = None) -> dict:
    """Return a stable, directly displayable Chinese validation response.

    Older clients only read ``error`` as a string, so that field remains a
    string for compatibility.  New clients can use ``field`` to focus the
    offending control and ``message`` as the display text.
    """
    message = str(exc) or "请求参数无效"
    if field is None:
        text = message
        markers = {
            "requested_capacities_kwp": "pv.requested_capacities_kwp",
            "pv.capacity_kwp": "pv.capacity_kwp",
            "光伏容量": "pv.capacity_kwp",
            "预算": "hybrid.budget_cny",
            "电价档案": "pv.tariff_id",
            "电价": "pv.tariff_id",
            "tariff_escalation_rate": "hybrid.tariff_escalation_rate",
            "电价年涨幅": "hybrid.tariff_escalation_rate",
            "天气": "weather",
            "房间": "room",
            "设备型号": "room.equipment_id",
            "外送": "hybrid.export_limit_kw",
        }
        for marker, key in markers.items():
            if marker in text:
                field = key
                break
    return {"status": "failed", "error": message, "message": message, "field": field}


def _capacity_candidates(pv_payload: dict) -> list[float]:
    """Resolve an explicit or automatic finite PV capacity sweep."""
    raw = pv_payload.get("requested_capacities_kwp")
    if raw is not None:
        if not isinstance(raw, list) or not raw:
            raise ValueError("pv.requested_capacities_kwp 必须是非空数组")
        values = []
        for value in raw:
            if isinstance(value, bool):
                raise ValueError("pv.requested_capacities_kwp 含非数值")
            try:
                value = float(value)
            except Exception as exc:
                raise ValueError("pv.requested_capacities_kwp 含非数值") from exc
            if not math.isfinite(value) or value < 0:
                raise ValueError("pv.requested_capacities_kwp 必须是非负有限数")
            values.append(value)
        return sorted(set(values))
    if pv_payload.get("auto_capacity"):
        try:
            roof = float(pv_payload.get("roof_area_m2", 0.0))
            usable = float(pv_payload.get("usable_fraction", 0.8))
        except Exception as exc:
            raise ValueError("pv.roof_area_m2 与 pv.usable_fraction 必须是数字") from exc
        if not math.isfinite(roof) or roof <= 0 or not math.isfinite(usable) or not 0 < usable <= 1:
            raise ValueError("自动比选需要有效的pv.roof_area_m2和pv.usable_fraction")
        maximum = roof * usable * DEFAULT_KWP_PER_M2
        # Keep the finite sweep explainable and bounded.  The capacity limit
        # is always included so users can see the roof constraint.
        return sorted(set([0.0, round(maximum * 0.25, 6), round(maximum * 0.5, 6), round(maximum, 6)]))
    value = pv_payload.get("capacity_kwp", None)
    if value is not None:
        try:
            value = float(value)
        except Exception as exc:
            raise ValueError("pv.capacity_kwp 必须是非负有限数") from exc
        if not math.isfinite(value) or value < 0:
            raise ValueError("pv.capacity_kwp 必须是非负有限数")
        return [value]
    return [2.0]


def _task_from(payload: dict, job_id: str) -> TaskSpec:
    raw = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    allowed = set(TaskSpec.__dataclass_fields__)
    values = {key: value for key, value in raw.items() if key in allowed}
    values.setdefault("task_id", job_id)
    values["user_request"] = str(payload.get("request", values.get("user_request", "")))
    values.setdefault("tariff_id", "boptest_dynamic")
    if values.get("tariff_id", "").startswith("boptest_"):
        values["price_profile"] = values["tariff_id"].removeprefix("boptest_")
    return TaskSpec(**values)


def _event(job_id: str, data: dict) -> None:
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.setdefault("events", []).append({"at": time.time(), **data})
        job["events"] = job["events"][-80:]
        if data.get("type") == "candidate_completed":
            job["completed_candidates"] = int(data.get("completed", 0))
            job["total_candidates"] = int(data.get("total", 0))


def _worker(job_id: str, payload: dict) -> None:
    with LOCK:
        JOBS[job_id].update(status="running", started_at=time.time())
    _event(job_id, {"type": "started", "message": "已验证任务约束，准备回放物理模型"})
    try:
        task = _task_from(payload, job_id)
        evaluator = PlanEvaluator(LocalBestestAirFMUAdapter(step_seconds=int(payload.get("step_seconds", 900))))
        evaluator.progress_callback = lambda data: _event(job_id, data)
        evaluator.cancel_callback = lambda: bool(JOBS.get(job_id, {}).get("cancel_requested"))
        if bool(payload.get("use_agent", False)):
            output = OperationPlanningAgent(evaluator=evaluator).run(task.user_request or "请根据结构化条件试算方案", task)
        else:
            report = evaluator.search(task)
            output = {"status": "success", "report": report.to_dict(), "trace": []}
        cancelled = bool(JOBS.get(job_id, {}).get("cancel_requested"))
        status = "cancelled" if cancelled else ("done" if output.get("status") == "success" else "failed")
        report = output.get("report") if isinstance(output, dict) else None
        current_result_id = None
        if report and report.get("recommended_plan_id"):
            chosen = next((x for x in report.get("candidates", []) if x.get("plan", {}).get("plan_id") == report["recommended_plan_id"]), None)
            current_result_id = chosen.get("result", {}).get("result_id") if chosen else None
        with LOCK:
            JOBS[job_id].update(status=status, finished_at=time.time(), output=output, task=task.to_dict(), current_result_id=current_result_id, user_confirmed=False)
        _event(job_id, {"type": "report_ready", "message": "已完成候选比较，等待用户确认当前方案"})
    except Exception as exc:
        with LOCK:
            JOBS[job_id].update(status="failed", finished_at=time.time(), output={"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        _event(job_id, {"type": "failed", "message": str(exc)})


def _selected(job: dict) -> tuple[dict, dict]:
    if job.get("status") != "done" or not job.get("output") or not job.get("current_result_id"):
        raise ValueError("没有可导出的当前结果")
    if not job.get("user_confirmed"):
        raise PermissionError("请先确认当前推荐方案，再导出")
    report = job["output"].get("report", {})
    result_id = job["current_result_id"]
    selected = next((x for x in report.get("candidates", []) if x.get("result", {}).get("result_id") == result_id), None)
    if not selected:
        raise ValueError("当前结果已失效，请重新计算")
    return report, selected


def _html_card(report: dict, selected: dict) -> str:
    task = report.get("task", {}); result = selected.get("result", {}); metrics = result.get("custom_metrics", {}); plan = selected.get("plan", {})
    name = {"baseline": "模型默认运行", "pre_cool": "营业前预冷", "setpoint_shift": "营业时段温度调整", "pre_cool_and_shift": "预冷并调整温度"}.get(plan.get("kind"), plan.get("plan_id", "当前方案"))
    amount = metrics.get("total_cost_cny", metrics.get("target_cost_usd")); currency = metrics.get("cost_currency", "USD")
    return f"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>能智核方案卡</title><style>body{{font:15px/1.6 system-ui,'Microsoft YaHei',sans-serif;max-width:920px;margin:40px auto;color:#172033}}table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;border-bottom:1px solid #dbe3ef;text-align:left}}.tag{{color:#2563eb}}</style><h1>能智核｜运行方案核查卡</h1><p class='tag'>当前推荐：{escape(str(name))}（{escape(str(plan.get('plan_id','')))}）</p><p>任务：{escape(str(task.get('user_request','')))}</p><table><tr><th>是否满足要求</th><td>{'满足使用要求' if selected.get('status')=='feasible' else '部分时段未达标'}</td></tr><tr><th>电费估算</th><td>{escape(str(amount))} {escape(str(currency))}；{escape(str(metrics.get('cost_period','目标日')))}</td></tr><tr><th>计费范围</th><td>{escape(str(metrics.get('cost_scope','')))}</td></tr><tr><th>空调电量</th><td>{escape(str(metrics.get('target_electric_kwh','')))} kWh</td></tr></table><h2>方案控制</h2><pre>{escape(json.dumps(plan.get('segments',[]),ensure_ascii=False,indent=2))}</pre><p>固定模型与天气下的地区电价情景试算，非当地楼宇预测。</p></html>"""


def _thermal_inputs(payload: dict) -> tuple[RoomSpec, dict, dict]:
    """Build one authoritative room/cost object for API and lifecycle."""
    room_data = dict(payload.get("room") or {})
    for name in ("room_count", "units_per_room"):
        if name in payload:
            if name in room_data and int(room_data[name]) != int(payload[name]):
                raise ValueError(f"顶层{name} 与 room.{name} 不一致；请确认房间口径")
            room_data[name] = payload[name]
    # The old UI sends quantity for same-room batches. Make this migration
    # explicit in the returned task object instead of guessing in lifecycle.
    if "room_count" not in room_data and "quantity" in payload:
        room_data["room_count"] = payload["quantity"]
    if "quantity" in payload and "room_count" in room_data and int(payload["quantity"]) != int(room_data["room_count"]):
        raise ValueError("quantity 与 room.room_count 不一致；请只保留 room_count")
    allowed = set(RoomSpec.__dataclass_fields__)
    room = RoomSpec(**{k: v for k, v in room_data.items() if k in allowed})
    cost_data = dict(payload.get("cost") or {})
    quote = dict(payload.get("equipment_quote") or cost_data.get("equipment_quote") or {})
    def value(name: str, default: object = None) -> object:
        return cost_data[name] if name in cost_data else payload.get(name, default)
    tariff_id = value("tariff_id")
    annual_price = value("annual_price_cny_per_kwh")
    if tariff_id and annual_price is not None:
        raise ValueError("annual_price_cny_per_kwh 与 tariff_id 不能同时提供")
    tariff = None
    tariff_mapping = None
    calendar_start = value("tariff_calendar_start", value("tariff_calendar_date"))
    if tariff_id:
        tariff = tariff_profile(str(tariff_id), cost_data.get("custom_tariff") or payload.get("custom_tariff"))
        tariff_mapping = {"tariff_id": tariff.tariff_id, "calendar_start": calendar_start, "note": "用户确认的电价有效期/评价日映射；未提供映射则使用天气首日并由有效期校验拒绝不覆盖情景"}
    cost = {
        "study_years": int(value("study_years", 10)),
        "price_cny_per_kwh": None if annual_price is None else float(annual_price),
        "tariff_profile": tariff,
        "calendar_start": calendar_start,
        "discount_rate": float(value("discount_rate", 0.0)),
        "room_count": int(room.room_count),
        "units_per_room": int(room.units_per_room if room.units_per_room is not None else (room.equipment_count or 1)),
        "expected_life_years": value("expected_life_years"),
        "warranty_years": value("warranty_years"),
        "quote_scope": str(value("quote_scope", "per_unit")),
        "quantity_semantics": "room_count × units_per_room; thermal energy is not multiplied by units_per_room again",
        "quote": quote,
        "tariff_mapping": tariff_mapping,
    }
    return room, cost, {"room": room_data, "cost": {k: v for k, v in cost.items() if k != "tariff_profile"}}


def _thermal_capacity_sweep(payload: dict) -> dict:
    """Run the same thermal model for 1..N units and report service gaps.

    Each run is a one-room trace; ``room_count`` is retained in the contract
    but is deliberately not multiplied here.  Project aggregation remains the
    responsibility of ``aggregate_project_load`` in the normal run endpoint.
    """
    room, _, contract = _thermal_inputs(payload)
    raw_max = payload.get("max_units", payload.get("max_equipment_count", 12))
    try:
        max_units = int(raw_max)
    except Exception as exc:
        raise ValueError("max_units 必须是1到50之间的整数") from exc
    if max_units < 1 or max_units > 50:
        raise ValueError("max_units 必须是1到50之间的整数")
    site_id = str(payload.get("site_id", "guangzhou")); year = int(payload.get("year", 2024))
    weather = payload.get("weather") or load_weather(site_id, year)
    rows = []
    adequacy_rule = None
    for units in range(1, max_units + 1):
        trial_payload = dict(payload)
        trial_room = dict(contract.get("room") or {})
        trial_room["units_per_room"] = units
        trial_room["equipment_count"] = units
        trial_payload["room"] = trial_room
        trial_room_obj, _, _ = _thermal_inputs(trial_payload)
        result = simulate_room(weather, trial_room_obj)
        if adequacy_rule is None:
            adequacy_rule = (result.get("load_series") or {}).get("adequacy_rule")
        summary = result.get("summary", {})
        gaps = {
            "capacity_shortfall_hours": float(summary.get("capacity_shortfall_hours", 0.0) or 0.0),
            "unmet_temp_degree_hours": float(summary.get("unmet_temp_degree_hours", 0.0) or 0.0),
            "unmet_rh_percent_hours": float(summary.get("unmet_rh_percent_hours", 0.0) or 0.0),
        }
        adequate = all(value <= 1e-9 for value in gaps.values())
        rows.append({
            "units_per_room": units,
            "service_status": "within_modeled_scope" if adequate else "service_gap",
            "service_quality": "within_modeled_scope" if adequate else "service_gap",
            "annual_electric_kwh": float(summary.get("electric_kwh", 0.0) or 0.0),
            "annual_cooling_kwh": float(summary.get("cooling_kwh", 0.0) or 0.0),
            "capacity_shortfall_hours": gaps["capacity_shortfall_hours"],
            "unmet_temp_degree_hours": gaps["unmet_temp_degree_hours"],
            "unmet_rh_percent_hours": gaps["unmet_rh_percent_hours"],
        })
    minimum = next((row["units_per_room"] for row in rows if row["service_status"] == "within_modeled_scope"), None)
    return {
        "status": "success", "site_id": site_id, "year": year,
        "weather_hash": weather.get("hash"), "input_contract": contract,
        "max_units": max_units, "minimum_adequate_units_per_room": minimum,
        "candidates": rows,
        "adequacy_rule": adequacy_rule,
        "notes": ["每个候选均为同一房间的独立热湿回放；未把room_count重复乘入。", "额定点设备适配，不等同现场实测选型。"],
    }


def _hybrid_capacity_run(payload: dict, progress=None) -> dict:
    """Run hybrid planning through one deterministic API path.

    A capacity sweep reuses the loaded weather and project load but executes
    the complete hybrid tool for each capacity.  The selected report is the
    one with the highest eligible S1 incremental NPV; all sweep rows remain
    visible so the UI can explain the recommendation.
    """
    payload = dict(payload)
    site_id = str(payload.get("site_id", "guangzhou")); year = int(payload.get("year", 2024))
    room, _, _ = _thermal_inputs(payload)
    load_weather_data = payload.get("weather") or load_weather(site_id, year)
    pv_weather_data = payload.get("pv_weather") or load_pv_weather(site_id, year)
    load_result = aggregate_project_load(simulate_room(load_weather_data, room))
    pv_raw = dict(payload.get("pv") or {})
    # State/review variants may pin one user-requested capacity so the API
    # returns its real unknown/excluded status instead of silently replacing
    # it with the 0 kWp baseline.  This is a validated task constraint, not a
    # recommendation shortcut; normal user requests continue to sweep.
    fixed_capacity_raw = pv_raw.get("fixed_capacity_kwp")
    fixed_capacity = None
    if fixed_capacity_raw is not None:
        try:
            fixed_capacity = float(fixed_capacity_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("pv.fixed_capacity_kwp必须是非负有限数") from exc
        if not math.isfinite(fixed_capacity) or fixed_capacity < 0:
            raise ValueError("pv.fixed_capacity_kwp必须是非负有限数")
        capacities = [fixed_capacity]
    else:
        capacities = _capacity_candidates(pv_raw)
    reports = []
    total = len(capacities)
    for index, capacity in enumerate(capacities, 1):
        one_payload = dict(payload)
        one_pv = dict(pv_raw)
        one_pv.pop("requested_capacities_kwp", None); one_pv.pop("auto_capacity", None); one_pv.pop("fixed_capacity_kwp", None)
        one_payload["pv"] = one_pv
        one_hybrid = dict(payload.get("hybrid") or {})
        one_hybrid["pv_capacity_kwp"] = capacity
        one_payload["hybrid"] = one_hybrid
        pv_scenario, hybrid = hybrid_task_from_dict(one_payload, site_id=site_id, year=year)
        # Sweep rows do not need 8,784-row hourly payloads.  The selected
        # capacity is rerun with hourly output below, keeping API memory
        # bounded while preserving a complete selected result.
        report = run_hybrid_planning(load_result, pv_weather_data, pv_scenario, hybrid,
                                     WindTurbineProfile.from_file(), include_hourly=False,
                                     carbon=payload.get("carbon"), storage=payload.get("storage"))
        reports.append(report)
        if progress:
            progress(index, total, capacity)
    if not reports:
        raise ValueError("没有可计算的光伏容量")
    # S1 is the PV-only option.  Preserve the full selected report (including
    # S0/S2/S3 hourly traces), while the sweep carries the comparison rows.
    sweep = []
    for capacity, report in zip(capacities, reports):
        row = next((candidate for candidate in report.get("candidates", []) if candidate.get("scenario_id") == "S1_pv"), None)
        if row is None:
            continue
        economics = row.get("economics") or {}
        sweep.append({
            "requested_capacity_kwp": capacity,
            "status": row.get("constraint_status"),
            "admission_status": row.get("admission_status"),
            "constraint_reasons": row.get("constraint_reasons"),
            "economics_status": economics.get("status"),
            "capex_cny": economics.get("capex_cny"),
            "total_cost_npv_cny": economics.get("total_cost_npv_cny"),
            "incremental_npv_vs_s0_cny": economics.get("incremental_npv_vs_s0_cny"),
            "self_use_kwh": row.get("self_use_kwh"),
            "generation_kwh": row.get("generation_kwh"),
            "self_consumption_rate": (row.get("self_use_kwh", 0.0) / row.get("generation_kwh", 1.0)) if row.get("generation_kwh", 0.0) else None,
            "self_use_rate": (row.get("self_use_kwh", 0.0) / row.get("generation_kwh", 1.0)) if row.get("generation_kwh", 0.0) else None,
            "curtailment_kwh": row.get("curtailment_kwh"),
            "waste_rate": (row.get("curtailment_kwh", 0.0) / row.get("generation_kwh", 1.0)) if row.get("generation_kwh", 0.0) else None,
            "grid_import_kwh": row.get("grid_import_kwh"),
            "carbon": row.get("carbon"),
            "avoided_tco2_study_period": (row.get("carbon") or {}).get("avoided_tco2_study_period"),
            "cost_per_tco2_cny": (row.get("carbon") or {}).get("cost_per_tco2_cny"),
        })
    eligible = [row for row in sweep if row.get("status") == "feasible" and row.get("incremental_npv_vs_s0_cny") is not None]
    # S0 is always retained.  If all nonzero rows are ineligible, the first
    # capacity remains the display report and recommendation says unresolved.
    best_capacity = fixed_capacity if fixed_capacity is not None else (max(eligible, key=lambda row: float(row["incremental_npv_vs_s0_cny"]))["requested_capacity_kwp"] if eligible else 0.0)
    selected_index = capacities.index(best_capacity) if best_capacity in capacities else 0
    selected = reports[selected_index]
    # Re-run only the selected capacity with the complete hourly traces used
    # by the UI.  This is a real deterministic computation, not a cached
    # replay; the sweep reports above remain the source of the comparison.
    selected_payload = dict(payload)
    selected_pv = dict(pv_raw); selected_pv.pop("requested_capacities_kwp", None); selected_pv.pop("auto_capacity", None); selected_pv.pop("fixed_capacity_kwp", None)
    selected_payload["pv"] = selected_pv
    selected_hybrid = dict(payload.get("hybrid") or {}); selected_hybrid["pv_capacity_kwp"] = best_capacity
    selected_payload["hybrid"] = selected_hybrid
    selected_pv_scenario, selected_hybrid_scenario = hybrid_task_from_dict(selected_payload, site_id=site_id, year=year)
    selected = run_hybrid_planning(load_result, pv_weather_data, selected_pv_scenario, selected_hybrid_scenario,
                                   WindTurbineProfile.from_file(), include_hourly=True,
                                   carbon=payload.get("carbon"), storage=payload.get("storage"))
    # Expose the project-load contract at a stable top-level key for replay
    # consumers; the underlying engine keeps the same nested provenance too.
    selected["project_load_contract"] = (selected.get("load_context") or {}).get("project_load_context")
    selected["pv_capacity_sweep"] = sweep
    selected["recommended_pv_capacity_kwp"] = best_capacity
    selected["recommendation_basis"] = ("状态变体按12.1固定1kWp主方案" if fixed_capacity is not None else "在有限、计价完整且满足屋顶/预算约束的PV-only容量候选中，按相对S0增量NPV选择；不是全局优化。")
    selected["calculation_timing"] = {"capacity_count": total}
    return selected


def _preview_period_indices(times: list[str], period: str, season: str, month: int | None = None) -> tuple[list[int], dict]:
    """Return a deterministic contiguous typical-week/month selection.

    The preview is deliberately a fixed replay window, rather than a
    data-dependent "most representative" choice.  Summer is July 15--21
    (inclusive) and winter is January 15--21; a month preview uses the whole
    corresponding July or January.  This keeps API calls reproducible across
    machines and avoids looking at the output before choosing the window.
    """
    normalized_period = str(period or "week").strip().lower()
    if normalized_period in {"typical_week", "summer_week", "winter_week"}:
        normalized_period = "week"
    if normalized_period in {"typical_month", "summer_month", "winter_month"}:
        normalized_period = "month"
    if normalized_period not in {"week", "month"}:
        raise ValueError("preview.period必须是week或month")
    normalized_season = str(season or "summer").strip().lower()
    if normalized_season in {"夏", "夏季", "july"}:
        normalized_season = "summer"
    elif normalized_season in {"冬", "冬季", "january"}:
        normalized_season = "winter"
    if normalized_season not in {"summer", "winter"}:
        raise ValueError("preview.season必须是summer或winter")
    if month is None:
        month = 7 if normalized_season == "summer" else 1
    else:
        try:
            month = int(month)
        except (TypeError, ValueError) as exc:
            raise ValueError("preview.month必须是1到12的整数") from exc
        if not 1 <= month <= 12:
            raise ValueError("preview.month必须是1到12的整数")
    parsed: list[datetime] = []
    for value in times:
        try:
            parsed.append(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
        except Exception as exc:
            raise ValueError(f"时间戳无法解析：{value}") from exc
    if not parsed:
        raise ValueError("预览时间序列为空")
    years = sorted({dt.year for dt in parsed if dt.month == month})
    if not years:
        raise ValueError(f"缓存天气中没有{month}月记录，无法生成{normalized_season}预览")
    year = years[0]
    day = 15
    if normalized_period == "month":
        day = 1
    start = parsed[0].replace(year=year, month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
    if normalized_period == "week":
        end = start + timedelta(days=7)
        rule = f"固定选择每年{month}月15日00:00至{month}月22日00:00；未指定月份时夏季7月、冬季1月"
    else:
        if month == 12:
            end = start.replace(year=year + 1, month=1, day=1)
        else:
            end = start.replace(month=month + 1, day=1)
        rule = f"固定选择每年{month}月完整月份；未指定月份时夏季7月、冬季1月"
    indices = [i for i, dt in enumerate(parsed) if start <= dt < end]
    if not indices:
        raise ValueError("固定预览窗口在当前天气时间轴中没有记录")
    expected_seconds = (end - start).total_seconds()
    # Do not silently accept a partial week/month.  The cache may be a user
    # upload, in which case the caller gets a clear boundary error instead of
    # a deceptively short "typical" curve.
    if len(parsed) >= 2:
        interval_seconds = (parsed[1] - parsed[0]).total_seconds()
    else:
        interval_seconds = 0
    if interval_seconds <= 0 or len(indices) * interval_seconds != expected_seconds:
        raise ValueError("典型预览需要完整连续的周或月记录")
    return indices, {"period": normalized_period, "season": normalized_season,
                     "month": month,
                     "selection_rule": rule, "start": str(times[indices[0]]),
                     "end_exclusive": end.isoformat(timespec="minutes"),
                     "expected_duration_hours": expected_seconds / 3600.0,
                     "row_count": len(indices)}


def _slice_weather(weather: dict, indices: list[int]) -> dict:
    """Slice an already-normalized weather object without changing values."""
    out = dict(weather)
    n = len(weather.get("time", []))
    out["time"] = [weather["time"][i] for i in indices]
    out["interval_seconds"] = [weather.get("interval_seconds", [3600] * n)[i] for i in indices]
    if "source_timestamp" in weather:
        out["source_timestamp"] = [weather["source_timestamp"][i] for i in indices]
    for field in ("interval_start", "interval_end", "representative_time"):
        if field in weather:
            out[field] = [weather[field][i] for i in indices]
    hourly = {}
    for name, values in (weather.get("hourly") or {}).items():
        if isinstance(values, list) and len(values) == n:
            hourly[name] = [values[i] for i in indices]
        else:
            hourly[name] = values
    out["hourly"] = hourly
    # Keep provenance, but expose the selected physical interval explicitly.
    normalization = deepcopy(weather.get("weather_normalization") or {})
    for field in ("source_timestamp", "interval_start", "interval_end", "representative_time", "interval_seconds"):
        if isinstance(normalization.get(field), list) and len(normalization[field]) == n:
            normalization[field] = [normalization[field][i] for i in indices]
    if normalization:
        out["weather_normalization"] = normalization
    return out


def _slice_project_load(load_result: dict, indices: list[int]) -> dict:
    """Keep a project load trace while selecting the same physical intervals."""
    out = deepcopy(load_result)
    series = out.get("load_series") or {}
    n = len(series.get("timestamps", []))
    for field, values in list(series.items()):
        if isinstance(values, list) and len(values) == n:
            series[field] = [values[i] for i in indices]
    seconds = [series.get("interval_seconds", [3600] * len(indices))[i] for i in range(len(indices))]
    summary = {}
    power_map = {"electric_kwh": "electric_power_w", "cooling_kwh": "cooling_load_w", "latent_cooling_kwh": "latent_load_w"}
    for energy, power in power_map.items():
        vals = series.get(power)
        if vals is not None:
            summary[energy] = sum(float(v) * float(sec) / 3_600_000.0 for v, sec in zip(vals, seconds))
    if "capacity_shortfall_w" in series:
        # ``capacity_shortfall_w`` is a physical residual and can be non-zero
        # while a room is unoccupied (for example the envelope-only trace
        # outside the schedule).  The annual thermal summary scores service
        # only in occupied/cooling intervals, so a preview must use the same
        # mask instead of counting every positive residual.  ``active`` is
        # preferred because cooling_active also includes bounded pre-cooling;
        # legacy uploaded traces without masks retain the old conservative
        # fallback and are explicitly covered by the contract tests.
        active_mask = series.get("active")
        cooling_mask = series.get("cooling_active")
        mask = active_mask if isinstance(active_mask, list) and len(active_mask) == len(seconds) else cooling_mask
        if not isinstance(mask, list) or len(mask) != len(seconds):
            mask = [True] * len(seconds)
        summary["capacity_shortfall_hours"] = sum(
            float(sec) / 3600.0
            for value, sec, is_service_interval in zip(series["capacity_shortfall_w"], seconds, mask)
            if bool(is_service_interval) and float(value) > 0
        )
    summary["unmet_temp_degree_hours"] = sum(float(v) for v in series.get("temperature_unmet_degree_hours", []))
    summary["unmet_rh_percent_hours"] = sum(float(v) for v in series.get("rh_unmet_percent_hours", []))
    out["summary"] = summary
    out["load_series"] = series
    return out


def _hybrid_preview(payload: dict) -> dict:
    """Compute physical matching for one fixed typical week or month.

    No lifecycle, tariff, carbon or annual extrapolation is run here.  The
    same thermal, pvlib and wind generation functions as the annual endpoint
    are applied to the selected interval rows, so the preview is a view of
    the annual physical series rather than a new approximation.
    """
    started = time.perf_counter()
    payload = dict(payload or {})
    site_id = str(payload.get("site_id", "guangzhou")); year = int(payload.get("year", 2024))
    preview = dict(payload.get("preview") or {})
    period = preview.get("period", payload.get("period", "week"))
    season = preview.get("season", payload.get("season", "summer"))
    room, _, _ = _thermal_inputs(payload)
    weather_full = payload.get("weather") or load_weather(site_id, year)
    pv_weather_full = payload.get("pv_weather") or load_pv_weather(site_id, year)
    if list(weather_full.get("time", [])) != list(pv_weather_full.get("time", [])):
        raise ValueError("负荷与风光天气时间轴不一致，拒绝生成预览")
    indices, selection = _preview_period_indices(list(weather_full.get("time", [])), period, season, preview.get("month"))
    full_load = aggregate_project_load(simulate_room(weather_full, room))
    load = _slice_project_load(full_load, indices)
    pv_weather = _slice_weather(pv_weather_full, indices)
    # Capacity is a user input for preview.  No candidate sweep or economic
    # recommendation is made; defaulting to the ordinary 2 kWp example is
    # explicit in the response metadata.
    hybrid_raw = dict(payload.get("hybrid") or {})
    pv_raw = dict(payload.get("pv") or {})
    if payload.get("pv_capacity_kwp") is not None:
        hybrid_raw["pv_capacity_kwp"] = payload["pv_capacity_kwp"]
    elif pv_raw.get("capacity_kwp") is not None:
        hybrid_raw["pv_capacity_kwp"] = pv_raw.get("capacity_kwp")
    hybrid_payload = dict(payload); hybrid_payload["hybrid"] = hybrid_raw
    pv_scenario, hybrid = hybrid_task_from_dict(hybrid_payload, site_id=site_id, year=year)
    explicit_capacity = (payload.get("pv_capacity_kwp") is not None or pv_raw.get("capacity_kwp") is not None or pv_raw.get("fixed_capacity_kwp") is not None or hybrid_raw.get("pv_capacity_kwp") is not None)
    if hybrid_raw.get("pv_capacity_kwp") is None and pv_raw.get("fixed_capacity_kwp") is not None:
        hybrid.pv_capacity_kwp = float(pv_raw["fixed_capacity_kwp"])
    roof_limit = float(pv_scenario.roof_area_m2) * float(pv_scenario.usable_fraction) * DEFAULT_KWP_PER_M2
    capacity_defaulted = not explicit_capacity
    if capacity_defaulted:
        # Preview is a physical view, not an optimization.  The fallback is
        # bounded by the stated roof input so a tiny roof never yields an
        # apparently executable over-sized array.
        hybrid.pv_capacity_kwp = min(2.0, roof_limit)
    pv_generation = asdict(generate_pv(pv_weather, hybrid.pv_capacity_kwp, pv_scenario))
    wind_generation = generate_wind(pv_weather, WindTurbineProfile.from_file(), hybrid.wind)
    zero_pv = dict(pv_generation); zero_pv["pv_ac_power_w"] = [0.0] * len(indices); zero_pv["pv_dc_power_w"] = [0.0] * len(indices)
    zero_wind = dict(wind_generation); zero_wind["wind_power_w"] = [0.0] * len(indices); zero_wind["wind_energy_kwh"] = [0.0] * len(indices)
    combinations = [("S0_grid", zero_pv, zero_wind, 0.0, 0),
                    ("S1_pv", pv_generation, zero_wind, hybrid.pv_capacity_kwp, 0),
                    ("S2_wind", zero_pv, wind_generation, 0.0, hybrid.wind.turbine_count),
                    ("S3_pv_wind", pv_generation, wind_generation, hybrid.pv_capacity_kwp, hybrid.wind.turbine_count)]
    candidates = []
    for scenario_id, pv_series, wind_series, capacity, turbine_count in combinations:
        matched = match_hybrid(load["load_series"], pv_series, wind_series,
                               allow_export=hybrid.allow_export,
                               export_limit_kw=hybrid.export_limit_kw)
        candidates.append({"scenario_id": scenario_id, "pv_capacity_kwp": capacity,
                           "wind_turbine_count": turbine_count,
                           "summary": matched["summary"], "intervals": matched["intervals"],
                           "economics": {"status": "not_calculated", "reason": "典型时段预览只做物理匹配，不做经济结论或全年外推"}})
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return {"status": "success", "scope": "preview_period_physics_only",
            "scope_note": "仅对固定典型时段执行负荷与风光逐区间物理匹配；不计算经济、碳排、回本或全年外推。",
            "preview": selection,
            "site_id": site_id, "year": year,
            "project_load_contract": project_load_context(load),
            "service_quality": {"scope": "selected_preview_period", "capacity_shortfall_hours": load["summary"].get("capacity_shortfall_hours"), "unmet_temp_degree_hours": load["summary"].get("unmet_temp_degree_hours"), "unmet_rh_percent_hours": load["summary"].get("unmet_rh_percent_hours")},
            "load_context": {"scope": "selected physical intervals from annual project load", "annual_extrapolation": False, "source": "same thermal trace as hybrid/run"},
            "weather_provenance": {"source_file": pv_weather_full.get("source_file"), "hash": pv_weather_full.get("hash"), "selected_interval_start": selection["start"], "selected_interval_end_exclusive": selection["end_exclusive"]},
            "pv_input": {"capacity_kwp": hybrid.pv_capacity_kwp, "capacity_defaulted": capacity_defaulted, "roof_area_m2": pv_scenario.roof_area_m2, "tilt_deg": pv_scenario.tilt_deg, "azimuth_open_meteo_deg": pv_scenario.azimuth_open_meteo_deg},
            "wind_input": {"turbine_count": hybrid.wind.turbine_count, "hub_height_m": hybrid.wind.hub_height_m},
            "candidates": candidates,
            "economics": {"status": "not_calculated", "reason": "preview endpoint does not calculate lifecycle, tariff, carbon price or payback"},
            "calculation_timing": {"elapsed_ms": elapsed_ms, "timing_scope": "selected typical week/month physical generation and matching only"},
            "notes": ["预览固定选择，不代表全年外推；数值来自同一热湿、pvlib、风电和match_hybrid物理链。", "改变电价或报价不会改变本接口物理结果；如需经济比较请调用hybrid/run。"]}


class Handler(BaseHTTPRequestHandler):
    server_version = "NengzhiheOperation/0.2"

    def log_message(self, *_: object) -> None:
        return

    def _send(self, status: int, body: object, content_type: str = "application/json; charset=utf-8") -> None:
        if isinstance(body, bytes): data = body
        elif isinstance(body, str): data = body.encode("utf-8")
        else: data = json.dumps(body, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2_000_000: raise ValueError("请求过大")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("请求体必须是有效JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("请求体必须是JSON对象")
        return value

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path); path = parsed.path
        if path in ("/", "/index.html"): return self._send(HTTPStatus.OK, (UI / "index.html").read_bytes(), MIME[".html"])
        if path == "/api/operation/agent/status": return self._send(HTTPStatus.OK, local_model_status())
        if path == "/api/operation/health": return self._send(HTTPStatus.OK, {"ok": True, "product": "能智核——公共建筑空调运行方案试算与优化智能体", "mode": "local_replay"})
        if path == "/api/operation/tariffs": return self._send(HTTPStatus.OK, _tariff_options())
        if path == "/api/operation/carbon/factors": return self._send(HTTPStatus.OK, factor_catalog())
        if path == "/api/operation/options":
            sites = available_sites()
            years = sorted({int(year) for site in sites for year in site.get("cached_years", []) if str(year).isdigit()})
            return self._send(HTTPStatus.OK, {"status": "success", "cities": sites, "years": years,
                "equipment_models": catalogue(), "tariffs": _tariff_options(), "carbon_factors": factor_catalog(),
                "carbon_price_scenarios": carbon_price_scenarios(),
                "units": {"area_m2": "m²", "height_m": "m", "power_kw": "kW", "energy_kwh": "kWh", "price_cny_per_kwh": "CNY/kWh"}})
        if path in ("/api/operation/cities", "/api/operation/years"):
            sites = available_sites()
            years = sorted({int(year) for site in sites for year in site.get("cached_years", []) if str(year).isdigit()})
            return self._send(HTTPStatus.OK, {"status": "success", "cities": sites, "years": years})
        if path == "/api/operation/weather/sites": return self._send(HTTPStatus.OK, {"items": available_sites()})
        if path == "/api/operation/pv/provenance": return self._send(HTTPStatus.OK, {"engine": "pvlib", "scope": "phase2A photovoltaic generation, hourly load matching and lifecycle comparison", "radiation": "Open-Meteo GHI/DNI/DHI preceding-hour means", "status": "local_replay"})
        if path == "/api/operation/wind/profiles":
            profile = WindTurbineProfile.from_file()
            return self._send(HTTPStatus.OK, {"profiles": [{"profile_id": profile.profile_id, "manufacturer": profile.manufacturer, "model": profile.model, "source_url": profile.source_url, "tested_hub_height_m": profile.tested_hub_height_m, "rated_power_kw": profile.rated_power_kw, "peak_power_kw": profile.peak_power_kw, "curve_range_m_s": profile.curve_range_m_s, "windpowerlib_version": __import__('windpowerlib').__version__}]})
        if path == "/api/operation/weather/import": return self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "请使用POST导入CSV"})
        if path == "/api/operation/equipment": return self._send(HTTPStatus.OK, {"items": catalogue()})
        if path == "/api/operation/provenance":
            adapter = LocalBestestAirFMUAdapter(); return self._send(HTTPStatus.OK, {"adapter": adapter.provenance(), "measurements": adapter.get_measurements(), "inputs": adapter.get_inputs()})
        if path == "/api/operation/external": return self._send(HTTPStatus.OK, summarize_external_physical())
        if path == "/api/operation/history":
            with LOCK: items = [{k: v for k, v in job.items() if k in {"job_id", "status", "created_at", "finished_at", "task", "current_result_id", "user_confirmed", "completed_candidates", "total_candidates"}} for job in JOBS.values()]
            return self._send(HTTPStatus.OK, {"items": sorted(items, key=lambda x: x.get("created_at", 0), reverse=True)})
        if path.startswith("/api/operation/task/"):
            with LOCK: job = JOBS.get(path.rsplit("/", 1)[-1])
            return self._send(HTTPStatus.OK if job else HTTPStatus.NOT_FOUND, job or {"error": "任务不存在"})
        if path.startswith("/api/operation/hybrid/jobs/") or path.startswith("/api/operation/hybrid/job/") or path.startswith("/api/operation/hybrid/task/"):
            job_id = path.rsplit("/", 1)[-1]
            with LOCK:
                job = JOBS.get(job_id)
                snapshot = dict(job) if job else None
            if snapshot is None:
                return self._send(HTTPStatus.NOT_FOUND, {"status": "failed", "error": "任务不存在", "message": "任务不存在", "field": "job_id"})
            events = snapshot.get("events") or []
            progress = snapshot.get("progress", 0.0)
            output = snapshot.get("output") or {}
            failed = snapshot.get("status") == "failed"
            return self._send(HTTPStatus.OK, {"job_id": job_id, "status": snapshot.get("status"), "progress": progress,
                "events": events[-20:], "elapsed_ms": ((snapshot.get("finished_at") or time.time()) - snapshot.get("created_at", time.time())) * 1000.0,
                "result": output if snapshot.get("status") in {"done", "failed"} else None,
                "error": output.get("error") if failed else None,
                "message": output.get("message") if failed else None,
                "field": output.get("field") if failed else None})
        if path.startswith("/api/operation/export/"):
            with LOCK: job = JOBS.get(path.rsplit("/", 1)[-1])
            try: report, selected = _selected(job or {})
            except PermissionError as exc: return self._send(HTTPStatus.CONFLICT, {"error": str(exc)})
            except Exception as exc: return self._send(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            fmt = parse_qs(parsed.query).get("format", ["json"])[0]
            if fmt == "html": return self._send(HTTPStatus.OK, _html_card(report, selected), "text/html; charset=utf-8")
            if fmt == "csv":
                result = selected.get("result", {}); out = io.StringIO(); writer = csv.writer(out); writer.writerow(["time_seconds", "temperature_c", "electric_power_w", "heating_power_w"])
                for row in zip(result.get("time_seconds", []), result.get("temperature_c", []), result.get("electric_power_w", []), result.get("heating_power_w", [])): writer.writerow(row)
                return self._send(HTTPStatus.OK, out.getvalue(), "text/csv; charset=utf-8")
            return self._send(HTTPStatus.OK, {"report": report, "selected": selected})
        if path.startswith("/samples/"):
            name = path.removeprefix("/samples/")
            if name not in REPLAY_SAMPLES or not (REPLAY_DIR / name).is_file(): return self._send(HTTPStatus.NOT_FOUND, {"error": "样例不存在"})
            return self._send(HTTPStatus.OK, (REPLAY_DIR / name).read_bytes(), "application/json; charset=utf-8")
        if path.startswith("/assets/"):
            candidate = (UI / "assets" / path.removeprefix("/assets/")).resolve()
            if UI.resolve() not in candidate.parents or not candidate.is_file(): return self._send(HTTPStatus.NOT_FOUND, {"error": "资源不存在"})
            return self._send(HTTPStatus.OK, candidate.read_bytes(), MIME.get(candidate.suffix.lower(), "application/octet-stream"))
        return self._send(HTTPStatus.NOT_FOUND, {"error": "路径不存在"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/operation/agent/parse":
            try:
                payload = self._read_json()
                request_text = payload.get("request")
                current_task = payload.get("current_task")
                if not isinstance(request_text, str) or not request_text.strip():
                    raise ValueError("request必须是非空文本")
                if not isinstance(current_task, dict):
                    raise ValueError("current_task必须是对象")
                return self._send(HTTPStatus.OK, parse_agent_request(request_text, current_task))
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, _api_error(exc, "request"))
        if path in ("/api/operation/thermal/size", "/api/operation/thermal/compare"):
            try:
                result = _thermal_capacity_sweep(self._read_json())
                return self._send(HTTPStatus.OK, result)
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, _api_error(exc, "max_units" if "max_units" in str(exc) else None))
        if path == "/api/operation/thermal/run":
            try:
                payload = self._read_json()
                if bool(payload.get("compare_units", False)) or bool(payload.get("unit_sweep", False)):
                    return self._send(HTTPStatus.OK, _thermal_capacity_sweep(payload))
                site_id = str(payload.get("site_id", "guangzhou")); year = int(payload.get("year", 2024))
                room, cost_input, input_contract = _thermal_inputs(payload)
                weather = payload.get("weather") or load_weather(site_id, year)
                result = simulate_room(weather, room)
                project_result = aggregate_project_load(result)
                quote = cost_input["quote"]
                cost = life_cycle_cost(
                    result,
                    study_years=cost_input["study_years"],
                    price_cny_per_kwh=cost_input["price_cny_per_kwh"],
                    room_count=cost_input["room_count"],
                    units_per_room=cost_input["units_per_room"],
                    discount_rate=cost_input["discount_rate"],
                    expected_life_years=cost_input["expected_life_years"],
                    warranty_years=cost_input["warranty_years"],
                    quote_scope=cost_input["quote_scope"],
                    tariff_profile=cost_input["tariff_profile"],
                    calendar_start=cost_input["calendar_start"],
                    equipment_price_cny=quote.get("equipment_price_cny"),
                    installation_cny=quote.get("installation_cny"),
                    maintenance_cny_per_year=quote.get("maintenance_cny_per_year"),
                )
                input_contract["cost"]["tariff"] = cost.get("lifecycle", {}).get("tariff_id")
                input_contract["project_load"] = project_load_context(project_result)
                return self._send(HTTPStatus.OK, {"status": "success", "weather": weather["context"], "weather_hash": weather["hash"], "input_contract": input_contract, "result": result, "project_load": {"context": project_load_context(project_result), "summary": project_result.get("summary"), "load_series": project_result.get("load_series")}, "cost": cost})
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, _api_error(exc))
        if path == "/api/operation/weather/import":
            try:
                payload = self._read_json(); imported = parse_user_csv(str(payload.get("csv", "")), str(payload.get("site_id", "user_csv")), str(payload.get("timezone", "Asia/Shanghai")))
                return self._send(HTTPStatus.OK, {"status": "success", "weather": imported})
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, _api_error(exc, "csv"))
        if path == "/api/operation/pv/run":
            try:
                payload = self._read_json()
                site_id = str(payload.get("site_id", "guangzhou")); year = int(payload.get("year", 2024))
                if bool(payload.get("use_agent", False)):
                    # Agent mode starts from the task only.  It must first
                    # interpret and validate the requested change; no final
                    # report is computed before the model invokes tools.
                    normalized_room, _, _ = _thermal_inputs(payload)
                    agent_pv = dict(payload.get("pv") or {})
                    if "tariff_escalation_rate" not in agent_pv and isinstance(payload.get("hybrid"), dict):
                        if "tariff_escalation_rate" in payload["hybrid"]:
                            agent_pv["tariff_escalation_rate"] = payload["hybrid"]["tariff_escalation_rate"]
                    task = {"site_id": site_id, "year": year, "room": asdict(normalized_room), "pv": agent_pv, "carbon": payload.get("carbon"), "weather": payload.get("weather"), "pv_weather": payload.get("pv_weather")}
                    agent_output = PVPlanningAgent().run(str(payload.get("request", "按现有空调负荷比较光伏容量")), task)
                    if agent_output.get("status") != "success":
                        return self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"status": agent_output.get("status", "failed"), "agent": agent_output, "error": agent_output.get("error") or agent_output.get("question", "Agent未完成任务")})
                    report = agent_output.get("report") or {}
                    # Keep the execution trace in the report without placing
                    # the report object inside itself (which is not JSON
                    # serializable and previously caused a circular result).
                    report["agent"] = {k: v for k, v in agent_output.items() if k != "report"}
                else:
                    room, _, _ = _thermal_inputs(payload)
                    load_weather_data = payload.get("weather") or load_weather(site_id, year)
                    pv_weather_data = payload.get("pv_weather") or load_pv_weather(site_id, year)
                    load_result = aggregate_project_load(simulate_room(load_weather_data, room))
                    pv_input = dict(payload.get("pv") or {})
                    # §19 accepts the shared escalation control either in the
                    # PV object or in the hybrid object used by the combined
                    # endpoint.  Keep one authoritative scenario field.
                    if "tariff_escalation_rate" not in pv_input:
                        shared_hybrid = payload.get("hybrid") or {}
                        if "tariff_escalation_rate" in shared_hybrid:
                            pv_input["tariff_escalation_rate"] = shared_hybrid["tariff_escalation_rate"]
                    if "tariff_escalation_rate" not in pv_input and "tariff_escalation_rate" in payload:
                        pv_input["tariff_escalation_rate"] = payload["tariff_escalation_rate"]
                    # The PV endpoint accepts the same bounded sweep contract
                    # as hybrid.  ``auto_capacity`` is resolved to explicit
                    # candidates before the PV engine is called.
                    if pv_input.get("auto_capacity") or pv_input.get("requested_capacities_kwp") is not None:
                        pv_input["requested_capacities_kwp"] = _capacity_candidates(pv_input)
                    scenario = scenario_from_dict(pv_input, site_id=site_id, year=year)
                    report = run_pv_planning(load_result, pv_weather_data, scenario, carbon=payload.get("carbon"), storage=payload.get("storage"))
                    report["agent"] = {"requested": False, "status": "disabled", "mode": "deterministic_tools", "note": "本接口的数值全部由Python工具计算；可按需启用本地模型工具协同。"}
                return self._send(HTTPStatus.OK, {"status": "success", "report": report})
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, _api_error(exc))
        if path == "/api/operation/hybrid/preview":
            try:
                payload = self._read_json()
                result = _hybrid_preview(payload)
                return self._send(HTTPStatus.OK, result)
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, _api_error(exc))
        if path == "/api/operation/hybrid/run":
            try:
                payload = self._read_json(); site_id = str(payload.get("site_id", "guangzhou")); year = int(payload.get("year", 2024))
                if bool(payload.get("use_agent", False)):
                    normalized_room, _, _ = _thermal_inputs(payload)
                    agent_payload = dict(payload); agent_payload["room"] = asdict(normalized_room)
                    agent_output = HybridPlanningAgent().run(str(payload.get("request", "比较只购电、仅光伏、仅风电和风光组合")), agent_payload)
                    if agent_output.get("status") != "success":
                        return self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"status":agent_output.get("status"),"agent":agent_output,"error":agent_output.get("error") or agent_output.get("question")})
                    report = agent_output.get("report") or {}; report["agent"] = {k:v for k,v in agent_output.items() if k != "report"}
                    return self._send(HTTPStatus.OK, {"status":"success","report":report})
                started = time.perf_counter()
                report = _hybrid_capacity_run(payload)
                timing = report.setdefault("calculation_timing", {})
                timing["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
                timing["timing_scope"] = "本次HTTP请求内天气读取、空调负荷、容量比选、匹配和经济计算；不含浏览器网络等待"
                report["agent"] = {"requested": False, "status": "disabled", "mode": "phase2b_hybrid_tools", "request": payload.get("request", "")}
                return self._send(HTTPStatus.OK, {"status":"success","report":report})
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, _api_error(exc))
        if path in ("/api/operation/hybrid/jobs", "/api/operation/hybrid/submit"):
            try:
                payload = self._read_json()
                # Validate and normalize before accepting the job, so a typo
                # is returned synchronously instead of becoming a failed job.
                _thermal_inputs(payload)
                _capacity_candidates(dict(payload.get("pv") or {}))
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, _api_error(exc))
            job_id = uuid.uuid4().hex[:12]
            with LOCK:
                JOBS[job_id] = {"job_id": job_id, "kind": "hybrid", "status": "queued", "created_at": time.time(), "progress": 0.0, "events": []}
            def worker() -> None:
                with LOCK:
                    JOBS[job_id]["status"] = "running"; JOBS[job_id]["started_at"] = time.time()
                _event(job_id, {"type": "started", "message": "已开始实时风光容量比选"})
                try:
                    started = time.perf_counter()
                    def progress(done, total, capacity):
                        with LOCK:
                            JOBS[job_id]["progress"] = float(done) / max(float(total), 1.0)
                        _event(job_id, {"type": "capacity_completed", "completed": done, "total": total, "capacity_kwp": capacity, "message": f"已完成{capacity:g}kWp容量计算"})
                    output = _hybrid_capacity_run(payload, progress=progress)
                    output.setdefault("calculation_timing", {})["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
                    output["calculation_timing"]["timing_scope"] = "异步任务真实计算耗时，不含排队与客户端轮询"
                    with LOCK:
                        JOBS[job_id].update(status="done", progress=1.0, finished_at=time.time(), output={"status": "success", "report": output})
                    _event(job_id, {"type": "report_ready", "message": "实时计算结果已生成"})
                except Exception as exc:
                    with LOCK:
                        JOBS[job_id].update(status="failed", finished_at=time.time(), output=_api_error(exc))
                    _event(job_id, {"type": "failed", "message": str(exc)})
            threading.Thread(target=worker, daemon=True).start()
            return self._send(HTTPStatus.ACCEPTED, {"status": "queued", "job_id": job_id, "progress": 0.0})
        if path == "/api/operation/run":
            try:
                payload = self._read_json(); task = _task_from(payload, "validation"); errors = task.validate()
                if errors: return self._send(HTTPStatus.BAD_REQUEST, {"error": "；".join(errors)})
            except Exception as exc: return self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            job_id = uuid.uuid4().hex[:12]
            with LOCK: JOBS[job_id] = {"job_id": job_id, "status": "queued", "created_at": time.time(), "request": payload.get("request", ""), "events": [], "completed_candidates": 0, "total_candidates": 0, "cancel_requested": False, "revision": int(task.revision)}
            threading.Thread(target=_worker, args=(job_id, payload), daemon=True).start()
            return self._send(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued", "revision": task.revision})
        if path.startswith("/api/operation/cancel/"):
            job_id = path.rsplit("/", 1)[-1]
            with LOCK:
                if job_id not in JOBS: return self._send(HTTPStatus.NOT_FOUND, {"error": "任务不存在"})
                JOBS[job_id]["cancel_requested"] = True; JOBS[job_id].setdefault("events", []).append({"at": time.time(), "type": "cancel_requested", "message": "已请求取消，等待当前回放安全结束"})
            return self._send(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "cancel_requested"})
        if path.startswith("/api/operation/confirm/"):
            job_id = path.rsplit("/", 1)[-1]
            with LOCK:
                job = JOBS.get(job_id)
                if not job or job.get("status") != "done" or not job.get("current_result_id"): return self._send(HTTPStatus.CONFLICT, {"error": "没有可确认的当前结果"})
                job["user_confirmed"] = True; job["confirmed_at"] = time.time()
            return self._send(HTTPStatus.OK, {"job_id": job_id, "user_confirmed": True})
        return self._send(HTTPStatus.NOT_FOUND, {"error": "路径不存在"})


def serve(host: str = "127.0.0.1", port: int = 18765) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler); print(f"能智核 operation-planning workbench: http://{host}:{port}", flush=True); httpd.serve_forever()


if __name__ == "__main__": serve()
