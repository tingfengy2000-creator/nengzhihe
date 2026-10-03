"""Loopback-only workbench server for the operation-planning product page."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
import uuid
from urllib.parse import urlparse

from .agent import OperationPlanningAgent
from .boptest_adapter import LocalBestestAirFMUAdapter
from .schemas import TaskSpec
from .search import PlanEvaluator


ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def _task_from(payload: dict, job_id: str) -> TaskSpec:
    raw = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    allowed = set(TaskSpec.__dataclass_fields__)
    values = {key: value for key, value in raw.items() if key in allowed}
    values.setdefault("task_id", job_id)
    values["user_request"] = str(payload.get("request", values.get("user_request", "")))
    return TaskSpec(**values)


def _worker(job_id: str, payload: dict) -> None:
    with LOCK:
        JOBS[job_id].update(status="running", started_at=time.time())
    try:
        task = _task_from(payload, job_id)
        step_seconds = int(payload.get("step_seconds", 900))
        evaluator = PlanEvaluator(LocalBestestAirFMUAdapter(step_seconds=step_seconds))
        if bool(payload.get("use_agent", True)):
            output = OperationPlanningAgent(evaluator=evaluator).run(task.user_request or "请根据结构化条件试算方案", task)
        else:
            report = evaluator.search(task)
            output = {"status": "success", "report": report.to_dict(), "trace": []}
        with LOCK:
            JOBS[job_id].update(status="done" if output.get("status") == "success" else "failed", finished_at=time.time(), output=output)
    except Exception as exc:
        with LOCK:
            JOBS[job_id].update(status="failed", finished_at=time.time(), output={"status": "failed", "error": f"{type(exc).__name__}: {exc}"})


class Handler(BaseHTTPRequestHandler):
    server_version = "NengzhiheOperation/0.1"

    def log_message(self, *_: object) -> None:
        return

    def _send(self, status: int, body: object, content_type: str = "application/json; charset=utf-8") -> None:
        if isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = json.dumps(body, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2_000_000:
            raise ValueError("请求过大")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(HTTPStatus.OK, (UI / "index.html").read_text(encoding="utf-8"), "text/html; charset=utf-8")
        if path == "/api/operation/health":
            return self._send(HTTPStatus.OK, {"ok": True, "product": "能智核——公共建筑空调运行方案试算与优化智能体", "mode": "local_replay"})
        if path == "/api/operation/provenance":
            adapter = LocalBestestAirFMUAdapter()
            return self._send(HTTPStatus.OK, {"adapter": adapter.provenance(), "measurements": adapter.get_measurements(), "inputs": adapter.get_inputs()})
        if path.startswith("/api/operation/task/"):
            job_id = path.rsplit("/", 1)[-1]
            with LOCK:
                job = JOBS.get(job_id)
            if not job:
                return self._send(HTTPStatus.NOT_FOUND, {"error": "任务不存在"})
            return self._send(HTTPStatus.OK, job)
        if path.startswith("/api/operation/export/"):
            job_id = path.rsplit("/", 1)[-1]
            with LOCK:
                job = JOBS.get(job_id)
            if not job or job.get("status") != "done":
                return self._send(HTTPStatus.NOT_FOUND, {"error": "任务未完成"})
            return self._send(HTTPStatus.OK, job["output"], "application/json; charset=utf-8")
        if path.startswith("/assets/"):
            candidate = (UI / path.removeprefix("/assets/")).resolve()
            if UI.resolve() not in candidate.parents or not candidate.is_file():
                return self._send(HTTPStatus.NOT_FOUND, {"error": "资源不存在"})
            return self._send(HTTPStatus.OK, candidate.read_bytes(), "text/plain; charset=utf-8")
        return self._send(HTTPStatus.NOT_FOUND, {"error": "路径不存在"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/operation/run":
            try:
                payload = self._read_json()
            except Exception as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            job_id = uuid.uuid4().hex[:12]
            with LOCK:
                JOBS[job_id] = {"job_id": job_id, "status": "queued", "created_at": time.time(), "request": payload.get("request", "")}
            threading.Thread(target=_worker, args=(job_id, payload), daemon=True).start()
            return self._send(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})
        return self._send(HTTPStatus.NOT_FOUND, {"error": "路径不存在"})


def serve(host: str = "127.0.0.1", port: int = 18765) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"能智核 operation-planning workbench: http://{host}:{port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    serve()
