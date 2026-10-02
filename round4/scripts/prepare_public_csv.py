"""Retain an unmodified day excerpt from the public raw CSV, not JSON reconstruction."""
from pathlib import Path
import zipfile,io,json,hashlib,argparse
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,required=True,help='Explicit official source ZIP. Runtime demo already includes the raw day excerpt and needs no ZIP.')
src=parser.parse_args().source
expected='8295fcf0f55bc955937cb4ec0198512c28e5ede32e6bbf735257b0df55426471'
with src.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
if actual!=expected:raise ValueError('Source archive hash changed; do not silently substitute a different dataset revision')
day='2018-04-10';dst=ROOT/'data/public_csv'/f'LBNL_SDAHU_{day}_raw_excerpt.csv'
with zipfile.ZipFile(src) as z:
    name=next(n for n in z.namelist() if Path(n).name=='AHU_annual.csv')
    rows=[]
    with z.open(name) as stream:
        header=stream.readline()
        for line in stream:
            if line.startswith(day.encode()):rows.append(line)
            elif rows:break
    dst.write_bytes(header+b''.join(rows))
meta={'source_url':'https://fdddata.lbl.gov/data/Simulated_LBNL_FDD_Data_Sets_SDAHU/LBNL_FDD_Data_Sets_SDAHU.zip',
 'source_member':name,'source_zip_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'source_date':day,
 'excerpt_policy':'Original header and source row bytes kept exactly; date subset only, not a full annual file; all original columns retained. No values transformed.',
 'rows':len(rows),'file':dst.name,'sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'origin':'simulated',
 'role':'Existing development demonstration only; not a new accuracy sample. Source member name stays provenance metadata, never features.',
 'license':'CC BY 4.0; Granderson et al. LBNL FDD datasets'}
(dst.parent/'provenance.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(meta,ensure_ascii=False,indent=2))
