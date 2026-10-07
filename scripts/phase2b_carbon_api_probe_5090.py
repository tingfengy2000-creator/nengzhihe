"""Short API contract probe for carbon factor listing and optional carbon input."""
from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from operation_planning.app import Handler
from operation_planning.carbon import normalize_request


def _request(server: ThreadingHTTPServer, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{path}", data=data, headers={"Content-Type": "application/json"}, method="GET" if data is None else "POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        factors = _request(server, "/api/operation/carbon/factors")
        invalid = None
        try:
            normalize_request("guangzhou", {"factor_id": "does_not_exist"})
        except Exception as exc:
            invalid = f"{type(exc).__name__}: {exc}"
    finally:
        server.shutdown()
        thread.join()
    items = factors.get("factors", [])
    result = {"status": "passed" if items and invalid else "failed", "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "factor_count": len(items), "guangdong_2023": next((x for x in items if x.get("factor_id") == "grid_avg_guangdong_2023"), None), "invalid_factor_rejected": invalid}
    out = ROOT / "operation_planning" / "results" / "phase2b_carbon_5090"
    out.mkdir(parents=True, exist_ok=True)
    (out / "api_probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
