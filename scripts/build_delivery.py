"""Post-evaluation reporting and reproducible demonstration exports; no retuning."""
import collections,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import ROOT
from policies import run_case
from freeze import sha
from run_benchmark import verify

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,o): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def main():
    freeze=read(ROOT/'output/protocol_frozen.json');verify(freeze)
    benchmark=read(ROOT/'output/benchmark.json'); rows=read(ROOT/'output/evaluation_v1/scored_rows.json')
    out=ROOT/'output/demos';out.mkdir(parents=True,exist_ok=True); demos=[]
    for cid,name in [('NZH-CFF0E57369E1','01_真实建筑用能回放'),('NZH-90C933F3C475','02_仿真机组正常核验'),('NZH-76889C2BA896','03_记录修正后继续核查')]:
        case=read(ROOT/'data/cases'/(cid+'.json')); r=run_case(case,'fixed',4,save=False);write(out/(name+'.json'),r)
        entry={'name':name,'case_id':cid,'origin':case['origin'],'perturbation':case['perturbation'],'steps':[x['action'] for x in r['steps']],
               'query_units':r['cost']['query_units'],'verdict':r['final']['label'],'record_count':r['final']['quality']['rows'],'duplicates':r['final']['quality']['duplicates']}
        if cid=='NZH-76889C2BA896':
            repaired=run_case(case,'fixed',4,repair=True,save=False);write(out/(name+'_修正后.json'),repaired)
            assert repaired['final']['quality']['duplicates']==0 and repaired['final']['label']==r['final']['label']=='damper_stuck'
            entry['after_repair']={'record_count':repaired['final']['quality']['rows'],'duplicates':0,'verdict':repaired['final']['label']}
        demos.append(entry)
    write(out/'manifest.json',demos)
    full=[r for r in rows if r['strategy']=='full_information']
    breakdown={label:dict(collections.Counter(r['prediction'] for r in full if r['truth']==label)) for label in ['normal','damper_stuck','coil_leakage']}
    reasons=collections.Counter()
    for r in full:
        if r['prediction']!='unresolved':continue
        run=read(ROOT/'output/evaluation_v1/predictions'/f"{r['case_id']}__full_information__b4.json")
        d=run['final'];reasons[d['status']+'|'+json.dumps(d.get('rule_evidence',{}),sort_keys=True)]+=1
    write(ROOT/'output/posthoc_failure_analysis.json',{'status':'posthoc_descriptive_only_no_retuning','full_information_by_true_class':breakdown,'unresolved_rule_states':dict(reasons),
       'limitations':'Same heldout records cannot serve as a fresh test set after analysis. These counts do not establish causal failure mechanisms.'})
    first=ROOT/'output/evaluation_v1/benchmark_first_run.json'
    if not first.exists(): write(first,benchmark)
    lines=['能智核：公共建筑用能异常核验工作台｜首轮交付说明','',
      '定位与结论','保留能智核、智慧能源与环境方向。当前建议继续保留可复现核验工作台，收缩大模型主动补证及自动故障识别的创新表述。以现有留出证据，尚不足以宣称具备争取高名次所需的稳定技术优势。',
      '项目在独立nengzhihe目录，未修改乡艺有据。前端为原生HTML/CSS/JavaScript，后端为Python标准库HTTP服务及NumPy；本地Qwen3-4B只选择证据动作，所有测量、特征和判断由程序产生。',
      '', '三个可复现演示','1. BDG2真实建筑电表：回放历史用能、天气和同小时历史参考；只提供核查线索，不给设备故障结论或节能收益。',
      '2. LBNL正常仿真机组：按记录、混风、盘管证据完成有限候选范围的正常核验。正常不是整栋楼或所有故障类型的保证。',
      '3. LBNL故障仿真叠加明确标注的人为重复记录：300条→288条，重复12→0，修正后风阀卡滞候选继续保留；修记录不等于修设备。',
      '', '预先冻结的实验','主预算4，次要预算2/3；四种策略使用相同证据池、共同初筛摘要、共同数值诊断规则。全部信息参照实付4次查询，不放到低预算免费比较。',
      '一项数据查询=读取一组已存在的离线证据，不等同于实际数据库延迟或人民币。此次现场补采为0，真实补采成本未知，没有测试远程控制或现场传感器。',
      '开发阈值由开发日期校准，固定次序采用留一开发日选择。代码、提示词客户端、阈值、策略、模型配置、封存清单在第一次评测读取前冻结；420次预测保存完毕后才读取评测标签。',
      '数据准备程序当然处理过原始标签，诊断开发与策略看不到留出标签；本地hash与记录支持复核，不构成对盲性的外部公证。',
      '', '主预算4结果（未决计入总分母）','策略：正确/42；错判；未决；平均查询；平均运行毫秒']
    names={'fixed':'固定流程','adaptive_rule':'自适应规则','local_model':'本地模型','full_information':'完整信息'}
    for m in benchmark['metrics']:
        if m['budget']==4:lines.append(f"{names[m['strategy']]}：{m['correct']}/42；{m['wrong']}；{m['unresolved']}；{m['avg_queries']:.3f}；{m['avg_latency_ms']:.3f}")
    lines += ['四法主预算正确率均为23.81%，覆盖率均为23.81%；0次错判同时伴随32次未决，不能解释为100%准确率。',
      '本地模型相对自适应规则正确数增加0，平均查询反而增加0.048，平均延时增加约640毫秒。预算2时规则正确6条、模型1条；预算3均正确10条，模型也未节省查询。没有观察到模型主动选择的实际优势。',
      '42条记录=21个基础日工况×2种记录形态，仅7个日期块、1套仿真机组。可运行时长足够的36条中也只正确10条，其余26条未决；问题不只是停机案例。',
      '评测后按真实类别汇总（描述性分析，不据此调参）：'+json.dumps(breakdown,ensure_ascii=False),
      '', '来源审计与适用范围','BDG2是实测电表回放；LBNL是有标签仿真；人为扰动仅是后加重复记录。两条数据线不拼成真实楼宇故障定位证据。',
      '实际风阀位置、实际水阀位置以及可能直接暴露仿真注入状态的通道已剔除；只用控制指令与温度响应。静压测点存在单位冲突，也予以排除。',
      'LBNL四个不同标称泄漏程度文件内容完全相同，审计后仅取一个代表；不把它们当成独立样本，不宣称泄漏严重度泛化。',
      '开发日可分的温度响应规则在新日期/不同工况上覆盖不足；本轮没有以加模型、扩大Agent或调低阈值掩盖失败。',
      '', '继续与收缩','继续：保留三演示、原始来源审计、记录质量与设备疑点双状态、逐步证据和可导出记录。自适应规则作为默认路线，本地模型保留为可关闭的实验选项。',
      '收缩：不写“智能体显著提高核验效率”“高精度故障定位”“跨楼宇泛化”“已节能X%”。节能机会只展示基线偏离供筛查，不计收益。',
      '下一次投入条件：先增加跨季节/跨系统的新开发案例与未经查看的新评测集，解决规则覆盖不足；获得真实BMS或运维人员回溯证据后再验证核查价值。维持当前轻量架构。',
      '若新增独立验证仍无优势，以可追溯数据核验和人工复核工作流定位参赛，不以大模型性能为中心卖点。当前保留为备选，不据此声称已有夺奖把握。',
      '', '比赛材料状态','已按四份上传文件的章节、字数上限和匿名边界准备简表、说明书、商业计划书结构化底稿；指标只取本轮主预算结果。姓名、单位、电话及未明确的匿名冲突保留待核对。',
      '当前环境缺少官方DOCX渲染工具所需LibreOffice。交付底稿及格式/字数校验；不把未完成渲染核验的Word文件标为可提交。无试点、合作、营收、节能收益的虚构记录。',
      '', '运行与复核','运行scripts/start.ps1后打开http://127.0.0.1:18190；停止用scripts/stop.ps1（只认领本项目进程）。',
      '首轮原始结果：output/evaluation_v1/benchmark_first_run.json；420条预测、分数、执行回执均保留。',
      '冻结后不要再运行prepare_engine或修改冻结文件。新--output-dir仅是复现实验，不能称新的未见测试；先保留首轮快照，因为现有评测脚本也会更新output/benchmark.json。',
      '运行环境与模型官方SHA、版本、source manifest和文档模板哈希另附。Windows路径/字体/运行环境需在其他机器安装相应依赖；贪心本地推理不保证跨GPU逐字完全一致。']
    (ROOT/'output/首轮交付说明.txt').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'demos':demos,'full_information_by_true_class':breakdown,'unresolved_states':dict(reasons)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
