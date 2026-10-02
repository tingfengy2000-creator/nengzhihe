"""Reproduce round4 from tracked/candidate files in a retained isolated copy."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess,sys,time,argparse
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--report',default='.review-work/latest_round4.json');args=parser.parse_args()
 report=(ROOT/args.report).resolve();assert report.is_relative_to(ROOT)
 raw=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT)
 files=sorted(set(x.decode() for x in raw.split(b'\0') if x.startswith(b'round4/')))
 before={f:sha(ROOT/f) for f in files}
 work=ROOT/'.review-work'/('round4_'+str(time.time_ns()));stage=work/'round4';logs=work/'logs';logs.mkdir(parents=True)
 for f in files:
  dest=work/f;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/f,dest)
 expected=read(stage/'output/comparison/rows.json')
 (stage/'output/comparison').rename(stage/'output/comparison_original')
 checks=[];start=time.perf_counter()
 for script in ['run_comparison.py','test_reliability.py','test_standalone.py','test_study.py','analyze_study.py','demo_import.py']:
  t=time.perf_counter();p=subprocess.run([sys.executable,'-X','utf8','scripts/'+script],cwd=stage,capture_output=True,text=True,encoding='utf-8',timeout=180)
  (logs/(script+'.txt')).write_text(p.stdout+p.stderr,encoding='utf-8')
  checks.append({'script':script,'exit_code':p.returncode,'seconds':round(time.perf_counter()-t,3)})
  if p.returncode:raise RuntimeError(f'{script} failed; inspect {logs}')
 actual=read(stage/'output/comparison/rows.json')
 clean=lambda rows:[{k:v for k,v in r.items() if k!='elapsed_ms'} for r in rows]
 assert clean(actual)==clean(expected) and len(actual)==336
 assert read(stage/'output/reliability_tests.json')['passed']==29
 assert read(stage/'output/standalone_tests.json')['passed']==13
 assert read(stage/'output/study_software_checks.json')['count']==21
 status=read(stage/'study/results/status.json');assert status['real_participants']==0
 pages=0
 qa=read(stage/'materials/qa/qa.json')
 for doc in qa['files']:
  assert sha(stage/doc['file'])==doc['sha256'] and sha(stage/doc['pdf'])==doc['pdf_sha256']
  for f,h in doc['page_sha256'].items():assert sha(stage/f)==h;pages+=1
 assert pages==11
 qa=read(stage/'presentation/qa/qa.json')
 for f,h in (qa['files']|qa['page_sha256']).items():assert sha(stage/f)==h
 assert len(qa['page_sha256'])==10
 qa=read(stage/'video/qa/qa.json');assert sha(stage/'video/final/nengzhihe_actual_operation_3min.mp4')==qa['video_sha256']
 packages=read(stage/'delivery/package_check.json')['packages']
 for package in packages:assert sha(stage/'delivery'/package['archive'])==package['sha256']
 assert before=={f:sha(ROOT/f) for f in files},'Source changed during isolated verification'
 for p in ['output/reliability_tests.json','output/standalone_tests.json','output/study_software_checks.json','output/import_demo.json','study/results/status.json']:
  if (stage/p).exists():shutil.copy2(stage/p,logs/Path(p).name)
 result={'status':'passed','timestamp_utc':datetime.now(timezone.utc).isoformat(),'commands':checks,'elapsed_seconds':round(time.perf_counter()-start,3),'reliability_checks':29,'isolated_http_checks':13,'study_software_checks':21,'method_case_records_reproduced':336,'prediction_or_evidence_changes':0,'main_unit':56,'paired_records':112,'word_pages_hash_verified':11,'slides_hash_verified':10,'video_hash_verified':True,'release_archives_hash_verified':len(packages),'real_participants':0,'value_study_status':status['status'],'original_files_unchanged':True,'source_manifest_sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),'retained_workdir':work.relative_to(ROOT).as_posix(),'scope':'Historical reproducibility and software checks only, not a new performance or human-value experiment.'}
 report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
