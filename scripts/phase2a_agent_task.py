"""Run the real local-model budget-change task and save its trace."""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from operation_planning.pv_agent import PVPlanningAgent

OUT = ROOT / "operation_planning" / "results" / "pv_phase2a_correctness" / "agent_budget_6000.json"
QUOTE = {"module_cny_per_kwp": 1800, "inverter_cny_per_kwp": 600, "structure_cny_per_kwp": 500, "installation_cny_per_kwp": 800, "grid_connection_cny": 0, "maintenance_cny_per_kwp_year": 30}
TASK = {"site_id": "guangzhou", "year": 2024, "room": {"area_m2": 35, "people_count": 4, "start_hour": 8, "end_hour": 18, "cooling_setpoint_c": 26, "rh_setpoint_percent": 60}, "pv": {"roof_area_m2": 50, "usable_fraction": 0.8, "budget_cny": 9000, "requested_capacities_kwp": [0, 1, 2, 3], "quote": QUOTE}}

result = PVPlanningAgent().run("预算改为6000元，其他条件不变", TASK)
payload = {"task_before": {"budget_cny": 9000, "requested_capacities_kwp": [0, 1, 2, 3]}, "request": "预算改为6000元，其他条件不变", "task_after": {"budget_cny": (result.get("report") or {}).get("scenario", {}).get("budget_cny"), "candidate_constraints": (result.get("report") or {}).get("candidate_constraints")}, "status": result.get("status"), "error": result.get("error"), "question": result.get("question"), "trace": result.get("trace", []), "claim_boundary": "只有真实本地模型完整执行并返回success才算Agent任务成功；数值来自PV Python工具。"}
OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"path": str(OUT), "status": payload["status"], "budget_after": payload["task_after"]["budget_cny"]}, ensure_ascii=False))
