# Response evidence mechanism v1

## User constraint and baseline limitation

The selected SZVAV record contains outdoor-air, mixed-air and return-air temperatures and **requested** OA/RA damper commands, but no measured damper position or airflow. An APAR rule violation can therefore detect a fault family while still admitting a coil, sensor, or air-path explanation. In the retained record, the adapted professional baseline produced three false damper attributions on heating-coil events.

The mechanism targets that one bottleneck. It does not change APAR thresholds, add an agent, or infer physical position from a command.

## Added capability

After the initial 15-minute occupied stable block, the workbench searches the same recorded day for a later stable block in which both coil commands are closed. It computes the residual between measured mixed-air temperature and the temperature implied by the requested OA/RA command ratio:

`MA_residual = |MA - (OAD/(OAD+RAD) * OA + RAD/(OAD+RAD) * RA)|`

This is a response check, not a position measurement. Its threshold is frozen from the two development normal days only: the normal 95th percentile plus 0.20 °C sensor margin, with a 0.50 °C floor. A promotion requires at least two 15-minute windows, with at least one window arriving after the initial block, and 30 minutes of support at an 80% within-window violation fraction. If no such block exists, the result is explicitly `missing_discriminating_air_path_evidence`; the system keeps the fault unresolved and requests independent position/flow feedback.

The mechanism is useful because coil heat is excluded from the response window. A mixing alarm accompanied by coil-family alarms but without a later coil-closed response is not promoted to a damper conclusion. A later supported response can advance a damper suspicion, while the final action still asks for physical feedback.

## Fair comparison

- **A, professional baseline:** adapted NISTIR6994 Table 2.1 rules, with SZVAV-specific disabled minimum-OA-fraction rules and normal-only calibration.
- **B, baseline + response evidence:** the same parsed points, quality handling, normal dates, thresholds and full recorded history, plus the frozen response check above.
- **C, necessary ablation:** the same baseline as A with the response mechanism disabled.

Labels, fault settings, dates and file names are joined only by the scoring script after inference. No synthetic future or field action is created. The measured record supplies a later same-day window; the reported wait is the elapsed minutes from the first eligible block to the later support block.

## Evidence boundary

The OpenEI 910 archive and retained Figshare file are byte-identical SZVAV data from the same FLEXLAB X3A controlled test-cell collection. The former holdout dates were already inspected during an earlier preflight, so this A/B/C result is a development and known-holdout reinspection, not untouched external validation. It is reported to expose the mechanism's benefit and failure modes, not as a new generalization claim.

