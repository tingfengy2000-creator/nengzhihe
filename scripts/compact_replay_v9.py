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


def _compact_candidate(candidate: Any) -> Any:
    if not isinstance(candidate, dict):
        return candidate
    out = _sanitize(copy.deepcopy(candidate))
    # The chart and chart_recommended fields carry the only UI time series.
    # Candidate.hourly duplicates all four scenarios and is evidence-only.
    out.pop("hourly", None)
    return out


def compact_case(case: dict[str, Any]) -> dict[str, Any]:
    out = _sanitize(copy.deepcopy(case))
    if "weather" in out:
        out["weather"] = _compact_weather(case.get("weather"))
    if isinstance(out.get("candidates"), list):
        out["candidates"] = [_compact_candidate(x) for x in out["candidates"]]
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
