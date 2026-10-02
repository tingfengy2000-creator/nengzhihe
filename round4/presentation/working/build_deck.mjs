import fs from 'node:fs/promises';
import path from 'node:path';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
const R=path.resolve(import.meta.dirname,'../..');
const P=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:'#173D38',teal:'#287D69',muted:'#56736C',paper:'#FAFCFA',pale:'#EDF4EF',amber:'#996723'};
const font='Microsoft YaHei';
function text(s,txt,x,y,w,h,size=27,bold=false,color=C.ink){const sh=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});sh.text=txt;sh.text.style={typeface:font,fontSize:size,bold,color,autoFit:'none'};return sh;}
function slide(title,kicker,source){let s=P.slides.add();s.background.fill=C.paper;text(s,kicker,64,28,1080,30,18,false,C.teal);text(s,title,64,76,1152,68,44,true);text(s,'能智核 · 智慧能源与环境',64,675,1000,25,17,false,C.muted);text(s,String(P.slides.items.length),1170,672,48,30,18,false,C.muted);s.speakerNotes.textFrame.setText(source);return s;}
async function img(s,name,x,y,w,h,crop){s.images.add({blob:new Uint8Array(await fs.readFile(path.join(R,'output/ui',name))),contentType:'image/png',alt:'实际运行界面 '+name,fit:'contain',position:{left:x,top:y,width:w,height:h},...(crop?{crop}:{})});}
function tbl(s,values,x,y,width,height,widths){let t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width,height,columnWidths:widths,values});t.borders.assign({fill:'#C8D7CE',width:1,style:'solid'});for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){let cell=t.getCell(r,c);cell.fill=r===0?C.ink:r%2===0?C.pale:'#FFFFFF';cell.text.style={typeface:font,fontSize:25,bold:r===0,color:r===0?'#FFFFFF':C.ink};}return t;}

let s=P.slides.add();s.background.fill=C.ink;
text(s,'能智核',72,122,1050,118,88,true,'#FFFFFF');
text(s,'公共建筑风阀疑点核验\n与补证工作台',74,265,1110,150,48,true,'#E4F0E8');
text(s,'告警之后，先查什么？',74,470,1050,65,36,false,'#D7E7BF');
text(s,'智慧能源与环境 · 公开数据原型',74,628,1090,34,21,false,'#D5E2DD');
s.speakerNotes.textFrame.setText('本作品聚焦告警之后的一项实际任务：核对风阀疑点并交接下一步动作。当前是公开数据原型，没有真实部署或人工提效结论。');

s=slide('把一条告警，变成一次有依据的核查','01 / 用户任务','依据：round4/server.py、importer.py、quality.py、diagnostics.py、reporter.py。对象为公共建筑运维人员及能源服务团队，需求价值仍须真人验证。');
text(s,'使用者需要回答三个问题',64,166,1140,48,31,true);
const xs=[64,460,850];
['01  数据可信吗？','02  当前能检验吗？','03  接下来补什么？'].forEach((x,i)=>text(s,x,xs[i],260,356,62,30,true,C.teal));
['核对单位与真实时间间隔\n保留重复、缺失和冲突证据','查看启停、温差和连续窗口\n工况不足时保留未决','写明点位、时段和现场动作\n让下一位人员能接着核查'].forEach((x,i)=>text(s,x,xs[i],352,352,164,26));
text(s,'一份运行 CSV → 一张可阅读、可追溯的核查卡',64,563,1135,60,33,true);

s=slide('从公开原始 CSV 开始，完成真实操作','02 / 导入与映射','实机图：output/ui/csv_mapping.png。原始片段2018-04-10，1440行31列。17允许点位；错误间隔拒绝；完整1分钟桶聚合为5分钟。该日期是开发演示，不是新性能样本。');
text(s,'1440 → 288',64,182,355,75,48,true,C.teal);
text(s,'原始观测 → 五分钟记录',64,267,352,56,26);
text(s,'确认字段、单位、时间间隔\n\n错误声明明确拒绝\n\n缺失保留，不补零或插值',64,353,335,236,26);
await img(s,'csv_mapping.png',433,162,785,458,{left:.185,top:.378,right:.025,bottom:.012});
text(s,'接入仅限已验证的 LBNL 单风道机组仿真配置',442,628,773,29,20,false,C.muted);

s=slide('数据修好了，设备疑点仍需继续核查','03 / 两个独立维度','实机图：output/ui/dual_dimensions.png。12条完全重复记录被删除后，数据质量通过，风阀候选仍存在。server与reporter共同使用规范化质量对象；followup同步UI和卡片的补证顺序。');
text(s,'300 → 288 条',64,189,370,60,39,true,C.teal);
text(s,'去掉 12 条完全重复记录',64,271,360,66,27);
text(s,'数据质量：记录检查通过\n\n设备判断：风阀疑点保留\n\n补证动作：测点与执行器复核',64,373,360,236,26);
await img(s,'dual_dimensions.png',446,167,769,438,{left:.183,top:.333,right:.035,bottom:.072});
text(s,'修正、修改证据后真实重算；移除风路证据会退回未决',445,628,768,28,19,false,C.muted);

s=slide('先核对可检验条件，再计算证据','04 / 技术实现','依据：diagnostics.py与quality.py冻结源码；LBNL SDAHU官方说明2022：https://fdddata.lbl.gov/data/Simulated_LBNL_FDD_Data_Sets_SDAHU/LBNL_FDD_Data_Sets_SDAHU.pdf。OA_DMPR_DM为控制指令，实际位置字段不作诊断输入。');
text(s,'单位 / 时间轴\n同一质量对象',64,183,320,97,31,true,C.teal);
text(s,'启停 / 温差 / 时段\n有效工况窗口',464,183,320,97,31,true,C.teal);
text(s,'支持 / 限制 / 缺口\n补证与导出',864,183,330,97,31,true,C.teal);
text(s,'风路条件',64,339,240,47,29,true);
text(s,'启动段之后 · 室外 / 回风温差 ≥ 3℃ · 开发参考覆盖\n连续窗口与有效持续时长满足要求，才形成候选',326,330,886,115,28);
text(s,'当前边界',64,502,240,47,29,true);
text(s,'控制指令 ≠ 实际阀位；参考内 ≠ 已排除卡滞\n盘管无合格关阀时段时不可检验，不自动判正常',326,495,886,119,28);

s=slide('56 个基础日工况，12 个一致风阀候选','05 / 历史回归，保留全部对照','来源：output/comparison/summary.json与base_case_results.csv。14日期，2连续日期块，1仿真系统。12/56是候选与源标签一致数，不是通用风阀准确率估计。旧112已用于开发/失败分析。025/075按官方文档表示卡滞开度。');
tbl(s,[['源工况设置','基础数','一致候选','未决'],['正常','14','0','14'],['卡滞开度 25%（025）','14','1','13'],['卡滞开度 75%（075）','14','11','3'],['盘管阀泄漏','14','0','14'],['合计','56','12','44']],64,179,1152,355,[510,190,235,217]);
text(s,'14 个日期 · 2 个日期块 · 1 套仿真系统；未决始终计入分母',64,558,1150,45,25);
text(s,'卡滞开度不等同故障轻重；正常与泄漏三分类召回仍为 0',64,617,1150,38,23,false,C.amber);

s=slide('增加必要对照，没有观察到性能优势','06 / 如实保留没有差异的结果','冻结清单output/comparison_frozen.json先于本次比较；三方法共用历史输入、质量与运行工况约束。固定阈值是自建工程基线，不是专业行业产品。消融仅去连续窗口约束，非新增算法。所有记录已经用于调试；没有新留出结果。软件计算工作范围不同，不比较毫秒提效。');
tbl(s,[['方法','一致候选 / 56','未决 / 56'],['当前工作台','12 / 56','44 / 56'],['固定温差阈值','12 / 56','44 / 56'],['消融：去连续窗口约束','12 / 56','44 / 56']],64,196,1152,287,[620,272,260]);
text(s,'112 条配对记录：56 组原始 / 重复记录，三方法各 0 组标签变化',64,524,1150,46,25);
text(s,'不主张算法领先、零误报或自适应提效；本轮无新留出成绩',64,602,1150,42,26,true,C.amber);

s=slide('真正要验证：人员能否完成更好的核查','07 / 真人价值实验包，待实施','依据：study/private/protocol.json、rubric.json、answer_key_draft.json、task_manifest.json。计划5–10人，实际0人。8任务来自2开发日期×4设置，匹配但不重复；4顺序交叉平衡。参考答案独立复核和难度匹配检查尚未完成，软件演练不算真人结果。');
text(s,'A：曲线 / 表格\nB：核验工作台',64,182,360,110,33,true,C.teal);
text(s,'相同数据、参考与检查清单\n\n8 个匹配且不重复的任务\n4 种交叉平衡顺序\n\n记录时间、遗漏、错误归因\n以及超时失败与人员背景',64,325,370,291,25);
await img(s,'study_welcome.png',459,180,757,431,{left:.015,top:.00,right:.02,bottom:.01});
text(s,'当前：0 位真实参与者；参考答案和评分须先独立复核',459,628,756,29,20,false,C.amber);

s=slide('已实现、已验证、待验证，分别交付','08 / 当前价值与边界','软件检查：output/reliability_tests.json 29项、standalone_tests.json 13项、study_software_checks.json 21项。软件检查通过不证明实际使用提效。商业模式为待检验的同类设备本地工具与接入服务假设，没有试点、合作、收入。');
const labels=['已实现','已验证','待验证'];const desc=[['CSV → 核查卡','三个演示与真实重算','支持证据和具体补证动作'],['单位与时间轴：2项修复','29 项可靠性检查','HTTP检查13项\n邀测机制21项'],['参考答案独立复核','真实人员任务质量与时间','同类真实设备与付费意愿']];
labels.forEach((x,i)=>{text(s,x,xs[i],204,350,68,40,true,C.teal);desc[i].forEach((d,j)=>text(s,d,xs[i],326+j*82,354,67,27));});
text(s,'拟服务公共建筑运维的核查交接；尚无试点、节能量或收入证明',64,608,1155,46,25,false,C.muted);

s=slide('让下一位核查人员，知道从哪里继续','09 / 可直接查看的交付','评审入口delivery/review/index.html；三分钟视频video/final；10页答辩PPTX/PDF；3份官方结构DOCX及PDF；study README与主持人独立复核包。下一步为参考答案独立复核与真实人员招募，不以更多回归次数替代价值证据。');
text(s,'评审无需安装',64,202,450,65,40,true,C.teal);
text(s,'三分钟实机演示\n\n答辩 PDF 与三份申报材料\n\n可阅读核查卡与真实分组结果',64,309,485,236,30);
await img(s,'card.png',619,170,594,421,{left:.055,top:.00,right:.055,bottom:.03});
text(s,'下一步：独立复核参考答案 → 真人邀测 → 再决定现场验证',64,615,1153,45,26,true);

await fs.writeFile(path.join(R,'presentation/working/slide_plan.json'),JSON.stringify({title:'能智核——公共建筑风阀疑点核验与补证工作台',slides:10,narrative:'actual_task',fonts:[font],native_table_slides:[6,7],sources:['output/comparison/summary.json','output/reliability_tests.json','output/standalone_tests.json','output/study_software_checks.json','study/private/protocol.json'],performance_claim:'historical regression only; no advantage or human-value result'},null,2));
await(await PresentationFile.exportPptx(P)).save(path.join(R,'presentation/working/candidate.pptx'));
console.log('10 editable slides exported');
