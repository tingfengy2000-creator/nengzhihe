"""Public-only, bounded acquisition. Raw files stay ignored; no product changes."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json, sys, urllib.request
from urllib.parse import urlencode
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'working/round24/sources'
OUT = ROOT / 'operation_planning/results/round24_public_validation'
SITES = {
    'hyderabad_2019': (17.385, 78.4867, 'Asia/Kolkata', '2019-05-10', '2019-05-29'),
    'bangkok_2019': (13.7563, 100.5018, 'Asia/Bangkok', '2019-01-01', '2020-01-01'),
    # UTC acquisition avoids ambiguous/absent local DST hours; analysis converts
    # each real instant to Europe/Madrid. No synthetic 8760-hour local year.
    'madrid_2024': (40.4168, -3.7038, 'UTC', '2023-12-31', '2025-01-01'),
}
VARIABLES = ['temperature_2m', 'relative_humidity_2m', 'surface_pressure', 'shortwave_radiation']

def fetch(name, url, limit=10_000_000):
    p=RAW/name
    action='reused' if p.exists() else 'downloaded'
    if not p.exists():
        req=urllib.request.Request(url, headers={'User-Agent':'nengzhihe-public-validation/1.0'})
        with urllib.request.urlopen(req,timeout=60) as response: b=response.read(limit+1)
        if len(b)>limit: raise ValueError('Bounded download limit exceeded')
        p.write_bytes(b)
    b=p.read_bytes()
    return {'file':p.relative_to(ROOT).as_posix(),'url':url,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'action':action}

def main():
    RAW.mkdir(parents=True,exist_ok=True); OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    rows.append(fetch('hyderabad_metadata.json','https://api.figshare.com/v2/articles/16869439'))
    meta=json.loads((RAW/'hyderabad_metadata.json').read_text(encoding='utf-8'))
    if meta['license']['name']!='CC0': raise ValueError('Review changed licence before data download')
    f=next(f for f in meta['files'] if f['name']=='dataset.zip')
    row=fetch('dataset.zip',f['download_url']); row.update(license=meta['license'],version=meta['version'])
    if hashlib.md5((RAW/'dataset.zip').read_bytes()).hexdigest()!=f['computed_md5']: raise ValueError('Publisher MD5 mismatch')
    rows.append(row)
    for site,(lat,lon,tz,start,end) in SITES.items():
        params=dict(latitude=lat,longitude=lon,timezone=tz,start_date=start,end_date=end,
                    models='era5',hourly=','.join(VARIABLES))
        row=fetch(site+'_weather.json','https://archive-api.open-meteo.com/v1/archive?'+urlencode(params))
        row.update(request_parameters=params,license='CC BY 4.0; Open-Meteo attribution required',
                   scope='ERA5 city reference reanalysis, not on-site measured weather')
        rows.append(row); print(json.dumps(row,ensure_ascii=False),flush=True)
    for name in ['2019Floor2.csv','madrid_monthly.csv','cu_metadata.json','madrid_dictionary.pdf','cu_paper.pdf']:
        p=ROOT/'working/round23/sources'/name
        if not p.exists(): raise FileNotFoundError('Run analysis/round23_real_case/fetch_sources.py for '+name)
        b=p.read_bytes(); rows.append({'file':p.relative_to(ROOT).as_posix(),'bytes':len(b),
          'sha256':hashlib.sha256(b).hexdigest(),'action':'reused exact round23 downloaded bytes'})
    manifest={'recorded_utc':datetime.now(timezone.utc).isoformat(),'sources':rows,
              'prior_failed_attempt':'Sandbox socket WinError10013; public download rerun with normal authorised network access',
              'raw_data_committed':False}
    p=OUT/'source_manifest.json'
    if p.exists() and json.loads(p.read_text(encoding='utf-8'))['sources']!=rows:
        raise RuntimeError('Preserve previous manifest; use a new output directory for a different acquisition')
    if not p.exists(): p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__': main()
