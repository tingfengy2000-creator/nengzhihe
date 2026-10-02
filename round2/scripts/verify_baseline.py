from pathlib import Path
import json,hashlib,datetime,zipfile
root=Path(r'E:\比赛\nengzhihe'); zippath=root/'delivery/能智核_首轮复核包_非提交版.zip'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
frozen=json.loads((root/'output/protocol_frozen.json').read_text(encoding='utf-8'))
checks={p:sha(root/p)==h for p,h in frozen['files_sha256'].items()}
assert all(checks.values())
with zipfile.ZipFile(zippath) as z:
 manifest=json.loads(z.read('nengzhihe/_package/文件清单.json'))
 records=manifest['source_files']
 mismatches=[r['path'] for r in records if sha(root/r['path'])!=r['sha256']]
assert not mismatches,mismatches
out={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'first_package_sha256':sha(zippath),'first_package_member_files_verified':len(records),'first_frozen_files':checks,'original_files_unchanged':True,'copy_engine_sha256':sha(root/'round2/baseline_v1/engine.py'),'copy_calibration_sha256':sha(root/'round2/baseline_v1/data/calibration.json')}
(root/'round2/output/baseline_preservation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'preserved_files':len(records),'unchanged':True}))
