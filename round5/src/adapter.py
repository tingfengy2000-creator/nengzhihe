"""Single physical source; ground truth, dates and injection settings never enter engine."""
from pathlib import Path
from datetime import datetime
import csv,json,hashlib,math
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
FIELDS={
 'SA':'AHU: Supply Air Temperature','HSP':'AHU: Supply Air Temperature Heating Set Point',
 'CSP':'AHU: Supply Air Temperature Cooling Set Point','OA':'AHU: Outdoor Air Temperature',
 'MA':'AHU: Mixed Air Temperature','RA':'AHU: Return Air Temperature',
 'FAN':'AHU: Supply Air Fan Status','SF':'AHU: Supply Air Fan Speed Control Signal',
 'OAD':'AHU: Outdoor Air Damper Control Signal','RAD':'AHU: Return Air Damper Control Signal',
 'EAD':'AHU: Exhaust Air Damper Control Signal','CC':'AHU: Cooling Coil Valve Control Signal',
 'HC':'AHU: Heating Coil Valve Control Signal','OCC':'Occupancy Mode Indicator'}
TEMPS={'SA','HSP','CSP','OA','MA','RA'}
MISSING={'','#VALUE!','#N/A','NA','N/A','NaN','nan'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def physical(split='development',allow_heldout=False):
 protocol=json.loads((ROOT/'protocol/external_split.json').read_text(encoding='utf8'))
 if split!='development':
  if not allow_heldout:raise ValueError('Heldout access requires frozen evaluation entry point')
  freeze=json.loads((ROOT/'protocol/frozen_methods.json').read_text(encoding='utf8'))
  for f,h in freeze['sha256'].items():assert sha(ROOT/f)==h, f
 raw=ROOT/'data/raw/SZVAV.csv';assert sha(raw)==protocol['source_sha256']
 labels={v['date']:(cid,v) for cid,v in protocol['labels'].items() if v['split']==split}
 groups={date:{'id':cid,'profile':'flexlab_szvav','minute':[],'signals':{k:[] for k in FIELDS}} for date,(cid,l) in labels.items()}
 with raw.open(encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f);reader.fieldnames=[s.strip() for s in reader.fieldnames]
  assert set(FIELDS.values()).issubset(reader.fieldnames)
  for row in reader:
   dt=datetime.strptime(row['Datetime'],'%m/%d/%Y %H:%M');date=dt.date().isoformat()
   if date not in groups:continue  # Never parse heldout sensor/control values during development.
   target=groups[date];target['minute'].append(dt.hour*60+dt.minute)
   for k,col in FIELDS.items():
    text=row[col].strip();v=float('nan') if text in MISSING else float(text)
    target['signals'][k].append((v-32)*5/9 if k in TEMPS else v)
 for case in groups.values():
  case['minute']=np.asarray(case['minute'],dtype=float)
  case['signals']={k:np.asarray(v,dtype=float) for k,v in case['signals'].items()}
 return list(groups.values())
def legacy():
 """All old112 are regression only. No source setting/file name in engine payload."""
 base=ROOT.parent/'round4/data/regression';labels=json.loads((base/'labels.json').read_text(encoding='utf8'))
 mapping={'SA':'SA_TEMP','HSP':'SA_TEMPSPT','CSP':'SA_TEMPSPT','OA':'OA_TEMP','MA':'MA_TEMP','RA':'RA_TEMP','FAN':'SF_SPD_DM','SF':'SF_CS','OAD':'OA_DMPR_DM','RAD':'RA_DMPR_DM','CC':'CHWC_VLV_DM'}
 cases=[]
 for cid,label in sorted(labels.items()):
  if label['perturbation']!='none':continue
  c=json.loads((base/'cases'/(cid+'.json')).read_text(encoding='utf8'));n=len(c['timestamps'])
  s={k:np.asarray(c['series'].get(col,[float('nan')]*n),dtype=float) for k,col in mapping.items()}
  # Heating coil absent in documented simulated SDAHU, not inferred from a missing measurement.
  s['HC']=np.zeros(n);s['EAD']=np.full(n,np.nan);s['OCC']=s['FAN'].copy()
  cases.append({'id':cid,'profile':'simulated_sdahu','minute':np.array([datetime.fromisoformat(t).hour*60+datetime.fromisoformat(t).minute for t in c['timestamps']],float),'signals':s})
 return cases
