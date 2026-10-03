"""Join frozen inference outputs to labels after inference and score events."""

from collections import defaultdict
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
labels = json.loads((ROOT / "protocol" / "external_split.json").read_text(encoding="utf-8"))["labels"]
records = json.loads((ROOT / "results" / "response_mechanism_case_results.json").read_text(encoding="utf-8"))


def score_method(method, rows):
    fault_rows = []
    damper_rows = []
    for r in rows:
        label = labels[r["id"]]
        is_fault = label["subsystem"] != "normal"
        is_damper = label["subsystem"] == "outdoor_damper"
        detected = bool(r["any_fault_detected"])
        suspicion = bool(r["damper_related_suspicion"])
        fault_rows.append((is_fault, detected))
        damper_rows.append((is_damper, suspicion))

    tp = sum(a and b for a, b in fault_rows)
    tn = sum((not a) and (not b) for a, b in fault_rows)
    fp = sum((not a) and b for a, b in fault_rows)
    fn = sum(a and (not b) for a, b in fault_rows)
    d_tp = sum(a and b for a, b in damper_rows)
    d_fp = sum((not a) and b for a, b in damper_rows)
    d_fn = sum(a and (not b) for a, b in damper_rows)
    positives = d_tp + d_fp
    support = sum(r["response_mechanism"].get("support_minutes", 0.0) for r in rows if method == "apar_plus_response_evidence")
    waits = [
        r["response_mechanism"]["wait_minutes_from_first_eligible"]
        for r in rows
        if method == "apar_plus_response_evidence"
        and r["response_mechanism"].get("wait_minutes_from_first_eligible") is not None
    ]
    return {
        "events": len(rows),
        "fault_detection": {
            "correct": tp + tn,
            "true_positive": tp,
            "true_negative": tn,
            "false_positive_normal": fp,
            "missed_fault": fn,
            "coverage": sum(r[1] for r in fault_rows) / len(rows) if rows else None,
            "error_rate_all_events": (fp + fn) / len(rows) if rows else None,
        },
        "damper_localization": {
            "supported": positives,
            "correct_supported": d_tp,
            "false_damper_attribution": d_fp,
            "unresolved_true_damper": d_fn,
            "precision_among_supported": d_tp / positives if positives else None,
            "recall_among_damper_events": d_tp / (d_tp + d_fn) if (d_tp + d_fn) else None,
        },
        "response_evidence": {
            "support_minutes_sum": support,
            "wait_minutes_observed_count": len(waits),
            "wait_minutes_min": min(waits) if waits else None,
            "wait_minutes_max": max(waits) if waits else None,
        },
    }


by_method = defaultdict(list)
for record in records:
    by_method[record["method"]].append(record)

baseline_by_id = {r["id"]: r for r in by_method["apar_professional_baseline"]}
ablation_by_id = {r["id"]: r for r in by_method["without_response_evidence"]}
compare_keys = ["any_fault_detected", "damper_related_suspicion", "judgment_state", "apar_alarms"]
ablation_mismatches = [
    case_id
    for case_id, baseline in baseline_by_id.items()
    if any(baseline[k] != ablation_by_id[case_id][k] for k in compare_keys)
]

out = {
    "evaluation_status": "development_and_known_holdout_reinspection",
    "ablation_check": {
        "compared_keys": compare_keys,
        "mismatching_case_ids": ablation_mismatches,
        "pass": not ablation_mismatches,
    },
    "methods": {},
}
for method, rows in sorted(by_method.items()):
    metric = score_method(method, rows)
    by_subsystem = defaultdict(list)
    by_group = defaultdict(list)
    for r in rows:
        by_subsystem[labels[r["id"]]["subsystem"]].append(r)
        by_group[r["evaluation_group"]].append(r)
    metric["by_subsystem"] = {
        k: score_method(method, v) for k, v in sorted(by_subsystem.items())
    }
    metric["by_evaluation_group"] = {
        k: score_method(method, v) for k, v in sorted(by_group.items())
    }
    out["methods"][method] = metric

# This is the mechanism-specific comparison the project actually claims:
# detection is unchanged while false damper attributions are removed on the
# retained development/failure-analysis record.
a = out["methods"]["apar_professional_baseline"]
b = out["methods"]["apar_plus_response_evidence"]
out["comparison"] = {
    "fault_detection_correct_change": b["fault_detection"]["correct"] - a["fault_detection"]["correct"],
    "fault_detection_coverage_change": b["fault_detection"]["coverage"] - a["fault_detection"]["coverage"],
    "false_damper_attribution_change": b["damper_localization"]["false_damper_attribution"] - a["damper_localization"]["false_damper_attribution"],
    "damper_precision_change": b["damper_localization"]["precision_among_supported"] - a["damper_localization"]["precision_among_supported"],
    "corrected_false_attributions": sum(
        labels[r["id"]]["subsystem"] != "outdoor_damper"
        and labels[r["id"]]["subsystem"] != "normal"
        and next(x for x in by_method["apar_professional_baseline"] if x["id"] == r["id"])["damper_related_suspicion"]
        and not r["damper_related_suspicion"]
        for r in by_method["apar_plus_response_evidence"]
    ),
    "claim_boundary": "same 11 controlled-test-cell experiment days, former holdout reinspection; no untouched external validation",
}

(ROOT / "results" / "response_mechanism_metrics.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(out["comparison"], ensure_ascii=False))
