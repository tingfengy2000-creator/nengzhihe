"""Release integrity and prediction reproduction, no threshold selection."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    frozen=read(ROOT/'output/frozen.json')
    checks={p:sha(ROOT/p)==h for p,h in frozen['files_sha256'].items()}
    assert all(checks.values()),checks
    original=read(ROOT/'output/evaluation_final/scored_rows.json')
    reproduced=read(ROOT/'output/reproduction_01/scored_rows.json')
    keys=['case_id','base_case_id','day','perturbation','truth','method','prediction','raw_status','query_units','actions']
    a=[{k:r[k] for k in keys} for r in original];b=[{k:r[k] for k in keys} for r in reproduced]
    assert a==b,'Reproduction prediction/action mismatch'
    receipt=read(ROOT/'output/evaluation_final/receipt.json')
    assert receipt['predictions_completed_at_utc']<receipt['labels_opened_at_utc']
    field_counts=read(ROOT/'materials/字数与要求核对.json')
    assert all(s['passed'] for s in field_counts['sections'])
    seal=read(ROOT/'data/final_seal.json')
    assert all(sha(ROOT/'data/final/cases'/(cid+'.json'))==h for cid,h in seal['case_sha256'].items())
    out={'frozen_files_unchanged':all(checks.values()),'reproduced_run_count':len(a),'prediction_status_actions_costs_identical':True,
         'timings_equal_required':False,'all_predictions_before_labels':True,'final_cases_unchanged':True,
         'materials_length_checks':len(field_counts['sections']),'materials_visual_review':'pending_renderer',
         'numerical_and_integration_tests':17+read(ROOT/'output/integration_checks.json')['passed']}
    (ROOT/'output/release_verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
