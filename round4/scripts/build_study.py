"""Prepare fixed matched tasks; independent human review is intentionally pending."""
from pathlib import Path
from collections import Counter
from datetime import datetime
import json,hashlib,copy,csv,statistics
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT.parent/'round2/data/dev'
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 dest=ROOT/'study';private=dest/'private';(private/'cases').mkdir(exist_ok=True)
 labels=json.loads((OLD/'labels.json').read_text(encoding='utf-8'))
 sources=['AHU_annual.csv','damper_stuck_025_annual.csv','damper_stuck_075_annual.csv','coi_leakage_025_annual.csv']
 days=sorted({x['day'] for x in labels.values() if x['perturbation']=='none'})[:2]
 tasks=[];keys=[]
 for group,source in enumerate(sources,1):
  for version,day in zip('AB',days):
   label=next(x for x in labels.values() if x['source_file']==source and x['day']==day and x['perturbation']=='none')
   original=json.loads((OLD/'cases'/(label['id']+'.json')).read_text(encoding='utf-8'))
   tid=f'T{group}{version}'
   case={k:copy.deepcopy(original[k]) for k in ['family','timestamps','series','units','sample_interval_minutes'] if k in original}
   case.update({'id':tid,'origin':'simulated','split':'study','title':'公开仿真核查任务 '+tid,'description':'只依据所提供点位核查，不能从任务编号推断故障。','perturbation':{'type':'none'}})
   if group==3:  # Same record-quality challenge on both matched, distinct dates.
    inds=list(range(100,112));case['timestamps'] += [case['timestamps'][i] for i in inds]
    for vals in case['series'].values():vals.extend([vals[i] for i in inds])
    case['perturbation']={'type':'exact_duplicate_rows','added_rows':12,'origin':'artificial_record_perturbation'}
   order=sorted(range(len(case['timestamps'])),key=lambda i:case['timestamps'][i])
   case['timestamps']=[case['timestamps'][i] for i in order]
   case['series']={k:[v[i] for i in order] for k,v in case['series'].items()}
   path=private/'cases'/(tid+'.json');write(path,case)
   # Reference facts from raw rows only. No diagnostics/policies import or output.
   ts=case['timestamps'];unique=sorted(set(ts));steps=[(datetime.fromisoformat(b)-datetime.fromisoformat(a)).total_seconds()/60 for a,b in zip(unique,unique[1:])]
   first={t:ts.index(t) for t in unique};ser=case['series'];inds=list(first.values())
   on=[i for i in inds if ser['SF_SPD_DM'][i]>=.99 and ser['RF_SPD_DM'][i]>=.99]
   strong=[i for i in on if abs(ser['OA_TEMP'][i]-ser['RA_TEMP'][i])>=3]
   closed=[i for i in on if ser['CHWC_VLV_DM'][i]<=.0001]
   facts={'rows':len(ts),'unique_rows':len(unique),'exact_repeats':len(ts)-len(unique),'actual_interval_minutes':sorted(set(steps)),
    'temperature_unit':case['units']['OA_TEMP'],'both_fans_on_minutes':len(on)*5,'on_with_temperature_difference_at_least_3C_minutes':len(strong)*5,
    'on_with_zero_coil_command_minutes_before_settling':len(closed)*5,'oa_command_range_during_on':[min(ser['OA_DMPR_DM'][i] for i in on),max(ser['OA_DMPR_DM'][i] for i in on)] if on else None,
    'first_on':ts[on[0]] if on else None,'last_on':ts[on[-1]] if on else None}
   keys.append({'task_id':tid,'source_file':source,'source_day':day,'source_label':label['label'],'source_case_id':label['id'],'input_sha256':digest(path),
    'independent_raw_facts':facts,'raw_facts_not_system_truth':True,
    'required_evidence':['E1_time_and_units','E2_quality_and_repair','E3_operating_window','E4_command_vs_response','E5_inspectability','E6_next_evidence'],
    'draft_acceptable_conclusions':['风阀疑点候选，仍需现场/测点核实','现有证据不足，不能排除风阀疑点'],
    'reviewer_must_resolve':'独立复核者根据原始曲线、单位、文档及所给参考表，逐任务圈定可接受结论、有效时段、必要补证与可接受替代答案；不得直接复制工作台输出。',
    'prohibited_attributions':['用控制指令当作实际阀位','仅凭参考内响应排除卡滞','仅凭本窗口确定卡滞开度','由持续制冷温降确认关阀泄漏','数据修正即认定设备正常'],
    'review_status':'pending'})
   tasks.append({'id':tid,'pair':group,'variant':version,'sha256':digest(path),'path':'private/cases/'+tid+'.json'})
 manifest={'status':'prepared_not_human_tested','selection_rule':'Take the first two chronological dates in the existing round2 development split, all four settings, without outcome-based selection. Duplicate-record challenge is applied identically to the two 75%-opening tasks. No repeated underlying case per participant.',
  'dates':days,'tasks':tasks,'matched_on':['source system','fault/source setting','same permitted signals and units','same checklist','same recording-quality challenge'],
  'not_assumed_equal':['weather','running duration','evidence strength','task difficulty'],
  'matching_review_required':True,'participants':0,'background_fields':['role','hvac_experience_band','csv_experience_band','previous_workbench_exposure']}
 write(private/'task_manifest.json',manifest);write(private/'answer_key_draft.json',{'status':'pending_independent_human_review','system_output_used_as_truth':False,'tasks':keys})
 rubric={'status':'pending_independent_human_review','items':[{'id':'E1_time_and_units','points':1,'criterion':'写明实际采样间隔与温度单位，不以记录数乘错标间隔。'},
 {'id':'E2_quality_and_repair','points':1,'criterion':'识别是否有重复/冲突，并说明去重只修数据。'},
 {'id':'E3_operating_window','points':1,'criterion':'用具体时段描述双风机和启动后工况，不把停机或全天均值当有效核验。'},
 {'id':'E4_command_vs_response','points':1,'criterion':'引用指令、混风温度及室外/回风温差，区分指令与实际位置。'},
 {'id':'E5_inspectability','points':1,'criterion':'给出有证据支持的候选或未决，解释限制，不从未发现直接推导正常。'},
 {'id':'E6_next_evidence','points':1,'criterion':'下一步明确点位、时段或现场动作，符合本任务缺口。'}],
 'omitted_evidence':'Each absent or substantively incorrect required item counts as one omission, range 0..6.',
 'wrong_attribution':'One or more unsupported causal assertions, counted per task; compare against independently approved acceptable alternatives. Source fault label alone must not force a conclusion that allowed observations cannot identify.',
 'timeout_seconds':300,'failure':'Timeout, missing submission or a critical unsupported attribution is a task failure. Report each component as well.',
 'time_analysis':'Cap all assigned task times at 300 seconds; missing tasks assigned 300 seconds and failure. Do not report speed only among successful completers.',
 'scoring':'Human score each item 0/1 plus wrong_attribution and rationale; blind scorers to condition where answer text allows. No LLM scoring or simulated participants.',
 'difficulty':'Independent reviewer checks pair matching before recruitment; if pairs change, regenerate and refreeze protocol and key before testing.'}
 write(private/'rubric.json',rubric)
 sequences={
 'S1':{'order':[1,2,3,4],'first_mode':'A','first_variant':'A'},
 'S2':{'order':[1,2,3,4],'first_mode':'B','first_variant':'A'},
 'S3':{'order':[4,3,2,1],'first_mode':'A','first_variant':'B'},
 'S4':{'order':[4,3,2,1],'first_mode':'B','first_variant':'B'}}
 for v in sequences.values():
  variant=v['first_variant'];other='B' if variant=='A' else 'A';mode=v['first_mode'];othermode='B' if mode=='A' else 'A'
  v['tasks']=[{'task_id':f'T{g}{variant}','mode':mode} for g in v['order']]+[{'task_id':f'T{g}{other}','mode':othermode} for g in v['order']]
 protocol={'title':'常规曲线表格与风阀核验工作台的任务对照','status':'pending_independent_review_and_recruitment','planned_participants':'团队拟招募5—10名真实人员，探索性实验，非已实现人数或功效保证。',
 'condition_A':'曲线、原始数值表、字段单位、相同检查清单、开发参考包络表及纸笔计算说明，无自动诊断。',
 'condition_B':'完全相同原始数据、曲线表格与清单，另提供当前工作台真实计算的质量、分支证据及核查卡。',
 'assignment':'按加入顺序循环分配S1..S4，不按参与者表现挑顺序。两阶段各四题，同一人不重复同一原始日工况。两阶段间休息3分钟。',
 'training':'两种条件各2分钟相同操作介绍；另有非测试示例。禁止在正式题间给答案反馈。',
 'sequences':sequences,'seconds_per_task':300,'primary_metrics':['含失败的封顶核查时间','关键证据遗漏0..6','错误归因比例','超时/未提交比例'],
 'analysis_unit':'先对每名参与者在A/B各四题汇总，再报告配对差值、每个任务对和顺序组。小样本仅探索性描述，不将8题当8名用户。',
 'participants_and_privacy':'仅化名编号和经验档，不收真实姓名、联系方式或雇主。自愿参加，可退出；实际招募由团队完成。真人数据默认不入Git。',
 'reference_precondition':'一名未参与本系统规则编写的复核者核查原始任务、答案及评分标准并签署哈希。该身份由团队负责核实。软件字段不是专家认证。',
 'reference_freeze':['private/answer_key_draft.json','private/rubric.json','private/task_manifest.json','private/protocol.json'],
 'no_result_claim':'当前无真人记录，不输出提效比例；测试软件自检不计参与者。'}
 write(private/'protocol.json',protocol)
 approval={'status':'pending','reviewer_code':'','reviewer_independent_of_implementation':False,'reviewed_utc':'','reviewed_task_ids':[],
  'checks':{'raw_signals_and_documentation':False,'matching_and_difficulty':False,'acceptable_conclusions_and_alternatives':False,'rubric_and_failure_rules':False,'no_system_output_as_truth':False},'notes':'','sha256':{f:digest(dest/f) for f in protocol['reference_freeze']}}
 write(dest/'admin/independent_review.json',approval)
 checklist=['核对时间列、实际间隔与单位','核对重复、缺失和冲突，说明修正范围','圈定双风机开启并已过启动段的时段','查看室外/回风温差、风阀指令与混风响应','区分指令和实际位置，检查参考适用性','判断是否缺少关阀/温差等可检验工况','分别记录数据状态与设备疑点','写明支持、限制及下一步点位/时段/现场动作']
 write(dest/'public/checklist.json',checklist)
 with (dest/'admin/scoring_template.csv').open('w',newline='',encoding='utf-8-sig') as f:
  csv.writer(f).writerow(['participant_id','task_id','E1_time_and_units','E2_quality_and_repair','E3_operating_window','E4_command_vs_response','E5_inspectability','E6_next_evidence','wrong_attribution','rater_code','rationale','approved_key_sha256'])
 print(json.dumps({'tasks':len(tasks),'dates':days,'participants':0,'independent_review':'pending'},ensure_ascii=False))
if __name__=='__main__':main()
