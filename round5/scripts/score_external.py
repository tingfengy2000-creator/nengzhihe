"""Score physical results after inference, keeping truth out of the adapter/engine."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
def main():
    split=json.loads((ROOT/'protocol/external_split.json').read_text(encoding='utf8'))
    truth={v['id'] if 'id' in v else cid:v for cid,v in split['labels'].items()}
    # labels keyed by opaque id in protocol; tolerate date-only keys in future snapshots
    truth={cid:v for cid,v in split['labels'].items()}
    rows=json.loads((ROOT/'results/apar_physical_case_results.json').read_text(encoding='utf8'))
    out=[]
    for r in rows:
        t=truth[r['id']]; cls='normal' if t['subsystem']=='normal' else t['subsystem']
        isfault=cls!='normal'; damper=cls=='outdoor_damper'
        suspect=bool(r['damper_related_suspicion']); anydet=bool(r['any_fault_detected'])
        # A positive APAR rule is detection; mapping it to a unique damper is a
        # separate, deliberately strict attribution claim.
        out.append({**r,'truth_class':cls,'truth_fault':isfault,
                    'fault_detection_outcome':'TP' if anydet and isfault else 'FP' if anydet else 'TN' if not isfault else 'FN',
                    'damper_suspicion_outcome':'correct_damper_suspicion' if suspect and damper else 'false_damper_attribution' if suspect and not damper else 'miss_or_unresolved',
                    'resolved_for_coverage':r['judgment_state']=='supported_suspicion'})
    summary={'source':'FLEXLAB SZVAV, labels joined only after engine evaluation', 'rows':len(out), 'methods':{}}
    for method in sorted({r['method'] for r in out}):
        q=[r for r in out if r['method']==method]
        cm={}
        for cls in ['normal','outdoor_damper','heating_coil','cooling_coil']:
            z=[r for r in q if r['truth_class']==cls]
            cm[cls]={'n':len(z),'fault_detection':sum(r['fault_detection_outcome'] in {'TP','TN'} for r in z),'damper_suspicion':sum(r['damper_suspicion_outcome']=='correct_damper_suspicion' for r in z),'false_damper_attribution':sum(r['damper_suspicion_outcome']=='false_damper_attribution' for r in z),'resolved':sum(r['resolved_for_coverage'] for r in z)}
        summary['methods'][method]={'all':{'n':len(q),'correct_fault_detection':sum(r['fault_detection_outcome'] in {'TP','TN'} for r in q),'false_alarm':sum(r['fault_detection_outcome']=='FP' for r in q),'miss':sum(r['fault_detection_outcome']=='FN' for r in q),'coverage':sum(r['resolved_for_coverage'] for r in q),'damper_correct':sum(r['damper_suspicion_outcome']=='correct_damper_suspicion' for r in q),'false_damper_attribution':sum(r['damper_suspicion_outcome']=='false_damper_attribution' for r in q)},'by_class':cm}
        for group in ['development','holdout']:
            ids=set(split[group+'_dates']);qg=[r for r in q if truth[r['id']]['date'] in ids]
            summary['methods'][method][group]={'n':len(qg),'correct_fault_detection':sum(r['fault_detection_outcome'] in {'TP','TN'} for r in qg),'false_alarm':sum(r['fault_detection_outcome']=='FP' for r in qg),'miss':sum(r['fault_detection_outcome']=='FN' for r in qg),'coverage':sum(r['resolved_for_coverage'] for r in qg),'false_damper_attribution':sum(r['damper_suspicion_outcome']=='false_damper_attribution' for r in qg)}
    (ROOT/'results/external_metrics.json').write_text(json.dumps({'summary':summary,'records':out},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
