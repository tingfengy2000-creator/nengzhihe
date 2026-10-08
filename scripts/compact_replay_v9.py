"""Build the small, read-only replay consumed by the review UI.

The complete HTTP replays remain the numerical evidence.  This command removes
weather audit vectors and per-candidate hourly traces while retaining the
recommended chart, candidate summaries, PV sweep and surplus-path cards.
Paths are made repository-relative so the UI replay is portable and anonymous.

Usage:
    python scripts/compact_replay_v9.py \
      --input operation_planning/results/phase2b_carbon_5090/replay_cases_v9.json \
      --output docs/handoff/replay_viewer/replay_cases_ui_v9.json
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


def _repo_relative(value: Any) -> Any:
    """Replace machine paths while leaving URLs and ordinary strings intact."""
    if not isinstance(value, str):
        return value
    normalized = value.replace("\\", "/")
    marker = "/operation_planning/"
    if marker in normalized:
        return normalized[normalized.index(marker) + 1 :]
    marker = "/docs/"
    if marker in normalized:
        return normalized[normalized.index(marker) + 1 :]
    # These are paths occasionally emitted by a local runner, not source data.
    for prefix in ("/home/", "/workspace/", "/tmp/"):
        if normalized.startswith(prefix):
            return Path(normalized).name
    return value


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return _repo_relative(value)


def _compact_weather(weather: Any) -> Any:
    if not isinstance(weather, dict):
        return weather
    out = _sanitize(copy.deepcopy(weather))
    provenance = out.get("provenance")
    if not isinstance(provenance, dict):
        return out
    normalization = provenance.get("normalization")
    if isinstance(normalization, dict):
        compact = {}
        for key, value in normalization.items():
            if isinstance(value, list):
                # Keep the audit cardinality and a constant interval when it is
                # available, but never ship the full weather audit vectors.
                compact[f"{key}_count"] = len(value)
                finite = [x for x in value if isinstance(x, (int, float))]
                if finite and len(set(finite)) == 1:
                    compact[f"{key}_constant"] = finite[0]
            else:
                compact[key] = value
        provenance["normalization"] = compact
    return out


def _year_one(rows: Any) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and int(row.get("year", -1)) == 1:
            return row
    return None


def _ensure_payback_fields(candidate: dict[str, Any], baseline: dict[str, Any] | None) -> None:
    """Carry the two UI payback fields without rerunning a physical model.

    Older v9 summaries retained the yearly cash-flow rows but dropped these
    two scalar fields.  They are reconstructed from the already stored year-1
    rows using the same simple-payback definition used by ``hybrid._lifecycle``.
    If a future full replay already contains either field, its authoritative
    value is kept unchanged.
    """
    economics = candidate.get("economics")
    if not isinstance(economics, dict):
        return
    if "simple_payback_years" in economics and "annual_saving_after_maintenance_cny" in economics:
        return
    row = _year_one(economics.get("yearly"))
    base_econ = (baseline or {}).get("economics") if isinstance(baseline, dict) else None
    base_row = _year_one(base_econ.get("yearly")) if isinstance(base_econ, dict) else None
    annual = None
    if row is not None and base_row is not None:
        try:
            annual = (
                float(base_row.get("grid_import_cost_cny", 0.0))
                - float(row.get("grid_import_cost_cny", 0.0))
                - float(row.get("maintenance_cny", 0.0))
                + float(row.get("export_income_cny", 0.0))
            )
        except (TypeError, ValueError):
            annual = None
    capex = candidate.get("capex_cny")
    payback = None
    if capex is not None and annual is not None and annual > 0:
        try:
            payback = float(capex) / annual
        except (TypeError, ValueError, ZeroDivisionError):
            payback = None
    economics.setdefault("annual_saving_after_maintenance_cny", annual)
    economics.setdefault("simple_payback_years", payback)


def _compact_candidate(candidate: Any, baseline: dict[str, Any] | None = None) -> Any:
    if not isinstance(candidate, dict):
        return candidate
    out = _sanitize(copy.deepcopy(candidate))
    _ensure_payback_fields(out, baseline)
    # The chart and chart_recommended fields carry the only UI time series.
    # Candidate.hourly duplicates all four scenarios and is evidence-only.
    out.pop("hourly", None)
    return out


def _candidate_total_cost(candidate: dict[str, Any], rate: float, discount_rate: float) -> float | None:
    economics = candidate.get("economics") or {}
    yearly = economics.get("yearly")
    capex = candidate.get("capex_cny", economics.get("capex_cny"))
    if not isinstance(yearly, list) or capex is None:
        return None
    total = float(capex)
    for row in yearly:
        year = int(row.get("year", 0))
        if year <= 0:
            continue
        import_key = "grid_import_cost_cny" if "grid_import_cost_cny" in row else "electricity_cost_cny"
        if row.get(import_key) is None:
            return None
        growth = (1.0 + float(rate)) ** (year - 1)
        cash_cost = float(row.get(import_key, 0.0) or 0.0) * growth
        cash_cost += float(row.get("maintenance_cny", 0.0) or 0.0)
        cash_cost += float(row.get("replacement_cny", 0.0) or 0.0)
        cash_cost -= float(row.get("export_income_cny", 0.0) or 0.0)
        cash_cost -= float(row.get("residual_cny", 0.0) or 0.0)
        total += cash_cost / ((1.0 + float(discount_rate)) ** year)
    return total


def _payback_details(selected: dict[str, Any] | None, baseline: dict[str, Any] | None, rate: float, study_years: int) -> tuple[float | None, int | None, str]:
    if not selected or not baseline:
        return None, None, "缺少完整经济数据，无法计算回本年限"
    ce = selected.get("economics") or {}; be = baseline.get("economics") or {}
    capex = selected.get("capex_cny", ce.get("capex_cny"))
    if capex is None or float(capex) <= 0:
        return None, None, "无非零初始投入，不适用回本年限"
    crows = {int(row.get("year", 0)): row for row in ce.get("yearly", [])}; brows = {int(row.get("year", 0)): row for row in be.get("yearly", [])}
    first = crows.get(1); base_first = brows.get(1)
    if not first or not base_first:
        return None, None, "缺少第1年数据，无法计算回本年限"
    key = "grid_import_cost_cny" if "grid_import_cost_cny" in first else "electricity_cost_cny"
    base_key = "grid_import_cost_cny" if "grid_import_cost_cny" in base_first else "electricity_cost_cny"
    first_saving = float(base_first.get(base_key, 0.0) or 0.0) - float(first.get(key, 0.0) or 0.0) - float(first.get("maintenance_cny", 0.0) or 0.0) - float(first.get("replacement_cny", 0.0) or 0.0) + float(first.get("export_income_cny", 0.0) or 0.0) + float(first.get("residual_cny", 0.0) or 0.0)
    simple = float(capex) / first_saving if first_saving > 0 else None
    cumulative = 0.0
    for year in range(1, int(study_years) + 1):
        row = crows.get(year); base_row = brows.get(year)
        if not row or not base_row:
            continue
        key = "grid_import_cost_cny" if "grid_import_cost_cny" in row else "electricity_cost_cny"
        base_key = "grid_import_cost_cny" if "grid_import_cost_cny" in base_row else "electricity_cost_cny"
        growth = (1.0 + float(rate)) ** (year - 1)
        cumulative += (float(base_row.get(base_key, 0.0) or 0.0) - float(row.get(key, 0.0) or 0.0)) * growth
        cumulative += -float(row.get("maintenance_cny", 0.0) or 0.0) - float(row.get("replacement_cny", 0.0) or 0.0) + float(row.get("export_income_cny", 0.0) or 0.0) + float(row.get("residual_cny", 0.0) or 0.0)
        if cumulative + 1e-9 >= float(capex):
            return simple, year, f"第{year}年累计净节省达到初始投入；simple_payback_years按第1年节省"
    return simple, None, "研究期内未回本；simple_payback_years按第1年节省"


def _ensure_escalation_fields(case: dict[str, Any]) -> None:
    """Add the §19 display-only sensitivity from stored yearly economics.

    This compact replay is derived from the already frozen full replay.  A
    uniform tariff multiplier scales the stored time-of-use import cost, so no
    physical trace is rerun while producing the four comparison rows.
    """
    candidates = case.get("candidates") if isinstance(case.get("candidates"), list) else []
    recommendation = case.get("recommendation") if isinstance(case.get("recommendation"), dict) else {}
    by_id = {str(item.get("scenario_id")): item for item in candidates if isinstance(item, dict) and item.get("scenario_id") is not None}
    baseline = by_id.get("S0_grid")
    selected_id = recommendation.get("scenario_id")
    selected = by_id.get(str(selected_id)) if selected_id is not None else None
    input_data = case.get("input") if isinstance(case.get("input"), dict) else {}
    hybrid = input_data.get("hybrid") if isinstance(input_data.get("hybrid"), dict) else {}
    discount = float(hybrid.get("discount_rate", input_data.get("discount_rate", 0.0)) or 0.0)
    rates = [-0.02, 0.0, 0.02, 0.04]
    rows = []
    for rate in rates:
        s0_cost = _candidate_total_cost(baseline, rate, discount) if baseline else None
        selected_cost = _candidate_total_cost(selected, rate, discount) if selected else None
        payback, cumulative_payback, payback_note = _payback_details(selected, baseline, rate, int((selected or {}).get("economics", {}).get("study_years", 10) or 10))
        incremental = None if s0_cost is None or selected_cost is None else s0_cost - selected_cost
        if rate == 0.0 and selected is not None:
            candidate_incremental = selected.get("incremental_npv_vs_s0_cny")
            if candidate_incremental is None:
                candidate_incremental = (selected.get("economics") or {}).get("incremental_npv_vs_s0_cny")
            if candidate_incremental is not None:
                incremental = float(candidate_incremental)
        rows.append({"rate": rate, "s0_total_cost_npv_cny": s0_cost, "recommended_scenario_id": selected_id, "recommended_total_cost_npv_cny": selected_cost, "incremental_npv_vs_s0_cny": incremental, "simple_payback_years": payback, "simple_payback_note": "按第1年节省，不含后续电价涨幅", "cumulative_payback_year": cumulative_payback, "payback_note": payback_note})
    case["tariff_escalation"] = {"rate": 0.0, "applies_to": "grid_import", "note": "各年电价按年涨幅等比调整，电价结构不变；不是电价预测。"}
    case["escalation_sensitivity"] = {"rates": rates, "recommendation_scenario_id": selected_id, "rows": rows, "note": "只复用完整回放中已计算的逐年购电成本；不重跑物理模型。"}


def _compact_chart(chart: Any) -> Any:
    """Keep the full source-resolution chart but use UI precision for numbers."""
    if not isinstance(chart, dict):
        return chart
    out = {}
    for key, value in chart.items():
        if isinstance(value, list):
            # Two decimals keeps the review file below a decimal 8 MB while
            # leaving the full-precision evidence package untouched.
            out[key] = [round(float(item), 2) if isinstance(item, (int, float)) and not isinstance(item, bool) else item for item in value]
        else:
            out[key] = value
    return out


def compact_case(case: dict[str, Any]) -> dict[str, Any]:
    out = _sanitize(copy.deepcopy(case))
    if "weather" in out:
        out["weather"] = _compact_weather(case.get("weather"))
    if isinstance(out.get("candidates"), list):
        baseline = out["candidates"][0] if out["candidates"] else None
        out["candidates"] = [_compact_candidate(x, baseline) for x in out["candidates"]]
    out["chart"] = _compact_chart(out.get("chart"))
    out["chart_recommended"] = _compact_chart(out.get("chart_recommended"))
    _ensure_escalation_fields(out)
    # Keep chart/chart_recommended at their real source resolution (8784 for a
    # leap year); do not silently truncate the calendar or alter physical data.
    out["ui_replay_contract"] = {
        "hourly_candidate_traces_omitted": True,
        "weather_audit_vectors_omitted": True,
        "charts_are_source_resolution": True,
        "full_case_path": "operation_planning/results/phase2b_carbon_5090/replay_cases_v9.json",
    }
    return out


def build(source: dict[str, Any]) -> dict[str, Any]:
    out = _sanitize(copy.deepcopy(source))
    out["format_version"] = "replay_cases_ui_v9"
    out["description"] = (
        "界面精简回放：保留推荐图表、候选摘要、容量比选和余电路径；"
        "完整HTTP证据见仓库相对路径。"
    )
    out["source"] = _sanitize(out.get("source", {}))
    out["source"]["full_precision_results"] = (
        "operation_planning/results/phase2b_carbon_5090/replay_cases_v9.json"
    )
    out["display_contract"] = _sanitize(out.get("display_contract", {}))
    out["display_contract"]["full_precision_results"] = out["source"]["full_precision_results"]
    out["cases"] = [compact_case(c) for c in source.get("cases", [])]
    # State variants are identifiers in v8/v9; retain them without expansion.
    out["state_variants"] = _sanitize(source.get("state_variants", []))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    compact = build(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(compact, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    size = args.output.stat().st_size
    if size > 8 * 1024 * 1024:
        raise SystemExit(f"compact replay is {size} bytes, above 8 MiB")
    print(json.dumps({"output": str(args.output), "bytes": size, "cases": len(compact["cases"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
