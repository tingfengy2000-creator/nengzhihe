"""One real local inference call, using only an invented interface payload."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import model_client

payload = {
    "purpose": "synthetic interface smoke test; not an energy dataset or performance evaluation",
    "remaining_budget": {"data_query": 2, "site_acquisition": 0},
    "revealed_evidence": ["No equipment feedback has been queried yet."],
    "actions": {
        "query_available_feedback": {"description": "Query an already logged feedback channel.", "data_query_cost": 1, "site_acquisition_cost": 0},
        "stop_insufficient": {"description": "Stop with insufficient evidence.", "data_query_cost": 0, "site_acquisition_cost": 0},
    },
}

if __name__ == "__main__":
    result = model_client.choose_action(payload, list(payload["actions"]))
    record = {
        "purpose": "interface_smoke_only_not_energy_validation",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "client_sha256": hashlib.sha256(Path(model_client.__file__).read_bytes()).hexdigest(),
        "system_prompt_sha256": hashlib.sha256(model_client.SYSTEM_PROMPT.encode()).hexdigest(),
        "request_payload": payload,
        "allowed_actions": list(payload["actions"]),
        "result": result,
    }
    (ROOT / "local_model_smoke.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("action", "reason", "latency_ms", "response_valid")}, ensure_ascii=False, indent=2))
    if not result["response_valid"]:
        raise SystemExit(1)
