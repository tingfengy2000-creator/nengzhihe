"""Round2 isolated local workbench. Public demo/dev cases only."""
import argparse,json,mimetypes,re,threading
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse,unquote
from policies import ROOT,run_case,prepare_case
from baseline_v1 import engine as old

OLD=ROOT.parent;LOCK=threading.Lock()
DEMO_IDS=['NZH-CFF0E57369E1','NZH-90C933F3C475','NZH-76889C2BA896']
def index():
    entries=json.loads((ROOT/'data/demo_index.json').read_text(encoding='utf-8'))
    entries=[x for cid in DEMO_IDS for x in entries if x['id']==cid]
    path=ROOT/'data/dev/index.json'
    if path.exists():entries+=json.loads(path.read_text(encoding='utf-8'))
    return entries
def get_case(cid):
    if not re.fullmatch('[A-Za-z0-9_-]{1,100}',cid):raise ValueError('Invalid case identifier')
    original=cid.removesuffix('__repaired');match=next((c for c in index() if c['id']==original),None)
    if match is None:raise ValueError('Only public demo/development cases can be opened')
    path=(ROOT/'data/demos'/(original+'.json')) if original in DEMO_IDS else ROOT/match['path']
    return prepare_case(json.loads(path.read_text(encoding='utf-8')),repair=cid.endswith('__repaired'))
def view(c):
    keys=['electricity_kwh','reference_kwh','OA_TEMP'] if c['family']=='bdg2' else ['SA_TEMP','SA_TEMPSPT','MA_TEMP','OA_TEMP','RA_TEMP','OA_DMPR_DM','CHWC_VLV_DM','SF_SPD_DM']
    names={'SA_TEMP':'送风温度','SA_TEMPSPT':'送风设定','MA_TEMP':'混合空气温度','OA_TEMP':'室外温度','RA_TEMP':'回风温度',
           'OA_DMPR_DM':'风阀控制指令','CHWC_VLV_DM':'冷阀控制指令','SF_SPD_DM':'实际风机启停','electricity_kwh':'实测电量','reference_kwh':'历史参考'}
    return {'case':c,'view':{'quality':old.quality(c),'operation':{'label':'pending','status':'pending','detail':'请选择证据和预算，运行真实核验。'},
       'initial_series':[{'key':k,'label':names[k],'unit':c.get('units',{}).get(k,''),'values':c['series'][k]} for k in keys if k in c['series']]}}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send_json(self,obj,status=200):
        blob=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode();self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(blob)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(blob)
    def do_GET(self):
        path=unquote(urlparse(self.path).path)
        try:
            if path=='/api/health':return self.send_json({'status':'ok','application':'能智核','revision':'round2','local_only':True})
            if path=='/api/cases':return self.send_json({'cases':index(),'revision':'round2','model':{'optimized':False,'available':False,'note':'本轮只比较固定流程与自适应规则，不调用或优化模型。'}})
            if path.startswith('/api/case/'):return self.send_json(view(get_case(path.rsplit('/',1)[-1])))
            if path=='/api/benchmark':
                p=ROOT/'output/benchmark.json';return self.send_json(json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'status':'not_run','diagnosis_comparison':[],'policy_comparison':[]})
            if path.startswith('/api/export/'):
                rid=path.rsplit('/',1)[-1]
                if not re.fullmatch('[0-9a-f]{16}',rid):raise ValueError('Invalid run ID')
                return self.send_json(json.loads((ROOT/'output/runs'/(rid+'.json')).read_text(encoding='utf-8')))
            web=(ROOT/'web').resolve();p=(web/('index.html' if path=='/' else path.lstrip('/'))).resolve()
            if not p.is_relative_to(web) or not p.is_file():return self.send_json({'error':'not found'},404)
            data=p.read_bytes();self.send_response(200);self.send_header('Content-Type',(mimetypes.guess_type(p.name)[0] or 'application/octet-stream')+'; charset=utf-8')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        except (ValueError,FileNotFoundError,KeyError) as e:self.send_json({'error':str(e)},400)
        except Exception as e:self.send_json({'error':type(e).__name__+': '+str(e)},500)
    def do_POST(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>16384 or size<0:raise ValueError('Request too large')
            req=json.loads(self.rfile.read(size));path=urlparse(self.path).path
            if path=='/api/repair':return self.send_json(view(prepare_case(get_case(req['case_id'].removesuffix('__repaired')),repair=True)))
            if path!='/api/run':return self.send_json({'error':'not found'},404)
            if not LOCK.acquire(blocking=False):return self.send_json({'error':'正在核验，请稍后'},409)
            try:r=run_case(get_case(req['case_id']),req.get('strategy','adaptive_rule'),req.get('budget',4),req.get('available_evidence'),req.get('repair',False),start_time=req.get('start_time'),end_time=req.get('end_time'))
            finally:LOCK.release()
            self.send_json(r)
        except (ValueError,FileNotFoundError,KeyError) as e:self.send_json({'error':str(e)},400)
        except Exception as e:self.send_json({'error':type(e).__name__+': '+str(e)},500)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=18192);a=p.parse_args()
    print(f'Nengzhihe Round2: http://127.0.0.1:{a.port}',flush=True);ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
