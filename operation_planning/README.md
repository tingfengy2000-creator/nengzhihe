# 能智核工作台

展示主张：**先试算，再决策。**

当前增强分支在保留 BOPTEST `bestest_air` 方案工作台的基础上，加入第一阶段空调选型闭环：城市或用户 CSV 天气 → 单房间热湿负荷 → 公开额定点设备响应 → 逐时电量 → 逐月费用 → 用户报价驱动的全生命周期现金流。页面不向设备下发控制，结果不等同于现场楼宇预测。

## 启动

```powershell
python operation_planning/run_server.py
# http://127.0.0.1:18765
```

第一阶段 API：

- `GET /api/operation/weather/sites`：查看 3 城市 2023–2025 缓存年份。
- `POST /api/operation/weather/import`：导入含 `timestamp,temp_c,rh_percent,pressure_hpa,solar_w_m2` 的用户 CSV。
- `POST /api/operation/thermal/run`：按城市/年份或导入天气运行单房间热湿模型；可传 `equipment_quote` 覆盖采购、安装、维护参考值。
- `GET /api/operation/equipment`：查看型号来源和限制。

完整数据哈希和范围说明见 `protocol/weather_manifest.json`、`protocol/first_stage_model.md`、`results/regional_product_v2/`。第二阶段只保留 `SiteContext`、`WeatherContext`、`LoadSeries`、`EquipmentProfile` 和现金流接口，本轮没有生成光伏或风电结果。

三个可复现演示可运行 `python scripts/first_stage_demo.py`，输出地区/年份比较、受控湿度目标变化和报价/批量房间场景到 `results/regional_product_v2/three_demos.json`。

## 证据边界

天气是 Open-Meteo Historical Weather API / ERA5 城市级再分析，按 CC BY 4.0 归因，不是楼宇微气候实测。热湿模型是可审计的集总参考模型；PsychroLib 2.5.0 以 MIT 许可证随项目分发。三条设备记录是公开网页/能效标签的额定点，SHR、报价和完整部分负荷曲线缺失时会在结果中保持待补或参考情景。`results/regional_product_v2/summary.json` 的 27 条组合用于复现地区、年份与型号变化，不能写成实测精度、节能收益或采购承诺。

旧轮次诊断源码、结果和发布包保持原状；本分支只在 `operation_planning/` 增加独立产品链。
