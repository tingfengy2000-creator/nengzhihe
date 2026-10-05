"""Generate corrected phase-two evidence without overwriting round-two results.

Run from repository root: ``python scripts/phase2a_correctness_demo.py``.
The compact JSON keeps all candidates and points to auditable CSV evidence for
0/1/2/3 kWp rather than retaining only the selected curve.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from operation_planning.pv import PVQuote, PVScenario, generate_pv, run_pv_planning
from operation_planning.thermal_model import RoomSpec, simulate_room
from operation_planning.weather import load_pv_weather, load_weather

OUT = ROOT / "operation_planning" / "results" / "pv_phase2a_correctness"
EVIDENCE = OUT / "candidate_evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)

QUOTE = PVQuote(module_cny_per_kwp=1800, inverter_cny_per_kwp=600, structure_cny_per_kwp=500, installation_cny_per_kwp=800, grid_connection_cny=0, maintenance_cny_per_kwp_year=30, inverter_replacement_year=12, inverter_replacement_fraction=0.8, residual_fraction=0.05, source="用户确认的演示情景报价；不是采购报价")
ROOM = RoomSpec(area_m2=35, people_count=4, start_hour=8, end_hour=18, cooling_setpoint_c=26, rh_setpoint_percent=60, equipment_id="midea_msagbu12_mox201")


def run(site: str, year: int, room: RoomSpec, scenario: PVScenario) -> dict:
    weather = load_weather(site, year)
    pv_weather = load_pv_weather(site, year)
    load = simulate_room(weather, room)
    return run_pv_planning(load, pv_weather, scenario, include_selected_series=True)


def compact(report: dict, prefix: str) -> dict:
    out = dict(report)
    out["candidates"] = []
    for candidate in report["candidates"]:
        row = {k: v for k, v in candidate.items() if k != "hourly"}
        hourly = candidate.get("hourly") or {}
        path = EVIDENCE / f"{prefix}_{candidate['capacity_kwp']:g}kwp.csv"
        fields = ["timestamp", "interval_seconds", "load_kwh", "pv_generation_kwh", "self_use_kwh", "grid_import_kwh", "grid_export_kwh", "curtailment_kwh"]
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for i, ts in enumerate(hourly.get("timestamps", [])):
                writer.writerow({field: (ts if field == "timestamp" else hourly[field][i]) for field in fields})
        row["hourly_evidence_file"] = str(path.relative_to(OUT)).replace("\\", "/")
        out["candidates"].append(row)
    return out


def main() -> None:
    base_scenario = PVScenario(site_id="guangzhou", year=2024, roof_area_m2=50, usable_fraction=0.8, tilt_deg=23, azimuth_open_meteo_deg=0, requested_capacities_kwp=[0, 1, 2, 3], import_price_cny_per_kwh=0.66, study_years=10, quote=QUOTE)
    base = run("guangzhou", 2024, ROOM, base_scenario)
    shifted_room = RoomSpec(**{**ROOM.__dict__, "start_hour": 18, "end_hour": 24})
    shifted = run("guangzhou", 2024, shifted_room, base_scenario)
    constrained = PVScenario(**{**base_scenario.__dict__, "roof_area_m2": 20, "budget_cny": 9000, "quote": QUOTE})
    constrained_report = run("guangzhou", 2024, ROOM, constrained)
    long_scenario = PVScenario(**{**base_scenario.__dict__, "study_years": 15, "quote": QUOTE})
    long_report = run("guangzhou", 2024, ROOM, long_scenario)
    fixed_rows = []
    for site in ("guangzhou", "beijing", "harbin"):
        for year in (2023, 2024, 2025):
            scenario = PVScenario(**{**base_scenario.__dict__, "site_id": site, "year": year, "requested_capacities_kwp": [0, 2], "quote": QUOTE})
            report = run(site, year, ROOM, scenario)
            candidate = next(x for x in report["candidates"] if x["capacity_kwp"] == 2.0)
            fixed_rows.append({"site": site, "year": year, "weather_hash": report["weather_provenance"]["hash"], "load_kwh": report["load_context"]["electric_load_kwh"], "pv_2kwp_kwh": candidate["generation_kwh"], "self_use_kwh": candidate["self_use_kwh"], "grid_import_kwh": candidate["grid_import_kwh"], "curtailment_kwh": candidate["curtailment_kwh"], "load_coverage_rate": candidate["load_coverage_rate"], "economics_status": candidate["economics"]["status"], "npv_cny": candidate["economics"]["npv_cny"]})
    corrected = {"scope": "phase2A correctness rerun; original pv_phase2a directory is preserved", "base": compact(base, "guangzhou_2024"), "shifted_hours": compact(shifted, "guangzhou_2024_shifted"), "roof_budget_constrained": compact(constrained_report, "guangzhou_2024_constrained"), "study_10_years": compact(base, "guangzhou_2024_10y"), "study_15_years": compact(long_report, "guangzhou_2024_15y"), "fixed_2kwp_9_years": fixed_rows}
    (OUT / "guangzhou_2024_full_chain_corrected.json").write_text(json.dumps(corrected, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "fixed_2kwp_9_years_corrected.json").write_text(json.dumps({"scope": "fixed 2 kWp time-year sensitivity; not independent building validation", "rows": fixed_rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "fixed_2kwp_9_years_corrected.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fixed_rows[0].keys()); writer.writeheader(); writer.writerows(fixed_rows)
    baseline = next(x for x in base["candidates"] if x["capacity_kwp"] == 0)
    (OUT / "counterexamples_before_after.json").write_text(json.dumps({"lifecycle_zero_kwp": {"before_total_import_cost_cny": 8060.746751414448, "after_total_import_cost_cny": baseline["economics"]["npv_cny"] * -1, "expected_total_import_cost_cny": 8243.780182079507, "note": "0kWp固定负荷每年重新匹配；NPV为负的累计购电现金流"}, "azimuth_mapping": {"south_0": 180.0, "east_minus90": 90.0, "west_plus90": 270.0, "north_180": 0.0}, "interval_validation": "real timestamp differences checked against declared intervals; NaN and negative values rejected", "quote_and_export": "0kWp has no PV quote costs; nonzero missing quotes and missing export price remain incomplete"}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "README.md").write_text("""# 阶段二A正确性修复结果\n\n本目录由 `python scripts/phase2a_correctness_demo.py` 生成，未覆盖 `results/pv_phase2a`。\n\n- `guangzhou_2024_full_chain_corrected.json`：广州 2024 完整链、晚间使用时段、屋顶/预算约束以及 10/15 年现金流；每个 0/1/2/3 kWp 候选都指向逐时 CSV。\n- `candidate_evidence/`：按区间电量保存负荷、交流发电、自用、购电、外送和弃电，便于逐行检查守恒。\n- `fixed_2kwp_9_years_corrected.json/csv`：广州、北京、哈尔滨 2023–2025 固定 2kWp 时间年敏感性，不称独立建筑验证。\n- `counterexamples_before_after.json`：生命周期、朝向、时间轴、缺失报价/外送价修复前后对照。\n\n第一阶段空调负荷仍是未校准的城市级冷却情景；服务缺口随报告保留。0kWp 是无光伏基准，不承担任何光伏报价项。非零报价或外送价格缺失时只交付物理结果，不证明“不安装最划算”。\n""", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "base_recommendation": base.get("recommendation"), "fixed_rows": len(fixed_rows), "candidate_evidence": len(list(EVIDENCE.glob("*.csv")))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
