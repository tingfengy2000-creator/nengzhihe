"""Loopback-only workbench server for the operation-planning product."""

from __future__ import annotations

import csv
from html import escape
import io
import json
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
from .tariffs import registry
from .equipment import catalogue
from .weather import available_sites, load_weather, parse_user_csv
from .weather import load_pv_weather
from .thermal_model import RoomSpec, simulate_room
from .lifecycle import life_cycle_cost
from .pv import PVScenario, PVQuote, run_pv_planning, scenario_from_dict
from .pv_agent import PVPlanningAgent
from .wind import WindTurbineProfile, WindScenario, WindQuote
from .hybrid import HybridScenario, run_hybrid_planning
from .hybrid_agent import HybridPlanningAgent


ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"
JOBS: dict[str, dict] = {}
LOCK = threading.RLock()
MIME = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".json": "application/json; charset=utf-8", ".csv": "text/csv; charset=utf-8",
}


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
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path); path = parsed.path
        if path in ("/", "/index.html"): return self._send(HTTPStatus.OK, (UI / "index.html").read_bytes(), MIME[".html"])
        if path == "/api/operation/health": return self._send(HTTPStatus.OK, {"ok": True, "product": "能智核——公共建筑空调运行方案试算与优化智能体", "mode": "local_replay"})
        if path == "/api/operation/tariffs": return self._send(HTTPStatus.OK, registry())
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
        if path.startswith("/assets/"):
            candidate = (UI / "assets" / path.removeprefix("/assets/")).resolve()
            if UI.resolve() not in candidate.parents or not candidate.is_file(): return self._send(HTTPStatus.NOT_FOUND, {"error": "资源不存在"})
            return self._send(HTTPStatus.OK, candidate.read_bytes(), MIME.get(candidate.suffix.lower(), "application/octet-stream"))
        return self._send(HTTPStatus.NOT_FOUND, {"error": "路径不存在"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/operation/thermal/run":
            try:
                payload = self._read_json(); site_id = str(payload.get("site_id", "guangzhou")); year = int(payload.get("year", 2024)); room_data = payload.get("room") or {}; room = RoomSpec(**{k: v for k, v in room_data.items() if k in RoomSpec.__dataclass_fields__}); weather = payload.get("weather") or load_weather(site_id, year); result = simulate_room(weather, room); price = payload.get("annual_price_cny_per_kwh"); quote = payload.get("equipment_quote") or {}; cost = life_cycle_cost(result, int(payload.get("study_years", 10)), float(price) if price is not None else None, int(payload.get("quantity", 1)), float(payload.get("discount_rate", 0.0)), equipment_price_cny=quote.get("equipment_price_cny"), installation_cny=quote.get("installation_cny"), maintenance_cny_per_year=quote.get("maintenance_cny_per_year")) if price is not None else {"monthly": {}, "yearly": [], "lifecycle": {"status": "缺少可覆盖研究期的价格情景"}}
                return self._send(HTTPStatus.OK, {"status": "success", "weather": weather["context"], "weather_hash": weather["hash"], "result": result, "cost": cost})
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        if path == "/api/operation/weather/import":
            try:
                payload = self._read_json(); imported = parse_user_csv(str(payload.get("csv", "")), str(payload.get("site_id", "user_csv")), str(payload.get("timezone", "Asia/Shanghai")))
                return self._send(HTTPStatus.OK, {"status": "success", "weather": imported})
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        if path == "/api/operation/pv/run":
            try:
                payload = self._read_json()
                site_id = str(payload.get("site_id", "guangzhou")); year = int(payload.get("year", 2024))
                if bool(payload.get("use_agent", False)):
                    # Agent mode starts from the task only.  It must first
                    # interpret and validate the requested change; no final
                    # report is computed before the model invokes tools.
                    task = {"site_id": site_id, "year": year, "room": payload.get("room") or {}, "pv": payload.get("pv") or {}, "weather": payload.get("weather"), "pv_weather": payload.get("pv_weather")}
                    agent_output = PVPlanningAgent().run(str(payload.get("request", "按现有空调负荷比较光伏容量")), task)
                    if agent_output.get("status") != "success":
                        return self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"status": agent_output.get("status", "failed"), "agent": agent_output, "error": agent_output.get("error") or agent_output.get("question", "Agent未完成任务")})
                    report = agent_output.get("report") or {}
                    # Keep the execution trace in the report without placing
                    # the report object inside itself (which is not JSON
                    # serializable and previously caused a circular result).
                    report["agent"] = {k: v for k, v in agent_output.items() if k != "report"}
                else:
                    room_data = payload.get("room") or {}
                    room = RoomSpec(**{k: v for k, v in room_data.items() if k in RoomSpec.__dataclass_fields__})
                    load_weather_data = payload.get("weather") or load_weather(site_id, year)
                    pv_weather_data = payload.get("pv_weather") or load_pv_weather(site_id, year)
                    load_result = simulate_room(load_weather_data, room)
                    scenario = scenario_from_dict(payload.get("pv") or {}, site_id=site_id, year=year)
                    report = run_pv_planning(load_result, pv_weather_data, scenario)
                    report["agent"] = {"requested": False, "status": "disabled", "mode": "deterministic_tools", "note": "本接口的数值全部由Python工具计算；可按需启用本地模型工具协同。"}
                return self._send(HTTPStatus.OK, {"status": "success", "report": report})
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        if path == "/api/operation/hybrid/run":
            try:
                payload = self._read_json(); site_id = str(payload.get("site_id", "guangzhou")); year = int(payload.get("year", 2024))
                if bool(payload.get("use_agent", False)):
                    agent_output = HybridPlanningAgent().run(str(payload.get("request", "比较只购电、仅光伏、仅风电和风光组合")), payload)
                    if agent_output.get("status") != "success":
                        return self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"status":agent_output.get("status"),"agent":agent_output,"error":agent_output.get("error") or agent_output.get("question")})
                    report = agent_output.get("report") or {}; report["agent"] = {k:v for k,v in agent_output.items() if k != "report"}
                    return self._send(HTTPStatus.OK, {"status":"success","report":report})
                room_data = payload.get("room") or {}; room = RoomSpec(**{k: v for k, v in room_data.items() if k in RoomSpec.__dataclass_fields__})
                load_weather_data = payload.get("weather") or load_weather(site_id, year); pv_weather_data = payload.get("pv_weather") or load_pv_weather(site_id, year); load_result = simulate_room(load_weather_data, room)
                pv_raw = payload.get("pv") or {}; pv = scenario_from_dict(pv_raw, site_id=site_id, year=year)
                hraw = payload.get("hybrid") or {}; wind_raw = hraw.get("wind") or {}
                wind = WindScenario(**{k:v for k,v in wind_raw.items() if k in WindScenario.__dataclass_fields__})
                pv_quote = PVQuote(**{k:v for k,v in (hraw.get("pv_quote") or pv_raw.get("quote") or {}).items() if k in PVQuote.__dataclass_fields__})
                wind_quote = WindQuote(**{k:v for k,v in (hraw.get("wind_quote") or {}).items() if k in WindQuote.__dataclass_fields__})
                hvals = {k:v for k,v in hraw.items() if k in HybridScenario.__dataclass_fields__ and k not in {"wind","pv_quote","wind_quote"}}; hvals.update({"site_id":site_id,"year":year,"wind":wind,"pv_quote":pv_quote,"wind_quote":wind_quote})
                hybrid = HybridScenario(**hvals); report = run_hybrid_planning(load_result, pv_weather_data, pv, hybrid, WindTurbineProfile.from_file())
                report["agent"] = {"requested": False, "status": "disabled", "mode": "phase2b_hybrid_tools", "request": payload.get("request", "")}
                return self._send(HTTPStatus.OK, {"status":"success","report":report})
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {"status":"failed","error":f"{type(exc).__name__}: {exc}"})
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
