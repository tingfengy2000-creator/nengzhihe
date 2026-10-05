"""Offline-first Open-Meteo weather context and bounded user CSV import."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timedelta
import csv, hashlib, io, json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .schemas import SiteContext, WeatherContext
BASE = Path(__file__).resolve().parent
WEATHER_DIR = BASE / "data" / "weather"
PV_WEATHER_DIR = BASE / "data" / "weather_pv"
INTERVAL_NORMALIZATION_VERSION = "preceding-hour-right-label-v2"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
VARIABLES = ["temperature_2m", "relative_humidity_2m", "surface_pressure", "shortwave_radiation", "wind_speed_10m", "wind_direction_10m"]
PV_VARIABLES = VARIABLES + ["direct_normal_irradiance", "diffuse_radiation"]
UNITS = {"temperature_2m": "°C", "relative_humidity_2m": "%", "surface_pressure": "hPa", "shortwave_radiation": "W/m² hourly average", "wind_speed_10m": "km/h", "wind_direction_10m": "°", "direct_normal_irradiance": "W/m² hourly average", "diffuse_radiation": "W/m² hourly average"}
SITES = {"guangzhou": {"name": "广州", "latitude": 23.1291, "longitude": 113.2644, "file": "guangzhou_2024.json"}, "beijing": {"name": "北京", "latitude": 39.9042, "longitude": 116.4074, "file": "beijing_2024.json"}, "harbin": {"name": "哈尔滨", "latitude": 45.8038, "longitude": 126.5350, "file": "harbin_2024.json"}}

def _context(site_id: str, payload: Dict[str, Any]) -> WeatherContext:
    hourly = payload.get("hourly", {}); times = hourly.get("time", []); spec = SITES.get(site_id, {"name": site_id, "latitude": payload.get("latitude", 0), "longitude": payload.get("longitude", 0)})
    provenance = payload.get("_phase2_provenance", {})
    site = SiteContext(site_id, spec["name"], float(payload.get("latitude", spec["latitude"])), float(payload.get("longitude", spec["longitude"])), str(payload.get("timezone", "Asia/Shanghai")), float(payload.get("elevation", 0.0)), str(payload.get("source", "Open-Meteo Historical Weather API")))
    missing = sum(sum(x is None for x in hourly.get(variable, [])) for variable in VARIABLES if variable in hourly)
    notes = ["城市级再分析代表区域条件，不是楼宇微气候实测。", "shortwave_radiation 为过去一小时平均值；不与 instant 辐照混用。"]
    requested = provenance.get("requested_model") or payload.get("requested_model")
    response = provenance.get("response_model_metadata") or payload.get("response_model")
    if requested and not response:
        notes.append(f"API请求模型为 {requested}；响应未提供显式模型字段，不能仅凭来源名称声称响应模型。")
    return WeatherContext(site, str(payload.get("source", "Open-Meteo Historical Weather API")), str(payload.get("dataset_kind", "historical_reanalysis")), str(times[0]) if times else "", str(times[-1]) if times else "", [x for x in VARIABLES if x in hourly], UNITS, 10.0, missing, notes, requested, response)

def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _format_time(value: datetime) -> str:
    return value.isoformat(timespec="minutes")


def _validate_payload(payload: Dict[str, Any]) -> None:
    hourly = payload.get("hourly", {}); times = hourly.get("time", [])
    if len(times) < 2: raise ValueError("天气序列至少需要两个时刻")
    required = ["temperature_2m", "relative_humidity_2m", "surface_pressure", "shortwave_radiation"]
    if any(len(hourly.get(v, [])) != len(times) for v in required): raise ValueError("天气变量缺失或长度不一致")
    for a, b in zip(times, times[1:]):
        dt = (_parse_time(b) - _parse_time(a)).total_seconds()
        if dt <= 0 or dt > 3 * 3600: raise ValueError(f"天气时间轴间隔无效：{a} -> {b}")


def normalize_preceding_hour_payload(
    payload: Dict[str, Any], *, calendar_start: Optional[str] = None,
    calendar_end: Optional[str] = None, boundary_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convert right-labelled preceding-hour radiation to left intervals.

    At source timestamp ``t`` Open-Meteo's hourly radiation is the mean over
    ``[t-dt,t)``.  The normalized row for ``[t,t+dt)`` therefore takes
    radiation from row ``t+dt`` while retaining instantaneous weather from
    row ``t``.  The last row must come from a real boundary record.
    """
    _validate_payload(payload)
    hourly = payload.get("hourly", {}) or {}
    raw_times = [str(x) for x in hourly.get("time", [])]
    raw_dt = int((_parse_time(raw_times[1]) - _parse_time(raw_times[0])).total_seconds())
    start = _parse_time(calendar_start) if calendar_start else _parse_time(raw_times[0])
    end = _parse_time(calendar_end) if calendar_end else _parse_time(raw_times[-1])
    if _parse_time(raw_times[0]) != start:
        raise ValueError(f"天气原始首行不是评价区间起点：{raw_times[0]}")
    if end <= start or (end - start).total_seconds() % raw_dt:
        raise ValueError("天气评价区间边界与采样间隔不一致")
    n = int((end - start).total_seconds() // raw_dt)
    if len(raw_times) != n:
        raise ValueError(f"天气原始行数与评价区间不一致：{len(raw_times)} != {n}")
    expected_raw = [start + timedelta(seconds=i * raw_dt) for i in range(n)]
    if [_parse_time(x) for x in raw_times] != expected_raw:
        raise ValueError("天气原始时间轴缺测、重复或不连续")
    boundary_hourly = (boundary_payload or {}).get("hourly", {}) or {}
    boundary_times = [str(x) for x in boundary_hourly.get("time", [])]
    if not boundary_times or _parse_time(boundary_times[0]) != end:
        raise ValueError(f"需要独立边界记录 {_format_time(end)}，不得复制、补零或循环移位")
    combined: Dict[str, List[Any]] = {}
    for variable in set(hourly) | set(boundary_hourly):
        if variable == "time":
            continue
        values = list(hourly.get(variable, [])); tail = list(boundary_hourly.get(variable, []))
        if variable in hourly and (len(values) != n or not tail):
            raise ValueError(f"天气边界缺少变量：{variable}")
        if variable in hourly:
            combined[variable] = values + [tail[0]]
    radiation = {"shortwave_radiation", "direct_normal_irradiance", "diffuse_radiation"}
    normalized_hourly: Dict[str, Any] = {"time": [_format_time(x) for x in expected_raw]}
    for variable, values in combined.items():
        normalized_hourly[variable] = values[1:n + 1] if variable in radiation else values[:n]
    interval_start = [_format_time(x) for x in expected_raw]
    interval_end = [_format_time(x + timedelta(seconds=raw_dt)) for x in expected_raw]
    normalized = dict(payload); normalized["hourly"] = normalized_hourly
    normalized["_interval_semantics"] = {
        "version": INTERVAL_NORMALIZATION_VERSION,
        "radiation": "source timestamp is right label for preceding-hour mean",
        "instantaneous": "temperature/RH/pressure/wind retain interval-start source row",
        "source_timestamp": interval_end,
        "instant_source_timestamp": interval_start,
        "interval_start": interval_start,
        "interval_end": interval_end,
        "representative_time": [_format_time(x + timedelta(seconds=raw_dt / 2)) for x in expected_raw],
        "interval_seconds": [raw_dt] * n,
        "calendar_start": interval_start[0],
        "calendar_end": interval_end[-1],
        "raw_row_count": n,
        "boundary_source_timestamp": _format_time(end),
    }
    # Expose the physical interval columns at the adapter boundary as well as
    # in the provenance object, so downstream consumers cannot infer them
    # from a bare timestamp string.
    normalized["time"] = interval_start
    normalized["interval_seconds"] = [raw_dt] * n
    normalized["source_timestamp"] = interval_end
    normalized["interval_start"] = interval_start
    normalized["interval_end"] = interval_end
    normalized["representative_time"] = normalized["_interval_semantics"]["representative_time"]
    return normalized


def _load_boundary(directory: Path, site_id: str, year: int) -> Tuple[Dict[str, Any], Path]:
    path = directory / "boundaries" / f"{site_id}_{year}_end.json"
    if not path.exists():
        raise FileNotFoundError(f"缺少天气评价区间末端边界记录：{path}")
    return json.loads(path.read_text(encoding="utf-8")), path


def _normalized_hash(source_path: Path, boundary_path: Path, normalized: Dict[str, Any]) -> str:
    digest = hashlib.sha256(source_path.read_bytes() + boundary_path.read_bytes())
    digest.update(json.dumps(normalized.get("_interval_semantics", {}), ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def _load_normalized(directory: Path, site_id: str, year: int, *, require_pv: bool) -> Dict[str, Any]:
    path = directory / f"{site_id}_{year}.json"
    if not path.exists(): raise FileNotFoundError(f"没有离线天气缓存：{path}")
    payload = json.loads(path.read_text(encoding="utf-8")); _validate_payload(payload)
    boundary, boundary_path = _load_boundary(directory, site_id, year)
    normalized = normalize_preceding_hour_payload(payload, calendar_start=f"{year:04d}-01-01T00:00", calendar_end=f"{year + 1:04d}-01-01T00:00", boundary_payload=boundary)
    hourly = normalized["hourly"]; required = ["temperature_2m", "relative_humidity_2m", "surface_pressure", "shortwave_radiation"]
    if require_pv: required += ["direct_normal_irradiance", "diffuse_radiation", "wind_speed_10m"]
    if any(len(hourly.get(v, [])) != len(hourly.get("time", [])) for v in required) or any(any(x is None for x in hourly.get(v, [])) for v in required):
        raise ValueError("归一化天气变量缺失或含缺测")
    context = _context(site_id, normalized)
    if require_pv:
        context.variables = [x for x in PV_VARIABLES if x in hourly]
        context.notes.extend(["GHI/DNI/DHI按右标记源行转换为左区间均值。", "pvlib使用显式温度和10米风速，不使用默认20℃/0风速。"])
    else:
        context.notes.append("辐照右标记已转换为左区间；温度、湿度、压力和风速保留区间起点源值。")
    return {"context": asdict(context), "time": hourly["time"], "hourly": hourly, "source_file": str(path), "boundary_file": str(boundary_path), "hash": _normalized_hash(path, boundary_path, normalized), "weather_normalization": normalized["_interval_semantics"], "interval_seconds": normalized["_interval_semantics"]["interval_seconds"], "pv_provenance": payload.get("_phase2_provenance", {})}


def load_weather(site_id: str = "guangzhou", year: int = 2024) -> Dict[str, Any]:
    if site_id not in SITES: raise ValueError(f"未支持的离线演示城市：{site_id}")
    return _load_normalized(WEATHER_DIR, site_id, year, require_pv=False)


def load_pv_weather(site_id: str = "guangzhou", year: int = 2024) -> Dict[str, Any]:
    """Load the phase-two cache with explicit GHI/DNI/DHI radiation components."""
    if site_id not in SITES: raise ValueError(f"未支持的离线演示城市：{site_id}")
    return _load_normalized(PV_WEATHER_DIR, site_id, year, require_pv=True)

def parse_user_csv(text: str, site_id: str = "user_csv", timezone: str = "Asia/Shanghai") -> Dict[str, Any]:
    if len(text.encode("utf-8")) > 2_000_000: raise ValueError("用户天气CSV不得超过2MB")
    reader = csv.DictReader(io.StringIO(text)); fields = set(reader.fieldnames or [])
    def find(*names):
        for name in names:
            if name in fields: return name
        return None
    mapping = {"time": find("timestamp", "time", "datetime"), "temperature_2m": find("temperature_2m", "temp_c", "outdoor_temp_c"), "relative_humidity_2m": find("relative_humidity_2m", "rh_percent", "outdoor_rh_percent"), "surface_pressure": find("surface_pressure", "pressure_hpa"), "shortwave_radiation": find("shortwave_radiation", "solar_w_m2")}
    if any(v is None for v in mapping.values()): raise ValueError("CSV需要 timestamp、temperature、RH、pressure、solar 五类字段")
    out = {k: [] for k in mapping if k != "time"}; times=[]
    for row in reader:
        ts = str(row[mapping["time"]]).strip();
        if not ts: raise ValueError("CSV含空时间戳")
        times.append(ts)
        for key, col in mapping.items():
            if key == "time": continue
            value = row[col]
            if value in (None, ""): raise ValueError(f"CSV在 {ts} 缺少 {key}")
            out[key].append(float(value))
    payload = {"latitude": 0.0, "longitude": 0.0, "timezone": timezone, "source": "user_csv", "dataset_kind": "user_uploaded", "hourly": {"time": times, **out}}
    _validate_payload(payload)
    context = _context(site_id, payload)
    return {"context": asdict(context), "time": times, "hourly": payload["hourly"], "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(), "source_file": "user_csv"}

def available_sites() -> List[Dict[str, Any]]:
    result=[]
    for site_id, spec in SITES.items():
        files=sorted(WEATHER_DIR.glob(f"{site_id}_*.json")); result.append({"site_id":site_id,"name":spec["name"],"latitude":spec["latitude"],"longitude":spec["longitude"],"cached_years":[p.stem.rsplit("_",1)[-1] for p in files]})
    return result

def fetch_weather(latitude: float, longitude: float, start_date: str, end_date: str, forecast: bool = False) -> Dict[str, Any]:
    params={"latitude":latitude,"longitude":longitude,"hourly":",".join(VARIABLES),"timezone":"auto","start_date":start_date,"end_date":end_date}; endpoint=OPEN_METEO_FORECAST if forecast else OPEN_METEO_ARCHIVE; request=Request(endpoint+"?"+urlencode(params),headers={"User-Agent":"nengzhihe-local/1.0"})
    with urlopen(request,timeout=30) as response: payload=json.loads(response.read().decode("utf-8"))
    _validate_payload(payload); return {"context":{"source":"Open-Meteo Forecast API" if forecast else "Open-Meteo Historical Weather API","dataset_kind":"forecast" if forecast else "historical_reanalysis","start":start_date,"end":end_date,"variables":VARIABLES,"units":UNITS,"timezone":payload.get("timezone"),"latitude":payload.get("latitude"),"longitude":payload.get("longitude")},"time":payload.get("hourly",{}).get("time",[]),"hourly":payload.get("hourly",{})}

def _sha256(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
