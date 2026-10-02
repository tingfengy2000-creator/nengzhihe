r"""Read-only numerical probes. Usage: python 复现新增问题.py E:\比赛\nengzhihe\round2
No source/data/config changes; the diagnostic entry is called with save=False.
"""
from __future__ import annotations
import argparse
import copy
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('project_root', type=Path)
    p.add_argument('--output', type=Path, help='Optional new JSON result path; existing files will not be replaced.')
    args = p.parse_args()
    root = args.project_root.resolve()
    if not (root / 'policies.py').is_file():
        p.error('project_root must be the extracted round2 directory containing policies.py')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    from policies import run_case
    source = root / 'data/demos/NZH-90C933F3C475.json'
    if not source.is_file():
        p.error(f'Missing original normal demonstration: {source}')
    original = json.loads(source.read_text(encoding='utf-8'))
    results = []
    for name in ['baseline', 'wrong_declared_unit', 'one_minute_timestamps_declared_as_five']:
        case = copy.deepcopy(original)
        if name == 'wrong_declared_unit':
            case['units']['OA_TEMP'] = 'degF'
        elif name == 'one_minute_timestamps_declared_as_five':
            start = datetime.fromisoformat(case['timestamps'][0])
            case['timestamps'] = [(start + timedelta(minutes=i)).isoformat() for i in range(len(case['timestamps']))]
        try:
            r = run_case(case, 'full_information', 4, save=False)
            step = {x['action']: x['features'] for x in r['steps']}
            quality = r['final']['quality']
            windows = step.get('air_path', {}).get('windows', [])
            row = {
                'test': name,
                'rejected_with_exception': False,
                'quality_status': quality.get('status'),
                'quality_label': quality.get('label'),
                'diagnostic_quality_status': step.get('quality', {}).get('quality_status'),
                'unit_errors': step.get('quality', {}).get('unit_errors'),
                'device_label': r['final'].get('label'),
                'device_status': r['final'].get('status'),
                'timestamps_span': [case['timestamps'][0], case['timestamps'][-1]],
                'declared_interval_minutes': case.get('sample_interval_minutes'),
                'reported_operating_minutes': step.get('quality', {}).get('unique_operating_minutes'),
                'first_air_window': {k: windows[0].get(k) for k in ['start', 'end', 'minutes', 'samples']} if windows else None,
            }
        except (ValueError, TypeError, KeyError) as e:
            row = {'test': name, 'rejected_with_exception': True, 'exception': type(e).__name__, 'message': str(e)}
        results.append(row)
    text = json.dumps(results, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        with args.output.open('x', encoding='utf-8') as f:
            f.write(text + '\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
