"""Serve the unchanged workbench while recording local browser acceptance.

No UI automation, response stubs or alternate numerical engine are used here.
Long vectors are represented by their byte hash/cardinality in the HTTP audit;
the API itself still returns the complete original response to the browser.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
from datetime import datetime, timezone

from operation_planning import app, agent_parse

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    events = output / "http_events.jsonl"
    if events.exists():
        raise SystemExit("Use a fresh output directory; existing evidence is never overwritten")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    lock = threading.Lock()
    seen_jobs = set()

    def pack(value):
        if isinstance(value, list) and len(value) > 40:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            return {"vector_count": len(value), "sha256": hashlib.sha256(encoded).hexdigest(),
                    "first": value[:2], "last": value[-2:], "omitted_from_audit_only": True}
        if isinstance(value, list):
            return [pack(item) for item in value]
        if isinstance(value, dict):
            return {key: pack(item) for key, item in value.items()}
        return value

    def record(kind, **data):
        row = {"kind": kind, "time_utc": datetime.now(timezone.utc).isoformat(), "source_commit": source, **data}
        with lock:
            with events.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    original_model_parse = agent_parse._model_parse
    def observed_model_parse(config, request_text, current_task):
        started = time.perf_counter()
        try:
            raw = original_model_parse(config, request_text, current_task)
            record("model_return", request=request_text, current_task=current_task,
                   model_id=config["model_id"], raw=raw,
                   elapsed_ms=(time.perf_counter() - started) * 1000)
            return raw
        except Exception as exc:
            record("model_error", request=request_text, model_id=config["model_id"],
                   error=str(exc), elapsed_ms=(time.perf_counter() - started) * 1000)
            raise
    agent_parse._model_parse = observed_model_parse

    original_read = app.Handler._read_json
    def observed_read(handler):
        payload = original_read(handler)
        handler._round21_payload = payload
        handler._round21_started = time.perf_counter()
        return payload
    app.Handler._read_json = observed_read

    original_send = app.Handler._send
    def observed_send(handler, status, body, content_type="application/json; charset=utf-8"):
        path = handler.path.split("?")[0]
        should_record = path in {"/api/operation/agent/parse", "/api/operation/agent/status",
                                "/api/operation/hybrid/preview", "/api/operation/hybrid/jobs",
                                "/api/operation/hybrid/run", "/api/operation/thermal/size"}
        if path.startswith("/api/operation/hybrid/jobs/") and isinstance(body, dict):
            job_key = body.get("job_id")
            if body.get("status") in {"done", "failed"} and job_key not in seen_jobs:
                seen_jobs.add(job_key)
                should_record = True
        if should_record:
            raw = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
            record("http_response", path=path, method=handler.command, http_status=int(status),
                   request=getattr(handler, "_round21_payload", None), response=pack(body),
                   complete_response_sha256=hashlib.sha256(raw).hexdigest(),
                   elapsed_ms=(time.perf_counter() - getattr(handler, "_round21_started", time.perf_counter())) * 1000)
        return original_send(handler, status, body, content_type)
    app.Handler._send = observed_send
    record("server_start", command=["python", "-m", "scripts.round21_http_evidence_server", "--port", str(args.port),
                                     "--output", str(args.output)], workspace_status=subprocess.check_output(
                                         ["git", "status", "--short"], cwd=ROOT, text=True).strip())
    app.serve("127.0.0.1", args.port)


if __name__ == "__main__":
    main()
