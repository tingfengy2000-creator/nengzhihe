"""Render source-backed figures with the bundled ReportLab runtime.

Figures depict measured records and observed coverage; no simulated prediction
is plotted as a calibrated result. See README for the two-runtime commands.
"""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import reportlab

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'operation_planning/results/round23_case_admission'
FIGURES=DATA/'figures'
WIDTH,HEIGHT=1000,700
BLUE='#156c91'
ORANGE='#be611a'
GRAY='#485463'


def read_csv(name):
    with (DATA/name).open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))


def header(c,title,subtitle):
    c.setFillColorRGB(1,1,1);c.rect(0,0,WIDTH,HEIGHT,fill=1,stroke=0)
    c.setFont('ArialBold',24);c.setFillColorRGB(.08,.17,.24);c.drawString(60,HEIGHT-60,title)
    c.setFont('Arial',12);c.setFillColorRGB(.24,.32,.38);c.drawString(60,HEIGHT-88,subtitle)


def axis(c,x,y,w,h,maximum,ticks=4,label=''):
    c.setFont('Arial',10)
    for i in range(ticks+1):
        value=maximum*i/ticks; yy=y+h*i/ticks
        c.setStrokeColorRGB(.85,.89,.91);c.line(x,yy,x+w,yy)
        tick=f'{value:.2f}'.rstrip('0').rstrip('.') if maximum < 10 else f'{value:,.0f}'
        c.setFillColorRGB(.25,.30,.35);c.drawRightString(x-10,yy-3,tick)
    c.setStrokeColorRGB(.3,.36,.4);c.line(x,y,x,y+h);c.line(x,y,x+w,y)
    c.setFont('Arial',11);c.drawString(x,y+h+15,label)


def bars(c,values,x,y,w,h,maximum,labels,colors=None):
    axis(c,x,y,w,h,maximum,label='kWh')
    step=w/len(values)
    for i,value in enumerate(values):
        c.setFillColor(colors[i] if colors else BLUE)
        c.rect(x+i*step+step*.14,y,step*.72,h*value/maximum,fill=1,stroke=0)
        c.setFont('Arial',10);c.setFillColor(GRAY);c.drawCentredString(x+(i+.5)*step,y-18,labels[i])


def note(c,y,lines):
    c.setFillColorRGB(.96,.97,.98);c.rect(60,y-16*len(lines)-12,880,16*len(lines)+24,fill=1,stroke=0)
    c.setFillColor(GRAY);c.setFont('Arial',11)
    for i,line in enumerate(lines):c.drawString(72,y-16*i,line)


def footer(c,text,page):
    c.setFont('Arial',9);c.setFillColor(GRAY);c.drawString(60,30,text);c.drawRightString(940,30,str(page))


def main():
    FIGURES.mkdir(parents=True,exist_ok=True)
    pdfmetrics.registerFont(TTFont('Arial',r'C:\Windows\Fonts\arial.ttf'))
    pdfmetrics.registerFont(TTFont('ArialBold',r'C:\Windows\Fonts\arialbd.ttf'))
    path=FIGURES/'public_measured_evidence.pdf'
    c=canvas.Canvas(str(path),pagesize=(WIDTH,HEIGHT),pageCompression=1)
    c.setTitle('Nengzhihe round23 - Public measured data eligibility')
    c.setAuthor('Nengzhihe project - public source analysis')
    cu=json.loads((DATA/'cu_summary.json').read_text(encoding='utf-8'))
    monthly=read_csv('cu_floor2_ac_observed_months.csv')
    header(c,'Measured AC records: missing time is not zero load',
           'CU-BEMS / Chamchuri 5 / floor 2 / 2019 / joint observations across 16 AC channels')
    values=[float(r['observed_all_16_ac_energy_kwh']) for r in monthly]
    coverage=[float(r['coverage_fraction'])*100 for r in monthly]
    bars(c,values,100,310,800,220,24000,[str(i) for i in range(1,13)],
         [BLUE if r['complete_month_energy_kwh'] else ORANGE for r in monthly])
    c.setFillColor(GRAY);c.setFont('Arial',11);c.drawString(100,275,'Month (2019)  /  orange: incomplete month; blue: complete observed month')
    axis(c,100,120,800,100,100,label='Joint valid minutes (%)')
    c.setStrokeColor(BLUE);c.setLineWidth(2)
    for i,v in enumerate(coverage):
        if i:c.line(100+(i-.5)*800/12,120+coverage[i-1],100+(i+.5)*800/12,120+v)
        c.setFillColor(BLUE);c.circle(100+(i+.5)*800/12,120+v,3,fill=1,stroke=0)
        c.setFillColor(GRAY);c.setFont('Arial',9);c.drawCentredString(100+(i+.5)*800/12,120+v-14,f'{v:.3f}%')
    c.setFont('Arial',11);c.drawString(100,90,f"Joint coverage: {cu['joint_coverage_fraction']*100:.2f}% ({cu['all_16_ac_joint_valid_minutes']:,} / 525,600 minutes).")
    c.drawString(100,72,'Only available samples are integrated: kW x 1/60 h. No complete annual energy total is asserted.')
    footer(c,'Source: DOI 10.6084/m9.figshare.11726517, v6 (CC BY 4.0); derived by project, no imputation.',1)
    c.showPage()

    rows=read_csv('cu_measured_week_hourly.csv')
    header(c,'A fixed week of actual submeter observations',
           'CU-BEMS / floor 2 / zone 2 AC2 / 1-7 July 2019 / source local-clock interpretation')
    axis(c,100,250,800,280,2.5,label='Hourly energy (kWh)')
    c.setStrokeColor(BLUE);c.setLineWidth(1.6)
    previous=None
    for i,row in enumerate(rows):
        value=None if row['complete_hour_energy_kwh']=='' else float(row['complete_hour_energy_kwh'])
        point=(100+(i+.5)*800/len(rows),250+280*value/2.5) if value is not None else None
        if point is not None and previous is not None:c.line(*previous,*point)
        previous=point
    c.setFont('Arial',11);c.setFillColor(GRAY)
    for d in range(7):c.drawCentredString(100+(d+.5)*800/7,228,f'Jul {d+1}')
    missing=sum(r['complete_hour_energy_kwh']=='' for r in rows)
    note(c,185,[f'Fixed chronological selection, without inspecting model error: 168 hourly intervals; {missing} incomplete hours.',
                'Only fully observed hours are drawn. Missing hourly values remain empty in the CSV.',
                'This device shares zone 2 with other AC units; its serviced area, capacity, COP and controls are not documented.',
                'No reference catalogue device or arbitrary 35 m2 room is substituted. This is measured evidence, not calibration.'])
    footer(c,'Source: 2019Floor2.csv, z2_AC2(kW); hourly sums derived from valid one-minute power samples.',2)
    c.showPage()

    madrid=json.loads((DATA/'madrid_summary.json').read_text(encoding='utf-8'))
    rows=read_csv('madrid_selected_12_months.csv')
    header(c,'One public building: 12 measured monthly records',
           'Madrid / Casa Consistorial - Casa de la Villa / 2024 / general active-electricity sensor')
    bars(c,[float(r['energy_kwh']) for r in rows],100,240,800,285,28000,[str(i) for i in range(1,13)])
    c.setFont('ArialBold',17);c.setFillColor(BLUE)
    c.drawString(100,565,f"Sum of 12 monthly meter values: {madrid['annual_meter_energy_kwh']:,.2f} kWh")
    note(c,182,['Selected deterministically from complete 2024 administrative-building general-meter records (lexical order).',
                'Electricity bills, invoice charges and AC-only submeters are not supplied in this source.',
                'Sensor is named general electricity; its exact physical boundary has not been independently audited.',
                'The current model covers cooling/dehumidification only. This total cannot establish model accuracy.'])
    footer(c,'Source: Ayuntamiento de Madrid monthly municipal energy dataset (CC BY 4.0); no model fit performed.',3)
    c.showPage();c.save()
    inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.glob('*.csv')}
    manifest={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'recorded_utc':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),
              'reportlab':reportlab.Version,'renderer':'ReportLab PDF; Poppler page rasterization separately recorded',
              'input_hashes':inputs,'pdf_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pages':3,
              'figure_scope':'public measured records and completeness; no fitted model or field-trial claim'}
    (FIGURES/'render_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Created {path.relative_to(ROOT)} (3 pages)')


if __name__=='__main__':main()
