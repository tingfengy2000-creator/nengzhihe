# 阶段二A接口正确性收尾交接

## 版本与范围

- 计算版本：`phase2a-interval-normalized-v2`
- 气象归一化版本：`preceding-hour-right-label-v2`
- pvlib：`0.11.2`
- 本轮只修正辐照区间、逆变器 `pdc0` 定义和区间内分时计费；没有改架构、Agent、价格参数或推荐规则。
- `results/pv_phase2a/` 与 `results/pv_phase2a_correctness/` 保留不变；本轮结果在 `results/pv_phase2a_interval_finalize/`。

## 三个可手验的定义结果

1. 原始 Open-Meteo 右标记辐照：源时间 `08:00` 表示区间 `[07:00,08:00)`，归一化后 `interval_start=07:00`、`interval_end=08:00`、代表时刻 `07:30`。温度、湿度、压力和风速仍取区间起点源行，不整体平移。全年末端只补下一年 `00:00` 的真实边界行，2024 保持 8784 个区间。
2. 2 kWp 组件、逆变器配比 0.85、`eta_inv_nom=0.96`：组件额定 DC 为 `2000 W`，逆变器额定 AC 为 `1700 W`，传给 pvlib 的 `pdc0=1700/0.96=1770.833333 W`；充分输入、其他损失关闭时交流输出为 `1700 W`。旧的直接传入 `1700 W` 会得到 `1632 W`，测试保留该反例。
3. 08:00—09:00 恒定 1 kW，前半小时 `0.50 CNY/kWh`、后半小时 `1.00 CNY/kWh`，区间被切成两个价格片段，费用为 `0.75 CNY`。跨午夜和整点边界也有测试；恒价 0.66 的路径保持不变。

## 重算内容

- 广州 2024：0/1/2/3 kWp、10 年和 15 年现金流、使用时段变更、屋顶/预算约束；每个候选保留逐时 CSV。
- 广州/北京/哈尔滨 2023—2025：固定 2 kWp 九组时间年结果；不称跨设备或实测建筑验证。
- Agent：预算 9000→6000 的真实本地模型任务成功；使用时段和报价修改成功；开启外送但缺外送价返回澄清，不以程序兜底冒充模型成功。

## 主要结果变化

区间修复改变了广州 2024 的空调情景负荷和发电匹配：0 kWp 基准负荷为 `1251.283914 kWh`，2 kWp 发电为 `2213.986711 kWh`。这是时间语义修正后的重算结果，不是调价或调参维持旧推荐。当前报价与服务缺口条件下，有限候选的条件性推荐仍为 0 kWp；这不证明真实项目“不安装最划算”。

## 复现

```powershell
python tests/test_phase2a_correctness.py
python tests/test_phase2_pv.py
python scripts/phase2a_interval_finalize_demo.py
python scripts/phase2a_interval_finalize_agent.py
python scripts/phase2a_interval_finalize_variants.py
```

`weather/boundaries/` 与 `weather_pv/boundaries/` 只包含每个缓存年度所需的单条末端真实边界记录，并保存原始来源 URL、缓存哈希和变量清单；没有上传模型权重或私人资料。
