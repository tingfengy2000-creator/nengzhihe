"""Extract fixed, read-only frontend fixtures from an accepted 5090 report.

This script never imports the simulation modules and never recalculates a
scenario. It only copies values from versioned JSON evidence into a small
fixture consumed by the static 5060 replay viewer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "operation_planning" / "results" / "phase2b_semantics_5090"
FULL = RESULTS / "guangzhou_2024_full_chain.json"
SUMMARY = RESULTS / "replay_cases.json"
AGENT = RESULTS / "agent_task_records.json"
OUT_DIR = ROOT / "docs" / "handoff" / "replay_viewer"
OUT = OUT_DIR / "replay_cases.json"
SOURCE_COMMIT = "a4d4bd139cab844eab0c1853889bd0320f45c941"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def candidate_summary(candidate: dict) -> dict:
    economics = candidate.get("economics", {})
    return {
        "scenario_id": candidate.get("scenario_id"),
        "pv_capacity_kwp": candidate.get("pv_capacity_kwp"),
        "wind_turbine_count": candidate.get("wind_turbine_count"),
        "generation_kwh": candidate.get("generation_kwh"),
        "pv_generation_kwh": candidate.get("pv_generation_kwh"),
        "wind_generation_kwh": candidate.get("wind_generation_kwh"),
        "self_use_kwh": candidate.get("self_use_kwh"),
        "grid_import_kwh": candidate.get("grid_import_kwh"),
        "grid_export_kwh": candidate.get("grid_export_kwh"),
        "curtailment_kwh": candidate.get("curtailment_kwh"),
        "load_coverage_rate": candidate.get("load_coverage_rate"),
        "capex_cny": economics.get("capex_cny"),
        "npv_cny": economics.get("npv_cny"),
        "total_cost_npv_cny": economics.get("total_cost_npv_cny"),
        "incremental_npv_vs_s0_cny": economics.get("incremental_npv_vs_s0_cny"),
        "economics_status": economics.get("status"),
        "constraint_status": candidate.get("constraint_status"),
        "constraint_reasons": candidate.get("constraint_reasons", []),
        "admission_status": candidate.get("admission_status"),
        "equivalent_to": candidate.get("equivalent_to"),
    }


def compact_weather(provenance: dict) -> dict:
    context = provenance.get("context", {})
    normalization = provenance.get("normalization", {})
    return {
        "source": provenance.get("source_file"),
        "hash": provenance.get("hash"),
        "site": context.get("site"),
        "start": context.get("start"),
        "end": context.get("end"),
        "variables": context.get("variables", []),
        "units": context.get("units", {}),
        "normalization_version": normalization.get("version"),
        "radiation_definition": normalization.get("radiation"),
        "instantaneous_definition": normalization.get("instantaneous"),
    }


def main() -> None:
    full = json.loads(FULL.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    agent = json.loads(AGENT.read_text(encoding="utf-8"))
    full_candidates = {c["scenario_id"]: c for c in full["candidates"]}
    source_info = {
        "source_commit": SOURCE_COMMIT,
        "calculation_version": full.get("calculation_version"),
        "source_result_file": "operation_planning/results/phase2b_semantics_5090/guangzhou_2024_full_chain.json",
        "source_result_sha256": sha256(FULL),
        "summary_result_file": "operation_planning/results/phase2b_semantics_5090/replay_cases.json",
        "summary_result_sha256": sha256(SUMMARY),
        "mode": "fixed_replay_only",
    }
    scenario = full["scenario"]
    fixed_input = {
        "site_id": scenario.get("site_id"),
        "year": scenario.get("year"),
        "pv_capacity_kwp": scenario.get("pv_capacity_kwp"),
        "wind_turbine_count": scenario.get("wind", {}).get("turbine_count"),
        "hub_height_m": scenario.get("wind", {}).get("hub_height_m"),
        "hellman_exponent": scenario.get("wind", {}).get("hellman_exponent"),
        "budget_cny": scenario.get("budget_cny"),
        "import_price_cny_per_kwh": scenario.get("import_price_cny_per_kwh"),
        "allow_export": scenario.get("allow_export"),
        "study_years": scenario.get("study_years"),
        "quote_scope": "user scenario; not a verified procurement quote",
    }
    default_case = {
        "case_id": "default_four_scenarios",
        "label": "默认四方案（完整图表样例）",
        "source": source_info,
        "input": fixed_input,
        "weather": compact_weather(full["weather_provenance"]),
        "load_context": full["load_context"],
        "recommendation": full["recommendation"],
        "candidates": [candidate_summary(c) for c in full["candidates"]],
        "chart": {
            "scenario_id": "S3_pv_wind",
            "sampling_rule": "完整8784个一小时间隔，未用抽样值重算年度指标",
            **full_candidates["S3_pv_wind"]["hourly"],
        },
        "not_provided": ["现场测风", "并网审批", "已核实采购报价", "同等服务水平保证"],
    }
    cases = [default_case]
    for item in summary["cases"]:
        if item["case_id"] == "default_90000":
            continue
        cases.append(
            {
                "case_id": item["case_id"],
                "label": {
                    "budget_60000": "预算60000元",
                    "missing_pv_quote": "PV报价缺失",
                    "roof_1m2": "屋顶可用面积1㎡",
                }.get(item["case_id"], item["case_id"]),
                "source": {
                    **source_info,
                    "source_result_file": "operation_planning/results/phase2b_semantics_5090/replay_cases.json",
                    "source_result_sha256": sha256(SUMMARY),
                },
                "input": item.get("request", {}),
                "service_quality": item.get("service_quality"),
                "recommendation": item.get("recommendation"),
                "candidates": item.get("candidates", []),
                "chart": None,
                "not_provided": ["完整API响应", "新的任意输入计算", "独立现场数据"],
            }
        )
    agent_cases = []
    for item in agent.get("cases", []):
        agent_cases.append(
            {
                "case_id": item.get("case_id"),
                "request": item.get("request"),
                "status": item.get("status"),
                "question": item.get("question"),
                "full_plan_calls": item.get("full_plan_calls"),
                "wall_time_ms": item.get("wall_time_ms"),
                "source_commit": SOURCE_COMMIT,
                "record_file": "operation_planning/results/phase2b_semantics_5090/agent_task_records.json",
                "normalized_modifications": item.get("report_summary", {}).get("agent_task", {}).get("modifications") if item.get("report_summary") else None,
            }
        )
    payload = {
        "format_version": "5060-frontend-replay-v1",
        "description": "只读固定回放；不导入或执行热湿、光伏、风电、生命周期或LLM核心。",
        "source": source_info,
        "cases": cases,
        "agent_cases": agent_cases,
        "display_contract": {
            "unknown_is_not_excluded": True,
            "service_gap_is_not_full_service": True,
            "pending_message": "待计算/待5090验算",
            "export_rule": "从当前已显示report导出，不为导出再次计算。",
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(OUT), "bytes": OUT.stat().st_size, "source_commit": SOURCE_COMMIT}, ensure_ascii=False))


if __name__ == "__main__":
    main()
