"""Generate v6 typical-week HTTP preview evidence on the local 5090 host.

The six calls (three v6 tier inputs × summer/winter) are made through the
same loopback endpoint exposed to the product.  They are physical previews
only: no economic result or annual extrapolation is copied into this file.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
V6 = ROOT / "docs" / "handoff" / "replay_viewer" / "replay_cases_v6.json"
OUT = ROOT / "operation_planning" / "results" / "phase2b_carbon_5090" / "replay_previews_v6.json"
VIEW = ROOT / "docs" / "handoff" / "replay_viewer" / "replay_previews_v6.json"


def _sha(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _payload(case: dict, season: str) -> dict:
    src = case["input"]
    room = dict(src.get("room") or {})
    pv_quote = dict(src.get("pv_quote") or {})
    wind_quote = dict(src.get("wind_quote") or {})
    return {"site_id": src.get("site_id", "guangzhou"), "year": src.get("year", 2024),
            "room": room,
            "pv": {"roof_area_m2": src.get("roof_area_m2", 50),
                   "usable_fraction": src.get("usable_fraction", 0.8),
                   "tilt_deg": src.get("tilt_deg", 23),
                   "azimuth_open_meteo_deg": src.get("azimuth_open_meteo_deg", 0),
                   "quote": pv_quote},
            "hybrid": {"pv_capacity_kwp": src.get("pv_capacity_kwp", 1),
                       "budget_cny": src.get("budget_cny"),
                       "allow_export": src.get("allow_export", False),
                       "tariff_id": src.get("tariff_id"),
                       "tariff_application": src.get("tariff_application"),
                       "pv_quote": pv_quote, "wind_quote": wind_quote,
                       "wind": {"turbine_count": src.get("wind_turbine_count", 0),
                                "hub_height_m": src.get("hub_height_m", 9),
                                "hellman_exponent": src.get("hellman_exponent", 0.14)}},
            "carbon": src.get("carbon"), "preview": {"period": "week", "season": season,
                                                        "month": 7 if season == "summer" else 1}}


def call(base_url: str, payload: dict) -> tuple[dict, float, int]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(base_url.rstrip("/") + "/api/operation/hybrid/preview", data=data,
                  headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    with urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8")); status = response.status
    return result, round((time.perf_counter() - started) * 1000.0, 3), status


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--base-url", default="http://127.0.0.1:18765")
    args = parser.parse_args()
    runtime_source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source = json.loads(V6.read_text(encoding="utf-8"))
    cases = []
    for tier in ("tier_small", "tier_medium", "tier_large"):
        original = next(item for item in source["cases"] if item["case_id"] == tier)
        for season in ("summer", "winter"):
            payload = _payload(original, season)
            response, elapsed, http_status = call(args.base_url, payload)
            if response.get("status") != "success":
                raise RuntimeError(f"preview failed for {tier}/{season}: {response}")
            report = response
            cases.append({"case_id": f"{tier}_{season}_week", "tier": tier, "season": season,
                          "label": f"{original.get('label', tier)}｜{season} fixed calendar week",
                          "source_case_id": tier, "source_commit": runtime_source_commit,
                          "request": payload, "request_sha256": _sha(payload),
                          "response": report, "response_sha256": _sha(report),
                          "http_status": http_status, "http_elapsed_ms": elapsed,
                          "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                          "notes": ["固定日历预览：每年7月15日至22日或1月15日至22日，不声称统计最代表性。", "仅物理发电与逐时匹配；不计算经济、碳价或全年外推。"]})
    output = {"format_version": "preview_v6_http_5090", "source_v6_file": str(V6.relative_to(ROOT)),
              "source_commit": runtime_source_commit,
              "endpoint": "/api/operation/hybrid/preview", "period_rule": {"week": "month-day 15 00:00 through day 22 00:00 exclusive", "summer_month": 7, "winter_month": 1},
              "cases": cases, "http_call_count": len(cases),
              "timing_summary": {"total_http_elapsed_ms": round(sum(x["http_elapsed_ms"] for x in cases), 3),
                                  "mean_http_elapsed_ms": round(sum(x["http_elapsed_ms"] for x in cases) / len(cases), 3),
                                  "max_http_elapsed_ms": max(x["http_elapsed_ms"] for x in cases)}}
    for path in (OUT, VIEW):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output["timing_summary"], ensure_ascii=False))


if __name__ == "__main__": main()
