from pathlib import Path
import json,hashlib,zipfile,copy,sys,re,shutil,ast
from lxml import etree
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import diagnostics
from policies import run_case
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 normal=read(ROOT/'data/demos/NZH-90C933F3C475.json');a=run_case(normal,'full_information',4,save=False)
 changed=copy.deepcopy(normal);changed.update(id='damper_stuck_075_truth_leakage',title='leakage',label='coil_leakage',source_file='damper_stuck_075_annual.csv',source_ref='fault_normal',severity=.75)
 b=run_case(changed,'full_information',4,save=False)
 assert a['final']==b['final']
 forbidden=copy.deepcopy(normal);forbidden['series']['OA_DMPR']=[.75]*len(normal['timestamps'])
 try:diagnostics.prepare(forbidden);blocked=False
 except ValueError:blocked=True
 assert blocked
 old_tree=ast.parse((ROOT.parent/'round2/diagnostics.py').read_text(encoding='utf-8-sig')) if (ROOT.parent/'round2/diagnostics.py').exists() else None
 old_gates=None
 if old_tree:
  old_gates=next(ast.literal_eval(n.value) for n in old_tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='GATES' for t in n.targets))
  assert old_gates==diagnostics.GATES
 write(ROOT/'output/contract_checks.json',{'metadata_label_filename_invariance':True,'direct_position_rejected':blocked,'gate_values_unchanged_from_round2':old_gates==diagnostics.GATES if old_tree else 'not_checked_without_prior_source','calibration_sha256':sha(ROOT/'data/calibration.json')})
 notes={1:['三页中文和所有选项完整；页1包含项目背景与立项思路；页2方案、商业及技术自评；页3三个指标与边界说明。没有表头孤行或缺字。'],2:['四页完整；实际界面图和流程图清晰；功能结果表跨页重复表头，无行内断裂；分组结果表与应用前景完整，来源说明在第4页。'],3:['三页完整；正文字体一致；标题均与后续正文同页起始，无小标题单独停在页末；末页经济效益和来源完整。']}
 qa=[];names=['附件1_能智核_项目简表.docx','附件2_能智核_项目说明书.docx','附件3_能智核_商业计划书.docx']
 for i,name in enumerate(names,1):
  path=ROOT/'materials/final'/name;render=ROOT/'materials/working'/f'render_final_{i}';pdf=next(render.glob('*.pdf'));reader=PdfReader(pdf)
  with zipfile.ZipFile(path) as z:
   assert not any(n.startswith('word/fonts/') for n in z.namelist())
   assert 'docProps/custom.xml' not in z.namelist()
   xml=z.read('word/document.xml');root=etree.fromstring(xml);ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
   text=''.join(root.xpath('//w:t/text()',namespaces=ns))
   assert TITLE in text
   assert '300%' not in text and '首轮保留' not in text and '不增加复杂Agent' not in text
   for n in z.namelist():
    if n.endswith('.xml') and n.startswith('word/'):
     s=z.read(n);assert b'embedRegular' not in s
   fonts=etree.fromstring(z.read('word/fontTable.xml')).xpath('//w:font/@w:name',namespaces=ns)
   assert fonts==['SimSun','SimHei']
   core=etree.fromstring(z.read('docProps/core.xml'))
   assert not core.findtext('{http://purl.org/dc/elements/1.1/}creator')
  page_texts=[p.extract_text() or '' for p in reader.pages];assert len(page_texts)=={1:3,2:4,3:3}[i]
  assert all(len(re.sub(r'\s','',t))>100 for t in page_texts)
  qa.append({'file':name,'sha256':sha(path),'page_count':len(page_texts),'rendered_pdf':str(pdf.relative_to(ROOT)),
    'font_table':fonts,'embedded_font_parts':0,'anonymous_author_metadata':True,'all_pages_visually_inspected':True,
    'inspection_notes':notes[i],'page_png_sha256':{p.name:sha(p) for p in sorted(render.glob('page-*.png'))}})
 write(ROOT/'materials/working/qa.json',{'renderer':'Packaged render_docx.py with task-private officially signed LibreOffice 26.2.6; local complete SimSun/SimHei','total_pages':10,'files':qa,'word_limits':read(ROOT/'materials/working/word_limits.json'),'status':'Visually reviewed editable anonymous drafts; maturity and identity-field handling require organizer submission rules.'})
 protected=read(ROOT/'preservation_initial.json')['files'];diff=[];missing=[]
 for rel,h in protected.items():
  p=ROOT.parent/rel
  if not p.exists():missing.append(rel)
  elif sha(p)!=h:diff.append(rel)
 assert not diff and not missing,(diff,missing)
 write(ROOT/'output/preservation_check.json',{'tracked_prior_files':len(protected),'changed':diff,'missing':missing,'scope':'Source, data, results and deliverables from first two rounds. Live logs/process files and caches excluded from initial snapshot. No xiangyi-youju operations.'})
 print(json.dumps({'word_pages':10,'font_checks':'passed','metadata_leakage_checks':'passed','prior_files_unchanged':len(protected)},ensure_ascii=False))
TITLE='能智核——公共建筑用能异常核验工作台'
if __name__=='__main__':main()
