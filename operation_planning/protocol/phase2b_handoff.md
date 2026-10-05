# Phase 2B 风光联算交接

## 业务任务

同一城市、年份、空调负荷、地区电价与研究期下比较 S0 只购电、S1 仅光伏、S2 仅风电、S3 风光组合。发电先按同一计量边界合并，再按逐时负荷一次匹配，避免两套发电重复占用负荷。

## 公开风机依据

首版选用 SD Wind Energy SD6 的 SWCC-11-04 认证系统。认证报告明确测试系统为 9 m 单极塔、SMA Wind Interface 与 Aurora Power One 6 kW 并网逆变器，额定 5.2 kW@11 m/s、峰值 6.1 kW@17 m/s，功率曲线参考密度 1.225 kg/m³。曲线提取为报告表格中的 W 值，`operation_planning/data/wind_profiles/sd6_swcc_11_04.json` 保存来源 URL、下载哈希、测量边界和区间外处理。原始 PDF 只在本地作来源核对，不随结果包再分发。

## 计算边界

复用已验收的 `weather_pv` 逐时缓存，10 m 风速 km/h 转 m/s，以 `windpowerlib.wind_speed.hellman` 做 10 m→9 m 高度换算，`windpowerlib.power_output.power_curve` 做线性插值。认证曲线已经是包含报告所列接口/逆变器的系统输出，不再重复扣逆变器效率。曲线范围外使用 0 W 的保守边界情景并记录标志，不把它解释成已知停机规则；负的低速辅助读数截为0并计数。风速保留区间起点，未沿用辐照的前一小时平移。

## 成本与约束

四个方案使用相同负荷与电价。首版只允许 0 或 1 台完整 SD6；风机场地、障碍、并网、噪声、基础和实测风况未核验。示例风机报价是用户情景参数，不是采购报价。预算超出或报价缺失的方案保留物理结果但不进入经济推荐。PV年衰减逐年重算小时匹配；风机不继承PV衰减，默认只使用显式可用率。

## 结果范围

广州2024保存全四候选逐时证据；广州、北京、哈尔滨2023—2025使用同一2 kWp+1台SD6、9 m、0.14幂律配置保存九组汇总。它们是城市级天气情景，不是现场勘测、实测楼宇或跨设备验证。

## 运行

```powershell
python scripts/phase2b_wind_demo.py
python tests/test_phase2b_wind.py
python -m operation_planning.app
```

工作台新增 `/api/operation/hybrid/run` 与“风光联算”页；`use_agent=true` 时本地模型先解释修改、校验输入、读取档案，再调用真实计算工具。模型失败不会伪装成确定性成功。
