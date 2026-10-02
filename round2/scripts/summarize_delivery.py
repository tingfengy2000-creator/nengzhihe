"""Render factual delivery notes from the locked first held-out result."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
def main():
    b=json.loads((ROOT/'output/benchmark.json').read_text(encoding='utf-8'))
    rows=json.loads((ROOT/'output/evaluation_final/scored_rows.json').read_text(encoding='utf-8'))
    metrics={m['method']:m for m in b['diagnosis_comparison']+b['policy_comparison']}
    correct={m:{r['case_id'] for r in rows if r['method']==m and r['truth']==r['prediction']} for m in metrics}
    lines=['能智核｜第二轮真实时间留出结果与继续建议','',
      '范围：同一LBNL仿真单风道机组；新日期时间留出，不是跨设备或真实建筑故障验证。',
      '最终日期：2018-06-04—10与2018-07-09—15；14日期、2连续周块、56基础日工况、112原始/人为重复成对记录。成对版本不是独立样本。',
      '规则冻结后一次性完成448次运行，所有预测落盘后才读取标签评分；首轮42条不在最终分母。','',
      '方法\t正确/总数\t未决\t已判错误率\t覆盖率\t正常/风阀/泄漏召回\t均查询\t平均/p95端到端ms']
    for m in metrics.values():
        recalls='/'.join(f'{100*m["recall"][k]:.2f}%' for k in ['normal','damper_stuck','coil_leakage'])
        lines.append(f'{m["label"]}\t{m["correct"]}/{m["n"]}\t{m["unresolved"]}\t{m["wrong"]}/{m["n"]-m["unresolved"]} ({100*m["error_rate"]:.2f}%)\t{100*m["coverage"]:.2f}%\t{recalls}\t{m["avg_queries"]:.4f}\t{m["avg_latency_ms"]:.3f}/{m["p95_latency_ms"]:.3f}')
    lines += ['',f'旧新完整信息正确集合交集：{len(correct["old_full"]&correct["new_full"])}条；新增正确{len(correct["new_full"]-correct["old_full"])}条；旧正确退为其他{len(correct["old_full"]-correct["new_full"])}条。',
      f'固定与自适应正确集合完全相同：{correct["fixed"]==correct["adaptive_rule"]}。',
      '未决没有从总体分母剔除；没有“异常未定位算正确”的处理。0错仅描述本批已判样本，不能解释为普遍零误报。',
      '原始与重复版本各56条，结果相同：旧3/56、新12/56正确。应以56基础工况和14日期理解数据规模。',
      '端到端实测为本机文件读取解析→处理/证据查询/规则判断→JSON编码；不含网络、日志落盘、网页绘制。新诊断器比旧版耗时增加，未声称提速。',
      '每组离线证据记1查询单位；现场补采未执行、成本未测，不能将查询变化换算节约现场工时。', '',
      '继续/收缩建议',
      b['decision'],
      '继续：展示工况与证据窗口约束后的风阀候选核验；展示实测/仿真/人为扰动标识、支持和反驳证据、具体补证动作，以及去重后继续设备核验。保留现有简单架构。',
      '收缩：不主打“主动Agent提高诊断效率”或通用三类诊断；最终正常和泄漏召回均0，说明当前新日期可用性仍有限。正常演示仅说明已见、合格工况的功能，不代表留出泛化能力。',
      '关键缺口：更多可辨识的稳定关阀时段及温度/指令覆盖；未来独立数据验证（本轮不扩大设备）；真实BMS/运维证据接入。若考虑实际位置反馈须单列接入条件、重新评价，当前无此依赖。',
      '不可写入：原创诊断算法、模型推理收益、真实楼宇自动故障定位、跨设备泛化、实测节能率、合作试点、商业收入或保证获奖。',
      '三份DOCX遵循原模板结构和字数限制；本机缺可用渲染器，标待视觉复检，不作为正式提交版。']
    (ROOT/'output/最终结果与建议.txt').write_text('\n'.join(lines),encoding='utf-8')
    print('\n'.join(lines[:12]))
if __name__=='__main__':main()
