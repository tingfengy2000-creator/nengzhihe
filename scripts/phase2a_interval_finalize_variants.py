"""Run three bounded real-agent interaction checks and save their traces."""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from operation_planning.pv_agent import PVPlanningAgent

quote = {"module_cny_per_kwp": 1800, "inverter_cny_per_kwp": 600, "structure_cny_per_kwp": 500, "installation_cny_per_kwp": 800, "grid_connection_cny": 0, "maintenance_cny_per_kwp_year": 30}
base = {"site_id": "guangzhou", "year": 2024, "room": {"area_m2": 35, "people_count": 4, "start_hour": 8, "end_hour": 18, "cooling_setpoint_c": 26, "rh_setpoint_percent": 60}, "pv": {"roof_area_m2": 50, "usable_fraction": 0.8, "budget_cny": 9000, "requested_capacities_kwp": [0, 1], "quote": quote}}
cases = [("schedule", "使用时段改到晚上，其他条件不变", base), ("quote", "把组件报价改为2000元每kWp，其他条件不变", base), ("conflict", "开启外送但暂时不提供外送价，其他条件不变", {**base, "pv": {**base["pv"], "allow_export": False, "export_price_cny_per_kwh": None}})]
agent = PVPlanningAgent(); output = {}
for name, request, task in cases:
    result = agent.run(request, task)
    output[name] = {"request": request, "status": result.get("status"), "question": result.get("question"), "error": result.get("error"), "modifications": next((x.get("result", {}).get("modifications") for x in result.get("trace", []) if x.get("action") == "interpret_request"), None), "actions": [x.get("action") for x in result.get("trace", [])], "report_budget": (result.get("report") or {}).get("scenario", {}).get("budget_cny"), "report_room_modifications": (result.get("report") or {}).get("agent_task", {}).get("modifications"), "trace": result.get("trace", [])}
path = ROOT / "operation_planning" / "results" / "pv_phase2a_interval_finalize" / "agent_task_variants_interval_normalized.json"; path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"path": str(path), "statuses": {k: v["status"] for k, v in output.items()}}, ensure_ascii=False))

