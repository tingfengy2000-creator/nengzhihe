"""Run the packaged document renderer with a task-private signed LibreOffice image.
Profiles/intermediates are retained; no cache cleanup or desktop Office control.
"""
from pathlib import Path
import os,sys,runpy,tempfile,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
DEP=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
LO=ROOT/'runtime/libreoffice_private/program'
if not (LO/'soffice.exe').exists():
 LO=ROOT.parent/'round3/runtime/libreoffice_private/program'
assert (LO/'soffice.exe').exists(),'Use only the retained task-private signed renderer.'
SKILL=Path.home()/'.codex/plugins/cache/openai-primary-runtime/documents/26.921.10847/skills/documents'
temp_root=ROOT/'runtime/render_tmp';temp_root.mkdir(exist_ok=True)
poppler=next((DEP/'native/poppler').rglob('pdftoppm.exe')).parent
os.environ['PATH']=os.pathsep.join([str(LO),str(poppler),str(DEP/'python'),os.environ.get('PATH','')])
os.environ['TEMP']=str(temp_root);os.environ['TMP']=str(temp_root);tempfile.tempdir=str(temp_root)
class RetainedDirectory:
 @classmethod
 def __class_getitem__(cls,item):return cls
 def __init__(self,suffix=None,prefix=None,dir=None,**kwargs):self.name=tempfile.mkdtemp(suffix=suffix or '',prefix=prefix or 'kept_',dir=dir or temp_root)
 def __enter__(self):return self.name
 def __exit__(self,*args):return False
 def cleanup(self):pass
tempfile.TemporaryDirectory=RetainedDirectory
original_popen=subprocess.Popen
def tolerant_popen(*args,**kwargs):
 if kwargs.get('text') or kwargs.get('universal_newlines') or kwargs.get('encoding'):
  kwargs.setdefault('errors','replace')
 return original_popen(*args,**kwargs)
subprocess.Popen=tolerant_popen
sys.argv=[str(SKILL/'render_docx.py'),*sys.argv[1:]]
runpy.run_path(str(SKILL/'render_docx.py'),run_name='__main__')
