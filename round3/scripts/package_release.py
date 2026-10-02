"""Build and verify a self-contained review archive; retain every cache and prior package."""
from pathlib import Path
import hashlib,json,zipfile,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def main():
 dest=ROOT/'delivery';dest.mkdir(exist_ok=True)
 demo=json.loads((ROOT/'output/import_demo.json').read_text(encoding='utf-8'))
 shutil.copy2(ROOT/demo['card'],dest/'导入任务核查卡.html')
 files=[]
 for name in ['baseline_v1','web','data','scripts','audit_input']:
  files.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
 for name in ['materials/final','materials/references']:
  files.extend(p for p in (ROOT/name).rglob('*') if p.is_file())
 for name in ['materials/QA_视觉复检.txt','materials/working/qa.json','materials/working/word_limits.json','materials/working/artifact.md','materials/working/flow.svg','materials/working/flow.png']:
  files.append(ROOT/name)
 files.extend(ROOT.glob('*.py'));files.extend(ROOT.glob('*.txt'));files.extend([ROOT/'AGENTS.md',ROOT/'preservation_initial.json'])
 files.extend(p for p in (ROOT/'output').glob('*.json') if p.name!='workbench_process.json')
 for name in ['output/regression','output/cards','output/runs','output/ui']:
  files.extend(p for p in (ROOT/name).rglob('*') if p.is_file())
 files=sorted(set(files));manifest={p.relative_to(ROOT).as_posix():{'sha256':sha_bytes(p.read_bytes()),'bytes':p.stat().st_size} for p in files}
 manifest_text=json.dumps({'purpose':'Round3 review archive, not a completed competition submission','files':manifest,'excluded_retained_locally':['renderer binaries and download parts','render profiles and page PNG/PDF intermediates','standalone scratch copies','live server process/log files','Python caches']},ensure_ascii=False,indent=2)
 (dest/'manifest.json').write_text(manifest_text,encoding='utf-8')
 archive=dest/'能智核_第三轮_可靠性修复与导入演示.zip'
 with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in files:z.write(p,'round3/'+p.relative_to(ROOT).as_posix())
  z.writestr('round3/manifest.json',manifest_text)
 verify=dest/('unpack_check_'+str(time.time_ns()));verify.mkdir()
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for name in z.namelist():
   target=(verify/name).resolve();assert target.is_relative_to(verify.resolve())
   if name!='round3/manifest.json':assert sha_bytes(z.read(name))==manifest[name.removeprefix('round3/')]['sha256']
  z.extractall(verify)
 log=verify/'package_smoke.log'
 with log.open('w',encoding='utf-8') as f:
  result=subprocess.run([sys.executable,'-X','utf8','scripts/test_standalone.py'],cwd=verify/'round3',stdout=f,stderr=subprocess.STDOUT,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 assert result.returncode==0,log.read_text(encoding='utf-8')
 result={'archive':archive.name,'sha256':sha_bytes(archive.read_bytes()),'bytes':archive.stat().st_size,'files':len(manifest),'zip_integrity':'passed','all_manifest_hashes':'passed','extracted_archive_http_checks':json.loads((verify/'round3/output/standalone_tests.json').read_text(encoding='utf-8'))['passed'],'kept_extraction':str(verify)}
 (dest/'package_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
