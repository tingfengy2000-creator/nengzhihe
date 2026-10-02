"""Reproduce a real original CSV -> mapping -> verification -> readable card task."""
from pathlib import Path
import json,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import importer,reporter
from policies import run_case
def main():
 start=time.perf_counter();source=ROOT/'data/public_csv/LBNL_SDAHU_2018-04-10_raw_excerpt.csv'
 text=source.read_text(encoding='utf-8');p=importer.preview(text)
 units={k:'degF' if k in importer.TEMPS else 'binary' if k in importer.FLAGS else 'fraction' for k in p['fields']}
 mapping={'mapping':p['default_mapping'],'time_column':'Datetime','units':units,'source_interval':1,'profile':'lbnl_sdahu_public_2022'}
 c=importer.convert(text,**mapping);r=run_case(c,'full_information',4);reporter.card(r)
 out={'case_id':c['id'],'run_id':r['run_id'],'source_file':source.name,'source_sha256':c['import_provenance']['source_sha256'],
      'input_rows':1440,'output_rows':len(c['timestamps']),'quality':r['final']['quality'],'device_label':r['final']['label'],
      'branches':r['final']['branches'],'card':'output/cards/'+r['run_id']+'.html','mapping':mapping,
      'elapsed_ms_including_file_parse_conversion_verification_and_export':round((time.perf_counter()-start)*1000,3),
      'scope':'Existing development demonstration, not independent accuracy or human efficiency evidence.'}
 (ROOT/'output/import_demo.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in out.items() if k not in ['quality','branches','mapping']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
