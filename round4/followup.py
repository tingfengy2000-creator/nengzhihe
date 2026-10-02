"""Prioritize the human follow-up for an existing damper candidate; no diagnosis change."""
def prioritize(run):
    final=run['final']
    if final.get('label')=='damper_stuck':
        action={'action':'damper_field_check','type':'field_unmeasured',
                'text':'风阀优先补证：复核室外、回风与混风温度测点；由运维人员在允许的稳定工况下核对风阀指令与执行器实际动作，排查卡滞或传感器偏差。',
                'detail':'程序未读取实际阀位，也不自动控制设备；现场检查尚未实施。'}
        final['next_actions']=[action,*[a for a in final.get('next_actions',[]) if a.get('action')!='damper_field_check']]
        # The browser reads the normalized operation, while the card reads final.
        # Keep this presentation advice in sync without changing any diagnosis.
        for obj in [final.get('operation'), final.get('diagnosis'), (final.get('diagnosis') or {}).get('operation')]:
            if isinstance(obj,dict):
                obj['next_actions']=final['next_actions']
    return run
