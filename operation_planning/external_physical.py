"""Bounded adapter for one public physical AHU subset.

The OEDI/LBNL benchmark is useful for checking the provenance and channel
assumptions of a building workflow, but it is not a counterfactual simulator.
This module therefore reports what the measured trace can support and refuses
to turn it into an operation-plan score when required feedback is absent.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List


BASE = Path(__file__).resolve().parent
DATA_PATH = BASE / "data" / "external" / "mzvav2_1_physical_subset.csv"

SOURCE = {
    "title": "Building fault detection data to aid diagnostic algorithm creation and performance testing",
    "dataset_entry": "https://data.openei.org/submissions/910",
    "doi": "10.25984/1824861",
    "article": "https://www.nature.com/articles/s41597-020-0398-6",
    "physical_file": "MZVAV-2-1.csv",
    "facility": "Iowa Energy Center experimental AHU (MZVAV AHU-2)",
    "source_type": "physical controlled experiment",
    "license": "CC BY 4.0 (dataset entry; retain attribution and indicate modifications)",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "original_zip_sha256": "68C58568E3F0E4E7D0F0DE3194A2CE7CA80703C057325EE402A94D3EAB5A76C1",
    "subset_sha256": "75F5061EB6E4C0F41A4A8B936D05B96F7B1AC300610D496972BC86BEE4F6C0FC",
}

APAR_RULE = {
    "name": "APAR-inspired supply-air tracking screen",
    "reference": "https://www.nist.gov/publications/expert-rule-set-fault-detection-air-handling-units",
    "report": "https://nvlpubs.nist.gov/nistpubs/Legacy/IR/nistir6994.pdf",
    "adaptation": "The physical file exposes supply-air temperature and setpoint but not all APAR points; this is an adapted screening rule, not a complete APAR reproduction.",
    "threshold_mae_c": 0.8,
}

# The inventory identifies these three days as manually imposed heating-coil
# bypass leaks. The selected normal days are listed as unfaulted in the same
# inventory. This map is metadata only and is never fed to the calculations.
EVENTS = {
    "2007-08-28": {"class": "fault", "scenario": "heating_coil_bypass_leak", "intensity_gpm": 0.4},
    "2007-08-29": {"class": "fault", "scenario": "heating_coil_bypass_leak", "intensity_gpm": 1.0},
    "2007-08-30": {"class": "fault", "scenario": "heating_coil_bypass_leak", "intensity_gpm": 2.0},
    "2008-08-19": {"class": "normal", "scenario": "unfaulted"},
    "2008-08-25": {"class": "normal", "scenario": "unfaulted"},
    "2008-09-04": {"class": "normal", "scenario": "unfaulted"},
}

FIELD = {
    "timestamp": "Datetime",
    "supply_temp_f": "AHU: Supply Air Temperature",
    "supply_setpoint_f": "AHU: Supply Air Temperature Set Point",
    "outdoor_temp_f": "AHU: Outdoor Air Temperature",
    "mixed_temp_f": "AHU: Mixed Air Temperature",
    "return_temp_f": "AHU: Return Air Temperature",
    "fan_status": "AHU: Supply Air Fan Status",
    "oa_damper_command": "AHU: Outdoor Air Damper Control Signal  ",
    "ra_damper_command": "AHU: Return Air Damper Control Signal",
    "ea_damper_command": "AHU: Exhaust Air Damper Control Signal  ",
    "cooling_valve_command": "AHU: Cooling Coil Valve Control Signal",
    "heating_valve_command": "AHU: Heating Coil Valve Control Signal",
    "occupancy": "Occupancy Mode Indicator",
}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _float(row: Dict[str, str], key: str) -> float | None:
    value = row.get(FIELD[key], "").strip()
    if not value or value.upper() in {"NA", "NAN"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _read_rows(path: Path = DATA_PATH) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _group_day(rows: Iterable[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    groups: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        stamp = datetime.strptime(row[FIELD["timestamp"]], "%m/%d/%Y %H:%M")
        groups[stamp.date().isoformat()].append(row)
    return dict(groups)


def _tracking_mae(rows: List[Dict[str, str]]) -> float | None:
    values = []
    for row in rows:
        if str(row.get(FIELD["occupancy"], "")).strip() != "1":
            continue
        temp = _float(row, "supply_temp_f")
        setpoint = _float(row, "supply_setpoint_f")
        if temp is not None and setpoint is not None:
            values.append(abs(temp - setpoint) * 5.0 / 9.0)
    return round(mean(values), 6) if values else None


def _rule_decision(mae_c: float | None) -> str:
    if mae_c is None:
        return "unresolved_missing_sat_pair"
    return "fault_suspect" if mae_c > APAR_RULE["threshold_mae_c"] else "normal_assumed"


def _gate_decision(mae_c: float | None) -> str:
    """Keep the professional screen but refuse unsupported normal conclusions."""
    if mae_c is None:
        return "unresolved_missing_sat_pair"
    if mae_c > APAR_RULE["threshold_mae_c"]:
        return "fault_suspect"
    return "unresolved_no_actuator_feedback"


def _external_rule_comparison(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    development = {"2007-08-28", "2008-08-19"}
    holdout = [event for event in events if event["date"] not in development]
    rows: List[Dict[str, Any]] = []
    for event in holdout:
        truth = event["metadata"].get("class")
        for name, decision in (("professional_screen", _rule_decision(event["supply_setpoint_tracking_mae_c"])), ("能智核_evidence_gate", _gate_decision(event["supply_setpoint_tracking_mae_c"]))):
            correct = (decision == "fault_suspect" and truth == "fault") or (decision == "normal_assumed" and truth == "normal")
            rows.append({"date": event["date"], "truth_for_evaluation": truth, "engine": name, "decision": decision, "correct_if_decided": bool(correct), "counted_as_decided": decision in {"fault_suspect", "normal_assumed"}})
    summary: Dict[str, Any] = {}
    for name in ("professional_screen", "能智核_evidence_gate"):
        selected = [row for row in rows if row["engine"] == name]
        decided = [row for row in selected if row["counted_as_decided"]]
        summary[name] = {
            "holdout_date_blocks": len(selected),
            "decided": len(decided),
            "unresolved": len(selected) - len(decided),
            "correct_if_decided": sum(row["correct_if_decided"] for row in decided),
            "wrong_if_decided": sum(not row["correct_if_decided"] for row in decided),
            "coverage": len(decided) / len(selected) if selected else 0.0,
            "error_rate_among_decided": (sum(not row["correct_if_decided"] for row in decided) / len(decided)) if decided else 0.0,
        }
    return {
        "rule": APAR_RULE,
        "development_date_blocks": sorted(development),
        "holdout_date_blocks": [event["date"] for event in holdout],
        "records": rows,
        "summary": summary,
        "interpretation": "The gate trades coverage for avoiding unsupported normal conclusions when actual actuator feedback is absent; this is a safety result, not a savings or general diagnostic claim.",
    }


def summarize(path: Path = DATA_PATH) -> Dict[str, Any]:
    rows = _read_rows(path)
    groups = _group_day(rows)
    field_names = set(rows[0]) if rows else set()
    events: List[Dict[str, Any]] = []
    for day in sorted(groups):
        day_rows = groups[day]
        timestamps = [datetime.strptime(r[FIELD["timestamp"]], "%m/%d/%Y %H:%M") for r in day_rows]
        intervals = [(b - a).total_seconds() for a, b in zip(timestamps, timestamps[1:])]
        commands = {key: sum(_float(r, key) is not None for r in day_rows) for key in ("oa_damper_command", "ra_damper_command", "ea_damper_command", "heating_valve_command")}
        events.append({
            "date": day,
            "metadata": EVENTS.get(day, {"class": "unknown", "scenario": "not_in_selected_inventory"}),
            "rows": len(day_rows),
            "sampling_seconds": {"min": min(intervals) if intervals else None, "max": max(intervals) if intervals else None},
            "occupied_rows": sum(str(r.get(FIELD["occupancy"], "")).strip() == "1" for r in day_rows),
            "supply_setpoint_tracking_mae_c": _tracking_mae(day_rows),
            "available_command_values": commands,
        })

    # The source CSV contains a ground-truth column. It is deliberately
    # excluded from the adapter's evidence fields; the event map above is used
    # only for post-run comparison and provenance reporting.
    excluded = [name for name in field_names if "Ground Truth" in name]
    required_for_counterfactual_planning = {
        "zone_air_temperature": False,
        "electric_power_or_energy": False,
        "actual_damper_or_valve_position": False,
        "weather_or_outdoor_temperature": FIELD["outdoor_temp_f"] in field_names,
        "control_commands": all(FIELD[key] in field_names for key in ("oa_damper_command", "heating_valve_command")),
    }
    comparison = _external_rule_comparison(events)
    return {
        "source": {**SOURCE, "data_path": str(path), "data_sha256": _hash(path)},
        "adapter": {
            "measurement_units": {"temperature": "degF in source, converted to degC for summary", "commands": "fraction/control signal", "time": "minute timestamps"},
            "input_fields": [FIELD[key] for key in FIELD if key not in {"timestamp", "occupancy"}],
            "excluded_from_diagnostics": excluded,
            "label_source": "inventory event table; source ground-truth column is excluded from inputs",
            "events": events,
        },
        "planning_eligibility": {
            "status": "insufficient_for_counterfactual_plan",
            "required_channels": required_for_counterfactual_planning,
            "reasons": [
                "no zone-air-temperature feedback in this exported physical subset",
                "no electric-power/energy meter aligned to the AHU trace",
                "control signals are commands; actual damper/valve positions are not logged",
            ],
            "usable_for": ["physical channel and timestamp replay", "source/label separation check", "input admissibility gate"],
            "not_used_for": ["counterfactual energy/cost ranking", "measured building savings", "training or tuning the BOPTEST planner"],
        },
        "comparison": {
            "baseline": "field-presence assumption (would accept the trace as a planning input)",
            "能智核_gate": "requires zone feedback, energy signal and actual-actuator evidence before claiming a plan score",
            "baseline_result": "inadmissible assumption detected",
            "gate_result": "refused counterfactual score with explicit missing-channel reasons",
        },
        "professional_baseline_comparison": comparison,
        "counts": {"rows": len(rows), "date_blocks": len(events), "normal_blocks": sum(e["metadata"].get("class") == "normal" for e in events), "fault_blocks": sum(e["metadata"].get("class") == "fault" for e in events)},
    }


def write_result(output: Path | None = None) -> Dict[str, Any]:
    result = summarize()
    output = output or (BASE / "results" / "experiments" / "external_physical_validation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    result = write_result()
    print(json.dumps({"rows": result["counts"]["rows"], "date_blocks": result["counts"]["date_blocks"], "status": result["planning_eligibility"]["status"]}, ensure_ascii=False))
