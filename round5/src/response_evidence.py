"""A bounded air-path response check layered on the adapted APAR baseline.

This is an explicit adaptation for the FLEXLAB SZVAV signals, not a new APAR
rule set.  It uses only the command and sensor allowlist.  The ground-truth
field, fault setting, date, and file name never enter this module.

The extra evidence is deliberately conservative: during an occupied stable
interval with both coil commands closed, compare mixed-air temperature with
the temperature implied by the requested OA/RA command ratio.  A second
stable interval with a persistent residual is treated as air-path response
evidence.  A command is not a measured damper position, so the result remains
a supported suspicion and still requests independent position/flow feedback.
"""

import numpy as np

from apar import context, evaluate, windows


RESPONSE_DEFAULTS = {
    "response_quantile": 0.95,
    "response_sensor_margin_c": 0.20,
    "response_floor_c": 0.50,
    "response_violation_fraction": 0.80,
    "response_alarm_minutes": 30.0,
    "coil_closed_epsilon": 0.05,
}


def _response_series(case, params):
    """Return context, eligibility and commanded-air-path residuals."""
    c = context(case)
    s = c["s"]
    n = c["n"]
    finite = c["finite"]("MA", "OA", "RA", "OAD", "RAD", "CC", "HC")
    denominator = s["OAD"] + s["RAD"]
    with np.errstate(divide="ignore", invalid="ignore"):
        command_fraction = np.divide(
            s["OAD"], denominator, out=np.full(n, np.nan), where=denominator > 0.0
        )
    expected_ma = command_fraction * s["OA"] + (1.0 - command_fraction) * s["RA"]
    residual = np.abs(s["MA"] - expected_ma)
    coil_closed = (s["CC"] <= params["coil_closed_epsilon"]) & (
        s["HC"] <= params["coil_closed_epsilon"]
    )
    # Mode 1 contains active heating.  Restricting this check to modes 2--5
    # with closed coils prevents coil heat from being misread as air-path
    # response.  A control command remains a requested position, never a
    # measured position.
    eligible = (
        c["occupied"]
        & c["stable"]
        & (c["mode"] >= 2)
        & coil_closed
        & finite
        & np.isfinite(residual)
    )
    return c, eligible, residual, command_fraction


def calibrate_response(normal_cases, base_calibration):
    """Calibrate one normal-only residual threshold before evaluation."""
    params = dict(RESPONSE_DEFAULTS)
    values = []
    for case in normal_cases:
        _, eligible, residual, _ = _response_series(case, params)
        values.extend(residual[eligible].tolist())
    arr = np.asarray(values, dtype=float)
    q = float(np.quantile(arr, params["response_quantile"])) if arr.size else None
    threshold = max(
        params["response_floor_c"],
        (q if q is not None else 0.0) + params["response_sensor_margin_c"],
    )
    return {
        "parameters": params,
        "threshold_c": float(threshold),
        "normal_q95_c": q,
        "normal_minutes": int(arr.size),
        "normal_ids": [c["id"] for c in normal_cases],
        "base_calibration_normal_ids": base_calibration.get("normal_ids", []),
        "interpretation": "requested OA/RA command ratio versus measured MA; command is not actual damper feedback",
    }


def _windows_with_evidence(c, eligible, residual, fraction, calibration):
    p = calibration["parameters"]
    threshold = calibration["threshold_c"]
    bad = residual > threshold
    window_params = {
        "window_minutes": 15,
        "violation_fraction": p["response_violation_fraction"],
    }
    hits, all_windows = windows(c, eligible, bad, window_params)
    for record in all_windows:
        mask = (
            eligible
            & (c["t"] >= record["start_minute"])
            & (c["t"] < record["end_minute"])
        )
        record["residual_mean_c"] = float(np.nanmean(residual[mask])) if np.any(mask) else None
        record["residual_max_c"] = float(np.nanmax(residual[mask])) if np.any(mask) else None
        record["command_fraction_mean"] = float(np.nanmean(fraction[mask])) if np.any(mask) else None
    return hits, all_windows


def evaluate_response(case, base_calibration, response_calibration):
    """Evaluate the response mechanism using the same full signal record.

    The baseline receives the same record through ``evaluate``.  The added
    mechanism can only upgrade a damper suspicion when a separate, coil-closed
    response window is present; otherwise it preserves a conservative gap.
    """
    base = evaluate(case, base_calibration, method="apar")
    params = response_calibration["parameters"]
    c, eligible, residual, fraction = _response_series(case, params)
    hits, all_windows = _windows_with_evidence(c, eligible, residual, fraction, response_calibration)
    support_minutes = float(sum(w["minutes"] for w in hits))
    available_minutes = float(sum(w["minutes"] for w in all_windows))
    first_eligible = float(c["t"][eligible][0]) if np.any(eligible) else None
    initial_end = first_eligible + 15.0 if first_eligible is not None else None
    later_hits = [w for w in hits if initial_end is not None and w["start_minute"] >= initial_end]
    # The first block is the initial check.  A promotion requires a second
    # block that arrives later, so one burst in the first window cannot be
    # presented as active or temporal evidence.
    enough_support = (
        support_minutes >= params["response_alarm_minutes"] and bool(later_hits)
    )
    mixing_alarm = any(
        base["rules"].get(str(rule), {}).get("alarm", False) for rule in (2, 10, 18)
    )
    coil_alarm = any(rule in {1, 3, 4, 7, 11, 13, 14, 16, 19, 20} for rule in base["apar_alarms"])

    if enough_support and base["any_fault_detected"]:
        state = "damper_supported_by_command_response"
        suspicion = True
        explanation = (
            "A second occupied stable interval with both coil commands closed "
            "shows a persistent mixed-air residual against the requested OA/RA "
            "ratio. This separates an air-path response issue from coil heat, "
            "but does not prove physical stroke without position or flow feedback."
        )
    elif mixing_alarm or base["damper_related_suspicion"]:
        suspicion = False
        if available_minutes < 15.0:
            state = "missing_discriminating_air_path_evidence"
            explanation = (
                "The APAR mixing indication has no 15-minute coil-closed "
                "response window. The record cannot distinguish a damper from "
                "a coil or sensor/air-path explanation."
            )
        elif coil_alarm:
            state = "competing_coil_evidence_or_unresolved"
            explanation = (
                "A mixing indication is accompanied by coil-family rule alarms, "
                "so the response evidence is not sufficient to name a damper."
            )
        else:
            state = "response_not_confirmatory"
            explanation = (
                "A coil-closed response window exists, but it does not sustain "
                "the calibrated residual for the confirmation duration."
            )
    else:
        suspicion = False
        state = base["judgment_state"]
        explanation = "No damper-family APAR indication was available for this response check."

    if available_minutes < 15.0:
        action = {
            "code": "obtain_discriminating_air_path_window",
            "instruction": (
                "Collect a later occupied stable interval with both coil commands "
                "closed and a changed OA/RA command ratio for at least 15 minutes; "
                "if unavailable, obtain independent damper position or airflow."
            ),
        }
    elif not enough_support:
        action = {
            "code": "obtain_independent_damper_feedback",
            "instruction": (
                "The available response did not sustain the calibrated residual; "
                "check independent damper position or airflow before localization."
            ),
        }
    else:
        action = {
            "code": "confirm_physical_response",
            "instruction": (
                "Confirm the supported air-path suspicion with an independent "
                "damper position or airflow measurement; control commands are not feedback."
            ),
        }

    first_evidence = float(later_hits[0]["start_minute"]) if later_hits else None
    wait_minutes = (
        float(first_evidence - first_eligible)
        if first_eligible is not None and first_evidence is not None
        else None
    )
    return {
        **base,
        "method": "apar_plus_response_evidence",
        "damper_related_suspicion": suspicion,
        "judgment_state": state,
        "response_mechanism": {
            "current_gap": "No measured damper position or airflow feedback is in this source.",
            "evidence_basis": "coil-closed stable interval; commanded OA/RA ratio; measured MA residual",
            "support_minutes": support_minutes,
            "available_minutes": available_minutes,
            "initial_window_start_minute": first_eligible,
            "initial_window_end_minute": initial_end,
            "later_support_windows": later_hits,
            "threshold_c": response_calibration["threshold_c"],
            "wait_minutes_from_first_eligible": wait_minutes,
            "all_windows": all_windows,
            "support_windows": hits,
            "before_state": base["judgment_state"],
            "after_state": state,
            "explanation": explanation,
        },
        "damper_evidence_status": "supported" if suspicion else "unresolved_or_insufficient",
        "next_actions": [action] + base.get("next_actions", []),
        "limitations": base.get("limitations", [])
        + [
            "The response check uses a requested command ratio and measured mixed-air temperature; it cannot establish physical damper position.",
            "This mechanism was developed on the retained 11-day controlled-test-cell record; the source has no untouched independent event set in this round.",
        ],
    }
