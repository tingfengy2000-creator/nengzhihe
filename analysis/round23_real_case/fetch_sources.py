"""Bounded read-only source acquisition for calibration eligibility.

No planning API or model is changed or called. Raw third-party files remain
in ignored working/; hashes and provenance are retained for review.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'working/round23/sources'
OUT = ROOT / 'operation_planning/results/round23_case_admission'
URLS = {
    'cu_metadata.json': 'https://api.figshare.com/v2/articles/11726517',
    'madrid_monthly.csv': 'https://datos.madrid.es/dataset/300430-0-consumo-energia-edificios/resource/300430-0-consumo-energia-edificios-csv/download/datos-abiertos_consumo-energia-edificios.csv',
    'madrid_dictionary.pdf': 'https://datos.madrid.es/dataset/300430-0-consumo-energia-edificios/resource/300430-2-consumo-energia-edificios/download/estructura_ds_consumo_energc3ada_edificios_municipales.pdf',
    'cu_paper.pdf': 'https://vtechworks.lib.vt.edu/bitstream/10919/100834/1/s41597-020-00582-3.pdf',
}


def fetch(name, url, limit=110_000_000):
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    if path.exists():
        data = path.read_bytes()
        return {'file': f'working/round23/sources/{name}', 'url': url, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'action': 'existing bytes reused'}
    # External public downloads respect the host's ordinary network settings.
    # Local model loopback handling is unrelated and remains unchanged.
    opener = urllib.request.build_opener()
    request = urllib.request.Request(url, headers={'User-Agent': 'nengzhihe-public-case-audit/1.0'})
    with opener.open(request, timeout=45) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Source exceeds bounded download limit')
        headers = {'content_type': response.headers.get('Content-Type'), 'last_modified': response.headers.get('Last-Modified')}
        # Public redirects may contain temporary signed access parameters.
        # The stable source URL plus byte hash suffice for reproducibility.
        parts = urlsplit(response.url)
        actual_url = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
    path.write_bytes(data)
    return {'file': f'working/round23/sources/{name}', 'url': url, 'resolved_url': actual_url, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'action': 'downloaded', 'downloaded_utc': datetime.now(timezone.utc).isoformat(), **headers}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--metadata-only', action='store_true')
    parser.add_argument('--cu-floor', choices=['1','2'], default='2')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    for name,url in URLS.items():
        if args.metadata_only and name != 'cu_metadata.json':
            continue
        try:
            row = fetch(name,url)
        except Exception as exc:
            row = {'file': name, 'url': url, 'error': str(exc), 'action': 'failed'}
        records.append(row)
        print(json.dumps(row,ensure_ascii=False), flush=True)
    metadata_path = RAW/'cu_metadata.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else None
    if metadata:
        print(json.dumps({'title': metadata['title'], 'version': metadata['version'], 'license': metadata['license'],
                          'files': [{k:v for k,v in f.items() if k in ('id','name','size','download_url','computed_md5')} for f in metadata['files']]},ensure_ascii=False), flush=True)
    if not args.metadata_only and metadata:
        filename = f'2019Floor{args.cu_floor}.csv'
        selected = [f for f in metadata['files'] if f['name'].lower()==filename.lower()]
        if len(selected)!=1:
            raise ValueError('Expected one documented floor/year file; do not guess or download an entire archive')
        row = fetch(filename, selected[0]['download_url'])
        row['license'] = metadata['license']
        row['dataset_version'] = metadata['version']
        row['declared_md5'] = selected[0].get('computed_md5')
        row['actual_md5'] = hashlib.md5((RAW/filename).read_bytes()).hexdigest()
        records.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    manifest_name = 'acquisition_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.json'
    (OUT/manifest_name).write_text(json.dumps({'recorded_utc': datetime.now(timezone.utc).isoformat(), 'sources': records,
                   'scope': 'public-source eligibility, not bill calibration; raw files not committed'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
