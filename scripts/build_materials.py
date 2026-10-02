"""Build anonymous, word-counted competition drafts from verified aggregates.

This script never opens holdout cases or labels. DOCX output is gated on
reference rendering/inspection; text drafts remain explicitly non-submittable.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, math, os, re, shutil, subprocess
from pathlib import Path
from zipfile import ZipFile
from lxml import etree

ROOT=Path(__file__).resolve().parents[1]
MATERIALS=ROOT/'materials'
ORIGINAL_SOURCES=ROOT.parent/'能智核_参赛设计'/'sources'
SOURCES=MATERIALS/'references'
RUNTIME=Path(os.environ.get('NENGZHIHE_BUNDLED_DEPENDENCIES',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies')))
SKILL=Path(os.environ.get('NENGZHIHE_DOCUMENT_SKILL',str(Path.home()/'.codex/plugins/cache/openai-primary-runtime/documents/26.921.10847/skills/documents')))
PROJECT='能智核 公共建筑用能异常核验工作台'
TRACK='定向赛道 智慧能源与环境'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W='{'+NS['w']+'}'
STRATEGIES={'fixed':'固定流程','adaptive_rule':'自适应规则','local_model':'本地模型主动补证','full_information':'完整信息'}
LIMITS={'brief':{'background':300,'idea':300,'solution':600,'business':300},
        'technical':{'rationale':2000,'innovation':3000,'implementation':3000,'prospect':500},
        'commercial':{'overview':200,'team':200,'product':2000,'market':2000,'model':2000,'economics':500}}
TITLES={'brief':'附件1 项目简表','technical':'附件2 项目说明书','commercial':'附件3 项目商业计划书'}
SECTION_TITLES={
 'brief':{'background':'项目背景','idea':'立项思路','solution':'解决方案','business':'商业模式和预期效益'},
 'technical':{'rationale':'一、立项依据','innovation':'二、项目创新内容','implementation':'三、实施方案','prospect':'四、应用前景分析'},
 'commercial':{'overview':'一、项目方案概述','team':'二、项目团队','product':'三、项目产品（服务）化','market':'四、项目产品（服务）市场与竞争','model':'五、商业模式','economics':'六、预期经济效益分析'}}

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def retain_references():
    SOURCES.mkdir(parents=True,exist_ok=True)
    manifest=SOURCES/'reference_manifest.json'
    if manifest.exists():
        for entry in json.loads(manifest.read_text(encoding='utf-8')):
            if digest(SOURCES/entry['filename'])!=entry['sha256']:raise RuntimeError('Retained official reference changed')
        return
    files=[next(ORIGINAL_SOURCES.glob(f'附件{i}*docx')) for i in [1,2,3]]+[next(ORIGINAL_SOURCES.glob('*.pdf'))]
    records=[]
    for source in files:
        target=SOURCES/source.name;shutil.copy2(source,target)
        if digest(source)!=digest(target):raise RuntimeError('Reference copy hash mismatch')
        records.append({'filename':source.name,'sha256':digest(target),'original_sha256':digest(source),'unchanged_copy':True})
    write_json(manifest,records)

def count(text):
    # Conservative: every non-whitespace code point, including Latin letters,
    # numerals and punctuation, counts as one character.
    return len(re.sub(r'\s+','',text))

def numeric(row,key):
    value=row.get(key)
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(f'Invalid metric {row.get("strategy")} {key}: {value}')
    return value

def read_results(path):
    if not path.exists():
        return {'available':False,'source':'output/benchmark.json','status':'pending',
          'summary':'留出评测结果尚未回填。本文未将开发案例或演示表现当作性能证明。',
          'innovation_decision':'主动补证目前仅是待检验方法，不作为已证实的创新增益。',
          'table':[],'metric_rows':[]}
    if path.resolve()!=(ROOT/'output/benchmark.json').resolve():
        raise ValueError('Only the approved aggregate output/benchmark.json may populate materials')
    report=json.loads(path.read_text(encoding='utf-8'))
    protocol=report.get('protocol',{})
    if protocol.get('primary_budget')!=4 or protocol.get('secondary_budgets')!=[2,3]:
        raise ValueError('Material budget binding does not match the frozen protocol')
    rows=report.get('metrics')
    if not isinstance(rows,list): raise ValueError('benchmark.metrics must be a list')
    main={r['strategy']:r for r in rows if r.get('budget')==4}
    if set(main)!=set(STRATEGIES): raise ValueError('Need all four preregistered budget-4 strategy rows')
    for row in rows:
        if row.get('strategy') not in STRATEGIES or row.get('budget') not in [2,3,4]: raise ValueError('Unexpected strategy/budget')
        for k in ['n','accuracy','macro_f1','coverage','error_rate','avg_queries','avg_latency_ms','model_calls','correct','wrong','unresolved','invalid_model_response_rate']:
            if row.get(k) is None and (k=='error_rate' or (k=='invalid_model_response_rate' and row.get('strategy')!='local_model')): continue
            value=numeric(row,k)
            if k in ['accuracy','macro_f1','coverage','error_rate','invalid_model_response_rate'] and not 0<=value<=1:
                raise ValueError(f'{k} out of [0,1]')
    if len({r['n'] for r in main.values()})!=1: raise ValueError('Main comparison sample counts differ')
    local=main['local_model'];rule=main['adaptive_rule'];fixed=main['fixed'];full=main['full_information']
    def rate(value):return '不适用（无已回答案例）' if value is None else f'{value*100:.2f}%'
    text=(f'预先确定的主要预算为4项证据查询。四种策略均按相同证据池计费，完整信息版本取得全部4组证据。'
          f'本地模型、固定流程、自适应规则和完整信息的Macro-F1分别为{local["macro_f1"]:.4f}、{fixed["macro_f1"]:.4f}、{rule["macro_f1"]:.4f}和{full["macro_f1"]:.4f}。'
          f'本地模型与自适应规则的准确率分别为{rate(local["accuracy"])}、{rate(rule["accuracy"])}，结论覆盖率为{rate(local["coverage"])}、{rate(rule["coverage"])}；'
          f'已回答案例中的错误率为{rate(local["error_rate"])}、{rate(rule["error_rate"])}。'
          f'二者平均查询次数为{local["avg_queries"]:.3f}、{rule["avg_queries"]:.3f}，平均端到端耗时为{local["avg_latency_ms"]:.3f}、{rule["avg_latency_ms"]:.3f}毫秒。'
          f'本地模型共调用{local["model_calls"]}次，无效响应率为{rate(local["invalid_model_response_rate"])}。预算2、3为次要分析，未据其结果改选主预算。'
          f'在{local["n"]}个配对记录中，本地模型正确{local["correct"]}、错误{local["wrong"]}、未决{local["unresolved"]}；'
          f'完整信息版本正确{full["correct"]}、错误{full["wrong"]}、未决{full["unresolved"]}。'
          '已回答中的错误率只描述获得结论的子集，不能单列零错判作为高准确率证据。耗时为本机单轮测量，受缓存与负载影响，未完成多次独立时延实验，也不等于人工效率。')
    # The frozen evaluation owns the decision rule. Never invent a new
    # threshold after seeing held-out results in a document generator.
    decision=report.get('decision')
    if not isinstance(decision,str) or not decision.strip():raise ValueError('Need the actual frozen-benchmark decision text')
    if full['coverage']<0.5:
        decision+=(f'完整信息仅覆盖{full["coverage"]*100:.2f}%的案例，说明共享诊断底座对留出工况的覆盖仍不足，当前不能包装为可部署的高准确率诊断产品。'
                   '后续应先收缩适用工况并核查规则失效原因；若调整阈值或方法，本次留出已被使用，必须另设未参与调试的验证数据。')
    table=[]
    for key,title,unit,higher in [('macro_f1','Macro-F1','',True),('coverage','结论覆盖率','%',True),('error_rate','已回答中的错误率','%',False),('avg_queries','平均证据查询次数','次',False),('avg_latency_ms','平均端到端耗时','毫秒',False)]:
        a=local[key];b=rule[key]
        def format_metric(value):
            if value is None:return '不适用（无已回答案例）'
            return f'{value*100:.2f}%' if unit=='%' else f'{value:.4f}' if key=='macro_f1' else f'{value:.3f}{unit}'
        av=format_metric(a);bv=format_metric(b)
        if a is None or b is None:
            change='不计算'
        else:
            change='基线为0不计算' if b==0 else f'{((a-b) if higher else (b-a))/abs(b)*100:+.2f}%'
        table.append([title,av,bv,change,'自适应规则 预算4'])
    return {'available':True,'source':'output/benchmark.json','source_sha256':digest(path),'status':report.get('status'),
      'summary':text,'innovation_decision':decision,'table':table,'metric_rows':rows,
      'benchmark_decision':report.get('decision'),'primary_budget':4,'secondary_budgets':[2,3],
      'note':'提升度为相对变化，负值表示退步；耗时为本机软件测量，不等于人工核查效率。'}

def content(results):
    result=results['summary'];decision=results['innovation_decision']
    docs={
      'brief':{
        'background':'公共建筑管理人员面对用能告警，需要先分清记录问题与运行疑点，再决定是否补查设备。单条异常曲线无法证明故障，修复数据也不代表设备问题消失。能智核面向校园、办公楼等公共建筑的核验工作流程，形成可追溯的证据卡；节能机会仅作为相对历史参考的差额线索。当前使用公开数据，尚无实际客户试点或实测节能收益。',
        'idea':'把数据可信度和设备运行证据分开判断，按预算逐步查询证据，证据不足时明确保留疑点。先验证本地免费模型的主动补证是否优于固定流程和不使用大模型的自适应规则。所有数值由程序计算，模型仅选择下一查询动作。若未产生实际增益，保留简洁核验产品并收缩创新表述。',
        'solution':'搭建本地核验工作台，提供案例回放、数据质量检查、证据查询、结论与证据卡。BDG2承担三栋公开建筑的小时电表及天气回放；LBNL单风道空调机组承担正常、风阀卡滞和盘管阀泄漏的有标签仿真验证。两类数据不做楼宇设备关联。查询分为记录质量、风路响应、盘管响应和运行背景四组，按相同证据池和预算比较四种策略，主要预算预先设为4。实际位置等故障注入相关点位禁止进入算法。留出集含单一仿真系统的7天、21个底层日场景及42个原始与污染配对版本；配对版本不算独立样本。三例演示分别展示实测回放、正常仿真、重复记录修复后继续核查设备疑点。现场补采未实施，其成本不与档案查询混计。',
        'business':'拟服务具有历史表计或设备记录的校园后勤、办公园区运维及能源服务团队，采用本地部署与数据接入服务，后续按维护与分析服务探索收费。首要验证可核查性和接入成本，再通过访谈检验付费意愿及人工复核价值。目前无已确认客户、合作、收入或节能收益；不填无依据的市场规模、售价和回报率。'},
      'technical':{
        'rationale':[
          '能智核的用途是核验公共建筑用能异常：告警出现后，管理者需要知道记录是否可信、已有证据支持哪一种运行疑点，以及下一步值得查什么。仅凭电表曲线不能定位暖通设备故障；数据错误和设备异常也可能同时存在。因此，本项目将数据可信度与运行证据作为两个独立维度，并把结论限定在可复核证据能够支持的范围内。',
          '公共数据为首轮提供了两种不同基础。BDG2由真实建筑表计、天气和建筑属性组成，可支撑数据接入与历史回放；LBNL公开暖通数据提供正常及故障仿真情形，可检验设备核验方法。前者缺少真实设备故障真值，后者来自仿真，二者不拼接成真实建筑故障定位证据。数据来源与授权分别按BDG2的CC BY-SA 4.0和LBNL数据许可元数据的CC BY 4.0保留署名。',
          '本项目不把“模型读取数据后生成报告”直接视为技术突破。主要研究问题是在相同证据池、相同预算和相同数值诊断底座下，本地模型选择下一查询动作是否比固定流程及自适应规则更有价值。现有技术工作方式的比较由本项目对照实验给出，未开展市场份额调查，不声称替代或领先全部商业系统。',
          '应用对象暂定为校园后勤、公共办公楼运维和能源服务人员。该客户定位属于待访谈验证的假设。近期价值是让复核过程可见、结论来源可追溯；实际人工节省和节能收益均需后续现场验证。来源：Miller等，Scientific Data 2020，doi:10.1038/s41597-020-00712-x；Granderson等，LBNL FDD Datasets，doi:10.25984/1881324。'],
        'innovation':{
          '1．项目总体思路':[
            '以一张核验卡贯通“记录检查—证据查询—运行疑点—补证建议”。卡片包含异常时间范围、已观察的程序计算结果、未解决的证据缺口和下一步动作。初始证据与每次查询后揭示的证据明确分开，模型不能读取隐藏标签或未查询的设备点位。',
            '节能机会筛查是附属能力：对实测电表给出相对历史参考的差额线索，并提示其受运行条件变化影响。差额不写为设备故障原因，不写为已经实现的节能量。'],
          '2．可行性分析：项目的技术或实施可行性。':[
            '首轮以公开数据、单机后端和网页工作台实现。已完成三栋建筑回放数据及LBNL案例准备，来源文件有哈希记录。LBNL温度由华氏转换为摄氏，分钟数据统一为五分钟均值，算法只使用允许的常规监测点位。数值统计和结论规则由程序执行；本地免费模型负责动作选择，不生成或改写测量数值。',
            '数据审计发现，四个盘管泄漏严重度文件的完整内容哈希完全相同，因此只保留一份代表，不报告泄漏严重度泛化。静压实值与设定值的单位口径存在冲突，相关点位不进入定量诊断。风阀和盘管实际位置与故障注入机制重合，连同其他非常规点位一起排除。上述处理降低了可用信息，但避免把仿真注入信息当作核验能力。'],
          '3．本项目的特色与创新之处。':[
            '方法特色是把数据问题与设备疑点并行保留，并使受预算约束的证据查询过程可审计。候选创新是主动补证的选择价值，必须通过与自适应规则的实际对照才能成立。固定流程、自适应规则、本地模型与完整信息版本共享数据、证据工具和数值诊断底座，避免把不同工具能力误当成模型收益。',
            result,decision]},
        'implementation':[
          '实现形态为独立本地核验工作台，包含案例列表、曲线回放、证据步骤、核验结论和导出记录。后端读取标准化案例并执行数据查询和数值规则；前端展示回放曲线和核验证据及其来源。本地模型输出限定为允许的下一查询动作，非法动作或无效响应显式记录，不用规则代答伪装成模型结果。结论不展示未经校准的概率分数。',
          '四组证据为：记录质量，检查缺失、重复及序列结构；风路响应，比较室外、回风、混合温度和风阀指令；盘管响应，比较混合、送风、设定温度和冷却阀指令；运行背景，查看风机状态、区域温度与风机指令。所有策略先执行同样计费的记录质量检查，每次查询成本计1。现场补采成本不在本轮测量范围，不按一次档案查询推算现场工时或传感器费用。',
          '数值底座采用在开发案例上确定的指令与温度响应规则，冻结后用于全部留出策略。模型只能看到共同初始摘要和已查询的数值摘要。原始故障文件名、真实故障标签、标称严重度、实际执行器位置均不进入模型输入；候选类型和共享规则对策略公开。规则停止条件和记录修复规则对各策略一致。',
          '开发阶段使用2018年4月2日至5日的12个仿真日场景；演示使用4月10日，不计入留出成绩。留出时间块为4月16日至22日整周，包含正常、未用于调试的风阀源文件标称严重度及唯一盘管泄漏代表，共21个底层日场景。每个场景有原始和统一重复记录污染两个版本，合计42例。相同日期的所有场景和扰动留在同一划分，禁止随机打散时间窗。',
          '主要查询预算预先定为4，预算2和3只作为辅助分析。完整信息版本使用全部4组证据并计入真实查询成本。指标包括准确率、Macro-F1、结论覆盖率、已回答案例错误率、平均查询次数、端到端耗时、模型调用数和无效响应率。无法回答和运行失败均保留在报告中。21个场景共享一个仿真系统及7个日块，不能把42例视为独立建筑验证。',
          '三个可复现演示依次呈现真实表计回放、正常仿真核验及“记录污染与设备疑点共存”。第三例向原始记录插入12条完全重复记录，明确标记人为扰动；去重只修正记录结构，不改变原始运行数据，修复后继续查询设备证据。原始版本、修复步骤及后续结论均可追溯。',
          '留出清单、标签和案例哈希封存；策略、阈值、提示词和预算冻结后才运行正式对照。材料生成器仅从实际汇总结果回填指标，不读取留出案例或标签。系统、源码、依赖与数据许可、案例复现命令和评测记录构成软件作品证明材料。尚未开展真实建筑安装、人工效率实验或节能干预验证。'],
        'prospect':[
          '后续优先寻找能够提供授权历史表计和基础设备记录的公共建筑管理方，先验证字段映射、时间口径、记录质量和人工核验流程，再讨论现场接入。阶段目标是让管理员能依据证据卡复查疑点，而非自动控制设备。若主动模型无增益，则以固定或自适应规则为主要流程，模型只保留可选实验功能。只有取得真实试点授权并完成独立验证后，才扩展设备类型、评估人工收益与节能成效。现阶段不预测推广数量、销售额或节能比例。']},
      'commercial':{
        'overview':'能智核面向公共建筑用能异常核验，提供记录体检、证据查询、运行疑点说明与证据卡，节能机会仅作差额线索。首轮交付本地工作台和公开数据可复现实验，验证对象与真实建筑回放分别标注。当前无实际客户试点、合作、收入或实测节能业绩，商业方案为待验证假设。',
        'team':'按匿名角色规划职责：产品与场景负责人负责需求、核验流程和材料；数据与算法负责人负责数据契约、规则及冻结评测；工程负责人负责工作台、部署与测试。角色可由同一成员兼任，不代表已确认人数或专业经历。队员姓名、电话、培养单位等身份信息不在此稿填写，待官方匿名口径明确后按要求处理。',
        'product':{
          '1.项目产品（服务）特性':[
            '产品围绕一次异常核验提供清楚的操作路径：选择案例，查看记录质量，按预算取得证据，比较修复前后状态，导出结论与待补信息。数据来源分为实测、仿真及人为扰动，界面与报告始终保留区分。用户可检查每个数字来自哪个程序步骤，不能把模型说明当作设备测量。',
            '拟采用本地部署方式，减少历史数据外发；本地免费模型可以关闭或替换，规则流程可独立工作。当前模型和规则的适用性仅由首轮公开数据实验界定，不承诺复杂建筑的直接即用能力。数据接入、时区单位核对、现场点位许可和维护责任仍是产品化的必要工作。'],
          '2.产品（服务）化实施计划':[
            '第一阶段完成公开数据工作台、冻结对照、失败案例说明与可复现代码。第二阶段通过结构化访谈确认使用者、预算负责人、已有记录类型、复核责任与付费意愿；访谈和潜在客户名单目前均未作为已完成成果。第三阶段在获得数据使用与试验授权后开展小范围接入，记录每次映射、复核时间与错报处置，再决定是否提供付费服务。',
            '进入下一阶段的依据是可接入、可复核和维护成本可承受，而不是增加智能体数量。若主动模型不能在同质量下减少查询，且增加时延或维护负担，则采用规则优先的交付形态，避免为展示模型而增加客户负担。']},
        'market':{
          '1.市场概述':[
            '候选使用者是校园后勤、公共办公楼运维和能源服务团队；潜在付费方可能为物业管理单位、建筑业主或服务承包方，需要访谈确认。目标场景是已经拥有历史数据、仍需要人工核实告警的组织。当前未调查可服务市场规模、竞品价格或购买周期，不能据此填入市场份额和销售预测。'],
          '2.竞争优势分析':[
            '拟比较的工作方式包括人工表格复核、固定规则告警、自适应规则核验和模型辅助分析。能智核的产品设计侧重证据来源、修复过程与未解决问题的可见性。是否形成竞争优势，需要同时衡量数据接入成本、核验质量、耗时、复核责任和使用体验。首轮实验只比较查询策略，不等于完成商业竞品横评。',
            decision],
          '3.项目实施风险及应对措施':[
            '数据接入风险通过字段、时区、单位和缺失规则的接入检查管理；跨建筑泛化风险通过限制适用场景和后续独立案例验证管理；模型无效输出通过受限动作、失败记录和可关闭功能处理；结论误用风险通过证据卡与人工复核责任说明控制。公开数据授权与第三方署名随分发材料保留。',
            '仿真源的重复严重度、静压口径冲突及注入相关点位已在首轮审计中处理。后续遇到类似源问题时先修订数据契约，不以不透明的数据筛选维持成绩。真实设备风险、现场维修建议和收益承诺需要具备现场条件与专业责任主体，本轮不作这些承诺。']},
        'model':{
          '1.项目产品（服务）的开发、生产（服务）策略':[
            '拟按“本地软件包＋授权数据接入＋维护分析服务”组织交付。标准部分包括案例导入、证据步骤、核验卡和报告导出；非标准部分包括点位映射、历史规则校准、现场流程确认与维护。先记录这些环节的实际工时和资源消耗，再评估可复制交付范围。'],
          '2.项目产品（服务）的营销策略':[
            '先以公开可复现演示说明产品能处理和不能处理的问题，再向候选用户开展需求访谈。试用须有明确授权、时间范围、评价指标及退出条件。不得把参赛演示写成客户案例，也不把尚未落实的意向描述为合作。推广目标是获得可验证需求，暂不设无依据的客户增长数字。'],
          '3.项目产品（服务）获利方式':[
            '收入假设包括一次性部署与数据接入服务，以及后续维护和分析服务；按楼宇、表计规模或服务范围计费的可行性需调研。价格、毛利和回本周期都依赖接入工时、支持成本、软硬件资源、支付意愿及履约责任，当前不提供无依据报价。免费本地模型不等于运维服务零成本。'],
          '4.（若创业）企业发展计划':[
            '尚无已成立企业、融资或经营业绩可报告。若后续独立需求验证与合法授权试点均支持产品价值，再决定组织形式、知识产权安排、责任边界和服务规模。现阶段优先完成作品与验证，避免以商业包装替代技术及用户证据。']},
        'economics':'当前没有实际销售、客户试点、节能干预和人工工时研究，因此不填营收、利润、投资回报率或节能收益。后续用真实交付数据计算：收入＝部署服务收入＋维护分析服务收入；成本＝数据接入工时成本＋运行资源＋维护支持＋必要授权费用。人工复核时间需在相同任务条件下实测；节能量需在明确干预后采用适当基准验证。软件查询减少不能直接折算为现场节约。取得数据前，各项金额均保持未测。'} }
    if results['available']:
        main_local=next(r for r in results['metric_rows'] if r['strategy']=='local_model' and r['budget']==4)
        docs['brief']['idea']=('首轮已在冻结留出集比较固定流程、自适应规则、本地模型主动补证和完整信息版本。所有数值由程序计算，模型只选择查询动作。'
          f'{main_local["n"]}例中仅{main_local["correct"]}例正确、{main_local["unresolved"]}例未决。'+decision)
        docs['technical']['innovation']['3．本项目的特色与创新之处。'][0]='已检验的候选方法是受预算约束的主动补证。四种策略共享证据池、查询工具和数值底座；本轮结果用于判断模型选择是否增加价值。当前可明确保留的产品特性，是数据问题与设备疑点并行呈现，以及每一步证据与修复过程可追溯。'
        docs['technical']['prospect']=[
          '按首轮结果，以规则核验和可追溯证据工作台为后续基础，本地模型选择仅保留为实验选项。优先收缩适用工况、审计共享数值规则的失效原因；方法调整后另设未参与调试的验证数据。再寻找授权历史记录验证字段、时间口径、数据质量和人工核验流程。产品目前用于研究和演示，不具备真实楼宇设备诊断或自动控制能力的验证。只有取得实际试点授权并完成独立检验后，才讨论扩大设备范围、人工价值与节能成效。']
        docs['commercial']['product']['2.产品（服务）化实施计划'][0]='首轮已完成公开数据工作台与冻结对照，结果明确保留低覆盖和失败边界。下一阶段先收缩适用工况、核查共享规则不足，再以未参与调试的数据复验。随后通过访谈确认使用者、预算负责人、记录类型、复核责任与付费意愿；目前没有完成客户访谈或取得试点授权，不以此填报市场成果。'
        docs['commercial']['product']['2.产品（服务）化实施计划'][1]='本轮未支持将模型主动补证作为主要创新收益。交付路线以简洁的规则核验与证据工作台为主，模型选择只作可关闭实验功能。取得实际数据接入和核验质量证据后，才评估可复制交付范围及服务成本。'
    return docs

def paragraphs(value):
    if isinstance(value,str): return [value]
    if isinstance(value,list): return value
    result=[]
    for subtitle,paras in value.items(): result.extend([subtitle,*paras])
    return result

def validate_counts(docs):
    result=[]
    for doc,sections in docs.items():
        for key,value in sections.items():
            n=count('\n'.join(paragraphs(value)));limit=LIMITS[doc][key]
            result.append({'document':TITLES[doc],'section':SECTION_TITLES[doc][key], 'characters_including_punctuation':n,'limit':limit,'passed':n<=limit})
            if n>limit:raise ValueError(f'{doc}.{key} has {n}>{limit} characters')
    return result

def template_inventory():
    entries=[]
    for number in [1,2,3]:
        source=next(SOURCES.glob(f'附件{number}*docx'))
        with ZipFile(source) as z:
            tree=etree.fromstring(z.read('word/document.xml'))
            part_hash={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not n.endswith('/')}
            section=tree.xpath('//w:sectPr',namespaces=NS)
            entries.append({'number':number,'source':str(source),'sha256':digest(source),'page_count_verified':None,
              'section_count':len(section),'section_xml':[etree.tostring(e,encoding='unicode') for e in section],
              'package_parts_sha256':part_hash,'editable_parts':['word/document.xml','word/settings.xml','docProps/core.xml','docProps/custom.xml','docProps/app.xml'],
              'preserve_only_parts':[n for n in part_hash if n not in ['word/document.xml','word/settings.xml','docProps/core.xml','docProps/custom.xml','docProps/app.xml']],
              'footer_field_inventory':{'word/footer1.xml':['PAGE','PAGE'],'update_required':True},
              'body_paragraphs':[ ''.join(e.xpath('.//w:t/text()',namespaces=NS)) for e in tree.find('w:body',NS) if e.tag==W+'p']})
    return entries

def write_drafts(docs,results,counts,inventory):
    for name,sections in docs.items():
        out=[TITLES[name]+' 非正式填报底稿',PROJECT,TRACK,
             '状态：逐节字数已校验；原模板分页尚未渲染核验；身份字段与TRL待按官方口径确定；不得作为正式提交版本。','']
        if name=='brief':out.extend(['团队名称：[待匿名团队名]','队长姓名：[待官方匿名口径明确]','队长联系电话：[待官方匿名口径明确]','团队成员：[仅保留匿名职责说明]',''])
        for key,value in sections.items():
            row=next(r for r in counts if r['document']==TITLES[name] and r['section']==SECTION_TITLES[name][key])
            out.extend([f'{SECTION_TITLES[name][key]}  当前{row["characters_including_punctuation"]}字  上限{row["limit"]}字','',*paragraphs(value),''])
        if name=='brief':
            out.extend(['技术自评价','研发阶段：软件开发原型阶段，不填写工程部署完成。','先进性：无法判断，不选国内或国际领先。','交付物：软件、方法；源码与复现说明随作品提交。','技术成熟度：暂不选择数字级别，所给指南未提供判级依据。','对照对象：固定流程、自适应规则、本地模型、完整信息；主要预算均为4。','关键指标（本地模型对自适应规则，预算4）：'])
            out.extend([' | '.join(row) for row in results['table']] if results['available'] else ['Macro-F1、结论覆盖率、已回答中的错误率、平均查询次数、平均端到端耗时：均待留出汇总回填。'])
            out.extend(['提升维度：以真实指标为准，不预勾选质量、成本或效率提升。',results['innovation_decision']])
        (MATERIALS/'drafts'/(TITLES[name].replace(' ','_')+'_非正式填报底稿.txt')).write_text('\n'.join(out),encoding='utf-8')
    write_json(MATERIALS/'填报内容.json',{'project':PROJECT,'track':TRACK,'submission_ready':False,'documents':docs,'results':results})
    write_json(MATERIALS/'字数与要求核对.json',{'counting_rule':'Each non-whitespace Unicode code point counts as one, including Latin letters, numerals, punctuation and subsection labels. Conservative relative to ordinary Chinese word counts.','sections':counts,'all_passed':all(x['passed'] for x in counts),'render_verified':False,'submission_ready':False})
    write_json(MATERIALS/'working/template_inventory.json',inventory)
    write_json(MATERIALS/'渲染状态.json',{'status':'BLOCKED_MISSING_ALLOWED_RENDERER','rendered':False,'official_renderer':str(SKILL/'render_docx.py'),'probe_log':'materials/working/render_probe.log','error':'LibreOffice soffice.exe was not found on the controlled bundled-runtime PATH','constraint':'Do not launch user desktop LibreOffice or interrupt other applications.','delivered':'Structured and plain-text drafts only. No DOCX delivered as verified.','resolution':'Provide an isolated authorized renderer, render all original templates, visually inspect each page, then populate the reference render receipt; render every generated DOCX and inspect all pages before formal delivery.'})
    artifact=['# Official template execution contract','', 'Reference files remain authoritative and unchanged. This is an internal generation contract, not a submission document.', '',
      'Render status: unresolved. The official packaged renderer failed because no allowed LibreOffice executable is available. Page counts and visual template patterns are therefore unverified. DOCX creation is gated; text drafts are permitted.', '',
      'Page system: one portrait A4 section per template; top/bottom margins 25.4 mm; left/right 31.75 mm. Exact section XML and package hashes are recorded in template_inventory.json.',
      'Typography: preserve source properties. Original title predominantly FangZheng XiaoBiaoSong 18 pt centered; technical/commercial body FangSong 14 pt, 1.5 lines; brief table FangSong 12 pt. Do not substitute generic styles.',
      'Tables: preserve all source grids, merges, row rules and nested table. Rows use atLeast height. Brief table has 20 rows and one nested 5-column metric table. Fonts are embedded in source package and remain byte-identical.',
      'Recurring components: preserve original footer including drawing/text-box elements and two PAGE fields in AlternateContent branches; customXml contains WPS shape properties; no body content controls or revisions found. Footer appearance remains a render-gate uncertainty. Set updateFields=true in settings to request refresh on Word open; do not flatten page numbers or rewrite the footer.',
      'Editable package parts: document.xml for listed slots; settings.xml only for updateFields; core/custom/app properties for anonymous metadata. Every other part is preserve-only and must keep its SHA-256. Blank creator/lastModifiedBy, tracking identifiers, application fingerprint, cached statistics are intentional anonymity/accuracy deviations.',
      '', 'Stable slot map',
      'Template 1: word/document.xml / w:body / w:tbl[1], zero-based row/cell slots: name 0/1; team 1/1; track 2/1; captain 3/1; phone 3/3; members 4/1; background 6/1; idea 8/1; solution 10/1; business 12/1; stage 13/2; advancement 14/2; outputs 15/2; TRL 16/2; comparators 17/2; nested metrics 18/2; improvement 19/2. Keep captions and merged label cells unchanged.',
      'Template 2: original direct w:body child indexes: 6 rationale slot; 8/9/10 innovation subhead anchors; 12 implementation slot; 13 prospect heading anchor. Paragraph 3 is a draft status marker. Preserve other headings. Clone source body paragraph properties when adding content.',
      'Template 3: original direct body child anchors 5 overview; 6 team; 8/9 product subheads; 11/12/13 market subheads; 15/16/17/18 business subheads; 19 economics. Preserve headings and exact source styles.',
      '', 'Fidelity gates: reference SHA unchanged; same section geometry and package part set; preserve-only hashes unchanged; edits confined to mapped content and anonymous metadata; per-section character caps pass; no invented identity/performance; all final pages rendered and visually inspected.']
    (MATERIALS/'working/artifact.md').write_text('\n'.join(artifact),encoding='utf-8')

def source_text(p,text):
    ts=p.xpath('.//w:t',namespaces=NS)
    if ts:
        ts[0].text=text
        ts[0].set('{http://www.w3.org/XML/1998/namespace}space','preserve')
        for t in ts[1:]: t.text=''
    else:
        r=etree.SubElement(p,W+'r');t=etree.SubElement(r,W+'t');t.text=text
    return p

def new_body_paragraph(sample,text):
    p=etree.Element(W+'p')
    props=sample.find(W+'pPr')
    if props is not None:p.append(copy.deepcopy(props))
    r=etree.SubElement(p,W+'r');rprops=sample.find('w:r/w:rPr',NS)
    if rprops is not None:r.append(copy.deepcopy(rprops))
    t=etree.SubElement(r,W+'t');t.text=text;t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    return p

def insert_after(anchor,values,sample):
    for value in values:
        p=new_body_paragraph(sample,value);anchor.addnext(p);anchor=p

def cell_content(cell,text):
    ps=cell.findall(W+'p')
    if not ps:ps=[etree.SubElement(cell,W+'p')]
    source_text(ps[0],text)
    for p in ps[1:]:cell.remove(p)

def anonymous_properties(parts):
    for name in ['docProps/core.xml','docProps/custom.xml','docProps/app.xml']:
        root=etree.fromstring(parts[name])
        for node in root.iter():
            local=etree.QName(node).localname
            if name.endswith('core.xml') and local in ['creator','lastModifiedBy','description','subject','title','keywords']:
                node.text=''
            elif name.endswith('custom.xml') and local not in ['Properties','property']:
                node.text=''
            elif name.endswith('app.xml') and local in ['Company','Manager','Application','Pages','Words','Characters','CharactersWithSpaces','Lines','Paragraphs','TotalTime']:
                node.text='' if local in ['Company','Manager','Application'] else '0'
        parts[name]=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)

def assert_reference_render_receipt(inventory):
    receipt=MATERIALS/'working/template_render_receipt.json'
    if not receipt.exists():raise RuntimeError('DOCX export blocked: original templates have not been rendered and visually verified. See materials/渲染状态.json.')
    data=json.loads(receipt.read_text(encoding='utf-8'))
    if data.get('all_pages_visually_verified') is not True:raise RuntimeError('Template visual QA receipt is not verified')
    for entry in inventory:
        r=next((r for r in data.get('templates',[]) if r.get('sha256')==entry['sha256']),None)
        if not r or not r.get('page_images') or not all(Path(p).is_file() for p in r['page_images']):
            raise RuntimeError('Missing rendered page evidence for an original template')

def emit_docx(docs,results,inventory):
    assert_reference_render_receipt(inventory)
    # Runs exactly once immediately before the first DOCX authoring operation.
    subprocess.run([str(RUNTIME/'node/bin/node.exe'),str(SKILL/'container_tools/mark_artifact_operation_started.mjs'),'--operation-kind','create','--expected-output-count','3','--output-format','docx'],check=True,cwd=MATERIALS)
    reports=[]
    for number,docname in [(1,'brief'),(2,'technical'),(3,'commercial')]:
        entry=next(x for x in inventory if x['number']==number);source=Path(entry['source'])
        if digest(source)!=entry['sha256']:raise RuntimeError('Retained reference changed')
        with ZipFile(source) as z:parts={name:z.read(name) for name in z.namelist()}
        tree=etree.fromstring(parts['word/document.xml']);body=tree.find(W+'body');original=list(body)
        source_text(original[3],'（非正式填报稿 待完成最终排版与匿名核验）')
        sections=docs[docname]
        if number==1:
            rows=body.find(W+'tbl').findall(W+'tr')
            cells=lambda r:rows[r].findall(W+'tc')
            for r,c,text in [(0,1,PROJECT),(1,1,'[待匿名团队名]'),(3,1,'[待官方匿名口径]'),(3,3,'[待官方匿名口径]'),(4,1,'产品与场景、数据与算法、工程实现等匿名职责；不填未经确认成员身份。'),(6,1,sections['background']),(8,1,sections['idea']),(10,1,sections['solution']),(12,1,sections['business']),(13,2,'软硬件开发类；首轮软件原型。'),(14,2,'无法判断；不作国内或国际领先评价。'),(17,2,'固定流程、自适应规则、本地模型和完整信息；主要预算4。'),(19,2,'以留出结果核定质量、成本和效率；不预填改善承诺。')]:cell_content(cells(r)[c],text)
            track=cells(2)[1]
            for p in track.findall(W+'p'):
                t=''.join(p.xpath('.//w:t/text()',namespaces=NS))
                if '6.定向赛道-智慧能源与环境' in t:
                    # Preserve preceding track-5 checkbox; only select the final checkbox.
                    ix=t.rfind('□');source_text(p,t[:ix]+'☑'+t[ix+1:])
            out=cells(15)[2]
            for p in out.findall(W+'p'):
                t=''.join(p.xpath('.//w:t/text()',namespaces=NS));source_text(p,t.replace('□软件','☑软件').replace('□方法','☑方法'))
            metrics=cells(18)[2].find(W+'tbl').findall(W+'tr')
            values=results['table'] if results['available'] else [[title,'待留出结果','待留出结果','待核验','自适应规则 预算4'] for title in ['Macro-F1','结论覆盖率','已回答中的错误率','平均查询次数','平均端到端耗时']]
            for row,vals in zip(metrics[1:],values):
                for cell,value in zip(row.findall(W+'tc'),vals):cell_content(cell,value)
        elif number==2:
            sample=original[6]
            source_text(original[6],sections['rationale'][0]);insert_after(original[6],sections['rationale'][1:],sample)
            for anchor,key in zip([8,9,10],sections['innovation']):insert_after(original[anchor],sections['innovation'][key],sample)
            source_text(original[12],sections['implementation'][0]);insert_after(original[12],sections['implementation'][1:],sample)
            insert_after(original[13],sections['prospect'],sample)
        else:
            sample=original[20]
            # The blank body paragraph's properties are source-derived. Copy body
            # run properties from source subheading only if the blank has none.
            if sample.find('w:r/w:rPr',NS) is None:sample=original[8]
            insert_after(original[5],[sections['overview']],sample);insert_after(original[6],[sections['team']],sample)
            for anchors,key in [([8,9],'product'),([11,12,13],'market'),([15,16,17,18],'model')]:
                for anchor,subkey in zip(anchors,sections[key]):insert_after(original[anchor],sections[key][subkey],sample)
            insert_after(original[19],[sections['economics']],sample)
        parts['word/document.xml']=etree.tostring(tree,xml_declaration=True,encoding='UTF-8',standalone=True)
        settings=etree.fromstring(parts['word/settings.xml'])
        update=settings.find(W+'updateFields')
        if update is None:update=etree.SubElement(settings,W+'updateFields')
        update.set(W+'val','true')
        parts['word/settings.xml']=etree.tostring(settings,xml_declaration=True,encoding='UTF-8',standalone=True)
        anonymous_properties(parts)
        for name in entry['preserve_only_parts']:
            if hashlib.sha256(parts[name]).hexdigest()!=entry['package_parts_sha256'][name]:raise RuntimeError('Preserve-only package part changed: '+name)
        target=MATERIALS/'working'/(TITLES[docname].replace(' ','_')+'_待渲染.docx')
        with ZipFile(target,'w') as z:
            for name,payload in parts.items():z.writestr(name,payload)
        if digest(source)!=entry['sha256']:raise RuntimeError('Original was modified')
        reports.append({'file':str(target.relative_to(ROOT)),'sha256':digest(target),'preserve_only_parts_unchanged':True,'render_verified':False,'submission_ready':False})
    write_json(MATERIALS/'working/docx_build_report.json',reports)
    print('Three working DOCX files created. They MUST be rendered and every page visually verified before delivery.')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--emit-docx',action='store_true');args=parser.parse_args()
    (MATERIALS/'drafts').mkdir(parents=True,exist_ok=True);(MATERIALS/'working').mkdir(parents=True,exist_ok=True)
    retain_references()
    results=read_results(ROOT/'output/benchmark.json');docs=content(results);counts=validate_counts(docs);inventory=template_inventory()
    write_drafts(docs,results,counts,inventory)
    if args.emit_docx:emit_docx(docs,results,inventory)
    print(json.dumps({'documents':3,'sections':len(counts),'all_character_caps_passed':True,'benchmark_populated':results['available'],'docx_render_verified':False,'submission_ready':False},ensure_ascii=False))

if __name__=='__main__':main()
