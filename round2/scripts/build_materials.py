"""Generate anonymous editable competition drafts from retained official templates.

Only round2/materials is written. This script reads aggregate benchmark output,
never cases, labels, or hidden holdout payloads. Unrendered documents are explicitly
marked 待视觉复检 under the user's request; no formal-submission claim is made.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, math, os, re, shutil, subprocess
from pathlib import Path
from datetime import date, timedelta
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree

ROOT=Path(__file__).resolve().parents[1]
M=ROOT/'materials'
SOURCES=M/'references'
BASE_SOURCES=ROOT.parent/'materials/references'
RUNTIME=Path(os.environ.get('NENGZHIHE_BUNDLED_DEPENDENCIES',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies')))
SKILL=Path(os.environ.get('NENGZHIHE_DOCUMENT_SKILL',str(Path.home()/'.codex/plugins/cache/openai-primary-runtime/documents/26.921.10847/skills/documents')))
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W='{'+NS['w']+'}'
PROJECT='能智核 公共建筑用能异常核验工作台'
TRACK='定向赛道 智慧能源与环境'
NAMES={'brief':'附件1_项目简表','technical':'附件2_项目说明书','commercial':'附件3_项目商业计划书'}
LIMITS={'brief':{'background':300,'idea':300,'solution':600,'business':300},
        'technical':{'rationale':2000,'innovation':3000,'implementation':3000,'prospect':500},
        'commercial':{'overview':200,'team':200,'product':2000,'market':2000,'model':2000,'economics':500}}
HEADS={'brief':{'background':'项目背景','idea':'立项思路','solution':'解决方案','business':'商业模式和预期效益'},
 'technical':{'rationale':'一、立项依据','innovation':'二、项目创新内容','implementation':'三、实施方案','prospect':'四、应用前景分析'},
 'commercial':{'overview':'一、项目方案概述','team':'二、项目团队','product':'三、项目产品（服务）化','market':'四、项目产品（服务）市场与竞争','model':'五、商业模式','economics':'六、预期经济效益分析'}}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def count(text):return len(re.sub(r'\s+','',text))
def paragraphs(value):
    if isinstance(value,str):return [value]
    if isinstance(value,list):return value
    return [text for subtitle,ps in value.items() for text in [subtitle,*ps]]
def retain_references():
    SOURCES.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((BASE_SOURCES/'reference_manifest.json').read_text(encoding='utf-8'))
    for row in manifest:
        source=BASE_SOURCES/row['filename'];target=SOURCES/source.name
        assert digest(source)==row['sha256'],'First-round reference was changed'
        if not target.exists():shutil.copy2(source,target)
        assert digest(target)==row['sha256'],'Retained reference mismatch'
    write_json(SOURCES/'reference_manifest.json',manifest)
    return manifest

def read_results():
    path=ROOT/'output/benchmark.json'
    if not path.exists():return {'available':False,'summary':'新日期块时间留出评价尚未完成，本稿暂不填写性能改进数值。','short':'性能数据待冻结后评价回填。','decision':'主动策略的价值只按新留出对照判断，不预先宣称节约成本。','table':[]}
    report=json.loads(path.read_text(encoding='utf-8'))
    if report.get('status')!='completed':raise ValueError('Final benchmark must be completed')
    metrics={row['method']:row for row in [*report['diagnosis_comparison'],*report['policy_comparison']]}
    if set(metrics)!={'old_full','new_full','fixed','adaptive_rule'}:raise ValueError('Missing preregistered comparison')
    old,new,fixed,adaptive=[metrics[key] for key in ['old_full','new_full','fixed','adaptive_rule']]
    scope=report['scope']
    if scope['systems']!=1 or scope['origin']!='simulated':raise ValueError('Unexpected validation scope')
    days=sorted(date.fromisoformat(row['day']) for row in report['per_day'])
    assert len(days)==scope['dates'] and len(set(days))==len(days)
    ranges=[]
    for day in days:
        if ranges and day==ranges[-1][1]+timedelta(days=1):ranges[-1][1]=day
        else:ranges.append([day,day])
    assert len(ranges)==scope['contiguous_blocks']
    dates_text='、'.join(str(a)+'至'+str(b) for a,b in ranges)
    for row in metrics.values():
        assert row['n']==scope['records'] and row['n']==row['correct']+row['wrong']+row['unresolved']
        assert row['budget']==4
        assert abs(row['accuracy']-row['correct']/row['n'])<1e-10
        assert abs(row['coverage']-(row['correct']+row['wrong'])/row['n'])<1e-10
        answered=row['correct']+row['wrong']
        if answered:assert abs(row['error_rate']-row['wrong']/answered)<1e-10
        else:assert row['error_rate'] is None
        for key in ['avg_queries','avg_latency_ms']:
            assert isinstance(row[key],(int,float)) and math.isfinite(row[key]) and row[key]>=0
        for key in ['normal','damper_stuck','coil_leakage']:assert row['recall'][key] is None or 0<=row['recall'][key]<=1
    pct=lambda x:'不适用' if x is None else f'{x*100:.2f}%'
    recall=lambda row:'／'.join(pct(row['recall'][key]) for key in ['normal','damper_stuck','coil_leakage'])
    summary=(f'冻结后评价覆盖同一仿真系统的{scope["dates"]}个日期块，日期为{dates_text}；'
      f'{scope["base_scenarios"]}个基础日工况各有原始与重复记录版本，共{scope["records"]}条记录。'
      f'相同完整允许证据下，旧诊断器正确{old["correct"]}、错误{old["wrong"]}、未决{old["unresolved"]}；'
      f'新诊断器正确{new["correct"]}、错误{new["wrong"]}、未决{new["unresolved"]}。'
      f'总体正确率从{pct(old["accuracy"])}变为{pct(new["accuracy"])}，结论覆盖率从{pct(old["coverage"])}变为{pct(new["coverage"])}，'
      f'已判案例错误率从{pct(old["error_rate"])}变为{pct(new["error_rate"])}。'
      f'正常／风阀卡滞／盘管泄漏召回分别为旧{recall(old)}、新{recall(new)}。'
      f'新诊断器下，预算4的固定与自适应规则总体正确率为{pct(fixed["accuracy"])}／{pct(adaptive["accuracy"])}，'
      f'覆盖率{pct(fixed["coverage"])}／{pct(adaptive["coverage"])}，已判错误率{pct(fixed["error_rate"])}／{pct(adaptive["error_rate"])}，'
      f'各类召回为固定{recall(fixed)}、自适应{recall(adaptive)}；'
      f'平均查询{fixed["avg_queries"]:.3f}／{adaptive["avg_queries"]:.3f}次，端到端耗时{fixed["avg_latency_ms"]:.3f}／{adaptive["avg_latency_ms"]:.3f}毫秒。'
      f'旧／新完整信息端到端耗时为{old["avg_latency_ms"]:.3f}／{new["avg_latency_ms"]:.3f}毫秒。'
      '这些为本机单轮软件测量；未决未从分母剔除，不将配对版本当作独立建筑。')
    short=(f'同一仿真系统{scope["dates"]}个新日期块、{scope["base_scenarios"]}个基础工况的时间留出中，'
      f'完整证据下总体正确率由{pct(old["accuracy"])}变为{pct(new["accuracy"])}，'
      f'已判错误率为旧{pct(old["error_rate"])}、新{pct(new["error_rate"])}；不代表真实楼宇验证。')
    limitation=''
    if new['recall']['normal']==0 and new['recall']['coil_leakage']==0:
        limitation='本次正常与盘管泄漏召回均为0，新增正确结论全部来自风阀候选，已验证效果收缩为适用窗口中的风阀疑点核验，不能宣称通用三分类成功。'
        summary+=limitation
        short+='正常与泄漏召回均为0，改善仅见风阀候选。'
    table=[]
    for key,title,higher,a,b,ref in [
      ('accuracy','总体正确率',True,new,old,'旧诊断器 完整信息'),
      ('coverage','结论覆盖率',True,new,old,'旧诊断器 完整信息'),
      ('error_rate','已判错误率',False,new,old,'旧诊断器 完整信息'),
      ('avg_queries','平均查询次数',False,adaptive,fixed,'固定流程 预算4'),
      ('avg_latency_ms','端到端耗时',False,adaptive,fixed,'固定流程 预算4')]:
        av,bv=a[key],b[key]
        def fmt(value):return pct(value) if key in ['accuracy','coverage','error_rate'] else f'{value:.3f}'+('毫秒' if key=='avg_latency_ms' else '次')
        change='不计算' if av is None or bv is None else '基线0 不计算' if bv==0 else f'{((av-bv) if higher else (bv-av))/abs(bv)*100:+.2f}%'
        table.append([title,fmt(av),fmt(bv),change,ref])
    return {'available':True,'source':'output/benchmark.json','source_sha256':digest(path),'freeze_sha256':report['freeze_sha256'],
      'summary':summary,'short':short,'decision':report['decision']+limitation,'table':table,'scope':scope,'metrics':metrics,
      'metric_table_note':'前三项比较新旧诊断器完整信息；后二项比较新诊断器下自适应与固定预算4。提升度为相对变化；基线为0不计算。'}

def content(result):
    return {
      'brief':{
        'background':'公共建筑出现用能告警后，运维人员首先需要决定查记录、查工况还是查设备。错误记录与设备疑点可能共存；仅凭电表曲线也无法可靠定位暖通故障。能智核面向这一核验环节，将数据质量与设备判断分开呈现，让每项判断对应可复查的证据，并给出下一步需要查询的点位或运行时段。',
        'idea':'以“告警之后，先查什么”为主线，建立记录检查、有效工况筛选、证据核验与下一步动作的闭环。先修复诊断器的实现和工况适用性，再检验查询策略是否有价值；不把工程修复描述为原创算法。'+result['short'],
        'solution':'本地网页工作台接入两条独立证据链：BDG2承担真实建筑用能回放，LBNL单风道空调机组承担有标签仿真验证，重复记录另标为人为扰动。数值、有效窗口和判断均由程序计算，展示支持证据、反驳证据、判断状态与下一步动作；缺证时保持未决。修改预算、修正数据或屏蔽证据后真实重算。三个演示分别展示实测回放、正常仿真核验，以及数据修正后仍须核查设备疑点。旧42条仅作开发回归；新数据按完整日期块划分开发与最终留出，同日期全部故障和扰动版本整组归属。先以相同完整允许证据比较旧、新诊断器，再用新诊断器在预算4下比较固定流程与自适应规则。完整信息不受预算4截断；结果保留未决分母与错误率，查询成本和现场补采成本分别报告。',
        'business':'候选使用者为公共建筑运维与能源服务人员，拟以本地软件、授权数据接入及维护分析服务交付。近期价值是明确核查顺序、展示证据与缺口、避免将数据修复误作设备恢复。客户需求、付费方式和人工收益尚待访谈与试用验证；目前没有试点、合作、销售、实测节能量或投资回报数据，不据公开仿真推算实际收益。'},
      'technical':{
        'rationale':[
          '本项目解决公共建筑用能告警之后的核验问题。面对一条异常曲线，工作人员需要先辨别记录是否可信、运行工况是否适合诊断、证据支持何种设备疑点，以及还需查什么。能智核以可操作工作台呈现这一过程，目标是帮助人理解并复查结论，而不是仅生成一份分析报告。节能机会筛查属于附属能力，主任务为用能异常核验。',
          '现有能源分析可使用表计基准、规则告警与暖通故障检测。不同方法依赖的数据粒度和工况并不相同。建筑总表可以指出相对历史的用能差额，不能据此认定某个风阀或冷却盘管存在故障；全天平均值还可能把启停和局部有效工况混在一起。诊断必须说明使用哪些指令、温度和时段，不能将缺证当作正常，也不能把未定位异常计作正确分类。',
          '公开数据支持可复现的软件验证。BDG2包含真实建筑用能、天气与元数据；LBNL故障检测公开数据提供有标签的暖通仿真。两者分别证明真实数据接入回放和窄范围仿真诊断，不合并成真实楼宇设备定位证据。LBNL文件中与故障注入重合的实际位置反馈、故障名称和标签不进入诊断输入。未开展商业竞品横评或市场规模调查，不作国内外领先评价。',
          '首轮四种策略的10条正确记录完全重合，包含2条正常与8条盘管泄漏。完整信息取得四组证据，但运行背景未进入旧判定。32条未决的互斥主因为18条判据结构不适用、6条停机工况不适用、8条缺乏稳定关阀证据；本批无未决可归因于单位或字段错误。本轮修复判据和证据窗口，适当保留停机与缺证未决。旧42条只作开发回归，新日期只称同一仿真系统的时间留出验证。',
          '数据与技术依据：Miller等，The Building Data Genome Project 2，Scientific Data，2020，doi:10.1038/s41597-020-00712-x；Granderson等，LBNL FDD Datasets，doi:10.25984/1881324；LBNL公开的单风道空调机组数据说明。数据署名及许可随复现包保留。'],
        'innovation':{
          '1．项目总体思路':[
            '将“告警之后，先查什么”具体化为四个可见部分：当前工况、支持与反驳证据、判断状态、下一步动作。核验前先确认记录质量和有效运行窗口，核验后将已知、未知和需要继续检查的内容同时交给使用者。数据质量与设备判断独立更新，记录修复不会自动清除设备疑点。',
            '架构保持单一数值诊断底座和简洁策略层。数据适配层负责时间、单位和允许字段；数值层计算窗口与证据并输出状态；策略层选择下一项查询；工作台展示过程并导出可追溯记录。固定流程与自适应规则使用同一诊断器。首轮本地免费模型保留为历史实验，本轮不增加复杂Agent、不接付费API。'],
          '2．可行性分析：项目的技术或实施可行性。':[
            '已有独立本地网页原型、公开数据准备程序、诊断源码和逐例评测记录。首轮源码、结果与交付包完整保留，本轮在独立目录实施。计算依据LBNL文档核对温度单位、控制指令和实际反馈的区别、风机启停以及可用控制工况；只在满足可辨识条件的窗口形成设备结论。未运行、缺点位或证据冲突时保留未决并说明所需时段或点位。',
            '源数据有明确限制：四个盘管泄漏严重度文件内容相同，只保留一份代表；静压实值与设定值口径冲突，不进入定量诊断；故障注入相关实际执行器位置不作为分类捷径。因此当前结论不依赖直接位置反馈，也不能扩展为严重度估计或跨设备能力。',
            result['summary']],
          '3．本项目的特色与创新之处。':[
            '可申报的产品设计特色是把数据修复与设备核验组合为可操作证据闭环，并在未决时指明下一步所需条件。第三个演示修正完全重复记录后继续计算设备证据，使“数据变干净”与“设备没有问题”的区别能够被直接观察。支持和反驳证据同时呈现，避免只展示有利结论。',
            '本轮核对单位和字段语义，修复工况、局部窗口及判据实现，属于工程修复，不包装为原创故障算法。主动补证是否构成方法优势，由同底座、同预算、同证据池的规则对照决定。'+result['decision']]},
        'implementation':[
          '实现形态为本地运行的核验工作台。案例数据、数值程序与页面分离；前端通过本地接口查询和计算证据，预算和可用证据改变后重新执行诊断，导出对应运行记录。页面保留实测、仿真和人为扰动标识，不能将演示回放误读为现场实时设备连接。',
          '接入流程先核对时间戳、采样间隔、重复和缺失，再统一温度单位、筛选允许字段。完全重复记录可以确定性去重；相同时间但数值冲突不能静默合并。运行窗使用实际启停和指令证据，排除不适用时间，避免全天平均掩盖局部响应。有效样本不足或缺少辨识所需激励时，系统给出需要补充的运行时段，而非放宽判据取得结论。',
          '风路将室外、回风和混合温度推算的混风响应与对应控制指令的正常参考范围比较，不把指令当作实测位置。盘管只在稳定关阀窗口比较相近风机指令条件下的温降，避免全天平均混淆启停和局部异常。正常参考范围由开发正常案例建立；开发泄漏样本只用于确定重叠拒判区，进一步收紧正常结论资格。运行背景参与适用性判定。运行时不输入故障标签、故障设置、文件名或实际执行器位置。仅有异常而无法确定类别的结果保持未决，不计作三分类正确。正常结论需要正向证据，不能由“未触发故障”反推。',
          '评测分两层。第一层让旧、新诊断器获得同一份完整允许证据，比较修复效果；第二层固定新诊断器，在主预算4下比较固定流程与自适应规则。完整信息参照取得全部允许证据，记录其实际查询量，不以预算4截断。查询记录数与现场补采成本分别报告，本轮为离线数据查询，未实施现场补采。',
          '旧42条案例仅用于错误归因、调试和回归。新日期在读取最终留出结果前按日期块确定开发与留出，同日期不同故障、强度与扰动版本整组归属，禁止随机拆窗。规则、阈值、证据池和评价口径冻结后执行最终评价。基础工况数、日期块数和记录版本数分列，不能把配对扰动版本当作独立建筑。',
          '报告总体正确率、各类召回、结论覆盖率、已判案例错误率、证据查询成本和端到端耗时。未决与失败保留在总体分母；耗时从输入文件读取解析到结果JSON编码，包含预处理、查询和诊断，不含网络、日志落盘及前端绘制。本机单轮顺序轮换测量不能替代独立时延研究。低错误率须结合覆盖率理解；软件耗时和离线查询减少不代表人工工时、维修效率或节能收益。',
          '三个演示保持一条操作主线。真实建筑演示显示历史用能与参考差额，仅供进一步核查。正常仿真演示显示正常判断所需的有效条件和正向证据。数据问题与设备疑点共存演示先显示重复记录，再执行修复并重新核验，展示修正后仍存在的设备疑点与下一步动作。演示案例不混入最终时间留出成绩。',
          '源码、启动说明、数据许可、输入哈希、冻结记录、逐例结果和汇总报告作为软件证明材料。参赛材料从已计算汇总回填；项目简表、说明书和商业计划书沿用官方模板章节、字数和格式。当前未完成真实楼宇接入、人工效率研究、节能干预或跨设备验证。'],
        'prospect':['近期用于公共建筑用能告警核验的教学、研究与演示，形成可复查证据和具体的下一步动作。下一阶段优先获得授权的同类空调机组历史记录，验证单位、点位、工况覆盖与诊断错误，再开展使用者访谈及人机核验评估。是否产品化取决于接入成本、诊断可靠性、复核责任和用户价值；不根据同一仿真系统的新日期成绩承诺真实楼宇即用能力。不扩展设备类型，不承诺自动控制、维修替代或节能收益。']},
      'commercial':{
        'overview':'能智核为公共建筑用能告警提供可操作核验工作台，回答先查什么、证据支持什么及还缺什么。产品区分记录质量与设备状态，采用本地程序完成计算，保留未决与下一步动作。当前交付为公开数据原型、三个演示与同一仿真系统的时间留出验证；真实建筑数据仅用于用能回放。尚无客户试点、合作、营收或实测节能业绩。',
        'team':'按匿名职责组织工作：产品与场景负责需求、核验流程和材料；数据与诊断负责数据契约、规则与评价；工程负责工作台、部署和回归。职责可由同一成员兼任，不代表已确认人数或专业经历。培养单位、导师和其他可识别身份不在本稿出现；模板姓名、电话栏保留待按官方匿名口径填写。',
        'product':{
          '1.项目产品（服务）特性':[
            '一次核验从“告警之后，先查什么”开始。使用者选择案例，查看记录与当前工况，按预算取得证据，再依据支持和反驳信息检查结论。遇到未决，系统指明需要补哪个点位或哪个运行时段。修复重复数据后重新计算，设备疑点不会因记录修正而自动消失。核验结果与来源可导出，便于复核和演示。',
            '采用本地软件交付，数值由程序计算。证据链区分BDG2真实建筑回放、LBNL暖通仿真以及人为扰动；不需要付费API。当前设备验证限定单风道空调机组。数据接入仍需确认字段、单位、采样和实际运行条件，不承诺任意建筑直接使用。'],
          '2.产品（服务）化实施计划':[
            '本阶段交付可运行原型、三个演示、诊断修复与新的时间留出对照。下一阶段先访谈运维使用者与预算负责人，确认最需要复核的告警、可获得点位、结果责任和付费意愿，再在授权条件下进行同类设备小规模历史记录验证。目前未将需求访谈或授权试点写为已经完成。',
            '产品化验收应同时检查字段接入、核验质量、未决处置、导出可追溯性和维护工时。'+result['decision']]},
        'market':{
          '1.市场概述':[
            '候选使用者为校园后勤、公共办公楼运维和能源服务人员，潜在付费方为业主、物业或服务承包方，需通过访谈确认。场景聚焦已有历史数据、仍需人工核实告警的组织。当前未完成市场规模、竞品价格、购买周期与支付意愿调查，不据一般建筑数量推算销售规模。'],
          '2.竞争优势分析':[
            '对照的工作方式包括人工表格复核、固定规则告警与自适应规则核验。能智核的展示特色是同时呈现数据问题、设备证据和下一步动作，并将修复操作直接连接到重新计算。技术对照限于本项目公开数据实验，未完成商业产品横评。工程修复不等于行业领先，软件查询节省也不等于人工或现场成本下降。',
            result['summary']],
          '3.项目实施风险及应对措施':[
            '接入风险通过字段、时间、单位和数据质量检查处理。诊断适用性通过启停、控制工况、有效窗口与证据充分性判断；缺证保持未决。仿真到实测的差异需用授权现场记录验证，不能通过删去未决或把未定位异常计为正确掩盖。真实使用中的复核责任、现场作业与维修流程仍需和责任主体确认。',
            '源数据重复严重度、单位冲突及注入信息问题随数据契约公开。第三方许可与必要署名随软件分发保留；匿名要求针对参赛团队身份，不据此删除数据版权归属。缺乏真实客户、人工收益与节能证据是现阶段商业判断的关键限制。']},
        'model':{
          '1.项目产品（服务）的开发、生产（服务）策略':[
            '拟按本地软件、授权数据接入和维护分析服务组织交付。标准软件提供案例导入、证据查询、核验卡与导出；项目服务负责点位映射、工况确认与使用培训。先记录各环节实际工时、运行资源和维护负担，判断哪些能够标准化，不通过增加Agent数量包装产品能力。'],
          '2.项目产品（服务）的营销策略':[
            '以可复现公开演示说明能力、条件和未决处置，作为需求访谈工具。后续试用应约定授权范围、评价任务、复核责任和退出条件。演示数据不作为客户案例，未落实意向不描述为合作，暂不制定无依据的客户增长或区域覆盖数字。'],
          '3.项目产品（服务）获利方式':[
            '收入假设包括一次性部署和数据接入服务，以及持续维护分析服务。按楼宇、表计或服务范围计费的方式需调查，价格和毛利需结合真实接入工时、支持成本、软硬件资源与支付意愿测算。免费本地模型不等于软件维护与现场服务零成本。目前不填写无依据报价。'],
          '4.（若创业）企业发展计划':[
            '尚无企业、融资或经营业绩可报告。只有独立需求验证、合法授权试用及可承受的履约责任支持产品价值时，才决定组织形式和知识产权安排。近期资源集中于同类设备的可用性和核验体验，不扩大设备范围或城市级平台规模。']},
        'economics':'当前无实际销售、客户试点、人工工时研究或节能干预，不填营收、利润、投资回报率与节能收益。后续收入按部署接入和维护分析服务计算，成本按接入工时、运行资源、维护支持与必要授权计算；每项采用实际记录或明确假设。人工效率需在相同任务条件下测量，节能量需在明确干预后通过适当基准验证。离线数据查询次数和软件耗时仅表示程序核查成本，不能换算为现场节约金额。'} }

def inventory():
    entries=[]
    for number in [1,2,3]:
        source=next(SOURCES.glob(f'附件{number}*docx'))
        with ZipFile(source) as z:
            parts={name:z.read(name) for name in z.namelist()}
        tree=etree.fromstring(parts['word/document.xml'])
        editable=['word/document.xml','word/settings.xml','docProps/core.xml','docProps/custom.xml','docProps/app.xml']
        entries.append({'number':number,'source':str(source),'sha256':digest(source),'page_count_verified':None,
          'section_xml':[etree.tostring(e,encoding='unicode') for e in tree.xpath('//w:sectPr',namespaces=NS)],
          'package_parts_sha256':{name:hashlib.sha256(value).hexdigest() for name,value in parts.items()},
          'preserve_only_parts':[name for name in parts if name not in editable],'editable_parts':editable})
    return entries

def counts(docs):
    rows=[]
    for name,sections in docs.items():
        for key,value in sections.items():
            n=count('\n'.join(paragraphs(value)));cap=LIMITS[name][key]
            rows.append({'document':NAMES[name],'section':HEADS[name][key],'characters':n,'limit':cap,'passed':n<=cap})
            assert n<=cap,f'{name}/{key} has {n}>{cap} characters'
    return rows

def source_text(p,text):
    ts=p.xpath('.//w:t',namespaces=NS)
    if not ts:
        r=etree.SubElement(p,W+'r')
        rp=p.find('w:pPr/w:rPr',NS)
        if rp is not None:r.append(copy.deepcopy(rp))
        ts=[etree.SubElement(r,W+'t')]
    ts[0].text=text;ts[0].set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    for t in ts[1:]:t.text=''

def new_paragraph(sample,text):
    p=etree.Element(W+'p');props=sample.find(W+'pPr')
    if props is not None:p.append(copy.deepcopy(props))
    r=etree.SubElement(p,W+'r');rp=sample.find('w:r/w:rPr',NS)
    if rp is not None:r.append(copy.deepcopy(rp))
    t=etree.SubElement(r,W+'t');t.text=text;t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    return p

def insert_after(anchor,values,sample):
    for value in values:
        p=new_paragraph(sample,value);anchor.addnext(p);anchor=p

def cell_content(cell,text):
    ps=cell.findall(W+'p')
    if not ps:ps=[etree.SubElement(cell,W+'p')]
    source_text(ps[0],text)
    for p in ps[1:]:cell.remove(p)

def anonymize(parts):
    for name in ['docProps/core.xml','docProps/custom.xml','docProps/app.xml']:
        root=etree.fromstring(parts[name])
        if name.endswith('custom.xml'):
            for child in list(root):root.remove(child)
        else:
            for node in root.iter():
                tag=etree.QName(node).localname
                if name.endswith('core.xml') and tag in ['creator','lastModifiedBy','description','subject','title','keywords']:node.text=''
                elif name.endswith('app.xml') and tag in ['Company','Manager','Application']:node.text=''
                elif name.endswith('app.xml') and tag in ['Pages','Words','Characters','CharactersWithSpaces','Lines','Paragraphs','TotalTime']:node.text='0'
        parts[name]=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)

def emit_docx(docs,result,items):
    reports=[]
    for number,name in [(1,'brief'),(2,'technical'),(3,'commercial')]:
        entry=next(x for x in items if x['number']==number);source=Path(entry['source'])
        assert digest(source)==entry['sha256']
        with ZipFile(source) as z:parts={n:z.read(n) for n in z.namelist()}
        tree=etree.fromstring(parts['word/document.xml']);body=tree.find(W+'body');original=list(body)
        source_text(original[3],'（可编辑底稿 待视觉复检 非正式提交版）')
        sections=docs[name]
        if number==1:
            rows=body.find(W+'tbl').findall(W+'tr');cells=lambda r:rows[r].findall(W+'tc')
            for r,c,text in [(0,1,PROJECT),(1,1,'[待填写匿名团队名称]'),(3,1,'[待按官方匿名口径填写]'),(3,3,'[待按官方匿名口径填写]'),(4,1,'产品与场景、数据与诊断、工程实现等匿名职责；成员身份待按官方口径填写。'),(6,1,sections['background']),(8,1,sections['idea']),(10,1,sections['solution']),(12,1,sections['business']),(13,2,'软硬件开发类；本地软件原型。'),(14,2,'无法判断；不作国内或国际领先评价。'),(17,2,'指标前三项为新诊断器对旧诊断器，均用完整允许证据；后二项为自适应对固定流程，均用新诊断器与预算4。提升度为相对变化，基线0不计算。'),(19,2,'已有功能：数据修复后继续核验；支持与反驳证据、下一步动作可见。技术改善以所附时间留出结果为准，不填写现场成本或节能收益。')]:cell_content(cells(r)[c],text)
            for p in cells(2)[1].findall(W+'p'):
                text=''.join(p.xpath('.//w:t/text()',namespaces=NS))
                if '6.定向赛道-智慧能源与环境' in text:
                    ix=text.rfind('□');source_text(p,text[:ix]+'☑'+text[ix+1:])
            for p in cells(15)[2].findall(W+'p'):
                text=''.join(p.xpath('.//w:t/text()',namespaces=NS));source_text(p,text.replace('□软件','☑软件').replace('□方法','☑方法'))
            # Keep the official 1-9 options; no unsupported TRL selection.
            table=cells(18)[2].find(W+'tbl').findall(W+'tr')
            values=result['table'] or [[key,'待评价','待评价','不计算','同完整证据旧诊断器'] for key in ['总体正确率','结论覆盖率','已判错误率','平均查询次数','端到端耗时']]
            assert len(values)==5 and all(len(row)==5 for row in values),'Official metric table must have 5x5 data slots'
            for row,vals in zip(table[1:],values):
                for cell,value in zip(row.findall(W+'tc'),vals):cell_content(cell,str(value))
        elif number==2:
            source_text(original[4],PROJECT)
            sample=original[6];source_text(original[6],sections['rationale'][0]);insert_after(original[6],sections['rationale'][1:],sample)
            for anchor,key in zip([8,9,10],sections['innovation']):insert_after(original[anchor],sections['innovation'][key],sample)
            source_text(original[12],sections['implementation'][0]);insert_after(original[12],sections['implementation'][1:],sample)
            insert_after(original[13],sections['prospect'],sample)
        else:
            source_text(original[4],PROJECT)
            sample=original[20]
            if sample.find('w:r/w:rPr',NS) is None:sample=original[8]
            insert_after(original[5],[sections['overview']],sample);insert_after(original[6],[sections['team']],sample)
            for anchors,key in [([8,9],'product'),([11,12,13],'market'),([15,16,17,18],'model')]:
                for anchor,subkey in zip(anchors,sections[key]):insert_after(original[anchor],sections[key][subkey],sample)
            insert_after(original[19],[sections['economics']],sample)
        parts['word/document.xml']=etree.tostring(tree,xml_declaration=True,encoding='UTF-8',standalone=True)
        settings=etree.fromstring(parts['word/settings.xml']);update=settings.find(W+'updateFields')
        if update is None:update=etree.SubElement(settings,W+'updateFields')
        update.set(W+'val','true');parts['word/settings.xml']=etree.tostring(settings,xml_declaration=True,encoding='UTF-8',standalone=True)
        anonymize(parts)
        for part in entry['preserve_only_parts']:assert hashlib.sha256(parts[part]).hexdigest()==entry['package_parts_sha256'][part],part
        assert [etree.tostring(e,encoding='unicode') for e in tree.xpath('//w:sectPr',namespaces=NS)]==entry['section_xml']
        target=M/(NAMES[name]+'_待视觉复检.docx')
        with ZipFile(target,'w',ZIP_DEFLATED) as z:
            for part,payload in parts.items():z.writestr(part,payload)
        assert digest(source)==entry['sha256']
        reports.append({'file':target.name,'sha256':digest(target),'reference_sha256':entry['sha256'],'preserve_only_parts_unchanged':True,'section_geometry_unchanged':True,'render_verified':False,'submission_ready':False})
    write_json(M/'working/docx_build_report.json',reports)
    return reports

def render_documents(reports):
    # A controlled PATH prevents fallback to the user's desktop installation.
    controlled=[RUNTIME/'python',RUNTIME/'bin/override',RUNTIME/'native/poppler/Library/bin',Path(os.environ.get('SystemRoot','C:/Windows'))/'System32']
    env=os.environ.copy();env['PATH']=os.pathsep.join(str(p) for p in controlled);env['PYTHONIOENCODING']='utf-8'
    rows=[]
    for report in reports:
        path=M/report['file'];out=M/'working/render'/path.stem
        run=subprocess.run([str(RUNTIME/'python/python.exe'),'-X','utf8',str(SKILL/'render_docx.py'),str(path),'--output_dir',str(out),'--emit_pdf'],env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        log=M/'working'/(path.stem+'_render.log');log.write_text(run.stdout+'\n'+run.stderr,encoding='utf-8')
        rows.append({'file':path.name,'returncode':run.returncode,'log':str(log.relative_to(M)),'pages':[str(p.relative_to(M)) for p in out.glob('page-*.png')],'visually_reviewed':False})
    write_json(M/'渲染状态.json',{'status':'RENDERED_PENDING_VISUAL_REVIEW' if all(row['pages'] for row in rows) else 'PENDING_VISUAL_REVIEW_MISSING_BUNDLED_RENDERER','documents':rows,'desktop_libreoffice_used':False,'submission_ready':False,'note':'用户明确要求先交可编辑DOCX；缺少允许的捆绑渲染器时标为待视觉复检，不阻塞产品开发。'})

def audit_documents(reports,docs):
    from docx import Document
    rows=[]
    for report,name in zip(reports,['brief','technical','commercial']):
        path=M/report['file']
        with ZipFile(path) as z:
            bad=z.testzip();assert bad is None,bad
            xml=z.read('word/document.xml');tree=etree.fromstring(xml)
            texts=[''.join(p.xpath('.//w:t/text()',namespaces=NS)) for p in tree.xpath('//w:p',namespaces=NS)]
            core=etree.fromstring(z.read('docProps/core.xml'));custom=etree.fromstring(z.read('docProps/custom.xml'))
            properties={etree.QName(n).localname:n.text for n in core}
            assert not properties.get('creator') and not properties.get('lastModifiedBy')
            assert len(custom)==0
            assert not tree.xpath('//w:ins|//w:del|//w:commentRangeStart|//w:sdt',namespaces=NS)
            assert not re.search(r'[A-Za-z]:\\|Administrator|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',xml.decode('utf-8'))
            for part in z.namelist():
                if part.endswith('.xml') or part.endswith('.rels'):
                    data=z.read(part).decode('utf-8')
                    assert not re.search(r'[A-Za-z]:\\|Administrator',data),'Identity path in '+part
            assert '（可编辑底稿 待视觉复检 非正式提交版）' in texts
            for value in docs[name].values():
                for text in paragraphs(value):
                    # Subheadings are original source text with possibly a trailing space.
                    assert text in [p.strip() for p in texts],text[:80]
            for heading in HEADS[name].values():
                assert any(heading in p for p in texts),heading
            if name=='brief':
                tables=tree.xpath('//w:tbl',namespaces=NS);assert len(tables)==2
                assert len(tables[0].findall(W+'tr'))==20
                assert len(tables[1].findall(W+'tr'))==6
                assert all(len(row.findall(W+'tc'))==5 for row in tables[1].findall(W+'tr'))
                assert sum('☑' in text and '智慧能源与环境' in text for text in texts)==1
        # Loading via an independent OOXML consumer verifies editable structure.
        doc=Document(path);assert len(doc.sections)==1
        section=doc.sections[0]
        assert abs(section.top_margin.mm-25.4)<.1 and abs(section.left_margin.mm-31.75)<.1
        rows.append({'file':path.name,'zip_crc_valid':True,'python_docx_loads':True,'required_chapters_and_native_editable_text_present':True,
          'anonymous_metadata':True,'no_local_identity_paths':True,'official_table_topology_preserved':True,
          'ooxml_part_fidelity_verified':True,'visual_layout_reviewed':False})
    write_json(M/'working/docx_structural_audit.json',rows)

def write_contract(items):
    write_json(M/'working/template_inventory.json',items)
    text='''# Official template execution contract

The three retained DOCX references and supplied guide are authoritative. Reference SHA-256 and all package-part hashes are in template_inventory.json. The first-round references are read-only.

Page system: one A4 portrait section per template, top/bottom 25.4 mm, left/right 31.75 mm, original header/footer distances and line grid preserved. Exact section XML is stored in the inventory. Page counts are unresolved until permitted rendering succeeds.

Typography: preserve original title font 方正小标宋简体 at 18 pt and original alignment. Preserve body 仿宋 14 pt and 1.5 line spacing in technical/commercial templates; brief table body mainly 仿宋 12 pt. Clone original paragraph and run properties only. Preserve source styles, embedded fonts, theme, footer PAGE fields, customXml shape data and all relationships byte-for-byte.

Tables: preserve the original brief 20-row merged table and its nested 5-column, 6-row metric table. Source atLeast row heights remain; no fixed row heights are introduced. Original column grids, merges, padding and border properties remain unchanged. New metric content uses all five official data rows.

Editable package parts: document.xml content slots; settings.xml updateFields only; docProps/core.xml, custom.xml and app.xml anonymous metadata/cached statistics. All other package parts and relationships are preserve-only. Core creators and custom properties are scrubbed; cached page/word statistics are reset until rendering. Draft marker replaces template marker under explicit user authorization. Identity fields stay visible as anonymous placeholders.

Slot map: brief original body table rows/cells (zero based) name 0/1, team 1/1, track 2/1, captain 3/1, phone 3/3, members 4/1, background 6/1, idea 8/1, solution 10/1, business 12/1, stage 13/2, advance 14/2, outputs 15/2, TRL 16/2 unchanged unselected, comparators 17/2, nested metrics 18/2, improvement 19/2. Technical original body indexes: marker 3, project title 4, rationale 6, innovation anchors 8/9/10, implementation 12, prospect anchor 13. Commercial original body indexes: marker 3, project title 4, overview 5, team 6, product 8/9, market 11/12/13, business 15/16/17/18, economics 19. Original headings remain unchanged.

Content flow: brief compresses problem, idea, solution and business; technical preserves four chapters and three original innovation subheadings; business preserves six chapters and all original subheadings. No new chapter or decorative design system is introduced. Body text and official metrics remain editable native Word text.

Fidelity gates: input references unchanged, preserve-only bytes unchanged, same section geometry, required headings present, draft marker present, all 14 capped sections pass, no identifiable team metadata, all declared numbers bound to actual aggregate output. DOCX rendering and page visual review remain a separate unfinished gate if the bundled renderer is unavailable. The explicit user request permits delivery of marked editable drafts without declaring them final submissions.
'''
    (M/'working/artifact.md').write_text(text,encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--emit-docx',action='store_true');parser.add_argument('--render',action='store_true');args=parser.parse_args()
    for folder in [M,M/'working',M/'drafts']:folder.mkdir(parents=True,exist_ok=True)
    retain_references();items=inventory();write_contract(items)
    result=read_results();docs=content(result);cap_rows=counts(docs)
    for name,sections in docs.items():
        lines=[PROJECT,TRACK,'可编辑填报内容 待视觉复检 非正式提交版','']
        for key,value in sections.items():lines.extend([HEADS[name][key],*paragraphs(value),''])
        (M/'drafts'/(NAMES[name]+'.txt')).write_text('\n'.join(lines),encoding='utf-8')
    write_json(M/'填报内容.json',{'project':PROJECT,'track':TRACK,'documents':docs,'results':result,'submission_ready':False})
    write_json(M/'字数与要求核对.json',{'counting_rule':'All non-whitespace code points including punctuation, Latin letters, digits and subheadings.','sections':cap_rows,'all_passed':all(row['passed'] for row in cap_rows),'submission_ready':False})
    if args.emit_docx:
        reports=emit_docx(docs,result,items)
        audit_documents(reports,docs)
        if args.render:render_documents(reports)
    print(json.dumps({'documents':3,'capped_sections':len(cap_rows),'all_caps_pass':True,'actual_results_populated':result['available'],'docx_written':args.emit_docx,'submission_ready':False},ensure_ascii=False))

if __name__=='__main__':main()
