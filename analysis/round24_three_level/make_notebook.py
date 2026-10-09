"""Executed companion reading saved results; does not rerun/tune the model."""
from __future__ import annotations
from contextlib import redirect_stdout
from datetime import datetime,timezone
import io,json,platform
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def main():
    cells=[];scope={};count=0
    def md(id,s):cells.append({'cell_type':'markdown','id':id,'metadata':{},'source':s.splitlines(True)})
    def code(id,s):
        nonlocal count
        count+=1;output=io.StringIO()
        with redirect_stdout(output):exec(compile(s,f'<round24:{id}>','exec'),scope)
        cells.append({'cell_type':'code','id':id,'metadata':{},'source':s.splitlines(True),'execution_count':count,
          'outputs':[{'output_type':'stream','name':'stdout','text':output.getvalue().splitlines(True)}]})
    md('summary','# 公开数据三层验证\n\n**趋势部分相符，房间绝对校准没有成立。** 产品源码冻结。\n这是已执行的结果伴随Notebook，读取5090真实结果；完整原始计算在`run_validation.py`，不是再次生成模型结果。\n')
    code('inputs','from pathlib import Path\nimport json,pandas as pd\nROOT=Path.cwd()\nwhile not (ROOT/"operation_planning").is_dir():\n    if ROOT==ROOT.parent:raise RuntimeError("Run inside repository")\n    ROOT=ROOT.parent\nOUT=ROOT/"operation_planning/results/round24_public_validation"\nread=lambda name:json.loads((OUT/name).read_text(encoding="utf-8"))\nrun=read("run_manifest_all.json")\nprint("Actual source_commit:",run["source_commit"])\nprint("Actual GPU query:",run["gpu_output"])\nprint("Model computation is CPU; no LLM called.")\n')
    md('method','## 方法与关键假设\n\n房间：3个单空调房，19天。9个开发日只选择一次共享U/热容；10个后段评价日。电流是家庭相电流，代理量230V/PF0.9，不是真实空调分表。楼宇只比198个共同完整工作日的归一化形状；城市只比3栋全年电表完整、有冬季气表的行政建筑。全部缺测不补0。详细来源、假设、失败与准入修订在README/protocol.json。\n')
    code('rooms','r=read("room_summary.json")\nrows=[]\nfor room in r["rooms"]:\n    for variant in ["untuned_evaluation","limited_fit_evaluation"]:\n        m=room[variant]\n        rows.append({"house":room["house_id"],"variant":variant,"days":m["n_days"],"proxy_NMBE_pct":m["nmbe_percent_model_minus_proxy"],"proxy_CVRMSE_pct":m["cvrmse_percent"],"room_T_RMSE_C":m["temperature_rmse_c"]})\nprint(pd.DataFrame(rows).round(4).to_string(index=False))\nprint("Individually complete room physical parameter sets:",r["rooms_with_individually_complete_physical_parameters"])\n')
    md('room-chart','![房间：电量代理与室温](../../operation_planning/results/round24_public_validation/figures/room_validation.png)\n\n有限调参室温降低，但两户电量代理误差变大；不宣称总体精度提升。\n')
    code('cu','cu=read("cu_summary.json")\nprint("Accepted weekdays:",cu["accepted_weekdays"],"of",cu["all_weekdays"])\nprint("Shape r:",cu["normalized_hourly_shape_correlation"])\nprint("Measured relative slope per C:",cu["measured_relative_sensitivity"]["relative_slope_per_c"])\nprint("Model relative slope per C:",cu["model_relative_sensitivity"]["relative_slope_per_c"])\n')
    md('cu-chart','![楼宇：形状及温度关联](../../operation_planning/results/round24_public_validation/figures/cu_validation.png)\n\n只验证规模无关的趋势；并非人员、季节因素控制后的因果敏感度。\n')
    code('madrid','madrid=read("madrid_summary.json")\nprint("Included/excluded:",madrid["included_buildings"],madrid["excluded_building_names"])\nprint(pd.read_csv(OUT/"madrid_building_statistics.csv")[["building","signed_increment_cdd18_correlation_12_months","summer_positive_excess_fraction","winter_positive_excess_fraction"]].round(4).to_string(index=False))\nprint("Gas boundary:",madrid["gas_boundary"])\n')
    md('madrid-chart','![城市：季节分布](../../operation_planning/results/round24_public_validation/figures/madrid_validation.png)\n\n保留负增量和冬季正超额。不能把正超额或燃气表存在等同于真实空调制冷量。\n')
    code('checks','v=read("verification.json")\nprint("Analysis contract/reconciliation checks:",v["count"],"passed:",v["all_passed"])\nprint("These are NOT accuracy or savings validations.")\n')
    md('takeaways','## 可支持与不可支持的结论\n\n完成公开数据三层对照及冻结模型局限检查；部分日内/季节形状符合，默认温度敏感度偏高，房间室温偏差明显。没有参数完整的房间与独立空调有功分表，不能说已校准、真实节能或已形成现场精度。\n')
    obj={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'},
      'language_info':{'name':'python','version':platform.python_version()},
      'execution_engine':'CPython executes reviewed result-reading cells sequentially; real stdout captured, no Jupyter kernel and no model rerun',
      'executed_utc':datetime.now(timezone.utc).isoformat()},'cells':cells}
    p=Path(__file__).parent/'public_validation.ipynb';p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved',count,'executed result-reading cells')

if __name__=='__main__':main()
