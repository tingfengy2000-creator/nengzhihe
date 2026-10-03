"""NISTIR6994 Table2.1, explicit FLEXLAB SZVAV adaptation; not original rules.

No labels, filenames, dates or injection settings are consumed here. APAR detects
rule violations, not uniquely identifiable mechanical causes (report section2.1.2.2).
"""
import numpy as np

DEFAULTS={'control_epsilon':.05,'temperature_floor_c':.5,'sensor_margin_c':.2,
          'fan_rise_c':1.1,'min_temperature_separation_c':3.,'window_minutes':15,
          'violation_fraction':.8,'alarm_minutes':30,'normal_quantile':.99}
COIL={1,7,11,16}; MIX={2,10,18}; SENSOR={26,27}
NAMES={1:'heating temperature rise',2:'minimum outside-air fraction',3:'heating capacity/setpoint',
4:'heating saturation',5:'economizer temperature limit',6:'economizer warmer than return',
7:'closed-coil temperature balance',8:'mechanical cooling below economizer limit',9:'economizer changeover',
10:'full outside-air mixing balance',11:'cooling temperature drop',12:'cooling warmer than return',
13:'full-OA cooling capacity/setpoint',14:'full-OA cooling saturation',15:'minimum-OA changeover',
16:'minimum-OA cooling temperature drop',17:'minimum-OA warmer than return',18:'minimum outside-air fraction',
19:'minimum-OA cooling capacity/setpoint',20:'minimum-OA cooling saturation',21:'three actuators active',
22:'simultaneous heating/cooling commands',23:'heating with economizer command',24:'cooling with partial economizer',
25:'supply setpoint error',26:'mixed air below both inlets',27:'mixed air above both inlets',28:'mode cycling'}

def context(case,p=DEFAULTS):
    s=case['signals'];n=len(case['minute']);t=case['minute'];eps=p['control_epsilon']
    finite=lambda *keys:np.logical_and.reduce([np.isfinite(s[k]) for k in keys])
    # No invented final interval, no credit for a gap/duplicate/nonmonotonic interval.
    dt=np.r_[np.diff(t),0.];cadence=1. if case['profile']=='flexlab_szvav' else 5.
    good=(dt==cadence);duration=np.where(good,dt,0.)
    occupied=(s['OCC']>.5)&(s['FAN']>.05)&finite('OCC','FAN')
    controls=['HC','CC','OAD','RAD','SF']
    validcontrols=finite(*controls)&np.logical_and.reduce([(s[k]>=0)&(s[k]<=1) for k in controls])
    full=(s['OAD']>=1-eps)&(s['RAD']<=eps)
    minimum=(s['OAD']<=.15+eps)&(s['RAD']>=1-eps)
    partial=~(full|minimum)
    heat=s['HC']>eps;cool=s['CC']>eps
    mode=np.full(n,5);mode[heat&~cool&minimum]=1
    mode[~heat&~cool&~minimum]=2
    mode[~heat&cool&full]=3;mode[~heat&cool&minimum]=4
    mode[~occupied|~validcontrols]=0
    # Fifteen minutes after a mode change, occupancy start, or broken time axis.
    stable=np.zeros(n,bool);start=0
    for i in range(n):
        if i==0 or mode[i]!=mode[i-1] or not good[i-1]:start=i
        stable[i]=(mode[i]>0 and t[i]-t[start]>=p['window_minutes'])
    return dict(s=s,n=n,t=t,duration=duration,occupied=occupied,mode=mode,
                stable=stable&good,full=full,minimum=minimum,partial=partial,finite=finite,
                quality={'status':'usable_with_gaps' if np.any(~good[:-1]) or any(np.any(~np.isfinite(v)) for v in s.values()) else 'usable',
                         'invalid_intervals':int(np.sum(~good[:-1])),
                         'missing_by_point':{k:int(np.sum(~np.isfinite(v))) for k,v in s.items()},
                         'declared_interval_minutes':cadence,'actual_interval_minutes':sorted(set(dt[:-1].tolist())),
                         'time_span_minutes':float(t[-1]-t[0]),'occupied_minutes':float(duration[occupied].sum())})

def expressions(case,p=DEFAULTS,fmin=None):
    c=context(case,p);s=c['s'];n=c['n'];m=c['mode'];f=c['finite'];e=p['control_epsilon']
    SA,MA,RA,OA=[s[k] for k in ['SA','MA','RA','OA']];HC,CC=s['HC'],s['CC']
    fan=p['fan_rise_c'];rows={}
    def rule(i,mask,expr,keys,unit='degC'):
        rows[i]={'eligible':mask&c['stable']&f(*keys),'residual':np.asarray(expr)+np.zeros(n),'unit':unit}
    rule(1,m==1,MA+fan-SA,['SA','MA'])
    for i,mode in [(2,1),(18,4)]:
        if fmin is not None:
            with np.errstate(divide='ignore',invalid='ignore'):fraction=(MA-RA)/(OA-RA)
            rule(i,(m==mode)&(abs(OA-RA)>=p['min_temperature_separation_c']),abs(fraction-fmin),['MA','RA','OA'],'fraction')
    rule(3,(m==1)&(HC>=1-e),s['HSP']-SA,['HSP','SA'])
    rule(4,m==1,HC,['HC'],'saturation')
    # Rules5/25 apply to a modulating economizer; a saturated free-cooling
    # command with both valves shut in the dual-setpoint deadband is capacity-limited.
    rule(5,(m==2)&c['partial'],OA-(s['HSP']-fan),['OA','HSP'])
    rule(6,m==2,SA-RA,['SA','RA'])
    rule(7,m==2,abs(SA-fan-MA),['SA','MA'])
    rule(8,m==3,(s['CSP']-fan)-OA,['CSP','OA'])
    rule(9,m==3,OA-(RA-2.),['OA','RA'])
    rule(10,m==3,abs(OA-MA),['OA','MA'])
    rule(11,m==3,SA-MA-fan,['SA','MA'])
    rule(12,m==3,SA-RA,['SA','RA'])
    rule(13,(m==3)&(CC>=1-e),SA-s['CSP'],['SA','CSP'])
    rule(14,m==3,CC,['CC'],'saturation')
    rule(15,m==4,(RA-2.)-OA,['OA','RA'])
    rule(16,m==4,SA-MA-fan,['SA','MA'])
    rule(17,m==4,SA-RA,['SA','RA'])
    rule(19,(m==4)&(CC>=1-e),SA-s['CSP'],['SA','CSP'])
    rule(20,m==4,CC,['CC'],'saturation')
    rule(21,m==5,((HC>e)&(CC>e)&c['partial']).astype(float),['HC','CC','OAD','RAD'],'binary')
    rule(22,m==5,((HC>e)&(CC>e)).astype(float),['HC','CC'],'binary')
    rule(23,m==5,((HC>e)&~c['minimum']).astype(float),['HC','OAD','RAD'],'binary')
    rule(24,m==5,((CC>e)&c['partial']).astype(float),['CC','OAD','RAD'],'binary')
    target=np.where(m==1,s['HSP'],np.where(m==2,s['HSP'],s['CSP']))
    rule(25,(m==1)|(m==3)|(m==4)|((m==2)&c['partial']),abs(SA-target),['SA','HSP','CSP'])
    rule(26,m>0,np.minimum(RA,OA)-MA,['RA','OA','MA'])
    rule(27,m>0,MA-np.maximum(RA,OA),['RA','OA','MA'])
    changes=np.r_[False,m[1:]!=m[:-1]]&(m>0)
    count=np.array([np.sum(changes[(c['t']>tt-60)&(c['t']<=tt)]) for tt in c['t']],float)
    rule(28,m>0,count,['HC','CC','OAD','RAD'],'transitions')
    return c,rows

def calibrate(normal_cases,p=DEFAULTS):
    """One deterministic normal-only pass; no fault-label tuning, no test access."""
    # The SZVAV inventory has no measured airflow/design minimum-OA fraction.
    # A command percentage is not that fraction, so APAR rules 2 and 18 stay
    # disabled rather than inventing a calibration from mixed-air temperature.
    fractions=[]; fmin=None
    pools={};units={}
    for case in normal_cases:
        _,rows=expressions(case,p,fmin)
        for i,r in rows.items():pools.setdefault(i,[]).extend(r['residual'][r['eligible']].tolist());units[i]=r['unit']
    thresholds={};stats={}
    for i,values in pools.items():
        unit=units[i];a=np.asarray(values);q=float(np.quantile(a,p['normal_quantile'])) if len(a) else None
        if unit=='degC':th=max(p['temperature_floor_c'],(q or 0)+p['sensor_margin_c'])
        elif unit=='fraction':th=max(.1,(q or 0)+.05)
        elif unit=='saturation':th=1-p['control_epsilon']
        elif unit=='binary':th=.5
        else:th=max(5.,q or 0)
        thresholds[str(i)]=float(th);stats[str(i)]={'n_normal_minutes':len(a),'normal_q99':q,'unit':unit}
    return {'parameters':dict(p),'fmin':fmin,'fmin_samples':len(fractions),'thresholds':thresholds,'normal_statistics':stats,
            'normal_ids':[c['id'] for c in normal_cases],
            'disabled_rules':{str(i):'minimum outside-air fraction unavailable; fewer than60 eligible normal minutes' for i in [2,18]} if fmin is None else {}}

def windows(c,eligible,bad,p):
    """Fixed nonoverlapping15-minute blocks in each contiguous eligible run.
    Actual observed intervals only. Last unbounded sample has zero credit."""
    hits=[];allwindows=[];run=[];elapsed=0
    for i in range(c['n']):
        if not eligible[i] or c['duration'][i]<=0:run=[];elapsed=0;continue
        run.append(i);elapsed+=c['duration'][i]
        if elapsed>=p['window_minutes']:
            ratio=float(np.average(bad[run],weights=c['duration'][run]));w={'start_minute':float(c['t'][run[0]]),'end_minute':float(c['t'][i]+c['duration'][i]),'minutes':float(elapsed),'violation_fraction':ratio}
            allwindows.append(w)
            if ratio>=p['violation_fraction']:hits.append(w)
            run=[];elapsed=0
    return hits,allwindows

def evaluate(case,cal,method='apar'):
    p=cal['parameters'];c,rows=expressions(case,p,cal['fmin']);s=c['s'];reports={};totalmask=np.zeros(c['n'],bool)
    for i,r in rows.items():
        th=cal['thresholds'][str(i)];mask=r['eligible'];bad=r['residual']>th
        hits,allw=windows(c,mask,bad,p);mins=sum(w['minutes'] for w in hits)
        totalmask|=mask
        reports[str(i)]={'name':NAMES[i],'threshold':th,'unit':r['unit'],'eligible_minutes':float(c['duration'][mask].sum()),
                         'support_minutes':mins,'alarm':mins>=p['alarm_minutes'],'windows':hits}
    alarms=[int(i) for i,r in reports.items() if r['alarm']]
    mix=[i for i in alarms if i in MIX];coil=[i for i in alarms if i in COIL]
    # Minimal verification: can mixing evidence be interpreted without violating
    # its own inlet-temperature bounds? Same rawAPAR reports kept for all methods.
    verification=[];verified_minutes=0.;applicable_minutes=0.
    for i in sorted(MIX&set(rows)):
        r=rows[i];sep=abs(s['OA']-s['RA'])>=p['min_temperature_separation_c']
        plausible=(s['MA']>=np.minimum(s['OA'],s['RA'])-p['sensor_margin_c'])&(s['MA']<=np.maximum(s['OA'],s['RA'])+p['sensor_margin_c'])
        mask=r['eligible']&c['finite']('OA','RA','MA')&sep
        if method!='without_consistency':mask&=plausible
        hits,allw=windows(c,mask,r['residual']>cal['thresholds'][str(i)],p)
        applicable_minutes+=sum(w['minutes'] for w in allw);verified_minutes+=sum(w['minutes'] for w in hits)
        verification.extend(hits)
    detected=bool(alarms)
    # APAR baseline reports a rule-family alarm. The workbench candidate adds
    # the independent inlet-temperature consistency check; its ablation removes
    # only that check while keeping every other input, threshold and window.
    candidate=bool(mix) if method=='apar' else bool(mix) and verified_minutes>=p['alarm_minutes']
    if candidate:state='supported_suspicion'
    elif mix:state='evidence_conflict_or_insufficient_window'
    elif not any(reports.get(str(i),{}).get('eligible_minutes',0)>=p['window_minutes'] for i in MIX):state='operating_condition_not_testable'
    else:state='no_sufficient_mixing_violation'
    # Never reinterpret an absent rule violation as evidence for mechanical health.
    reason=['Control commands are not actual damper position; mixing alarms also admit sensor or return/exhaust-path causes.']
    actions=[{'code':'independent_temperature_check','instruction':'Synchronously recheck OA/RA/MA temperatures in the flagged occupied window; verify sensor placement and mixing uniformity.'},
             {'code':'damper_command_response','instruction':'With site authorization, compare requested OA/RA commands with independent physical stroke/position response; do not use control command as actual feedback.'}]
    if state=='operating_condition_not_testable':actions.insert(0,{'code':'obtain_excitation_window','instruction':'Collect occupied stable mode3/full-OA plus RA-closed commands, |OA-RA| >=3C, at least15min settling and30min verification; or obtain design minimum OA flow for rules2/18.'})
    if c['quality']['status']!='usable':actions.insert(0,{'code':'repair_missing_or_time','instruction':'Recover missing setpoints/measurements or correct source time intervals; preserve unresolved branch until valid data exist.'})
    if any(i in SENSOR for i in alarms):reason.append('At least one APAR inlet mixing bound is violated; prioritize independent sensor/air-path check before naming the damper.')
    return {'id':case['id'],'method':method,'any_fault_detected':detected,'damper_related_suspicion':candidate,
            'exact_fault_localization':'unresolved','healthy_conclusion':False,'judgment_state':state,
            'quality':c['quality'],'apar_alarms':alarms,'coil_balance_suspicion':bool(coil),
            'rules':reports,'verification_support_minutes':verified_minutes,'verification_applicable_minutes':applicable_minutes,
            'apar_applicable_minutes':float(c['duration'][totalmask].sum()),'mode_minutes':{str(k):float(c['duration'][c['mode']==k].sum()) for k in range(6)},
            'limitations':reason,'next_actions':actions,'verification_windows':verification,
            'input_contract':'physical command/sensor allowlist only; labels, injection parameters and date names excluded'}
