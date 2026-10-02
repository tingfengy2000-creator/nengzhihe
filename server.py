"""Loopback-only review workbench. Standard-library server; no paid cloud API."""
from __future__ import annotations
import argparse
import json
import mimetypes
import re
import threading
import urllib.request
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse,unquote

from engine import ROOT,quality,repair_duplicates,initial_summary
from policies import run_case,STRATEGIES

RUN_LOCK=threading.Lock()
SERIES_LABELS={'SA_TEMP':'送风温度','SA_TEMPSPT':'送风设定温度','MA_TEMP':'混合空气温度','OA_TEMP':'室外温度',
               'RA_TEMP':'回风温度','electricity':'建筑电力表计','electricity_kwh':'实测电量','reference_kwh':'历史同类时段参考',
               'air_temperature':'室外温度'}


def index():
    p=ROOT/'data'/'index.json'
    if not p.exists():
        return []
    obj=json.loads(p.read_text(encoding='utf-8-sig'))
    return obj.get('cases',[]) if isinstance(obj,dict) else obj


def get_case(case_id):
    repaired=case_id.endswith('__repaired')
    original=case_id.removesuffix('__repaired')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',original):
        raise ValueError('Invalid case identifier')
    allowed={x['id'] for x in index()}
    if original not in allowed:
        raise ValueError('Only public demonstration/development cases are available in the workbench')
    p=ROOT/'data'/'cases'/(original+'.json')
    obj=json.loads(p.read_text(encoding='utf-8-sig'))
    return repair_duplicates(obj) if repaired else obj


def case_view(obj):
    keys=(['SA_TEMP','SA_TEMPSPT','MA_TEMP'] if obj['family']=='lbnl' else ['electricity_kwh','reference_kwh'])
    selected=[k for k in keys if k in obj.get('series',{})]
    if not selected:
        selected=list(obj.get('series',{}))[:2]
    initial=[{'key':k,'label':SERIES_LABELS.get(k,k),'unit':obj.get('units',{}).get(k,''),'values':obj['series'][k]} for k in selected]
    return {'case':obj,'view':{'quality':quality(obj),'operation':{'status':'pending','detail':'尚未执行本次设备核验；数据检查与运行疑点独立。'},
                             'initial_series':initial,'initial_summary':initial_summary(obj)}}


def model_status():
    p=ROOT/'runtime'/'local_model_config.json'
    if not p.exists():
        return {'name':'本地模型准备中','available':False}
    cfg=json.loads(p.read_text(encoding='utf-8-sig'))
    available=False
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(cfg['base_url'].rstrip('/')+'/models',timeout=2) as response:
            available=response.status==200
    except Exception:
        pass
    return {'name':cfg.get('model_id','本地免费模型'),'available':available,'local':True,'paid_api':False}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):
        pass

    def send_json(self,obj,status=200):
        payload=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path=unquote(urlparse(self.path).path)
        try:
            if path=='/api/cases':
                return self.send_json({'cases':index(),'model':model_status()})
            if path.startswith('/api/case/'):
                return self.send_json(case_view(get_case(path.split('/')[-1])))
            if path=='/api/benchmark':
                p=ROOT/'output'/'benchmark.json'
                return self.send_json(json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'status':'not_run','metrics':[],
                         'notes':['尚未完成冻结留出评测；不显示预设性能。'],'decision':'等待真实对照实验。'})
            if path.startswith('/api/export/'):
                rid=path.split('/')[-1]
                if not re.fullmatch('[0-9a-f]{16}',rid):
                    raise ValueError('Invalid run ID')
                p=ROOT/'output'/'runs'/(rid+'.json')
                if not p.exists():
                    return self.send_json({'error':'Run not found'},404)
                return self.send_json(json.loads(p.read_text(encoding='utf-8')))
            if path=='/api/health':
                return self.send_json({'status':'ok','application':'能智核','cases':len(index()),'local_only':True})
            web=(ROOT/'web').resolve()
            target=(web/('index.html' if path=='/' else path.lstrip('/'))).resolve()
            if not target.is_relative_to(web) or not target.is_file():
                return self.send_json({'error':'Not found'},404)
            body=target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',(mimetypes.guess_type(target.name)[0] or 'application/octet-stream')+'; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ValueError,KeyError,FileNotFoundError) as exc:
            self.send_json({'error':str(exc)},400)
        except Exception as exc:
            self.send_json({'error':type(exc).__name__+': '+str(exc)},500)

    def do_POST(self):
        path=urlparse(self.path).path
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length>16384:
                return self.send_json({'error':'Request too large'},413)
            req=json.loads(self.rfile.read(length))
            if path=='/api/repair':
                case=get_case(req['case_id'].removesuffix('__repaired'))
                return self.send_json(case_view(repair_duplicates(case)))
            if path=='/api/run':
                if not RUN_LOCK.acquire(blocking=False):
                    return self.send_json({'error':'已有核验任务运行，请等待完成。'},409)
                try:
                    case=get_case(req['case_id'])
                    result=run_case(case,req.get('strategy','fixed'),int(req.get('budget',4)),bool(req.get('repair',False)))
                finally:
                    RUN_LOCK.release()
                return self.send_json(result)
            return self.send_json({'error':'Not found'},404)
        except (ValueError,KeyError,FileNotFoundError) as exc:
            self.send_json({'error':str(exc)},400)
        except Exception as exc:
            self.send_json({'error':type(exc).__name__+': '+str(exc)},500)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=18190)
    args=parser.parse_args()
    print(f'Nengzhihe workbench: http://127.0.0.1:{args.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
