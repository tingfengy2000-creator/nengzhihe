"""Package reviewed static evidence and independently runnable study/workbench."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
import hashlib,json,zipfile,subprocess,shutil,sys,time,argparse
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class Links(HTMLParser):
 def __init__(self):super().__init__();self.refs=[]
 def handle_starttag(self,tag,attrs):
  self.refs += [v for k,v in attrs if k in ['href','src','poster'] and v]
def main():
 args=argparse.ArgumentParser();args.add_argument('--suffix',default='');suffix=args.parse_args().suffix
 assert suffix in ['', '_v2'], 'Explicit bounded review versions only'
 dest=ROOT/'delivery';dest.mkdir(exist_ok=True)
 parser=Links();parser.feed((dest/'review/index.html').read_text(encoding='utf8'))
 for ref in parser.refs:
  if not ref.startswith('#'):
   p=(dest/'review'/unquote(ref)).resolve();assert p.is_relative_to((dest/'review').resolve()) and p.is_file(),ref
 raw=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=REPO)
 all_files=sorted(set(REPO/x.decode() for x in raw.split(b'\0') if x.startswith(b'round4/')))
 source=[p for p in all_files if p.is_file() and not p.relative_to(ROOT).as_posix().startswith(('delivery/','materials/qa/','presentation/qa/','video/qa/'))]
 packages=[('nengzhihe_round4_review'+suffix+'.zip',[(p,'review/'+p.relative_to(dest/'review').as_posix()) for p in sorted((dest/'review').rglob('*')) if p.is_file()]),('nengzhihe_round4_workbench_study'+suffix+'.zip',[(p,'round4/'+p.relative_to(ROOT).as_posix()) for p in source])]
 receipts=[]
 for name,files in packages:
  archive=dest/name;assert not archive.exists(),'Immutable package exists; use a new version instead.'
  manifest={rel:{'sha256':sha(p),'bytes':p.stat().st_size} for p,rel in files}
  with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
   for p,rel in files:z.write(p,rel)
   z.writestr('package_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
  with zipfile.ZipFile(archive) as z:
   assert z.testzip() is None
   for rel,m in manifest.items():assert hashlib.sha256(z.read(rel)).hexdigest()==m['sha256']
  receipts.append({'archive':name,'sha256':sha(archive),'bytes':archive.stat().st_size,'files':len(files),'all_member_hashes_verified':True})
 work=dest/('unpack_check_'+str(time.time_ns()));work.mkdir()
 with zipfile.ZipFile(dest/packages[1][0]) as z:
  for name in z.namelist():assert (work/name).resolve().is_relative_to(work.resolve())
  z.extractall(work)
 for script in ['test_standalone.py','test_study.py']:
  p=subprocess.run([sys.executable,'-X','utf8','scripts/'+script],cwd=work/'round4',capture_output=True,text=True,encoding='utf8',timeout=90)
  (work/(script+'.log')).write_text(p.stdout+p.stderr,encoding='utf8');assert p.returncode==0,p.stderr
 result={'packages':receipts,'extracted_http_checks':13,'extracted_study_checks':21,'local_relative_links_verified':len(parser.refs),'portal_browser_preview':'Not performed: browser file URL policy blocked local-file navigation. Static local references checked; constituent PDFs/video/cards independently inspected.','retained_extraction':work.relative_to(ROOT).as_posix(),'purpose':'Stage review and invitation readiness; no real participant or benefit result.'}
 (dest/'package_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 (dest/'SHA256SUMS.txt').write_text(''.join(r['sha256']+'  '+r['archive']+'\n' for r in receipts),encoding='utf8')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
