"""Bind completed visual inspection to exact final files; preserve all renders."""
from pathlib import Path
import hashlib,json,shutil,zipfile,re
from lxml import etree
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 docs=[]
 for i,stem,folder,pages in [(1,'附件1_能智核_项目简表','render_final_1',3),(2,'附件2_能智核_项目说明书','render_verified_2',5),(3,'附件3_能智核_商业计划书','render_verified_3',3)]:
  doc=ROOT/'materials/final'/(stem+'.docx');render=ROOT/'materials/working'/folder
  dest=ROOT/'materials/qa'/str(i);dest.mkdir(parents=True,exist_ok=True)
  pdf=ROOT/'materials/final'/(stem+'.pdf');shutil.copy2(render/(stem+'.pdf'),pdf)
  assert len(PdfReader(pdf).pages)==pages
  for page in PdfReader(pdf).pages:assert len(re.sub(r'\s','',page.extract_text() or ''))>100
  with zipfile.ZipFile(doc) as z:
   assert not any(n.startswith('word/fonts/') for n in z.namelist())
   ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
   fonts=etree.fromstring(z.read('word/fontTable.xml')).xpath('//w:font/@w:name',namespaces=ns)
   assert fonts==['SimSun','SimHei']
   text=''.join(etree.fromstring(z.read('word/document.xml')).xpath('//w:t/text()',namespaces=ns))
   assert '公共建筑风阀疑点核验与补证工作台' in text
   assert all(v not in text for v in ['300%','首轮保留','不增加复杂Agent'])
   assert not etree.fromstring(z.read('docProps/core.xml')).findtext('{http://purl.org/dc/elements/1.1/}creator')
  for p in sorted(render.glob('page-*.png')):shutil.copy2(p,dest/p.name)
  docs.append({'file':doc.relative_to(ROOT).as_posix(),'sha256':sha(doc),'pdf':pdf.relative_to(ROOT).as_posix(),'pdf_sha256':sha(pdf),'pages':pages,'fonts':fonts,'embedded_fonts':0,'anonymous_author':True,'all_pages_visually_inspected':True,'page_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(dest.glob('*.png'))}})
 write(ROOT/'materials/qa/qa.json',{'status':'visually_reviewed_anonymous_editable_drafts','total_pages':11,'files':docs,'word_limits':read(ROOT/'materials/working/word_limits.json'),'notes':'All 11 pages inspected. Final unchanged pages additionally matched earlier inspected PNG bytes. Full Chinese fonts; no missing glyphs, blank tail pages, clipped tables or orphan headings. Administrative identity fields remain intentionally blank; maturity is self-assessed level 3, not certification.'})
 pqa=ROOT/'presentation/qa';pqa.mkdir(exist_ok=True)
 for p in sorted((ROOT/'presentation/working/render_verified').glob('slide-*.png')):shutil.copy2(p,pqa/p.name)
 ppt=ROOT/'presentation/final/能智核_实际核查任务答辩.pptx';pdf=ppt.with_suffix('.pdf')
 assert read(ROOT/'presentation/working/final_validation_v2.json')['finalSha256']==sha(ppt)
 assert len(PdfReader(pdf).pages)==10
 write(pqa/'qa.json',{'all_pages_visually_inspected':True,'pages':10,'files':{p.relative_to(ROOT).as_posix():sha(p) for p in [ppt,pdf]},'page_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in pqa.glob('slide-*.png')},'notes':'Final 10-slide PDF visually inspected after finalization; native editable text/tables, real UI screenshots, no clipping or missing glyphs. Task-based narrative; no new performance claim.'})
 video=ROOT/'video/final/nengzhihe_actual_operation_3min.mp4';meta=read(ROOT/'video/final/recording_provenance.json');assert meta['video_sha256']==sha(video)
 write(ROOT/'video/qa/qa.json',{'video_sha256':sha(video),'duration_seconds':180,'size':[1280,1002],'all_17_chapter_midpoints_visually_inspected':True,'decode_to_end_passed':True,'audio':False,'source':'Actual browser UI captures, sampled at 2 fps; captions added; idle gaps removed, source order preserved. Not a human study or latency recording.','chapter_frame_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'video/qa').glob('chapter-*.png')}})
 protected=read(ROOT/'preservation_before.json');changed=[f for f,h in protected.items() if sha(ROOT.parent/f)!=h];assert not changed
 write(ROOT/'output/preservation_check.json',{'round3_tracked_files':len(protected),'changed':changed,'prior_rounds_modified':False,'scope':'Round3 byte hashes checked; git scope separately checked for prior rounds. No operations on xiangyi-youju.'})
 print('Bound visual QA: Word 11 pages, deck 10 pages, video 17 chapters; prior round3 unchanged:',len(protected))
if __name__=='__main__':main()
