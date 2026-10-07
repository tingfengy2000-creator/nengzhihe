"""Compare real HTTP preview rows to frozen full-year v6 intervals."""
from pathlib import Path
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'operation_planning/results/phase2b_carbon_5090'


def main():
    annual_path = RESULTS / 'replay_cases_v6.json'
    preview_path = RESULTS / 'replay_previews_v7.json'
    annual = json.loads(annual_path.read_text(encoding='utf-8'))
    previews = json.loads(preview_path.read_text(encoding='utf-8'))
    by_id = {c['case_id']: c for c in annual['cases']}
    cases = []
    keys = ('load_kwh', 'pv_generation_kwh', 'wind_generation_kwh', 'self_use_kwh', 'grid_import_kwh', 'grid_export_kwh', 'curtailment_kwh')
    for case in previews['cases']:
        reference = by_id[case['source_case_id']]
        refs = {c['scenario_id']: c for c in reference['candidates']}
        checked = 0; maximum = 0.0; failures = []
        for candidate in case['response']['candidates']:
            ref = refs[candidate['scenario_id']]['hourly']
            lookup = {t: i for i, t in enumerate(ref['timestamps'])}
            for row in candidate['intervals']:
                i = lookup[row['timestamp']]
                for key in keys:
                    expected = float(ref[key][i]); actual = float(row[key])
                    relative = abs(actual - expected) / (abs(expected) if abs(expected) > 1e-12 else 1.0)
                    maximum = max(maximum, relative); checked += 1
                    if not math.isfinite(actual) or relative > 1e-9:
                        failures.append({'timestamp': row['timestamp'], 'scenario_id': candidate['scenario_id'], 'field': key, 'expected': expected, 'actual': actual})
        cases.append({'case_id': case['case_id'], 'checked_numeric_fields': checked, 'max_relative_error': maximum, 'mismatch_count': len(failures), 'first_mismatches': failures[:5], 'pass': not failures})
    output = {'source_preview_commit': previews['source_commit'], 'annual_sha256': hashlib.sha256(annual_path.read_bytes()).hexdigest(), 'preview_sha256': hashlib.sha256(preview_path.read_bytes()).hexdigest(), 'tolerance': 1e-9, 'cases': cases, 'pass': all(c['pass'] for c in cases), 'warmup': 'full annual thermal trace is simulated before slicing; PV and wind are computed on the same selected interval values'}
    (RESULTS / 'preview_v7_equivalence.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output['pass'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
