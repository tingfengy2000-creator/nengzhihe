"""Freeze and run the professional baseline plus the response mechanism.

The retained 11-day record has already been inspected in an earlier physical
preflight.  This run is therefore labelled development/failure analysis (the
former holdout is a known reinspection), not untouched external validation.
"""

from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adapter import physical  # noqa: E402
from apar import calibrate, evaluate  # noqa: E402
from response_evidence import calibrate_response, evaluate_response  # noqa: E402


NORMAL_IDS = ["5138876d3912", "b5a5b08a1984"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    development = physical("development")
    base_cal = calibrate([c for c in development if c["id"] in NORMAL_IDS])
    response_cal = calibrate_response(
        [c for c in development if c["id"] in NORMAL_IDS], base_cal
    )
    freeze = {
        "protocol": "round5 response evidence mechanism v1",
        "status": "frozen_before_reinspection_run",
        "evaluation_status": "development_and_known_holdout_reinspection",
        "holdout_claim": "not_untouched_external_validation; prior preflight inspected the former holdout",
        "normal_ids": NORMAL_IDS,
        "baseline": "adapted NISTIR6994 Table 2.1 rules in src/apar.py",
        "added_mechanism": "coil-closed stable commanded-air-path response residual",
        "ablation": "remove added response evidence and retain the same APAR baseline",
        "same_evidence": "A, B and C receive the same parsed signal record, quality handling, calibration dates, history and thresholds",
        "parameters": response_cal,
        "truth_separation": "labels and injection settings are joined only by scripts/score_response_mechanism.py after inference",
        "sha256": {
            "data/raw/SZVAV.csv": sha(ROOT / "data/raw/SZVAV.csv"),
            "protocol/external_split.json": sha(ROOT / "protocol/external_split.json"),
            "src/adapter.py": sha(ROOT / "src/adapter.py"),
            "src/apar.py": sha(ROOT / "src/apar.py"),
            "src/response_evidence.py": sha(ROOT / "src/response_evidence.py"),
        },
    }
    (ROOT / "protocol" / "response_mechanism_freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    cases = development + physical("holdout", allow_heldout=True)
    development_ids = {c["id"] for c in development}
    records = []
    for case in cases:
        base = evaluate(case, base_cal, method="apar")
        candidate = evaluate_response(case, base_cal, response_cal)
        ablation = dict(base)
        ablation["method"] = "without_response_evidence"
        ablation["response_mechanism"] = {
            "enabled": False,
            "reason": "necessary ablation; all APAR inputs and calibration remain unchanged",
        }
        for method, result in (
            ("apar_professional_baseline", {**base, "method": "apar_professional_baseline"}),
            ("apar_plus_response_evidence", candidate),
            ("without_response_evidence", ablation),
        ):
            result["evaluation_group"] = (
                "development" if case["id"] in development_ids else "known_holdout_reinspection"
            )
            records.append(result)

    out = ROOT / "results" / "response_mechanism_case_results.json"
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "results" / "response_mechanism_calibration.json").write_text(
        json.dumps({"base": base_cal, "response": response_cal}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"cases": len(cases), "records": len(records), "output": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
