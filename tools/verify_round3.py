"""Run frozen checks in a retained isolated copy, never over historical results."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', default='.review-work/latest.json')
    args = parser.parse_args()
    report = (ROOT / args.report).resolve()
    if not report.is_relative_to(ROOT):
        raise ValueError('Report must remain inside this repository.')
    raw = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT)
    files = sorted(set(s.decode('utf-8') for s in raw.split(b'\0') if s.startswith(b'round3/')))
    before = {name: sha(ROOT / name) for name in files}
    work = ROOT / '.review-work' / str(time.time_ns())
    work.mkdir(parents=True)
    for name in files:
        dest = work / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)
    stage = work / 'round3'
    (stage / 'output' / 'regression').mkdir(parents=True, exist_ok=True)
    logs = work / 'logs'
    logs.mkdir()
    checks = []
    start = time.perf_counter()
    for script in ['scripts/test_reliability.py', 'scripts/test_standalone.py', 'scripts/regression.py', 'scripts/demo_import.py']:
        run_start = time.perf_counter()
        proc = subprocess.run([sys.executable, '-X', 'utf8', script], cwd=stage,
                              capture_output=True, text=True, encoding='utf-8', timeout=240)
        (logs / (Path(script).stem + '.txt')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
        checks.append({'script': script, 'exit_code': proc.returncode,
                       'elapsed_seconds': round(time.perf_counter() - run_start, 3)})
        if proc.returncode:
            raise RuntimeError(f'{script} failed; inspect {logs}')
    def read(relative):
        return json.loads((stage / relative).read_text(encoding='utf-8'))
    reliability = read('output/reliability_tests.json')
    standalone = read('output/standalone_tests.json')
    regression = read('output/regression/summary.json')
    assert reliability['passed'] == 29
    assert standalone['passed'] == 11
    assert regression['records'] == 112
    assert regression['round3_vs_round2_label_changes'] == []
    assert regression['coil_qualified_zero_records'] == 112
    expected = {'AHU_annual.csv': 0, 'damper_stuck_025_annual.csv': 1,
                'damper_stuck_075_annual.csv': 11, 'coi_leakage_025_annual.csv': 0}
    for name, count in expected.items():
        assert regression['source_groups'][name]['correct'] == count
        assert regression['source_groups'][name]['base_cases'] == 14
    # Verify both document and final-page hashes, without rerendering unchanged files.
    qa = read('materials/working/qa.json')
    checked_pages = 0
    for doc in qa['files']:
        assert sha(stage / 'materials/final' / doc['file']) == doc['sha256']
        folder = stage / Path(doc['rendered_pdf'].replace('\\', '/')).parent
        for png, digest in doc['page_png_sha256'].items():
            assert sha(folder / png) == digest
            checked_pages += 1
    assert checked_pages == 10
    archive = read('delivery/package_check.json')
    assert sha(stage / 'delivery' / archive['archive']) == archive['sha256']
    assert before == {name: sha(ROOT / name) for name in files}, 'Historical source or evidence changed.'
    for name in ['reliability_tests.json', 'standalone_tests.json', 'import_demo.json']:
        shutil.copy2(stage / 'output' / name, logs / name)
    shutil.copy2(stage / 'output/regression/summary.json', logs / 'regression_summary.json')
    digest = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    result = {'status': 'passed', 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'python': sys.version.split()[0], 'commands': checks,
              'elapsed_seconds': round(time.perf_counter() - start, 3),
              'reliability_checks': 29, 'isolated_http_checks': 11,
              'regression_records': 112, 'regression_label_changes': 0,
              'source_groups': regression['source_groups'],
              'coil_qualified_zero_records': 112, 'word_files_sha_verified': 3,
              'final_page_png_hashes_verified': checked_pages, 'release_zip_sha_verified': True,
              'original_round3_files_unchanged': True, 'source_files': len(files),
              'source_manifest_sha256': digest, 'retained_workdir': work.relative_to(ROOT).as_posix(),
              'scope': 'Repository reproducibility check; historical regression only; no new performance claim.'}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
