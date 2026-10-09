"""Source-backed scientific plots and a one-page Chinese evidence summary.

Uses existing bundled ReportLab/Pillow rather than installing a plotting stack.
All plot coordinates derive from committed comparison tables. No AI images.
"""
from __future__ import annotations
import json, math, re
from pathlib import Path
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'operation_planning/results/round24_public_validation'
FIG=OUT/'figures'
BLUE='#087D9E';ORANGE='#C15D21';GRAY='#71808E';GREEN='#488545'
W,H=1100,750

def text(c,x,y,s,size=11,color='#233341',font='Arial'):
    c.setFont(font,size);c.setFillColor(HexColor(color));c.drawString(x,y,str(s))
def base(c,title,subtitle):
    text(c,45,H-44,title,22,font='ArialBold');text(c,45,H-68,subtitle,11)
def plot(c,x,y,w,h,xv,series,xlim,ylim,xlabel,ylabel,xticks=None,yticks=None,scatter=False):
    xl,xh=xlim;yl,yh=ylim
    xp=lambda v:x+(v-xl)/(xh-xl)*w;yp=lambda v:y+(v-yl)/(yh-yl)*h
    c.setLineWidth(.5)
    xticks=xticks if xticks is not None else [xl+(xh-xl)*i/4 for i in range(5)]
    yticks=yticks if yticks is not None else [yl+(yh-yl)*i/4 for i in range(5)]
    for v in yticks:
        c.setStrokeColor(HexColor('#E1E7EB'));c.line(x,yp(v),x+w,yp(v))
        c.setFillColor(HexColor('#53626E'));c.setFont('Arial',9);c.drawRightString(x-6,yp(v)-3,f'{v:.2f}'.rstrip('0').rstrip('.'))
    for v in xticks:
        c.setFillColor(HexColor('#53626E'));c.setFont('Arial',9);c.drawCentredString(xp(v),y-14,f'{v:g}')
    c.setStrokeColor(HexColor('#65747F'));c.line(x,y,x+w,y);c.line(x,y,x,y+h)
    text(c,x,y+h+10,ylabel,10);text(c,x,y-33,xlabel,10)
    for values,color in series:
        c.setStrokeColor(HexColor(color));c.setFillColor(HexColor(color));c.setLineWidth(1.7)
        for i,v in enumerate(values):
            if not math.isfinite(float(v)):continue
            if scatter:c.circle(xp(xv[i]),yp(v),1.6,stroke=0,fill=1)
            else:
                if i and math.isfinite(float(values[i-1])):c.line(xp(xv[i-1]),yp(values[i-1]),xp(xv[i]),yp(v))
                c.circle(xp(xv[i]),yp(v),1.9,stroke=0,fill=1)
def legend(c,items,x,y,size=10,gap=220):
    for i,(label,col) in enumerate(items):
        xx=x+i*gap;c.setStrokeColor(HexColor(col));c.setLineWidth(2);c.line(xx,y+3,xx+18,y+3);text(c,xx+24,y,label,size)

def room_figure():
    d=pd.read_csv(OUT/'room_daily_comparison.csv');t=pd.read_csv(OUT/'room_daily_operating_temperature.csv')
    c=canvas.Canvas(str(FIG/'room_validation.pdf'),pagesize=(W,H));base(c,'Room-level evidence: substantial untuned mismatch',
      'Hyderabad / 2019-05-10 to 28 IST / first 9 days development, last 10 dates evaluation / three single-AC homes')
    legend(c,[('Household-current incremental proxy',GRAY),('Untuned frozen model',BLUE),('Limited fit: shared U/mass',ORANGE)],55,650,gap=320)
    for row,i in enumerate([2,6,9]):
        y=467-row*191
        ud=d[(d.house_id==i)&(d.variant=='untuned')];fd=d[(d.house_id==i)&(d.variant=='limited_fit')]
        ut=t[(t.house_id==i)&(t.variant=='untuned')];ft=t[(t.house_id==i)&(t.variant=='limited_fit')]
        days=list(range(10,29));maximum=max(ud.proxy_kwh.max(),ud.model_kwh.max(),fd.model_kwh.max())*1.08
        plot(c,85,y,425,127,days,[(ud.proxy_kwh.tolist(),GRAY),(ud.model_kwh.tolist(),BLUE),(fd.model_kwh.tolist(),ORANGE)],(10,28),(0,maximum),'May day / evaluation starts 19',f'House {i}: daily kWh vs PROXY reference',[10,14,18,22,26,28])
        plot(c,640,y,400,127,days,[(ut.measured_c.tolist(),GRAY),(ut.model_c.tolist(),BLUE),(ft.model_c.tolist(),ORANGE)],(10,28),(20,40),'May day / same operating samples','Mean ON-period room temperature (C)',[10,14,18,22,26,28],[20,25,30,35,40])
        # Frozen chronological division drawn without switching model parameters.
        for x,w in [(85,425),(640,400)]:
            xx=x+(18.5-10)/18*w;c.setDash(3,3);c.setStrokeColor(HexColor('#AAB3BA'));c.line(xx,y,xx,y+127);c.setDash()
    text(c,45,32,'No AC submeter, measured PF/COP or individual room area. Energy proxy uses 230V / PF0.9; +/-10% recorded separately.',10)
    text(c,45,16,'Reported homeowner setpoint + labelled ON/OFF; same frozen equations. A lower fitted room-T error is not calibrated AC energy.',10)
    c.showPage();c.save()

def cu_figure():
    s=json.loads((OUT/'cu_summary.json').read_text(encoding='utf-8'));p=pd.read_csv(OUT/'cu_normalized_weekday_profile.csv');d=pd.read_csv(OUT/'cu_complete_weekdays.csv')
    c=canvas.Canvas(str(FIG/'cu_validation.pdf'),pagesize=(W,H));base(c,'Office floor: timing agrees, temperature response differs',
      'CU-BEMS / floor 2 / 16 AC channels / 198 fully observed weekdays out of 261 / Bangkok 2019 ERA5 city reference')
    legend(c,[('Measured floor AC',BLUE),('Default office room model',ORANGE)],70,628,gap=340)
    plot(c,90,300,430,275,p.hour.tolist(),[(p.measured_kwh.tolist(),BLUE),(p.model_kwh.tolist(),ORANGE)],(0,23),(0,2.9),
      'Hour (Asia/Bangkok)','Each hour / same-day mean; weekday average',[0,4,8,12,16,20,23])
    measured=d.measured_kwh/d.measured_kwh.mean();model=d.model_kwh/d.model_kwh.mean()
    plot(c,650,300,390,275,d.outdoor_temp_c.tolist(),[(measured.tolist(),BLUE),(model.tolist(),ORANGE)],
      (float(d.outdoor_temp_c.min())-.3,float(d.outdoor_temp_c.max())+.3),(0,2.3),'Daily mean outdoor T (C)','Daily AC energy / accepted-day average',xticks=[23,26,29,32,34],scatter=True)
    text(c,90,235,f"24-point profile correlation: {s['normalized_hourly_shape_correlation']:.3f}; normalized RMSE: {s['normalized_shape_rmse']:.3f}",13)
    text(c,90,205,f"Relative daily slope: measured {s['measured_relative_sensitivity']['relative_slope_per_c']*100:.2f}%/C; model {s['model_relative_sensitivity']['relative_slope_per_c']*100:.2f}%/C",13)
    text(c,90,167,'63 incomplete weekdays excluded; missing channels are never zero-filled. Both methods use the same accepted dates.',11)
    text(c,90,139,'No zone area, unit capacity or true operating schedule: normalization supports trend comparison only.',11)
    text(c,90,111,'OLS associations include occupancy, humidity, solar and season effects. Correlation does not establish causal sensitivity.',11)
    text(c,45,28,'Sources: CU-BEMS DOI 10.6084/m9.figshare.11726517 v6 (CC BY 4.0); Open-Meteo ERA5 (CC BY 4.0). No floor sizing fit.',10)
    c.showPage();c.save()

def madrid_figure():
    d=pd.read_csv(OUT/'madrid_building_months.csv');m=pd.read_csv(OUT/'madrid_model_months.csv');s=pd.read_csv(OUT/'madrid_building_statistics.csv')
    colors=[BLUE,GREEN,GRAY];series=[]
    c=canvas.Canvas(str(FIG/'madrid_validation.pdf'),pagesize=(W,H));base(c,'Gas-metered offices: seasonal agreement has clear limits',
       'Madrid / local-calendar 2024 / 3 administrative buildings; 25 names excluded / electricity complete, winter gas observed')
    labels=[(name.replace('í','i'),col) for (name,g),col in zip(d.groupby('building',sort=True),colors)]+[('Default room model',ORANGE)]
    legend(c,labels,55,635,size=10,gap=260)
    for (name,g),col in zip(d.groupby('building',sort=True),colors):series.append(((g.positive_excess_fraction*100).tolist(),col))
    series.append(((m.model_cooling_fraction*100).tolist(),ORANGE))
    plot(c,90,255,910,330,list(range(1,13)),series,(1,12),(0,40),'Month (2024, Europe/Madrid)',
      'Month / annual positive excess (%) vs model cooling (%)',list(range(1,13)),[0,10,20,30,40])
    text(c,90,189,'Electricity baseline: mean April / May / October / November. Positive excess is a seasonal proxy, NOT AC metering.',12)
    text(c,90,158,'All 12 months retained: winter excess in 2 buildings remains visible; gas meters do not prove gas-dominant heating.',12)
    values=s.signed_increment_cdd18_correlation_12_months
    text(c,90,124,f'Signed monthly excess vs CDD18: r range {values.min():.3f} to {values.max():.3f}; median {values.median():.3f} (12 points/building).',12)
    text(c,90,93,'Missing summer gas stays missing. No model sizing, absolute electricity-error or energy-savings claim.',12)
    text(c,45,28,'Source: Madrid municipal monthly dataset snapshot (CC BY 4.0), same round23 hash; Open-Meteo ERA5 reference weather.',10)
    c.showPage();c.save()

def wrap_cn(c,s,x,y,width,font='CN',size=10,leading=16):
    line=''
    tokens=re.findall(r'[A-Za-z0-9_./%+−±—:()·-]+[℃㎡]?|.',s)
    punctuation='，。；、！：）'
    for i,ch in enumerate(tokens):
        tail=tokens[i+1] if i+1<len(tokens) and tokens[i+1] in punctuation else ''
        if line and pdfmetrics.stringWidth(line+ch+tail,font,size)>width:
            text(c,x,y,line,size,font=font);y-=leading;line=ch
        else:line+=ch
    if line:text(c,x,y,line,size,font=font);y-=leading
    return y

def summary_pdf():
    c=canvas.Canvas(str(FIG/'公开数据验证.pdf'),pagesize=(595.28,841.89));c.setTitle('能智核：公开数据三层验证（未校准）')
    text(c,35,802,'公开数据验证｜冻结模型的三层证据',19,font='CN')
    wrap_cn(c,'结果支持部分曲线与季节趋势；房间用电真值不足且室温偏差明显，不支持“已校准”或“节能收益已验证”。',35,774,520,size=10.5)
    texts=[
      ('房间级｜3户 × 19天（先报告未调参）',
       '海得拉巴2019年5月10—28日，户号2/6/9。后10天未调参室温RMSE为3.80/5.94/2.90℃；电量代理NMBE为+30.82%/+37.38%/−15.26%，CV(RMSE)为40.40%/39.30%/23.86%。仅以此前9天选择一组U/热容，室温降至3.30/5.09/2.26℃，但两户电量代理误差变大。没有逐房间面积或空调分表；230V、PF0.9和±10%换算敏感性明示，不能报告真实空调校准误差。','room_validation'),
      ('楼宇级｜曼谷办公楼二层：198个完整工作日',
       '16路空调，261个工作日中剔除63个缺测日。按同日均值归一化的24小时曲线相关r=0.948、RMSE=0.404；逐日相对温度斜率实测5.69%/℃，默认办公房间模型9.73%/℃。验证日内时间形状和关联方向，不验证楼层规模或绝对精度，也不能把未控制的人员、湿度和季节影响当成因果温度系数。','cu_validation'),
      ('城市级｜马德里2024年：3栋电/气范围明确的行政建筑',
       '28个行政建筑名称纳入3个、剔除25个；全年电表完整，冬季三个月有燃气读数。以4/5/10/11月平均电量作基线，保留12个月正超额分布和负增量。增量与CDD18相关r=0.763—0.936（中位0.783）；夏季占年度正超额56.7%—77.2%，模型74.1%。两栋仍有冬季超额，燃气计量不证明主要以燃气供暖；仅支持有限季节趋势。','madrid_validation')]
    for (title,body,img),top in zip(texts,[722,503,284]):
        text(c,35,top,title,12,font='CN')
        png=FIG/(img+'.png')
        if png.exists():c.drawImage(str(png),35,top-151,width=200,height=136,mask='auto')
        wrap_cn(c,body,249,top-25,310,size=9.2,leading=14)
    wrap_cn(c,'公开许可：海得拉巴figshare v3为CC0；CU-BEMS、马德里、Open-Meteo为CC BY 4.0。完整定义、逐例表、三张大图、源码版本和哈希见同目录及analysis/round24_three_level/README.md。',35,50,525,size=8,leading=11)
    c.showPage();c.save()

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--summary',action='store_true');args=p.parse_args()
    FIG.mkdir(parents=True,exist_ok=True)
    pdfmetrics.registerFont(TTFont('Arial',r'C:\Windows\Fonts\arial.ttf'))
    pdfmetrics.registerFont(TTFont('ArialBold',r'C:\Windows\Fonts\arialbd.ttf'))
    pdfmetrics.registerFont(TTFont('CN',r'C:\Windows\Fonts\simsun.ttc',subfontIndex=0))
    if args.summary:summary_pdf()
    else:room_figure();cu_figure();madrid_figure()
    print('Rendered '+('one-page Chinese summary' if args.summary else 'three independent source-backed figures'))

if __name__=='__main__':main()
