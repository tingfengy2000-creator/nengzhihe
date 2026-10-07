"""Small, provenance-first regional tariff registry and integrator.

The registry intentionally contains a small set of historical, verified
official profiles plus one explicitly provisional latest Guangzhou profile and
a user supplied custom profile.  It is not a nationwide tariff service.
Physical model output is evaluated first and tariff prices are then applied to
the same time series, so changing a tariff never changes the temperature or
electrical trajectory.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .schemas import RegionProfile, TariffProfile, stable_hash


FUJIAN_URL = "https://www.dehua.gov.cn/zwgk/zdxxgk/ggqsy/gd/202607/t20260715_3309391.htm"
GUANGDONG_URL = "https://www.heyuan.gov.cn/zwgk/ggqsydwxx/gd/content/post_709619.html"
# The October 2026 table was located in the public Guangdong tariff index while
# the original CSG attachment was not yet exposed by the searchable government
# pages.  Keep the profile explicitly provisional until the original PDF is
# independently retrieved and checked; it must not be described as verified
# official evidence in a submission.
GUANGZHOU_202610_INDEX_URL = "https://energydc.cn/policy/guangdong/2026-09/ffdcada5-baab-11f1-959b-ce30ac533824"


REGIONS: Dict[str, RegionProfile] = {
    "fujian_dehua": RegionProfile("fujian_dehua", "福建省", "德化县", "国网福建省电力有限公司代理购电区域", "Asia/Shanghai", ["fujian_industrial_lt1kv_202607"]),
    "guangdong_north": RegionProfile("guangdong_north", "广东省", "河源市（粤北山区）", "广东电网粤北山区供电区域", "Asia/Shanghai", ["guangdong_north_industrial_lt1kv_202607"]),
    "guangzhou_prd": RegionProfile("guangzhou_prd", "广东省", "广州（珠三角六市）", "广东电网珠三角六市供电区域", "Asia/Shanghai", ["guangzhou_industrial_lt1kv_202610", "guangzhou_industrial_lt1kv_202110"]),
    "model_reference": RegionProfile("model_reference", "模型参考", "模型日期", "固定模型天气样本，不对应当地楼宇", "UTC", ["boptest_dynamic", "boptest_constant", "boptest_highly_dynamic"]),
}


TARIFFS: Dict[str, TariffProfile] = {
    "fujian_industrial_lt1kv_202607": TariffProfile(
        tariff_id="fujian_industrial_lt1kv_202607",
        version="2026-07-official-v1",
        area="福建省国网代理购电工商业区域（德化供电区示例）",
        category="工商业单一制",
        voltage_level="不满1kV",
        billing_type="单一制电度电费",
        price_type="TOU",
        effective_start="2026-07-01",
        effective_end="2026-07-31",
        currency="CNY",
        unit="CNY/kWh",
        periods=[
            {"name": "valley", "start": "00:00", "end": "08:00", "price": 0.40579316},
            {"name": "peak", "start": "10:00", "end": "12:00", "price": 0.85626769},
            {"name": "peak", "start": "15:00", "end": "20:00", "price": 0.85626769},
            {"name": "peak", "start": "21:00", "end": "22:00", "price": 0.85626769},
            {"name": "super_peak", "start": "11:00", "end": "12:00", "price": 0.93817215, "months": [7, 8, 9]},
            {"name": "super_peak", "start": "17:00", "end": "18:00", "price": 0.93817215, "months": [7, 8, 9]},
            {"name": "flat", "start": "00:00", "end": "24:00", "price": 0.64033775},
        ],
        source_url=FUJIAN_URL,
        source_title="国网福建省电力有限公司代理购电工商业用户电价表（7月）",
        verified=True,
        inclusions=["工商业单一制不满1kV电度电费", "按官方峰平谷时段计价"],
        exclusions=["不含需量/容量基本电费", "不含燃气供热费用", "不代表建筑总表"],
        notes=["官方时段：谷00:00–08:00；峰10:00–12:00、15:00–20:00、21:00–22:00；其余平段。7–9月11:00–12:00、17:00–18:00为尖峰覆盖。", "历史档案，日期超出有效期时必须显式选择并提示。"],
    ),
    "guangzhou_industrial_lt1kv_202110": TariffProfile(
        tariff_id="guangzhou_industrial_lt1kv_202110",
        version="2021-10-official-v1",
        area="广州市（广州、珠海、佛山、中山、东莞五市）一般工商业不满1kV",
        category="一般工商业原普通工业专变用户",
        voltage_level="不满1kV",
        billing_type="单一制电度电费",
        price_type="TOU",
        effective_start="2021-10-01",
        effective_end="2021-12-31",
        currency="CNY",
        unit="CNY/kWh",
        periods=[
            {"name": "valley", "start": "00:00", "end": "08:00", "price": 0.2556},
            {"name": "peak", "start": "10:00", "end": "12:00", "price": 1.1433},
            {"name": "peak", "start": "14:00", "end": "19:00", "price": 1.1433},
            {"name": "super_peak", "start": "11:00", "end": "12:00", "price": 1.4291, "months": [7, 8, 9]},
            {"name": "super_peak", "start": "15:00", "end": "17:00", "price": 1.4291, "months": [7, 8, 9]},
            {"name": "flat", "start": "00:00", "end": "24:00", "price": 0.6725},
        ],
        source_url="https://fgw.gz.gov.cn/ztzl/gzsfzggwzdlyxxgkzl/ys/content/post_9497778.html",
        source_title="广东省发展改革委粤发改价格〔2021〕331号附件：广州、珠海、佛山、中山、东莞五市电价价目表（2021年10月1日起）",
        verified=True,
        inclusions=["广州五市一般工商业不满1kV电度电价", "峰平谷与7–9月尖峰时段规则"],
        exclusions=["不含政府性基金及附加", "不含需量/容量基本电费", "仅适用于原普通工业专变用户；普通商业用户不自动适用", "不是2024年度广州实际账单"],
        notes=["官方表格单位为分/千瓦时：平67.25、谷25.56、峰114.33；尖峰按峰段上浮25%并按表格四舍五入。", "本档案有效期登记为2021-10-01至2021-12-31；套用2024参考天气必须显式选择 tariff_application=current_tariff_on_reference_weather，不能绕过默认日期校验。"],
    ),
    "guangdong_north_industrial_lt1kv_202607": TariffProfile(
        tariff_id="guangdong_north_industrial_lt1kv_202607",
        version="2026-07-official-v1",
        area="广东省粤北山区（河源等官方适用区域）",
        category="工商业单一制",
        voltage_level="不满1kV",
        billing_type="单一制电度电费",
        price_type="TOU",
        effective_start="2026-07-01",
        effective_end="2026-07-31",
        currency="CNY",
        unit="CNY/kWh",
        periods=[
            {"name": "valley", "start": "00:00", "end": "08:00", "price": 0.26826875},
            {"name": "peak", "start": "10:00", "end": "12:00", "price": 1.10426875},
            {"name": "peak", "start": "14:00", "end": "19:00", "price": 1.10426875},
            {"name": "super_peak", "start": "11:00", "end": "12:00", "price": 1.37346875, "months": [7, 8, 9]},
            {"name": "super_peak", "start": "15:00", "end": "17:00", "price": 1.37346875, "months": [7, 8, 9]},
            {"name": "flat", "start": "00:00", "end": "24:00", "price": 0.66096875},
        ],
        source_url=GUANGDONG_URL,
        source_title="广东电网代理购电工商业用户电价表（粤北山区7月）",
        verified=True,
        inclusions=["粤北山区工商业单一制不满1kV电度电费", "按官方峰平谷及时段尖峰规则计价"],
        exclusions=["不含需量/容量基本电费", "不含燃气供热费用", "不代表广东全省或建筑总表"],
        notes=["官方适用区域为粤北山区；谷00:00–08:00，峰10:00–12:00、14:00–19:00，其余平段。7–9月11:00–12:00、15:00–17:00尖峰覆盖。", "历史档案，日期超出有效期时必须显式选择并提示。"],
    ),
    "guangzhou_industrial_lt1kv_202610": TariffProfile(
        tariff_id="guangzhou_industrial_lt1kv_202610",
        version="2026-10-provisional-v1",
        area="广东省珠三角六市（含广州、珠海、佛山、中山、东莞、江门除恩平/台山/开平）",
        category="工商业单一制",
        voltage_level="不满1kV",
        billing_type="单一制电度电费",
        price_type="TOU",
        effective_start="2026-10-01",
        effective_end="2026-10-31",
        currency="CNY",
        unit="CNY/kWh",
        periods=[
            {"name": "valley", "start": "00:00", "end": "08:00", "price": 0.32136875},
            {"name": "peak", "start": "10:00", "end": "12:00", "price": 1.34176875},
            {"name": "peak", "start": "14:00", "end": "19:00", "price": 1.34176875},
            {"name": "super_peak", "start": "11:00", "end": "12:00", "price": 1.67036875, "months": [7, 8, 9]},
            {"name": "super_peak", "start": "15:00", "end": "17:00", "price": 1.67036875, "months": [7, 8, 9]},
            {"name": "flat", "start": "00:00", "end": "24:00", "price": 0.80066875},
        ],
        source_url=GUANGZHOU_202610_INDEX_URL,
        source_title="广东电网有限责任公司关于2026年10月代理购电工商业用户价格的公告（珠三角六市；原始公告待核验）",
        verified=False,
        inclusions=["珠三角六市工商业单一制不满1kV电度电费（当前公开索引转录）", "峰平谷与7–9月尖峰时段规则"],
        exclusions=["不含需量/容量基本电费", "不含建筑总表其他负荷", "原始广东电网公告PDF尚未从官方可检索入口取得；不得写作已完成官方核验"],
        notes=[
            "公开索引标示适用广州、珠海、佛山、中山、东莞、江门六市（不含恩平、台山、开平），执行时间2026-10。",
            "不满1kV单一制：平0.80066875、谷0.32136875、峰1.34176875、尖峰1.67036875元/kWh；原表单位为分/kWh并含税。",
            "尖峰价格仅在7–9月全月及广州日最高气温≥35℃高温日11–12、15–17执行；本档案按官方时段规则保留，当前有效期为10月。",
            "价格数值和适用区域待直接核对广东电网原始公告PDF后再将verified改为True；套用2024参考天气必须显式选择tariff_application=current_tariff_on_reference_weather。",
        ],
    ),
}


def registry() -> Dict[str, Any]:
    return {
        "regions": [asdict(x) for x in REGIONS.values()],
        "tariffs": [asdict(x) for x in TARIFFS.values()],
        "scope": "仅为空调冷却设备与风机计算电功率做地区电价情景试算，不含建筑总表、需量/容量基本电费或燃气供热。",
    }


def profile(tariff_id: str, custom: Optional[Dict[str, Any]] = None) -> TariffProfile:
    if tariff_id == "custom_user":
        if not custom:
            raise ValueError("自定义电价需要提供完整分时价格")
        return custom_profile(custom)
    if tariff_id not in TARIFFS:
        raise ValueError(f"未支持的电价档案：{tariff_id}")
    return TARIFFS[tariff_id]


def custom_profile(data: Dict[str, Any]) -> TariffProfile:
    required = ["effective_start", "effective_end", "periods"]
    missing = [x for x in required if not data.get(x)]
    if missing:
        raise ValueError("自定义电价缺少：" + ",".join(missing))
    periods = data["periods"]
    if not isinstance(periods, list) or not periods:
        raise ValueError("自定义电价至少需要一个分时时段")
    return TariffProfile(
        tariff_id="custom_user",
        version=str(data.get("version", "user-supplied-v1")),
        area=str(data.get("area", "用户提供供电区域")),
        category=str(data.get("category", "用户确认类别")),
        voltage_level=str(data.get("voltage_level", "用户确认电压")),
        billing_type=str(data.get("billing_type", "单一制电度电费")),
        price_type="TOU",
        effective_start=str(data["effective_start"]),
        effective_end=str(data["effective_end"]),
        currency="CNY",
        unit="CNY/kWh",
        periods=periods,
        source_url="user-supplied",
        source_title="用户提供电价（未作官方核验）",
        verified=False,
        inclusions=["用户录入的空调冷却与风机电量范围"],
        exclusions=["未核验的需量/容量费用", "建筑总表和燃气热量"],
        notes=["用户提供档案，使用前由用户确认类别、电压和有效期。"],
    )


def tariff_hash(tariff: TariffProfile) -> str:
    return stable_hash(asdict(tariff))


def validate_profile(tariff: TariffProfile, calendar_start: date, days: int) -> None:
    start = date.fromisoformat(tariff.effective_start)
    end = date.fromisoformat(tariff.effective_end)
    if start > end:
        raise ValueError("电价有效期无效")
    if calendar_start < start or calendar_start + timedelta(days=max(days - 1, 0)) > end:
        raise ValueError(f"电价档案未覆盖完整评价时段：{tariff.effective_start} 至 {tariff.effective_end}")
    if not tariff.periods:
        raise ValueError("电价没有分时时段")
    if days < 1:
        raise ValueError("电价评价天数必须为正")
    # Check coverage and precedence on every calendar day.  A full-day flat
    # entry is the normal fallback; custom profiles may instead tile the day.
    for day in range(days):
        d = calendar_start + timedelta(days=day)
        intervals: List[Tuple[int, int, str, float]] = []
        for item in tariff.periods:
            months = item.get("months")
            if months and d.month not in months:
                continue
            a, b = _clock(item.get("start")), _clock(item.get("end"))
            if b <= a:
                b = 86400
            price = float(item.get("price"))
            if price < 0:
                raise ValueError("电价不能为负")
            intervals.append((a, b, str(item.get("name", "flat")), price))
        boundaries = sorted({0, 86400, *(x for item in intervals for x in item[:2])})
        for left, right in zip(boundaries, boundaries[1:]):
            if left == right:
                continue
            if not any(a <= left and right <= b for a, b, _, _ in intervals):
                raise ValueError(f"电价档案在 {d} {left}s 缺少覆盖")
        for i, (a, b, name, _) in enumerate(intervals):
            if float(item_price(tariff, name, d.month, a)) < 0:
                raise ValueError("电价不能为负")
            for c, d2, name2, _ in intervals[i + 1 :]:
                if max(a, c) < min(b, d2) and name != "flat" and name2 != "flat":
                    # flat is the default filler; explicit peak/super/valley
                    # overlap is only legal when super_peak intentionally
                    # overrides peak.
                    if {name, name2} != {"peak", "super_peak"}:
                        raise ValueError(f"电价时段重叠：{name}/{name2}")


def _clock(value: str) -> int:
    if value == "24:00":
        return 86400
    parts = str(value).split(":")
    if len(parts) != 2:
        raise ValueError(f"无效时刻：{value}")
    hour, minute = int(parts[0]), int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"无效时刻：{value}")
    return hour * 3600 + minute * 60


def item_price(tariff: TariffProfile, name: str, month: int, second: int) -> float:
    for item in tariff.periods:
        if str(item.get("name", "flat")) != name:
            continue
        months = item.get("months")
        if months and month not in months:
            continue
        a, b = _clock(item["start"]), _clock(item["end"])
        if b <= a:
            b = 86400
        if a <= second < b:
            return float(item["price"])
    # This is only reached for a named fallback and is an error for malformed
    # custom profiles; never silently use zero.
    raise ValueError(f"缺少 {name} 时段单价")


def rate_at(tariff: TariffProfile, calendar: date, second: int, *, validate_dates: bool = True) -> Tuple[str, float]:
    if validate_dates:
        validate_profile(tariff, calendar, 1)
    candidates: List[Tuple[str, int, float]] = []
    for item in tariff.periods:
        months = item.get("months")
        if months and calendar.month not in months:
            continue
        a, b = _clock(item["start"]), _clock(item["end"])
        if b <= a:
            b = 86400
        if a <= second < b:
            rank = {"super_peak": 4, "peak": 3, "flat": 1, "valley": 2}.get(str(item.get("name")), 0)
            candidates.append((str(item.get("name", "flat")), rank, float(item["price"])))
    if not candidates:
        raise ValueError(f"电价档案在 {calendar} {second}s 缺少覆盖")
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0], candidates[0][2]


def integrate_power(times: Sequence[float], power_w: Sequence[float], tariff: TariffProfile, calendar_start: date, start: float, end: float, timeline_origin: Optional[float] = None) -> Tuple[float, Dict[str, float]]:
    """Integrate W over actual intervals, splitting at price jumps."""
    if len(times) != len(power_w):
        raise ValueError("功率与时间轴长度不一致")
    origin = float(start if timeline_origin is None else timeline_origin)
    days = max(1, int((max(end, origin + 1.0) - origin + 86400 - 1) // 86400))
    validate_profile(tariff, calendar_start, days)
    total = 0.0
    by_period: Dict[str, float] = {}
    for ta, tb, pa, pb in zip(times, times[1:], power_w, power_w[1:]):
        left, right = max(float(ta), start), min(float(tb), end)
        if right <= left:
            continue
        # Include tariff transitions and midnight boundaries inside the FMU
        # interval.  Linear power interpolation remains valid within each
        # constant-price fragment.
        cuts = [left, right]
        rel_day_left = left - origin
        rel_day_right = right - origin
        for n in range(int(rel_day_left // 86400), int(rel_day_right // 86400) + 1):
            base = origin + n * 86400
            for item in tariff.periods:
                cuts.extend([base + _clock(item["start"]), base + (86400 if _clock(item["end"]) <= _clock(item["start"]) else _clock(item["end"]))])
        cuts = sorted({x for x in cuts if left <= x <= right})
        span = max(float(tb - ta), 1e-9)
        for x, y in zip(cuts, cuts[1:]):
            va = float(pa) + (float(pb) - float(pa)) * (x - float(ta)) / span
            vb = float(pa) + (float(pb) - float(pa)) * (y - float(ta)) / span
            mid = (x + y) / 2.0
            day = calendar_start + timedelta(days=int((mid - origin) // 86400))
            sec = int((mid - origin) % 86400)
            name, price = rate_at(tariff, day, sec)
            kwh = max(0.0, (va + vb) * (y - x) / 2.0 / 3600000.0)
            cost = kwh * price
            total += cost
            by_period[name] = by_period.get(name, 0.0) + cost
    return total, by_period


def profile_public_dict(tariff: TariffProfile) -> Dict[str, Any]:
    data = asdict(tariff)
    data["hash"] = tariff_hash(tariff)
    data["status"] = "verified" if tariff.verified else "user-supplied"
    return data
