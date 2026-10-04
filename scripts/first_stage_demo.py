"""Reproduce the three first-stage product demonstrations.

Usage: python scripts/first_stage_demo.py
The script only uses versioned weather caches and deterministic program
calculations; it does not call a model or invent a reference answer.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from operation_planning.equipment import catalogue
from operation_planning.lifecycle import life_cycle_cost
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.weather import load_weather

EQUIPMENT = catalogue()[0]["equipment_id"]
QUOTE = {"equipment_price_cny": 3000.0, "installation_cny": 800.0, "maintenance_cny_per_year": 260.0}

def run(site: str, year: int, room: RoomSpec, quote: dict = QUOTE) -> dict:
    weather = load_weather(site, year)
    result = simulate_room(weather, room)
    cost = life_cycle_cost(result, study_years=10, price_cny_per_kwh=0.66, **quote)
    return {"site": site, "year": year, "weather_hash": weather["hash"], "room": result["room"], "summary": result["summary"], "cost": cost["lifecycle"]}

def main() -> None:
    demos = {
        "01_region_comparison": {"guangzhou_2024": run("guangzhou", 2024, RoomSpec(equipment_id=EQUIPMENT)), "harbin_2024": run("harbin", 2024, RoomSpec(equipment_id=EQUIPMENT))},
        "02_humidity_target": {"rh60": run("guangzhou", 2024, RoomSpec(equipment_id=EQUIPMENT, rh_setpoint_percent=60, indoor_rh_percent=60)), "rh50": run("guangzhou", 2024, RoomSpec(equipment_id=EQUIPMENT, rh_setpoint_percent=50, indoor_rh_percent=50))},
        "03_quote_and_batch": {"one_room": run("guangzhou", 2024, RoomSpec(equipment_id=EQUIPMENT), QUOTE), "batch_quote": run("guangzhou", 2024, RoomSpec(equipment_id=EQUIPMENT, equipment_count=2), {"equipment_price_cny": 3200.0, "installation_cny": 900.0, "maintenance_cny_per_year": 280.0})},
    }
    out = ROOT / "operation_planning" / "results" / "regional_product_v2" / "three_demos.json"
    out.write_text(json.dumps({"scope": "真实缓存天气 + 程序热湿/设备/费用计算；不是楼宇实测", "demos": demos}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, group in demos.items():
        print(name)
        for label, value in group.items():
            print(" ", label, round(value["summary"]["electric_kwh"], 1), value["cost"].get("total_pv_cny"))

if __name__ == "__main__":
    main()