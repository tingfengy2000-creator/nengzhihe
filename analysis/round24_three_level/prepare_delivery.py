"""Summarize reviewed results and hash delivered evidence; no physical rerun."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'operation_planning/results/round24_public_validation'
read=lambda name:json.loads((OUT/name).read_text(encoding='utf-8'))

def main():
    room,cu,madrid=read('room_summary.json'),read('cu_summary.json'),read('madrid_summary.json')
    roomrows=[]
    for r in room['rooms']:
        for variant in ['untuned_evaluation','limited_fit_evaluation']:
            x=r[variant]
            roomrows.append({'house':r['house_id'],'variant':variant,'proxy_NMBE_percent':x['nmbe_percent_model_minus_proxy'],
              'proxy_CVRMSE_percent':x['cvrmse_percent'],'temperature_RMSE_c':x['temperature_rmse_c']})
    common=[{'label':'同期天气定义','url':'https://open-meteo.com/en/docs/historical-weather-api'}]
    receipt={'schemaVersion':1,'items':[
      {'id':'room-comparison','title':'房间级：未调参偏差明显，真值不足','queries':[{'id':'hyderabad-2019','source':{
        'label':'印度住宅数据v3（CC0）＋冻结模型',
        'links':[{'label':'原始数据及许可','url':'https://doi.org/10.6084/m9.figshare.16869439.v3'},
          {'label':'原论文及计量范围','url':'https://link.springer.com/article/10.1186/s42162-022-00225-4'}]+common,
        'files':[{'label':'room_summary.json'},{'label':'room_parameter_basis.json'},{'label':'room_limited_fit_freeze.json'}],
        'metricDefinitions':[{'label':'室温RMSE','definition':'后10天运行标签对应的实测室温与模型区间末状态RMSE；未调参和有限拟合分开。'},
          {'label':'代理电量误差','definition':'逐日家庭相电流增量代理与模型用电的NMBE和CV(RMSE)，采用显式n−1描述分母。'}],
        'filters':['户号：2、6、9','设备：单台非变频分体','选择：元数据与时序质量，未按拟合好坏选择'],
        'caveats':['家庭进线电流不是独立空调有功分表；230V、PF0.9是假设，另存±10%敏感性。',
          '逐房间面积、COP及控制设置不足；没有完整参数房间，不能称正式校准。',
          '只以此前9天选择共享U/热容；有限调参室温改善但两户电量代理误差变大。']},
        'reportingPeriod':'开发2019-05-10—18；评价2019-05-19—28，Asia/Kolkata',
        'rows':roomrows,'methods':[{'language':'python','code':'e = predicted_daily_kwh - proxy_daily_kwh\nnmbe = e.sum() / ((n - 1) * proxy_daily_kwh.mean()) * 100\ncvrmse = ((e**2).sum() / (n - 1))**0.5 / proxy_daily_kwh.mean() * 100'}]}]},
      {'id':'office-trend','title':'楼宇级：形状相符，温度敏感度偏高','queries':[{'id':'cu-floor2-2019','source':{
        'label':'CU-BEMS二层16路空调（CC BY 4.0）',
        'links':[{'label':'数据','url':'https://doi.org/10.6084/m9.figshare.11726517'},
          {'label':'原论文','url':'https://www.nature.com/articles/s41597-020-00582-3'}]+common,
        'files':[{'label':'cu_normalized_weekday_profile.csv'},{'label':'cu_complete_weekdays.csv'},{'label':'cu_daily_quality.csv'}],
        'metricDefinitions':[{'label':'归一化形状','definition':'每个小时除以同日24小时均值，再取198个共同完整工作日的平均曲线。'},
          {'label':'相对温度斜率','definition':'同日期日空调用电对日平均外温的OLS斜率除以平均日电量。'}],
        'filters':['范围：2019年二层，全部16路空调','纳入：198/261个完整工作日','剔除：63个缺测工作日，未补零'],
        'caveats':['没有楼层面积/设备冷量，只比较规模无关趋势。','温度斜率是未控制人员、湿度、日照和季节的关联，不是因果系数。']},
        'reportingPeriod':'2019年，Asia/Bangkok',
        'rows':[{'shape_r':cu['normalized_hourly_shape_correlation'],'normalized_RMSE':cu['normalized_shape_rmse'],
          'measured_slope_pct_per_c':cu['measured_relative_sensitivity']['relative_slope_per_c']*100,
          'model_slope_pct_per_c':cu['model_relative_sensitivity']['relative_slope_per_c']*100}],
        'methods':[{'language':'python','code':"profile = hourly_energy / hourly_energy.groupby(day).transform('mean')\nslope_relative = np.polyfit(daily_outdoor_temperature, daily_energy, 1)[0] / daily_energy.mean()"}]}]},
      {'id':'city-season','title':'城市级：3栋有冬季用气的行政建筑，季节趋势有限相符','queries':[{'id':'madrid-2024','source':{
        'label':'Ayuntamiento de Madrid月度总表（CC BY 4.0）',
        'links':[{'label':'官方数据与许可','url':'https://datos.gob.es/en/catalogo/l01280796-consumo-de-energia-en-edificios-municipales-datos-mensuales'}]+common,
        'files':[{'label':'madrid_building_months.csv'},{'label':'madrid_building_statistics.csv'},{'label':'madrid_building_selection.json'}],
        'metricDefinitions':[{'label':'季节超额','definition':'月有功电量减4/5/10/11月平均基线；图展示12个月正超额份额，相关性保留负增量。'},
          {'label':'CDD关联','definition':'每栋12个月有符号增量与同年CDD18的Pearson相关，统计三栋范围与中位数。'}],
        'filters':['建筑：行政类28个名称选3个','电表：同名、明确总表、全年12月完整','气表：同名、范围唯一、冬季1/2/12月有效且有正用气'],
        'caveats':['气表存在不证明主要以燃气供暖，夏季缺测燃气没有填零。',
          '季节超额可能含其他用电；两栋冬季正超额保留，不当成已知制冷。','最初全年气表完整筛选为零，在季节计算前改用冬季观测准入；修订和排除记录已保留。']},
        'reportingPeriod':'2024年相同12个月，Europe/Madrid，8784真实小时',
        'rows':[{'included_buildings':madrid['included_buildings'],'excluded_names':madrid['excluded_building_names'],
          'r_min':madrid['signed_increment_vs_cdd18_correlation']['min'],'r_median':madrid['signed_increment_vs_cdd18_correlation']['median'],
          'r_max':madrid['signed_increment_vs_cdd18_correlation']['max'],'summer_proxy_fraction_min':madrid['summer_positive_excess_fraction']['min'],
          'summer_proxy_fraction_max':madrid['summer_positive_excess_fraction']['max'],'model_summer_fraction':madrid['model_summer_cooling_fraction']}],
        'methods':[{'language':'python','code':'baseline = electricity_months[[4, 5, 10, 11]].mean()\nsigned_excess = electricity_months - baseline\npositive_fraction = signed_excess.clip(lower=0) / signed_excess.clip(lower=0).sum()\nr = corr(signed_excess, CDD18_by_month)'}]}]}
    ]}
    for item in receipt['items']:
        for query in item['queries']:
            query['columns']=[{'field':key,'label':key} for key in query['rows'][0]]
    (OUT/'inline_sources_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    manifest={'numeric_source_commit':read('run_manifest_all.json')['source_commit'],
      'request_source_commit':'7db47e3184a913f909f78e82c6fdffd8001914a8','recorded_utc':datetime.now(timezone.utc).isoformat(),
      'visual_review':{'status':'completed','pages_reviewed':4,'files':['figures/room_validation.pdf','figures/cu_validation.pdf','figures/madrid_validation.pdf','figures/公开数据验证.pdf'],
        'observed_repairs':['room temperature axis includes all daily means','CU tick labels simplified','Chinese numeric groups and punctuation kept together']},
      'additional_preparation_failures':['CLI py_compile did not expand Windows wildcard; explicit compileall passed',
        'inline delivery-manifest draft mixed relative/absolute paths; corrected in this script, no result files changed'],
      'files':{f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(OUT.rglob('*')) if f.is_file() and f.name!='delivery_manifest.json'}}
    (OUT/'delivery_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Delivered evidence:',len(manifest['files']),'hashed files; four pages visually reviewed')

if __name__=='__main__':main()
