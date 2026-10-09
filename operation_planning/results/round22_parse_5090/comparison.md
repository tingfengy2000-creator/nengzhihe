# 第22节：18句逐例对照

口径：同一current_task、同一模型/采样，每阶段每句一次真实HTTP解析；不进行全年计算，不用规则补造。失败和中间开发轮次保留。

| 句子 | 修改前 | 冻结版本 | 剔除字段 |
|---|---|---|---|
| 每间改成3台空调，其他条件不变 | 正确修改：room.units_per_room=3 | 正确修改：room.units_per_room=3 | — |
| 把空调型号换成美的GAIA-12HRFN8 | 正确修改：room.equipment_id=midea_gaia12 | 正确修改：room.equipment_id=midea_gaia12 | — |
| 把空调改成格力三匹，其他条件不变 | 不支持，未产生修改 | 不支持，未产生修改 | — |
| 预算翻倍，其他条件不变 | 正确修改：hybrid.budget_cny=180000.0 | 正确修改：hybrid.budget_cny=180000.0 | — |
| 把使用时段改为18:00到22:00，其他条件不变 | 正确修改：room.start_hour=18; room.end_hour=22 | 正确修改：room.start_hour=18; room.end_hour=22 | — |
| 关闭余电卖给电网，其他条件不变 | 正确修改：hybrid.allow_export=False | 正确修改：hybrid.allow_export=False | — |
| 光伏改为2kWp，其他条件不变 | failed：模型光伏容量与用户明确输入的数值/单位不一致，请重新说明容量 | 正确修改：pv.capacity_kwp=2 | — |
| 风机改为0台，其他条件不变 | failed：模型修改了用户未提及的字段：room.equipment_id | 正确修改：hybrid.wind.turbine_count=0 | — |
| 电价每年涨3%，其他条件不变 | 正确修改：hybrid.tariff_escalation_rate=0.03 | 正确修改：hybrid.tariff_escalation_rate=0.03 | — |
| 储能单价改为600元/kWh，容量列表改为0、5、10kWh | 正确修改：storage.quote.cny_per_kwh=600; storage.capacities_kwh=[0, 5, 10] | 正确修改：storage.quote.cny_per_kwh=600; storage.capacities_kwh=[0, 5, 10] | — |
| 让储能按峰谷电价自动套利并保证回本 | failed：模型修改了用户未提及的字段：hybrid.allow_export | 不支持，未产生修改 | hybrid.allow_export, hybrid.import_price_cny_per_kwh, hybrid.export_price_cny_per_kwh, hybrid.tariff_escalation_rate |
| 预算调低一些 | 追问，未产生修改 | 追问，未产生修改 | — |
| 光伏装机设置为2千瓦，其他条件不变 | 正确修改：pv.capacity_kwp=2 | 正确修改：pv.capacity_kwp=2 | — |
| 风机数量设为零台，其他条件不变 | failed：模型修改了用户未提及的字段：room.equipment_id | 正确修改：hybrid.wind.turbine_count=0 | — |
| 不要风机了 | failed：模型修改了用户未提及的字段：room.equipment_id | 正确修改：hybrid.wind.turbine_count=0 | — |
| 装两台风机 | failed：hybrid.wind.turbine_count超出范围 | failed：hybrid.wind.turbine_count超出范围 | — |
| 光伏装 5kWp | failed：不支持的修改字段：pv.requested_capacities_kwp | 正确修改：pv.capacity_kwp=5 | — |
| 预算改为6万 | 正确修改：hybrid.budget_cny=60000 | 正确修改：hybrid.budget_cny=60000 | — |

原14句：可执行修改8→11（11条允许执行）；18句：9→14（14条允许执行）。最终另有2条unsupported、1条追问、1条数量超限failed。
“装两台风机”理解为2台，但现有WindScenario和共同schema仅支持0/1，故不修改模型、不给假成功。
最终HTTP耗时约0.199–0.481秒；模型与采样未变。缓存温度不同，不据此声称提速。
after是首次开发重跑，其中套利句被错误附带当前购电价；after_final修正这一界限；after_frozen为最终源码的整组回归。全部保留，未按最佳结果挑选。
