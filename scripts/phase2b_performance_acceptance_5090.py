"""Real loopback HTTP acceptance on the local 5090; no replay answers."""
from __future__ import annotations
import ctypes
from datetime import datetime
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from operation_planning.app import Handler
from scripts import compare_v6_equivalence_5090 as comparison
from scripts import phase2b_preview_replay_v7_5090 as previews

RESULTS = ROOT / 'operation_planning/results/phase2b_carbon_5090'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def post(base, endpoint, payload):
    request = Request(base + endpoint, data=json.dumps(payload, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'})
    started = time.perf_counter()
    with urlopen(request, timeout=120) as response:
        result = json.load(response)
    return result, time.perf_counter() - started


def main():
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    frozen_path = RESULTS / 'replay_cases_v6.json'
    frozen = json.loads(frozen_path.read_text(encoding='utf-8'))
    start = datetime.now().astimezone().isoformat()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    cases = []
    for case in frozen['cases']:
        result, elapsed = post(base, '/api/operation/hybrid/run', case['request'])
        if result['status'] != 'success':
            raise RuntimeError(result)
        report = result['report']
        actual = comparison._normalized(report, case)
        expected = {key: case[key] for key in actual}
        comparison._canonicalize_frozen_sweep(case, expected)
        mismatches = []; stats = {'fields': 0, 'numeric': 0, 'max_relative_error': 0.0}
        comparison._compare(expected, actual, '$', mismatches, stats)
        cases.append({'case_id': case['case_id'], 'http_elapsed_s': elapsed, 'server_elapsed_ms': report['calculation_timing']['elapsed_ms'], 'pass': not mismatches, 'mismatch_count': len(mismatches), 'first_mismatches': mismatches[:5], **stats})
    # Also measure the complete API with affinity restricted to one CPU.
    single_core = {'measured': False}
    if platform.system() == 'Windows':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        process = kernel.GetCurrentProcess()
        kernel.GetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
        kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        original = ctypes.c_size_t(); system = ctypes.c_size_t()
        if not kernel.GetProcessAffinityMask(process, ctypes.byref(original), ctypes.byref(system)):
            raise ctypes.WinError(ctypes.get_last_error())
        mask = original.value & -original.value
        if not kernel.SetProcessAffinityMask(process, mask):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            result, elapsed = post(base, '/api/operation/hybrid/run', frozen['cases'][0]['request'])
            thermal = dict(frozen['cases'][0]['request']); thermal['max_units'] = 50
            sized, size_elapsed = post(base, '/api/operation/thermal/size', thermal)
            single_core = {'measured': True, 'affinity_mask': hex(mask), 'original_mask': hex(original.value), 'hybrid_http_s': elapsed, 'hybrid_status': result['status'], 'thermal_max_units': 50, 'thermal_http_s': size_elapsed, 'thermal_status': sized['status']}
        finally:
            kernel.SetProcessAffinityMask(process, original.value)
    week_cases = []
    for case in frozen['cases'][:3]:
        for season in ('summer', 'winter'):
            payload = previews._payload(case, season)
            result, elapsed = post(base, '/api/operation/hybrid/preview', payload)
            week_cases.append({'case_id': f"{case['case_id']}_{season}_week", 'tier': case['case_id'], 'season': season, 'source_case_id': case['case_id'], 'source_commit': source, 'request': payload, 'response': result, 'http_elapsed_ms': elapsed * 1000, 'http_status': 200})
    preview_output = {'source_commit': source, 'format_version': 'preview_v7_http_5090', 'endpoint': '/api/operation/hybrid/preview', 'cases': week_cases, 'timing_summary': {'max_http_elapsed_ms': max(c['http_elapsed_ms'] for c in week_cases), 'total_http_elapsed_ms': sum(c['http_elapsed_ms'] for c in week_cases)}}
    for path in (RESULTS / 'replay_previews_v7.json', ROOT / 'docs/handoff/replay_viewer/replay_previews_v7.json'):
        path.write_text(json.dumps(preview_output, ensure_ascii=False, indent=2), encoding='utf-8')
    payload = previews._payload(frozen['cases'][0], 'summer'); payload['preview']['period'] = 'typical_month'
    month, month_elapsed = post(base, '/api/operation/hybrid/preview', payload)
    monthly = {'request': payload, 'response': month, 'http_elapsed_s': month_elapsed, 'source_commit': source}
    (RESULTS / 'preview_month_v7.json').write_text(json.dumps(monthly, ensure_ascii=False, indent=2), encoding='utf-8')
    server.shutdown(); server.server_close()
    environment = {'python': sys.version, 'platform': platform.platform(), 'processor': platform.processor(), 'dependencies': {name: importlib.metadata.version(name) for name in ('pandas', 'numpy', 'pvlib', 'windpowerlib')}}
    gpu = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'], capture_output=True, text=True)
    environment['gpu_name_command'] = 'nvidia-smi --query-gpu=name --format=csv,noheader'; environment['gpu_name_result'] = gpu.stdout.strip()
    outputs = [RESULTS / 'replay_previews_v7.json', RESULTS / 'preview_month_v7.json']
    manifest = {'run_id': 'phase2b-perf-preview-v7-5090', 'source_commit': source, 'source_worktree_status': status, 'machine_role': '5090', 'start': start, 'end': datetime.now().astimezone().isoformat(), 'command': 'python scripts/phase2b_performance_acceptance_5090.py', 'environment': environment, 'frozen_input_sha256': sha(frozen_path), 'cases': cases, 'all_equivalent': all(c['pass'] for c in cases), 'single_core': single_core, 'preview_max_week_http_s': preview_output['timing_summary']['max_http_elapsed_ms']/1000, 'preview_month_http_s': month_elapsed, 'outputs': [{'path': str(path.relative_to(ROOT)), 'sha256': sha(path)} for path in outputs], 'scope': 'cached official weather; real local HTTP calculation and serialization; no model or GPU needed; no laptop measurement claimed'}
    (RESULTS / 'run_manifest_v7_performance.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: manifest[key] for key in ('all_equivalent', 'cases', 'single_core', 'preview_max_week_http_s', 'preview_month_http_s')}, ensure_ascii=False, indent=2))
    return 0 if manifest['all_equivalent'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
