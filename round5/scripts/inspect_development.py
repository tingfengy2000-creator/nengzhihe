"""Bounded schema/physics inspection of only the predeclared development dates."""
from pathlib import Path
import sys,json,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from adapter import physical
cases=physical();out=[]
for c in cases:
 s=c['signals'];occ=s['OCC']>.5
 out.append({'id':c['id'],'rows':len(c['minute']),'occupied_rows':int(occ.sum()),'time_deltas':dict(zip(*[x.tolist() for x in np.unique(np.diff(c['minute']),return_counts=True)])),
 'signals':{k:{'missing':int((~np.isfinite(v)).sum()),'occupied_min':float(np.nanmin(v[occ])),'occupied_median':float(np.nanmedian(v[occ])),'occupied_max':float(np.nanmax(v[occ]))} for k,v in s.items()},
 'full_oa_command_minutes':int(((s['OAD']>=.99)&occ).sum()),'full_oa_and_ra_closed_minutes':int(((s['OAD']>=.99)&(s['RAD']<=.01)&occ).sum()),
 'both_valves_closed_minutes':int(((s['CC']<=.01)&(s['HC']<=.01)&occ).sum())})
(ROOT/'results/development_schema.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
print(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False))
