"""Encode actual CUA browser captures; no fabricated interface or human records."""
from pathlib import Path
import json,subprocess,textwrap,hashlib
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'video/working';O=ROOT/'video/final'
capture=json.loads((W/'capture.json').read_text(encoding='utf-8'));frames=capture['frames']
assert len(frames)==360,'Three minutes at 2 sampled frames per second'
width,height=Image.open(W/'frames'/frames[0]['name']).size
def stamp(sec):
 h=int(sec//3600);m=int(sec%3600//60);s=sec%60
 return f'{h}:{m:02}:{s:05.2f}'
header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height+100}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,26,&H00FFFFFF,&H00FFFFFF,&H00192D27,&H00192D27,0,0,0,0,100,100,0,0,1,0,0,2,36,36,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
events=capture['events'];intervals=[]
for i,e in enumerate(events):
 start=next((j for j,f in enumerate(frames) if f['elapsed_ms']>=e['start_ms']),len(frames))/2
 end=next((j for j,f in enumerate(frames) if i+1<len(events) and f['elapsed_ms']>=events[i+1]['start_ms']),len(frames))/2
 text='\\N'.join(textwrap.wrap(e['caption'],42));header+=f'Dialogue: 0,{stamp(start)},{stamp(end)},Default,,0,0,0,,{text}\n'
 intervals.append({'start_seconds':start,'end_seconds':end,'caption':e['caption']})
(W/'captions.ass').write_text(header,encoding='utf-8-sig')
ff=next((ROOT/'runtime/video_deps').rglob('ffmpeg*.exe'))
target=O/'nengzhihe_actual_operation_3min.mp4';O.mkdir(exist_ok=True)
args=[str(ff),'-y','-hide_banner','-loglevel','warning','-framerate','2','-c:v','mjpeg','-i','frames/%05d.png','-vf',f'pad=ceil(iw/2)*2:ceil((ih+100)/2)*2:0:0:color=0x192d27,subtitles=captions.ass,fps=12','-c:v','libx264','-preset','medium','-crf','22','-pix_fmt','yuv420p','-t','180','-movflags','+faststart','-metadata','title=能智核 实际核查操作','-metadata','comment=Actual browser screenshots sampled at 2 fps; quiet inter-segment gaps removed. No simulated user study. Silent captioned demonstration.',str(target)]
subprocess.run(args,cwd=W,check=True)
meta={'duration_seconds':180,'sampled_frames':360,'sampling_fps':2,'output_fps':12,'size':[width,height+100],'has_audio':False,'source':'Actual local browser operation; no mock screens','editing':'Quiet gaps between capture segments removed; source frame order preserved. Captions added below the interface. This is not a response latency or human-value measurement.','raw_capture_manifest_sha256':hashlib.sha256((W/'capture.json').read_bytes()).hexdigest(),'video_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'chapters':intervals}
(O/'recording_provenance.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
(O/'演示说明.txt').write_text('三分钟实际操作演示（无配音，中文字幕）。\n界面来自本地运行程序的实际操作，约每秒两帧采样；去除步骤之间未录制的停留，保持源画面次序，追加底部说明字幕。并非真人实验，也不能用视频推断软件响应耗时。\n完整原始帧与时间记录保存在本地 video/working，缓存未清理。\n',encoding='utf-8')
print(json.dumps({'output':str(target),'duration':180,'bytes':target.stat().st_size},ensure_ascii=False))
