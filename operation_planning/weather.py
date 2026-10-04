"""Offline-first Open-Meteo weather context and bounded user CSV import."""
from __future__ import annotations
from dataclasses import asdict
import csv, hashlib, io, json
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .schemas import SiteContext, WeatherContext
BASE = Path(__file__).resolve().parent
WEATHER_DIR = BASE / "data" / "weather"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
VARIABLES = ["temperature_2m", "relative_humidity_2m", "surface_pressure", "shortwave_radiation", "wind_speed_10m", "wind_direction_10m"]
UNITS = {"temperature_2m": "°C", "relative_humidity_2m": "%", "surface_pressure": "hPa", "shortwave_radiation": "W/m² hourly average", "wind_speed_10m": "km/h", "wind_direction_10m": "°"}
SITES = {"guangzhou": {"name": "广州", "latitude": 23.1291, "longitude": 113.2644, "file": "guangzhou_2024.json"}, "beijing": {"name": "北京", "latitude": 39.9042, "longitude": 116.4074, "file": "beijing_2024.json"}, "harbin": {"name": "哈尔滨", "latitude": 45.8038, "longitude": 126.5350, "file": "harbin_2024.json"}}

def _context(site_id: str, payload: Dict[str, Any]) -> WeatherContext:
    hourly = payload.get("hourly", {}); times = hourly.get("time", []); spec = SITES.get(site_id, {"name": site_id, "latitude": payload.get("latitude", 0), "longitude": payload.get("longitude", 0)})
    site = SiteContext(site_id, spec["name"], float(payload.get("latitude", spec["latitude"])), float(payload.get("longitude", spec["longitude"])), str(payload.get("timezone", "Asia/Shanghai")), float(payload.get("elevation", 0.0)), str(payload.get("source", "Open-Meteo Historical Weather API / ERA5")))
    missing = sum(sum(x is None for x in hourly.get(variable, [])) for variable in VARIABLES if variable in hourly)
    return WeatherContext(site, str(payload.get("source", "Open-Meteo Historical Weather API (ERA5)")), str(payload.get("dataset_kind", "historical_reanalysis")), str(times[0]) if times else "", str(times[-1]) if times else "", [x for x in VARIABLES if x in hourly], UNITS, 10.0, missing, ["城市级再分析代表区域条件，不是楼宇微气候实测。", "shortwave_radiation 为过去一小时平均值；不与 instant 辐照混用。"])

def _validate_payload(payload: Dict[str, Any]) -> None:
    hourly = payload.get("hourly", {}); times = hourly.get("time", [])
    if len(times) < 2: raise ValueError("天气序列至少需要两个时刻")
    required = ["temperature_2m", "relative_humidity_2m", "surface_pressure", "shortwave_radiation"]
    if any(len(hourly.get(v, [])) != len(times) for v in required): raise ValueError("天气变量缺失或长度不一致")
    from datetime import datetime
    for a, b in zip(times, times[1:]):
        dt = (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
        if dt <= 0 or dt > 3 * 3600: raise ValueError(f"天气时间轴间隔无效：{a} -> {b}")

def load_weather(site_id: str = "guangzhou", year: int = 2024) -> Dict[str, Any]:
    if site_id not in SITES: raise ValueError(f"未支持的离线演示城市：{site_id}")
    path = WEATHER_DIR / f"{site_id}_{year}.json"
    if not path.exists(): raise FileNotFoundError(f"没有离线天气缓存：{path}")
    payload = json.loads(path.read_text(encoding="utf-8")); _validate_payload(payload); context = _context(site_id, payload)
    return {"context": asdict(context), "time": payload.get("hourly", {}).get("time", []), "hourly": payload.get("hourly", {}), "source_file": str(path), "hash": _sha256(path)}

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