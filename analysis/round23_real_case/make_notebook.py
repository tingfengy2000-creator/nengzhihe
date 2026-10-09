"""Execute reviewed analysis cells and save an ordinary ipynb companion.

Uses the existing Python interpreter, with no Jupyter server/dependency install.
Metadata discloses the execution engine; outputs are captured actual stdout.
"""
from __future__ import annotations
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import platform

ROOT=Path(__file__).resolve().parents[2]


def main():
    cells=[]
    scope={}
    count=0
    def md(name,text):
        cells.append({'cell_type':'markdown','id':name,'metadata':{},'source':text.splitlines(True)})
    def code(name,text):
        nonlocal count
        count+=1
        stream=io.StringIO()
        started=datetime.now(timezone.utc).isoformat()
        with redirect_stdout(stream):exec(compile(text,f'<round23:{name}>','exec'),scope)
        cells.append({'cell_type':'code','id':name,'metadata':{'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat()},
                      'source':text.splitlines(True),'execution_count':count,
                      'outputs':[{'output_type':'stream','name':'stdout','text':stream.getvalue().splitlines(True)}]})
    md('purpose','# 公开真实案例准入\n\n实际测量已经取得；模型校准尚未成立。后端冻结，未进行模型计算或拟合。\n本Notebook只分析两个公开资料快照，数据源、许可和完整命令见README。\n')
    code('root','from pathlib import Path\nimport sys, json, pandas as pd\nROOT = Path.cwd()\nwhile not (ROOT / "operation_planning").is_dir():\n    if ROOT == ROOT.parent: raise RuntimeError("Open notebook inside the repository")\n    ROOT = ROOT.parent\nif str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))\nDATA = ROOT / "operation_planning/results/round23_case_admission"\nprint("Source scope: CU-BEMS floor 2 / 2019; Madrid one general meter / 2024")\n')
    code('audit','from analysis.round23_real_case.inspect_sources import main as inspect\nresult = inspect()\n')
    code('monthly','m = pd.read_csv(DATA / "madrid_selected_12_months.csv")\nprint(m[["month", "energy_kwh"]].to_string(index=False))\nprint("Sum(kWh):", m.energy_kwh.sum())\nc = pd.read_csv(DATA / "cu_floor2_ac_observed_months.csv")\nprint(c[["month", "jointly_valid_ac_minutes", "coverage_fraction", "complete_month_energy_kwh"]].to_string(index=False))\n')
    code('limits','print("Calibration:", result["status"])\nprint("Thermal model runs:", result["model_run_count"])\nprint("Fitting runs:", result["model_fitting_count"])\nprint("Accuracy metrics:", result["model_accuracy_metrics"])\nprint(result["reason"])\n')
    md('measured-figures','## 实测图表\n\n以下图来自相同CSV，不包含模型预测：\n\n![CU实际覆盖率与电量](../../operation_planning/results/round23_case_admission/figures/measured_page-1.png)\n\n![实际空调周](../../operation_planning/results/round23_case_admission/figures/measured_page-2.png)\n\n![一个市政建筑12个月](../../operation_planning/results/round23_case_admission/figures/measured_page-3.png)\n\nCU缺测不等于0；月度总表不等于空调计量；没有已校准精度或现场节能主张。\n')
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'},
              'language_info':{'name':'python','version':platform.python_version()},
              'execution_engine':'Reviewed cells executed sequentially by CPython exec; actual stdout captured, no notebook kernel or model used.',
              'created_utc':datetime.now(timezone.utc).isoformat()},'cells':cells}
    path=ROOT/'analysis/round23_real_case/public_case_admission.ipynb'
    path.write_text(json.dumps(notebook,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Wrote executed companion with {count} real output cells.')


if __name__=='__main__':main()
