from pathlib import Path
from datetime import datetime,timedelta
import copy,json,sys,re
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import diagnostics,importer,reporter,server
from quality import inspect_case
from policies import run_case
def main():
 checks=[]
 def check(name,condition):assert condition,name;checks.append(name)
 def fail(name,fn):
  try:fn();blocked=False
  except ValueError:blocked=True
  check(name,blocked)
 normal=json.loads((ROOT/'data/demos/NZH-90C933F3C475.json').read_text(encoding='utf-8'))
 for kind in ['baseline','wrong_unit','compressed_time','jitter','reverse','wrong_command_unit']:
  c=copy.deepcopy(normal)
  if kind=='wrong_unit':c['units']['OA_TEMP']='degF'
  if kind=='wrong_command_unit':c['units']['CHWC_VLV_DM']='percent'
  if kind=='compressed_time':c['timestamps']=[(datetime.fromisoformat(c['timestamps'][0])+timedelta(minutes=i)).isoformat() for i in range(288)]
  if kind=='jitter':c['timestamps'][80]=(datetime.fromisoformat(c['timestamps'][80])+timedelta(seconds=1)).isoformat()
  if kind=='reverse':c['timestamps'][20],c['timestamps'][21]=c['timestamps'][21],c['timestamps'][20]
  r=run_case(c,'full_information',4,save=False);q=r['final']['quality'];ev=r['steps'][0]['quality']
  text=reporter.card(r);embedded=json.loads(re.search(r'<script id="canonical-quality" type="application/json">(.*?)</script>',text,re.S).group(1))
  check(kind+' canonical quality identical across service/evidence/final/export',q==ev==server.view(c)['view']['quality']==embedded)
  if kind!='baseline':check(kind+' invalid quality + device refusal',q['status']=='invalid' and r['final']['status']=='invalid_evidence' and r['final']['label']=='unresolved')
  if kind in {'compressed_time','jitter','reverse'}:check(kind+' no fabricated operating time or windows',q['unique_operating_minutes']==0 and not r['final']['windows'])
 gap=copy.deepcopy(normal)
 for k in gap['series']:gap['series'][k]=gap['series'][k][:100]+gap['series'][k][101:]
 gap['timestamps']=gap['timestamps'][:100]+gap['timestamps'][101:]
 r=run_case(gap,'full_information',4,save=False)
 check('Missing five-minute record is a gap and never an inserted sample',r['final']['quality']['gap_count']==1 and r['final']['quality']['status']=='needs_review')
 check('Every valid window duration equals actual timestamp span plus one interval',all(w['minutes']==(datetime.fromisoformat(w['end'])-datetime.fromisoformat(w['start'])).total_seconds()/60+5 for w in r['final']['windows']))
 missing=copy.deepcopy(normal);missing['series'].pop('MA_TEMP');r=run_case(missing,'full_information',4,save=False)
 check('Missing sensor is distinct from inapplicable operation',r['final']['branches']['air_path']['state']=='missing_points' and r['final']['branches']['coil_response']['state']=='missing_points')
 conflict=copy.deepcopy(normal);conflict['timestamps'].append(conflict['timestamps'][-1])
 for k,v in conflict['series'].items():v.append(v[-1]+(1 if k=='MA_TEMP' else 0))
 r=run_case(conflict,'full_information',4,save=False)
 check('Conflicting duplicates do not yield a green quality card',r['final']['quality']['status']=='invalid' and r['final']['branches']['air_path']['state']=='evidence_conflict')
 demo=json.loads((ROOT/'data/demos/NZH-76889C2BA896.json').read_text(encoding='utf-8'));a=run_case(demo,'full_information',4,save=False);b=run_case(demo,'full_information',4,repair=True,save=False)
 check('Exact duplicate repair retains device concern',a['final']['quality']['duplicates']==12 and b['final']['quality']['duplicates']==0 and a['final']['label']==b['final']['label']=='damper_stuck')
 raw=(ROOT/'data/public_csv/LBNL_SDAHU_2018-04-10_raw_excerpt.csv').read_text(encoding='utf-8');p=importer.preview(raw)
 units={k:'degF' if k in importer.TEMPS else 'binary' if k in importer.FLAGS else 'fraction' for k in p['default_mapping']}
 args=dict(text=raw,mapping=p['default_mapping'],time_column='Datetime',units=units,source_interval=1,profile='lbnl_sdahu_public_2022',save=False)
 c=importer.convert(**args)
 check('Public original CSV conversion exactly reproduces existing numeric demo',c['timestamps']==normal['timestamps'] and c['series']==normal['series'] and c['units']==normal['units'])
 r=run_case(c,'full_information',4,save=False)
 check('Import produces 1440 to 288 explicit conversion and an actual card',c['import_provenance']['input_rows']==1440 and len(c['timestamps'])==288 and r['final']['label']=='normal' and '<table>' in reporter.card(r))
 fail('Raw cadence cannot be relabelled as five minutes',lambda:importer.convert(**(args|{'source_interval':5})))
 fail('Other equipment profiles refused',lambda:importer.convert(**(args|{'profile':'real_vav'})))
 badmap=dict(p['default_mapping']);badmap['OA_DMPR_DM']='OA_DMPR'
 fail('Actual actuator positions cannot enter mapped evidence',lambda:importer.convert(**(args|{'mapping':badmap})))
 lines=raw.splitlines();partial='\n'.join(lines[:100]+lines[101:])
 missing_lines=list(lines);cells=missing_lines[601].split(',');cells[p['columns'].index('OA_TEMP')]='';missing_lines[601]=','.join(cells)
 missing_import=importer.convert(**(args|{'text':'\n'.join(missing_lines)}))
 check('Resampling does not hide a missing original sensor value',missing_import['series']['OA_TEMP'][120] is None and inspect_case(missing_import)['status']=='needs_review')
 fail('Incomplete one-minute bucket refused instead of overstating five minutes',lambda:importer.convert(**(args|{'text':partial})))
 fail('Repeated CSV timestamps not silently averaged',lambda:importer.convert(**(args|{'text':raw+'\n'+lines[-1]})))
 r=run_case(normal,'full_information',1,save=False)
 check('Full evidence still bypasses budget1 truncation',len(r['steps'])==4)
 r=run_case(normal,'full_information',4,available_evidence=['operating_context','coil_response'],save=False)
 check('Missing queried evidence cannot inherit previous conclusion',r['final']['label']=='unresolved' and r['final']['branches']['air_path']['state']=='not_queried')
 out={'passed':len(checks),'checks':checks,'scope':'Counterexamples, data contracts and public import workflow. Not a new performance study.'}
 (ROOT/'output/reliability_tests.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
