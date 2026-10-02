"""Download official sources and prepare strictly separated, anonymized cases.

Run with --download first. Preparation code follows after source verification.
"""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, pathlib, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
SOURCES = {
    'electricity.csv': 'https://media.githubusercontent.com/media/buds-lab/building-data-genome-project-2/master/data/meters/raw/electricity.csv',
    'lbnl_sdahu.zip': 'https://fdddata.lbl.gov/data/Simulated_LBNL_FDD_Data_Sets_SDAHU/LBNL_FDD_Data_Sets_SDAHU.zip',
    'lbnl_sdahu.pdf': 'https://fdddata.lbl.gov/data/Simulated_LBNL_FDD_Data_Sets_SDAHU/LBNL_FDD_Data_Sets_SDAHU.pdf',
    'bdg2_README.md': 'https://raw.githubusercontent.com/buds-lab/building-data-genome-project-2/master/README.md',
    'bdg2_LICENSE': 'https://raw.githubusercontent.com/buds-lab/building-data-genome-project-2/master/LICENSE',
    'metadata.csv': 'https://media.githubusercontent.com/media/buds-lab/building-data-genome-project-2/master/data/metadata/metadata.csv',
    'weather.csv': 'https://media.githubusercontent.com/media/buds-lab/building-data-genome-project-2/master/data/weather/weather.csv',
    'lbnl_figshare_metadata.json': 'https://api.figshare.com/v2/articles/22338283',
    'electricity.csv.lfs_pointer': 'https://raw.githubusercontent.com/buds-lab/building-data-genome-project-2/master/data/meters/raw/electricity.csv',
    'metadata.csv.lfs_pointer': 'https://raw.githubusercontent.com/buds-lab/building-data-genome-project-2/master/data/metadata/metadata.csv',
    'weather.csv.lfs_pointer': 'https://raw.githubusercontent.com/buds-lab/building-data-genome-project-2/master/data/weather/weather.csv',
}

def range_download(name, url):
    target = RAW / name
    if target.exists() and target.stat().st_size > 1000:
        return download(name, url)
    probe = urllib.request.urlopen(urllib.request.Request(url, headers={'Range': 'bytes=0-0'}), timeout=120)
    if probe.status != 206:
        probe.close()
        return download(name, url)
    total = int(probe.headers['Content-Range'].split('/')[-1]); probe.close()
    partial = target.with_suffix(target.suffix + '.part')
    start = partial.stat().st_size if partial.exists() else 0
    chunkdir = RAW / (name + '.chunks'); chunkdir.mkdir(exist_ok=True)
    spans = [(s, min(s + 1024*1024, total)-1) for s in range(start, total, 1024*1024)]
    def fetch(span):
        a,b=span; dest=chunkdir/str(a)
        if dest.exists() and dest.stat().st_size == b-a+1: return
        for attempt in range(4):
            try:
                req=urllib.request.Request(url, headers={'Range': f'bytes={a}-{b}'})
                with urllib.request.urlopen(req,timeout=120) as res:
                    content=res.read()
                    expected_range=f'bytes {a}-{b}/{total}'
                    if res.status != 206 or len(content) != b-a+1 or res.headers.get('Content-Range') != expected_range:
                        raise RuntimeError('Range mismatch')
                dest.write_bytes(content); return
            except Exception:
                if attempt == 3: raise
                time.sleep(2+attempt)
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        for i,_ in enumerate(pool.map(fetch,spans),1):
            if i%10==0: print(f'RANGES {name}: {i}/{len(spans)}',flush=True)
    with partial.open('ab') as out:
        for a,b in spans:
            out.write((chunkdir/str(a)).read_bytes())
    assert partial.stat().st_size == total
    partial.replace(target)
    return download(name,url)

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def download(name, url):
    RAW.mkdir(parents=True, exist_ok=True)
    target = RAW / name
    if target.exists() and target.stat().st_size > 100:
        print(f'CACHE {name}: {target.stat().st_size}', flush=True)
    else:
        partial = target.with_suffix(target.suffix + '.part')
        request = urllib.request.Request(url, headers={'User-Agent': 'Nengzhihe-research/0.1'})
        with urllib.request.urlopen(request, timeout=120) as source, open(partial, 'wb') as dest:
            count = 0
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                dest.write(chunk)
                count += len(chunk)
                if count % (32 * 1024 * 1024) == 0:
                    print(f'DOWNLOAD {name}: {count // (1024*1024)} MiB', flush=True)
        partial.replace(target)
        print(f'DOWNLOADED {name}: {target.stat().st_size}', flush=True)
    return {'filename': name, 'url': url, 'bytes': target.stat().st_size,
            'sha256': sha(target), 'retrieved_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}

def download_all():
    manifest = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(range_download if n in ('electricity.csv','lbnl_sdahu.zip','weather.csv') else download, n, u): n for n, u in SOURCES.items()}
        for job in concurrent.futures.as_completed(jobs):
            try:
                manifest.append(job.result())
            except Exception as e:
                manifest.append({'filename': jobs[job], 'error': str(e)})
                print(f'ERROR {jobs[job]}: {e}', flush=True)
    (ROOT / 'data' / 'source_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    if any('error' in entry for entry in manifest):
        raise RuntimeError('One or more official sources failed; inspect data/source_manifest.json')

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

BASIC = ['SA_TEMP','SA_TEMPSPT','OA_TEMP','MA_TEMP','RA_TEMP','SF_SPD_DM',
         'RF_SPD_DM','SF_CS','RF_CS','OA_DMPR_DM','RA_DMPR_DM','CHWC_VLV_DM'] + [f'ZONE_TEMP_{i}' for i in range(1,6)]
TEMP = [k for k in BASIC if 'TEMP' in k]
LBNL_FILES = {'AHU_annual.csv': ('normal', None),
              'damper_stuck_025_annual.csv': ('damper_stuck', 0.25),
              'damper_stuck_075_annual.csv': ('damper_stuck', 0.75),
              'coi_leakage_025_annual.csv': ('coil_leakage', 0.25)}

def make_id(family, source, day, perturbation):
    key=f'nengzhihe-v1|{family}|{source}|{day}|{perturbation}'
    return 'NZH-' + hashlib.sha256(key.encode()).hexdigest()[:12].upper()

def lbnl_frame(filename):
    import pandas as pd, zipfile
    archive=RAW/'lbnl_sdahu.zip'
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            name=next(n for n in z.namelist() if pathlib.Path(n).name==filename)
            with z.open(name) as stream:
                frame=pd.read_csv(stream,usecols=['Datetime']+BASIC)
    else:
        frame=pd.read_csv(RAW/(pathlib.Path(filename).stem+'_prefix.csv'),usecols=['Datetime']+BASIC)
    frame['Datetime']=pd.to_datetime(frame['Datetime'])
    for key in TEMP: frame[key]=(frame[key]-32)*5/9
    return frame

def lbnl_case(frame, filename, day, split, polluted=False):
    import pandas as pd
    import numpy as np
    # A full day preserves start-up, occupied and unoccupied behavior.
    selected=frame[(frame.Datetime>=day)&(frame.Datetime<pd.Timestamp(day)+pd.Timedelta(days=1))].copy()
    selected=selected.set_index('Datetime').resample('5min').mean().reset_index()
    if len(selected)!=288: raise ValueError(f'Incomplete day {filename} {day}: {len(selected)}')
    # Uniform deterministic perturbation applied identically to every holdout scenario.
    if polluted:
        selected=pd.concat([selected,selected.iloc[108:120]],ignore_index=True).sort_values('Datetime',kind='stable').reset_index(drop=True)
    perturbation='duplicate_records_12' if polluted else 'none'
    case_id=make_id('lbnl',filename,day,perturbation)
    obj={'id':case_id,'split':split,'family':'lbnl','origin':'simulated',
         'source_ref':'lbnl_sdahu_2022','title':'仿真设备核验案例',
         'description':'LBNL公开单风道空调机组仿真；设备标签仅用于评测。',
         'perturbation':{'type':perturbation,'origin':'human_generated' if polluted else 'none',
            'description':'人为插入12条完全重复记录；设备运行曲线未改变。修复仅去重，不消除设备疑点。' if polluted else '无额外人为扰动。'},
         'timestamps':selected.Datetime.dt.strftime('%Y-%m-%dT%H:%M:%S').tolist(),
         'series':{k:[None if not np.isfinite(float(v)) else round(float(v),5) for v in selected[k]] for k in BASIC},
         'units':{k:'degC' if k in TEMP else ('binary' if k.endswith('_SPD_DM') else 'fraction') for k in BASIC},
         'sample_interval_minutes':5,'timezone':'source naive simulation clock; no UTC conversion',
         'evidence_scope':'Basic BAS points only; actual positions, flows, powers, SYS_CTL and inconsistent static pressure excluded',
         'attribution':'Granderson et al., LBNL FDD datasets, SDAHU; CC BY 4.0; temperature converted F to C; 5-minute mean resampling.'}
    label,severity=LBNL_FILES[filename]
    private={'id':case_id,'target':label,'label':label,'fault_class':label,
             'severity':None if label=='coil_leakage' else severity,
             'source_declared_severity':severity,
             'severity_verified':label!='coil_leakage',
             'source_file':filename,'day':day,'base_case_id':make_id('lbnl',filename,day,'none'),
             'perturbation':perturbation,'source_origin':'simulated',
             'group':f'single_simulated_system|{day}','is_actual_building_fault_evidence':False}
    return obj,private

def prepare_lbnl(include_holdout=False):
    import pandas as pd
    index=[]; dev_labels={}; demo_labels={}; holdout_labels={}; holdout_index=[]
    dates={'dev':[f'2018-04-{d:02d}' for d in range(2,6)],'demo':['2018-04-10'],
           'holdout':[f'2018-04-{d:02d}' for d in range(16,23)]}
    for name in LBNL_FILES:
        # This held-out severity is never read for development preparation.
        if '075' in name and not include_holdout: continue
        frame=lbnl_frame(name)
        for split in ('dev','demo','holdout'):
            if split=='holdout' and not include_holdout: continue
            if split=='holdout' and '025' in name and 'damper' in name: continue
            if split!='holdout' and '075' in name: continue
            if split=='demo' and name not in ('AHU_annual.csv','damper_stuck_025_annual.csv'): continue
            for day in dates[split]:
                pollution=[False,True] if split=='holdout' else [split=='demo' and 'damper' in name]
                for polluted in pollution:
                    obj,label=lbnl_case(frame,name,day,split,polluted)
                    case_dir=ROOT/'data'/('private/holdout_cases' if split=='holdout' else 'cases')
                    write_json(case_dir/(obj['id']+'.json'),obj)
                    entry={k:obj[k] for k in ('id','split','family','origin','title','description','perturbation')}
                    entry['path']=str((case_dir/(obj['id']+'.json')).relative_to(ROOT)).replace('\\','/')
                    if split=='holdout':
                        holdout_index.append(entry); holdout_labels[obj['id']]=label
                    else:
                        index.append(entry)
                        (dev_labels if split=='dev' else demo_labels)[obj['id']]=label
    write_json(ROOT/'data/private/dev_labels.json',dev_labels)
    write_json(ROOT/'data/private/demo_labels.json',demo_labels)
    if include_holdout:
        write_json(ROOT/'data/private/holdout_index.json',holdout_index)
        write_json(ROOT/'data/private/holdout_labels.json',holdout_labels)
        hashes={e['id']:sha(ROOT/e['path']) for e in holdout_index}
        write_json(ROOT/'data/holdout_seal.json',{'case_count':len(hashes),'base_day_scenarios':21,
            'independent_day_blocks':7,'simulated_systems':1,'date_block':['2018-04-16','2018-04-22'],
            'cases_sha256':hashes,'labels_sha256':sha(ROOT/'data/private/holdout_labels.json'),
            'note':'Cases and labels sealed from diagnostic development. Frozen evaluation only. Paired variants are not independent samples.'})
    return index

def prepare_bdg2():
    import pandas as pd
    import numpy as np
    names=['Panther_education_Misty','Panther_education_Gina','Panther_office_Karla']
    meter=pd.read_csv(RAW/'electricity.csv',usecols=['timestamp']+names)
    meter['timestamp']=pd.to_datetime(meter.timestamp)
    weather=pd.read_csv(RAW/'weather.csv',usecols=['timestamp','site_id','airTemperature'])
    weather=weather[weather.site_id=='Panther'].copy(); weather['timestamp']=pd.to_datetime(weather.timestamp)
    metadata=pd.read_csv(RAW/'metadata.csv').set_index('building_id')
    index=[]; mapping={}
    for j,name in enumerate(names):
        selected=meter[(meter.timestamp>='2017-05-08')&(meter.timestamp<'2017-06-12')][['timestamp',name]]
        selected=selected.merge(weather[['timestamp','airTemperature']],on='timestamp',how='left',validate='one_to_one')
        selected=selected.rename(columns={name:'electricity_kwh','airTemperature':'OA_TEMP'})
        history=selected[selected.timestamp<'2017-06-05'].copy()
        history['weekday']=history.timestamp.dt.dayofweek;history['hour']=history.timestamp.dt.hour
        reference=history.groupby(['weekday','hour']).electricity_kwh.median()
        selected['reference_kwh']=[reference.get((t.dayofweek,t.hour),np.nan) for t in selected.timestamp]
        obj={'id':make_id('bdg2',name,'2017-06-05','none'),'split':'demo' if j==0 else 'dev',
             'family':'bdg2','origin':'measured','source_ref':'bdg2_v2',
             'title':f'公开建筑回放 {j+1:02d}','description':'BDG2公开建筑电表与站点天气，仅支持异常候选筛查，无真实设备故障标签。',
             'perturbation':{'type':'none','origin':'none','description':'无额外人为扰动；保留原始缺测。'},
             'timestamps':selected.timestamp.dt.strftime('%Y-%m-%dT%H:%M:%S').tolist(),
             'series':{k:[None if not np.isfinite(float(v)) else round(float(v),5) for v in selected[k]] for k in ('electricity_kwh','OA_TEMP','reference_kwh')},
             'units':{'electricity_kwh':'kWh per hour','reference_kwh':'kWh per hour','OA_TEMP':'degC'},
             'analysis_start':'2017-06-05T00:00:00','analysis_end':'2017-06-12T00:00:00',
             'baseline_period':['2017-05-08','2017-06-04'],'baseline_method':'Past 4 weeks median for matching weekday/hour; descriptive reference, not a calibrated prediction interval.',
             'building_context':{'use':str(metadata.loc[name,'primaryspaceusage']),'area_m2':float(metadata.loc[name,'sqm']),
                                 'timezone':str(metadata.loc[name,'timezone'])},
             'sample_interval_minutes':60,
             'evidence_scope':'Measured meter and weather replay only; no equipment point linkage to LBNL.',
             'attribution':'Miller et al. (2020), Building Data Genome Project 2, DOI 10.1038/s41597-020-00712-x; CC BY-SA 4.0.'}
        write_json(ROOT/'data/cases'/(obj['id']+'.json'),obj)
        entry={k:obj[k] for k in ('id','split','family','origin','title','description','perturbation')}
        entry['path']='data/cases/'+obj['id']+'.json'; index.append(entry)
        mapping[obj['id']]={'building_id':name,'site_id':'Panther','origin':'measured','fault_label':None}
    write_json(ROOT/'data/private/bdg2_mapping.json',mapping)
    return index

def verify_bdg_lfs():
    report=[]
    for name in ('electricity.csv','metadata.csv','weather.csv'):
        pointer=RAW/(name+'.lfs_pointer')
        expected=next(line.split('sha256:')[1] for line in pointer.read_text().splitlines() if line.startswith('oid sha256:'))
        actual=sha(RAW/name)
        if actual!=expected: raise ValueError(f'Official LFS digest mismatch: {name}')
        report.append({'filename':name,'sha256':actual,'matches_official_lfs_oid':True,'pointer_source':SOURCES[name+'.lfs_pointer']})
    write_json(ROOT/'data/private/bdg2_integrity.json',report)

def audit_sources():
    import zipfile, io, struct, zlib
    archive=RAW/'lbnl_sdahu.zip'
    audits=[]
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            for x in z.infolist():
                if 'coi_leakage_' not in x.filename: continue
                h=hashlib.sha256()
                with z.open(x) as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''): h.update(chunk)
                audits.append({'source_file':x.filename,'bytes':x.file_size,'crc32':x.CRC,'sha256':h.hexdigest()})
    else:
        # During an interrupted transfer, complete early members can still be
        # audited against the official central directory. Never accept a partial member.
        partial=RAW/'lbnl_sdahu.zip.part'; tailpath=ROOT/'data/private/zip_tail.bin'
        if not partial.exists() or not tailpath.exists(): return
        tail=tailpath.read_bytes(); total=607666899
        with zipfile.ZipFile(io.BytesIO(tail)) as z, partial.open('rb') as stream:
            for x in z.infolist():
                if 'coi_leakage_' not in x.filename: continue
                start=x.header_offset+total-len(tail)
                stream.seek(start); header=stream.read(30)
                fields=struct.unpack('<4s5H3I2H',header)
                assert fields[0]==b'PK\x03\x04'
                start+=30+fields[-2]+fields[-1]
                if start+x.compress_size>partial.stat().st_size: return
                stream.seek(start); dec=zlib.decompressobj(-15); h=hashlib.sha256(); crc=0; size=0; remaining=x.compress_size
                while remaining:
                    raw=stream.read(min(1024*1024,remaining)); remaining-=len(raw)
                    block=dec.decompress(raw); h.update(block); crc=zlib.crc32(block,crc); size+=len(block)
                block=dec.flush(); h.update(block); crc=zlib.crc32(block,crc); size+=len(block)
                assert size==x.file_size and crc==x.CRC and dec.eof
                audits.append({'source_file':x.filename,'bytes':size,'crc32':crc,'sha256':h.hexdigest()})
    if audits:
        write_json(ROOT/'data/private/source_audit.json',{
            'leakage_members':audits,'leakage_unique_content_hashes':len(set(x['sha256'] for x in audits)),
            'exclusions':{
              'OA_DMPR/RA_DMPR/CHWC_VLV':'Actual positions overlap the documented fault injection controls; disallowed diagnostic evidence.',
              'OA_CFM/RA_CFM/SA_CFM/SF_WAT/RF_WAT/SF_SPD/RF_SPD/SYS_CTL':'Non-basic points excluded uniformly.',
              'SA_SP/SA_SPSPT':'Document reports inches H2O for both; inspected source values approximately 402 vs 1.607 suggest unit inconsistency. No inferred conversion or quantitative use.'},
            'decision':'Use only coi_leakage_025 as representative; no leakage severity generalization claim.'})

def prepare(include_holdout=False):
    verify_bdg_lfs()
    old_index=json.loads((ROOT/'data/index.json').read_text(encoding='utf-8')) if (ROOT/'data/index.json').exists() else []
    index=prepare_lbnl(include_holdout)+prepare_bdg2()
    write_json(ROOT/'data/index.json',index)
    live_ids={entry['id'] for entry in index}
    for entry in old_index:
        if entry['id'] not in live_ids:
            stale=(ROOT/'data/cases'/(entry['id']+'.json')).resolve()
            assert stale.parent==(ROOT/'data/cases').resolve()
            if stale.exists(): stale.unlink()
    if include_holdout: audit_sources()
    write_json(ROOT/'data/data_contract.json',{
        'schema_version':'1.0','allowed_lbnl_channels':BASIC,'temperature_conversion':'(F-32)*5/9',
        'sampling':'LBNL 5-minute mean; BDG2 source hourly unchanged',
        'splits':{'dev':['2018-04-02','2018-04-05'],'demo':['2018-04-10'],'holdout':['2018-04-16','2018-04-22']},
        'isolation':'Every source scenario on the same calendar day has the same split. All perturbations preserve base split. No holdout content used for development.',
        'privacy':'Source fault filenames, classes, severities are in data/private only; no diagnostic route exposes them.',
        'costs':'Existing archived-data queries only. No on-site acquisition was performed; field collection cost is unmeasured and must be reported separately.',
        'licenses':{'BDG2':'CC BY-SA 4.0 per repository LICENSE','LBNL SDAHU':'CC BY 4.0 per official Figshare article 22338283 metadata'},
        'limitations':['One simulated HVAC system and one held-out calendar week.','Repeated leakage severity files are deduplicated; paired perturbations are not independent samples.','BDG2 replay has no equipment fault ground truth.','No measured savings, field deployment or real building equipment localization has been established.']})
    print('PREPARED public cases:',len(index),'holdout sealed:',include_holdout,flush=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--download', action='store_true')
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--include-holdout', action='store_true')
    args = p.parse_args()
    if args.download:
        download_all()
    if args.prepare:
        prepare(args.include_holdout)
