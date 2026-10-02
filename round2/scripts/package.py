"""Make a new package only; never remove caches or replace round1 delivery."""
from pathlib import Path
import datetime,hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    target=ROOT/'delivery/能智核_第二轮工作台与参赛底稿_待视觉复检.zip'
    if target.exists():raise RuntimeError('Package already exists; choose a new revision instead of replacing')
    target.parent.mkdir(exist_ok=True)
    skip_names={'workbench_process.json','workbench_stdout.log','workbench_stderr.log'}
    files=[p for p in ROOT.rglob('*') if p.is_file() and not any(x in {'__pycache__','delivery'} for x in p.relative_to(ROOT).parts)
           and p.name not in skip_names and p.suffix not in {'.pyc','.tmp'}]
    records=[{'path':p.relative_to(ROOT).as_posix(),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]
    manifest={'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kind':'runnable workbench + evidence + editable drafts pending visual review',
              'not_formal_submission':True,'source_files':records,'exclusions':'Bytecode, live process identity/logs, delivery ZIP itself; nothing deleted. Raw annual archive and model weights remain in original cache, not duplicated.'}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(files):z.write(p,'round2/'+p.relative_to(ROOT).as_posix())
        z.writestr('round2/_package/文件清单.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for r in records:assert hashlib.sha256(z.read('round2/'+r['path'])).hexdigest()==r['sha256']
    result={'path':str(target),'files':len(records),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'all_members_verified':True}
    (target.parent/'包校验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
