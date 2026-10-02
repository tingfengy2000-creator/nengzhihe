"""One-time freeze; content hashes checked again before and after evaluation."""
from pathlib import Path
import datetime,hashlib,json,platform
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    target=ROOT/'output/frozen.json'
    if target.exists():raise RuntimeError('Already frozen; never overwrite')
    files=['diagnostics.py','policies.py','baseline_v1/engine.py','baseline_v1/data/calibration.json',
           'data/calibration.json','data/policy_config.json','data/split_plan.json','data/dev_seal.json','data/final_seal.json',
           'scripts/evaluate.py','scripts/prepare_round2_data.py','scripts/select_policy.py','scripts/test_diagnostics.py',
           'scripts/test_integration.py','scripts/freeze.py','PROTOCOL.txt']
    out={'frozen_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files_sha256':{p:sha(ROOT/p) for p in files},
         'runtime':platform.python_version(),'final_sensor_values_or_labels_used_for_development':False,
         'preparation_boundary':'Program parsed raw streams and serialized predeclared date blocks; no final value summaries or labels supplied to developers.',
         'development_metrics_not_final':True,'evaluation_rule':'No diagnosis, calibration, policy or metric changes after final evaluation begins.'}
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
