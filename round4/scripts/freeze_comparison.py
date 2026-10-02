"""Declare comparators and a future-date protocol before executing comparisons."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'output/comparison_frozen.json'
if out.exists():raise RuntimeError('Frozen protocol exists; never overwrite it.')
files=['scripts/comparators.py','diagnostics.py','quality.py','policies.py','data/calibration.json','data/regression/labels.json']
files += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'data/regression/cases').glob('*.json'))]
p={'frozen_utc':datetime.now(timezone.utc).isoformat(),'status':'historical_regression_comparison_not_blind_evaluation',
 'methods':['workbench','fixed_threshold','without_contiguity'],
 'fixed_threshold':{'temperature_residual_C':2.0,'low_command_max':.15,'high_command_min':.95,'window_minutes':30,'mismatch_fraction':.8,'minimum_support_minutes':60},
 'ablation':'Remove only temporal continuity/window mismatch aggregation. Keep quality, stable-mode/temperature gates, reference envelope and 60-minute support requirement.',
 'decision_set':['damper_suspicion','unresolved'],'negative_claim':'No untriggered case is declared fault-free.',
 'unit':'56 base day-scenarios on 14 dates. All source settings per date stay together. 112 original/duplicate versions only for paired robustness.',
 'groups':['normal','damper_stuck_at_25_percent','damper_stuck_at_75_percent','coil_leakage_control'],
 'primary_reports':['support_coverage_over_56','source_consistent_support_over_56','support_recall_over_28_damper_cases','normal_control_wrong_attribution_over_14','coil_control_wrong_attribution_over_14','unresolved_over_56'],
 'timing':'one measured run per method-case, including JSON read and numerical execution; not human time savings',
 'historical_caveat':'All 112 were inspected earlier. Freezing now does not restore holdout status; no method selection/tuning after results.',
 'future_performance_test':{'status':'not_executed','date_selection':'From the existing source annual calendar, exclude every date in all historical split manifests. Select the first two complete unused seven-day calendar blocks after 2018-10-31 by date, without inspecting signals or outcomes. If insufficient unused blocks, stop and amend the protocol before data access.',
 'grouping':'All normal, stuck-25%, stuck-75%, coil-leakage settings and perturbations on the same date belong together. Base unit is date x source setting.',
 'rules':'Use these frozen methods unchanged; never drop controls, pick successful dates or tune thresholds after evaluation. Report all selected days including unavailable/invalid evidence as unresolved. Same-system time holdout only.',
 'risk_coverage_curve':'Not produced: no reproducibly calibrated evidence ranking score.'},
 'sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
out.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8');print(out)
