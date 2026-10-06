"""Run the five bounded local-model phase-two B task probes and keep failures."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from operation_planning.hybrid_agent import HybridPlanningAgent

OUT=Path(__file__).resolve().parents[1]/"operation_planning"/"results"/"phase2b_cost_fix"
BASE={"site_id":"guangzhou","year":2024,"room":{"area_m2":35,"people_count":4,"start_hour":8,"end_hour":18,"cooling_setpoint_c":26,"rh_setpoint_percent":60},"pv":{"roof_area_m2":50,"usable_fraction":.8,"tilt_deg":23,"azimuth_open_meteo_deg":0,"import_price_cny_per_kwh":.66,"quote":{"module_cny_per_kwp":1800,"inverter_cny_per_kwp":600,"structure_cny_per_kwp":500,"installation_cny_per_kwp":800,"grid_connection_cny":0,"maintenance_cny_per_kwp_year":30}},"hybrid":{"pv_capacity_kwp":2,"wind":{"turbine_count":1,"hub_height_m":9,"source_height_m":10,"hellman_exponent":.14},"budget_cny":90000,"shared_connection_cny":0,"allow_export":False,"import_price_cny_per_kwh":.66,"study_years":10,"wind_quote":{"turbine_cny":45000,"tower_cny":15000,"foundation_cny":10000,"installation_cny":12000,"grid_connection_cny":0,"maintenance_cny_per_year":1200}}}
TASKS=["保持现有空调要求，比较仅光伏、仅风电和风光组合，不允许外送。","预算减少三分之一，其他条件不变。","塔架高度最多20米。","把使用时段改成18点到22点。","允许外送，但还没有卖电价格。"]
def main():
    agent=HybridPlanningAgent(); rows=[]
    for i,request in enumerate(TASKS,1):
        out=agent.run(request,BASE); rows.append({"case_id":f"agent_{i}","request":request,"status":out.get("status"),"message":out.get("message"),"question":out.get("question"),"error":out.get("error"),"trace":out.get("trace",[]),"report_summary":({"recommendation":out.get("report",{}).get("recommendation"),"agent_task":out.get("report",{}).get("agent_task")} if out.get("report") else None)})
        print(i,request,out.get("status"),out.get("error") or out.get("question") or "ok")
    OUT.mkdir(parents=True,exist_ok=True); (OUT/"agent_task_records.json").write_text(json.dumps({"model":"local_configured_model","cases":rows},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
if __name__=="__main__": main()
