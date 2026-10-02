"""Acquire a task-private official renderer installer; no desktop installation."""
from pathlib import Path
import urllib.request,hashlib,json,time,concurrent.futures,re
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'runtime';D.mkdir(exist_ok=True)
URL='https://download.documentfoundation.org/libreoffice/stable/26.2.6/win/x86_64/LibreOffice_26.2.6_Win_x86-64.msi'
target=D/'LibreOffice_26.2.6_Win_x86-64.msi'
if target.exists(): print('Existing installer',target);raise SystemExit()
req=urllib.request.Request(URL,headers={'Range':'bytes=0-0'})
with urllib.request.urlopen(req,timeout=60) as r:
    content_range=r.headers.get('Content-Range',''); total=int(content_range.split('/')[-1]) if content_range else int(r.headers['Content-Length'])
print('Official renderer bytes',total,flush=True)
parts=D/'renderer_parts';parts.mkdir(exist_ok=True)
spans=[(i,min(i+4*1024*1024,total)-1) for i in range(0,total,4*1024*1024)]
def get(span):
 a,b=span;p=parts/str(a)
 if p.exists() and p.stat().st_size==b-a+1:return
 for attempt in range(4):
  try:
   with urllib.request.urlopen(urllib.request.Request(URL,headers={'Range':f'bytes={a}-{b}'}),timeout=60) as r:
    data=r.read();assert r.status==206 and r.headers.get('Content-Range')==f'bytes {a}-{b}/{total}' and len(data)==b-a+1
   p.write_bytes(data);return
  except Exception:
   if attempt==3:raise
   time.sleep(1+attempt)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 for i,_ in enumerate(pool.map(get,spans),1):
  if i%10==0:print('Downloaded parts',i,'/',len(spans),flush=True)
with target.open('wb') as f:
 for a,b in spans:f.write((parts/str(a)).read_bytes())
meta={'url':URL,'bytes':total,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'purpose':'private headless renderer; no user desktop LibreOffice'}
(D/'renderer_source.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');print(meta)
