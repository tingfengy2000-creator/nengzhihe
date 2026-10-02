"""Freeze the protocol before the first holdout read. Never overwrites a freeze."""
import hashlib,json,sys,datetime,platform
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import ROOT,EXCLUDED

FROZEN=['engine.py','policies.py','model_client.py','scripts/prepare_engine.py','scripts/run_benchmark.py',
        'scripts/freeze.py','scripts/test_contracts.py','data/calibration.json','data/policy_config.json',
        'data/holdout_seal.json','data/data_contract.json','runtime/local_model_config.json','protocol_draft.json']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=ROOT/'output/protocol_frozen.json'
    if out.exists(): raise SystemExit('A freeze already exists; refusing to overwrite or retune after evaluation.')
    p=json.loads((ROOT/'protocol_draft.json').read_text(encoding='utf-8'))
    p.update(version='round1-frozen-v1',excluded_channels=sorted(EXCLUDED),
      diagnosis='Shared development-calibrated command/temperature response rules; model selects actions only.',
      evaluation_units={'cases':42,'paired_base_day_scenarios':21,'independent_date_blocks':7,'simulated_systems':1},
      shared_stopping='All non-full policies stop at the first supported shared-rule result or insufficient unique fan operation; full policy always reads all 4 groups.',
      decision_threshold='Primary budget 4 versus adaptive rules: either at least 2 more correct cases out of 42 without extra errors or queries, or nonlower accuracy with at least 0.25 fewer mean queries and no extra errors. This pragmatic gate does not establish statistical significance. Always report latency and all budgets.',
      interpretation='42 paired records are not 42 independent buildings. Dates share one simulation system. A full-information result is a reference, not a guaranteed accuracy upper bound.',
      budgets=[2,3,4],seed=20260930,
      initial_free_summary='All policies receive the same precomputed screening summary including supply-setpoint deviation and unique running time; its cost is common and excluded. Acquiring each full evidence group costs one query unit.',
      missing_and_failures='Undefined statistics remain null. Model invalid output is unresolved with actual cost; no fallback substitution.',
      label_opening='Holdout payloads are first read after this freeze; labels are opened only after all predictions have been saved. No parameter or prompt edits afterward.')
    frozen={'frozen_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'protocol':p,
            'files_sha256':{f:sha(ROOT/f) for f in FROZEN},'python':platform.python_version(),
            'holdout_read_before_freeze':False,'note':'This records the workflow and hashes; not a cryptographic proof of analyst blindness.'}
    out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(frozen,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'frozen':str(out),'sha256':sha(out),'at':frozen['frozen_at_utc']},ensure_ascii=False))
if __name__=='__main__': main()
