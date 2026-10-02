"""Frozen engineering comparators, not newly validated diagnostic algorithms."""
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import diagnostics as d
from policies import run_case

def predict(case, method):
    if method=='workbench':
        r=run_case(case,'full_information',4,save=False)
        return {'prediction':'damper_suspicion' if r['final']['label']=='damper_stuck' else 'unresolved',
                'legacy_label':r['final']['label'],'quality':r['final']['quality']['status']}
    v,cmd,mix,valid=d.raw_air(case)
    if not v['quality']['valid_for_diagnosis']:
        return {'prediction':'unresolved','quality':v['quality']['status'],'reason':'invalid quality'}
    if method=='fixed_threshold':
        # End-condition temperature heuristic, without treating command as position.
        s=v['s'];oa,ra,ma=[s(k) for k in ['OA_TEMP','RA_TEMP','MA_TEMP']]
        applicable=valid&((cmd<=.15)|(cmd>=.95))
        mismatch=((cmd<=.15)&(np.abs(ma-ra)>2.0))|((cmd>=.95)&(np.abs(ma-oa)>2.0))
        windows=d._windows(v,applicable,{'command':cmd})
        minutes=sum(w['minutes'] for w in windows if mismatch[w['_indices']].mean()>=.80)
    elif method=='without_contiguity':
        # Same quality, stable-mode gates, calibrated bins and sample thresholds.
        # Only temporal aggregation differs: count isolated mismatching samples.
        bounds=d.load_calibration()['air_envelope'];bad=[]
        for i in np.flatnonzero(valid):
            ref=bounds.get(str(d._bin(cmd[i],d.GATES['command_bin_width'])))
            if ref and not ref['low']<=mix[i]<=ref['high']:bad.append(i)
        minutes=len(bad)*5
    else:raise ValueError('Unknown method')
    context=d.extract(case,'operating_context')['features']['context_qualified']
    return {'prediction':'damper_suspicion' if minutes>=60 and context else 'unresolved',
            'quality':v['quality']['status'],'support_minutes':minutes,
            'reason':'absence of a trigger is unresolved, never proof of healthy equipment'}
