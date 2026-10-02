"""Development/regression-only calibration and contract tests. No final data reads."""
import collections,copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT.parent
sys.path.insert(0,str(ROOT))
import diagnostics as d
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def all_obs(case):return {a:d.extract(case,a) for a in d.ACTIONS}
def main():
 labels=read(ROOT/'data/dev/labels.json');cases={e['id']:read(ROOT/e['path']) for e in read(ROOT/'data/dev/index.json')}
 oldlabs=read(OLD/'data/private/dev_labels.json')
 normals=[c for cid,c in cases.items() if labels[cid]['label']=='normal' and labels[cid]['perturbation']=='none']
 for cid,l in oldlabs.items():
  if l['label']=='normal':normals.append(read(OLD/'data/cases'/f'{cid}.json'))
 leaks=[c for cid,c in cases.items() if labels[cid]['label']=='coil_leakage' and labels[cid]['perturbation']=='none']
 cfg=d.calibrate(normals,leaks)
 print('Calibration normal cases',len(normals),'airbins',len(cfg['air_envelope']),'coilbins',len(cfg['coil_envelope']))
 output=[]
 for cid,case in cases.items():
  pred=d.diagnose(all_obs(case));output.append({'case_id':cid,'day':labels[cid]['day'],'truth':labels[cid]['label'],'prediction':pred['label'],'evidence':pred['rule_evidence'],'perturbation':labels[cid]['perturbation']})
 print('DEV',collections.Counter((x['truth'],x['prediction']) for x in output))
 oldlabels=read(OLD/'data/private/holdout_labels.json');reg=[]
 for cid,l in oldlabels.items():
  c=read(OLD/'data/private/holdout_cases'/f'{cid}.json');obs=all_obs(c);pred=d.diagnose(obs)
  reg.append({'case_id':cid,'day':l['day'],'truth':l['label'],'prediction':pred['label'],'evidence':pred['rule_evidence'],'perturbation':l['perturbation'],'air_features':obs['air_path']['features'],'coil_features':obs['coil_response']['features']})
 print('REG',collections.Counter((x['truth'],x['prediction']) for x in reg))
 checks=[]
 def check(name,cond):
  assert cond,name;checks.append(name)
 demo=read(OLD/'data/cases/NZH-76889C2BA896.json');normal=read(OLD/'data/cases/NZH-90C933F3C475.json')
 ds=d.diagnose(all_obs(demo));repaired=d.repair_duplicates(demo);dr=d.diagnose(all_obs(repaired))
 check('exact repair removes12 only',len(demo['timestamps'])-len(repaired['timestamps'])==12)
 check('repair retains equipment suspicion',ds['label']=='damper_stuck' and dr['label']=='damper_stuck')
 check('duplicates do not weight equipment evidence',ds['rule_evidence']==dr['rule_evidence'])
 check('quality alone cannot call normal',d.diagnose({'quality':d.extract(normal,'quality')})['label']=='unresolved')
 obs=all_obs(normal);obs.pop('operating_context')
 check('context is used for diagnosis eligibility',d.diagnose(obs)['label']=='unresolved')
 renamed=copy.deepcopy(demo);renamed['id']='NORMAL';renamed['title']='normal';renamed['source_file']='normal.csv';renamed['label']='normal'
 check('labels and file names cannot affect verdict',d.diagnose(all_obs(renamed))==ds)
 invalid=copy.deepcopy(normal);invalid['series']['OA_DMPR']=[.25]*len(invalid['timestamps'])
 try:d.extract(invalid,'air_path');blocked=False
 except ValueError:blocked=True
 check('actual actuator fields rejected',blocked)
 wrong=copy.deepcopy(normal);wrong['units']['OA_TEMP']='degF'
 check('unit conflict fails closed',d.diagnose(all_obs(wrong))['status']=='invalid_evidence')
 missing=copy.deepcopy(normal);missing['series']['MA_TEMP']=[None]*len(missing['timestamps'])
 check('missing mixed temperature stays unresolved',d.diagnose(all_obs(missing))['label']=='unresolved')
 off=copy.deepcopy(normal)
 for k in ['SF_SPD_DM','RF_SPD_DM']:off['series'][k]=[0]*len(off['timestamps'])
 check('off does not imply normal',d.diagnose(all_obs(off))['label']=='unresolved')
 no_closed=copy.deepcopy(normal);no_closed['series']['CHWC_VLV_DM']=[.5]*len(normal['timestamps'])
 check('lack of closed window cannot certify normal',d.diagnose(all_obs(no_closed))['label']=='unresolved')
 # Window counts must never use duplicated records to satisfy minimum duration.
 short=copy.deepcopy(demo)
 for k in short['series']:short['series'][k]=short['series'][k][100:111]*10
 short['timestamps']=short['timestamps'][100:111]*10
 check('duplicate duration cannot pass operation gate',d.diagnose(all_obs(short))['label']=='unresolved')
 absent=copy.deepcopy(normal);absent['series']['SF_SPD_DM']=[None]*len(absent['timestamps'])
 check('all missing fan status is not active normal',d.diagnose(all_obs(absent))['label']=='unresolved')
 import datetime
 gaps=copy.deepcopy(normal);t0=datetime.datetime.fromisoformat(gaps['timestamps'][0])
 gaps['timestamps']=[(t0+datetime.timedelta(minutes=i*10)).isoformat() for i in range(len(gaps['timestamps']))]
 check('timestamp gaps reset stable window clock',d.diagnose(all_obs(gaps))['label']=='unresolved')
 conflict=copy.deepcopy(normal);conflict['timestamps'].append(conflict['timestamps'][100])
 for k in conflict['series']:conflict['series'][k].append(conflict['series'][k][100])
 conflict['series']['MA_TEMP'][-1]+=5
 check('conflicting timestamp values cannot be silently selected',d.diagnose(all_obs(conflict))['status']=='invalid_evidence')
 overlap=cases['NZH2-A54082878FC0']
 check('known development overlap rejected rather than normal',d.diagnose(all_obs(overlap))['label']=='unresolved')
 check('no errors hidden in reported dev coverage',not any(x['prediction'] not in ['unresolved',x['truth']] for x in output))
 save(ROOT/'output/root_cause_development_validation.json',{'development':output,'regression':reg,'tests':checks,'test_count':len(checks),'demo_before':ds,'demo_after':dr,'normal_demo':d.diagnose(all_obs(normal)),'scope':'development and old regression only; never final heldout'})
 print('Checks',len(checks),'demo',ds['label'],'normaldemo',d.diagnose(all_obs(normal))['label'])
if __name__=='__main__':main()
