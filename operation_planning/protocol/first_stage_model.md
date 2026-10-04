# 第一阶段：空调热湿负荷、设备响应与全生命周期成本

本轮产品主线是“先试算，再决策”。输入地点、参考年份或用户逐时 CSV、房间条件和用户报价后，系统生成逐时热湿负荷、设备能力、电量、逐月费用和研究期现金流。当前范围是单房间或相同房间数量，不能代替建筑总表、现场 BMS 或楼宇实测校准。

## 数据与可复现性

`data/weather/` 保存广州、北京、哈尔滨 2023–2025 年的 Open-Meteo Historical Weather API / ERA5 逐时缓存。`weather_manifest.json` 记录每个文件的哈希、变量、单位、坐标和时区。再分析资料代表城市尺度参考气候，不是楼宇微气候实测；辐照字段是过去一小时平均值。用户 CSV 可通过工作台导入，必须提供时间戳、室外温度、相对湿度、气压和太阳辐照，长缺口或错序会拒绝。Open-Meteo 数据按 CC BY 4.0 使用，交付材料保留 Open-Meteo 与 ERA5 归因；免费 API 的非商业调用量和服务准确性遵循其当前条款，离线演示优先使用缓存。

## 热湿模型边界

`thermal_model.py` 是可审计的单房间集总模型，显式计算围护传热、窗户太阳得热、人员/设备显热、新风与渗透显热、人员散湿和通风潜热；室内温度与含湿量按实际时间间隔推进。湿空气性质来自随项目分发的 PsychroLib 2.5.0（MIT，`vendor/psychrolib.py`），使用 SI 单位计算含湿量、焓、露点和湿球温度。设备只在冷却季、达到温控需求时提供冷量；容量不足、温度缺口和湿度缺口会保留在结果中，不以少供冷换取低成本。

围护传热、有效热容、窗户太阳得热系数、默认新风和默认 SHR 是建筑原型参考值，不是已校准参数。设备没有公开完整部分负荷曲线时，代码只对额定点作显式的有限温度修正，并在结果中标注“无完整性能曲线”。参考一致性和敏感性不能写成真实楼宇精度或节能收益。

## 型号与费用

`equipment.py` 保存三个同类、两个品牌的公开额定点：美的 MSAGBU-12HRFN8/MOX201-12HFN8、美的 GAIA-12HRFN8、大金 FTXF35E5V1B/RXF35F5V1B。每条档案保留原始网页、额定制冷量、额定输入及适用范围；厂家未发布的 SHR、设备报价、安装和维护费用必须由用户覆盖，缺失费用不会静默当作 0。工作台中的参考报价明确标为用户本次情景，不能视为采购承诺。

`lifecycle.py` 按真实时间间隔汇总逐月电量，并将用户确认的价格情景映射到研究期；初始投资只计入第 0 年，运行费用从第 1 年开始，寿命短于研究期才发生更换。当前长期费用默认重复一份参考年，除非用户提供多年份序列，因此不称未来电价预测。

## 接口与第二阶段

结果同时输出 `WeatherContext`、`LoadSeries`、`EquipmentProfile` 和现金流对象。`LoadSeries` 保留逐时功率、冷量、潜热量、时间间隔和范围，后续光伏先接同一时间轴，再接风电；本轮不生成任何发电仪表盘或收益结论。

来源：

- Open-Meteo Historical Weather API: https://open-meteo.com/en/docs/historical-weather-api
- Open-Meteo API docs: https://open-meteo.com/en/docs
- PsychroLib: https://psychrometrics.github.io/psychrolib/
- Midea MSAGBU-12HRFN8 / MOX201-12HFN8: https://www.midea.com/it/hvac/monosplit/xtreme/climatizzatore-xtreme-msagbu-12hrfn8-mox201-12hfn8
- Midea GAIA-12HRFN8: https://www.midea.com/ge-en/air-conditioners/inverter-conditioner/conditioner-gaia-12hrfn8.gaia-12hrfn8
- Daikin FTXF35E5V1B / RXF35F5V1B: https://energylabel.daikin.eu/eu/en_US/lot10/jcr%3Acontent/root/services.json/lot10/datasheet/html?locale=en_US&product=FTXF35E5V1B+%2F+RXF35F5V1B
