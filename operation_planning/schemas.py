"""Shared, JSON-serialisable contracts for the operation-planning workbench."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import re


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (list, dict, str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass
class TaskSpec:
    """A fully specified simulation request.

    Business schedule and physical occupancy/internal gains are deliberately
    separate.  The adapter never silently guesses a missing simulation date.
    """

    task_id: str
    testcase: str = "bestest_air"
    testcase_version: str = "v0.9.0"
    model_commit: str = "9b1610bf7a108826bb3d22c72bffd2d71d7bb0a9"
    simulation_day: int = 153
    business_start_hour: int = 8
    business_end_hour: int = 18
    occupancy_profile: str = "official_bestest_air"
    internal_gains_profile: str = "official_bestest_air"
    lower_temp_c: float = 21.0
    upper_temp_c: float = 24.0
    tolerance_c: float = 0.25
    pre_cool_minutes: int = 60
    recovery_hours: int = 24
    objective: str = "cost"
    price_profile: str = "dynamic"
    # Optional regional tariff scenario.  ``price_profile`` remains for
    # backwards compatibility with the BOPTEST USD fixtures.
    tariff_id: str = "boptest_dynamic"
    region_id: str = "model_reference"
    tariff_calendar_date: Optional[str] = None
    custom_tariff: Optional[Dict[str, Any]] = None
    revision: int = 1
    max_candidates: int = 12
    source: str = "official_boptest_local_fmu"
    user_request: str = ""
    user_confirmed: bool = False
    requested_lower_temp_c: Optional[float] = None
    requested_upper_temp_c: Optional[float] = None
    constraint_notes: str = ""

    def validate(self) -> List[str]:
        errors: List[str] = []
        if self.testcase != "bestest_air":
            errors.append("当前版本仅支持 bestest_air")
        if not 1 <= int(self.simulation_day) <= 365:
            errors.append("simulation_day 必须为 1..365")
        if not 0 <= self.business_start_hour < self.business_end_hour <= 24:
            errors.append("营业时段必须为合法的开始/结束小时")
        if self.lower_temp_c >= self.upper_temp_c:
            errors.append("温度下限必须小于上限")
        if self.tolerance_c < 0 or self.tolerance_c > 2:
            errors.append("温度容差必须在 0..2°C")
        if self.pre_cool_minutes not in (0, 30, 60, 90, 120):
            errors.append("预冷时长只能取 0/30/60/90/120 分钟")
        if self.recovery_hours < 24 or self.recovery_hours > 48:
            errors.append("恢复观察窗口必须在 24..48 小时")
        if self.objective not in ("cost", "energy"):
            errors.append("目标只能是 cost 或 energy")
        if self.price_profile not in ("constant", "dynamic", "highly_dynamic", "region", "custom"):
            errors.append("电价情景不受支持")
        if not 1 <= self.max_candidates <= 36:
            errors.append("候选方案数必须在 1..36")
        if self.requested_lower_temp_c is not None and self.requested_upper_temp_c is not None and self.requested_lower_temp_c >= self.requested_upper_temp_c:
            errors.append("用户要求的温度范围无效")
        if self.tariff_calendar_date:
            try:
                import datetime as _dt
                _dt.date.fromisoformat(str(self.tariff_calendar_date))
            except ValueError:
                errors.append("tariff_calendar_date 必须为 YYYY-MM-DD")
        if int(self.revision) < 1:
            errors.append("任务修订版本必须为正整数")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlanSegment:
    start_minute: int
    end_minute: int
    cooling_setpoint_c: float
    heating_setpoint_c: float
    reason: str = ""


@dataclass
class PlanSpec:
    plan_id: str
    kind: str
    segments: List[PlanSegment]
    objective: str = "cost"
    price_profile: str = "dynamic"
    provenance: str = "program_generated"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["segments"] = [asdict(s) for s in self.segments]
        return data


@dataclass
class SimulationResult:
    result_id: str
    task_id: str
    plan_id: str
    testcase: str
    testcase_version: str
    simulation_day: int
    step_seconds: int
    target_period: Tuple[int, int]
    recovery_period: Tuple[int, int]
    time_seconds: List[float]
    temperature_c: List[float]
    electric_power_w: List[float]
    heating_power_w: List[float]
    kpis: Dict[str, float]
    custom_metrics: Dict[str, float]
    feasible: bool
    rejection_reasons: List[str] = field(default_factory=list)
    runtime_seconds: float = 0.0
    cache_key: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    control_schedule: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionReport:
    task: Dict[str, Any]
    candidates: List[Dict[str, Any]]
    feasible: bool
    recommended_plan_id: Optional[str]
    recommendation_reason: str
    unresolved_requirements: List[str] = field(default_factory=list)
    agent_trace: List[Dict[str, Any]] = field(default_factory=list)
    generated_at_utc: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegionProfile:
    """A deliberately narrow supply-area profile, not a nationwide lookup."""

    region_id: str
    province: str
    city: str
    supply_area: str
    timezone: str
    supported_tariffs: List[str] = field(default_factory=list)


@dataclass
class TariffProfile:
    """Versioned tariff data with provenance and explicit billing scope."""

    tariff_id: str
    version: str
    area: str
    category: str
    voltage_level: str
    billing_type: str
    price_type: str
    effective_start: str
    effective_end: str
    currency: str
    unit: str
    periods: List[Dict[str, Any]]
    source_url: str
    source_title: str
    verified: bool
    inclusions: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class SimulationContext:
    """Physical model clock is kept separate from billing-calendar clock."""

    model: str
    model_version: str
    weather_sample_date: str
    simulation_day: int
    timezone: str = "UTC"
    initial_conditions: str = "official model warm-up"


@dataclass
class SiteContext:
    site_id: str
    name: str
    latitude: float
    longitude: float
    timezone: str
    elevation_m: Optional[float] = None
    source: str = ""


@dataclass
class WeatherContext:
    site: SiteContext
    source: str
    dataset_kind: str
    start: str
    end: str
    variables: List[str]
    units: Dict[str, str]
    wind_height_m: Optional[float] = None
    missing_count: int = 0
    notes: List[str] = field(default_factory=list)
    requested_model: Optional[str] = None
    response_model: Optional[str] = None


@dataclass
class LoadSeries:
    timestamps: List[str]
    interval_seconds: List[int]
    electric_power_w: List[float]
    cooling_load_w: List[float]
    latent_load_w: List[float]
    source: str
    scope: str
    temperature_unmet_degree_hours: List[float] = field(default_factory=list)
    rh_unmet_percent_hours: List[float] = field(default_factory=list)
    capacity_shortfall_w: List[float] = field(default_factory=list)
    equipment_count: int = 1
    model_version: str = ""
    assumptions: List[str] = field(default_factory=list)
    service_scope: str = "cooling_only"


@dataclass
class EquipmentProfile:
    equipment_id: str
    brand: str
    model: str
    combination: str
    rated_cooling_kw: float
    rated_input_kw: float
    cop: float
    shr: Optional[float]
    operating_range: Dict[str, Any]
    price_cny: Optional[float]
    installation_cny: Optional[float]
    maintenance_cny_per_year: Optional[float]
    expected_life_years: int
    source: str
    source_type: str = "public_datasheet_or_user_quote"
    limitations: List[str] = field(default_factory=list)


@dataclass
class CashFlowScenario:
    study_years: int
    discount_rate: float
    equipment_cny: Optional[float]
    installation_cny: Optional[float]
    electricity_cny: Optional[float]
    maintenance_cny: Optional[float]
    replacement_cny: Optional[float]
    residual_cny: Optional[float]
    source_notes: List[str] = field(default_factory=list)


def stable_hash(payload: Any) -> str:
    """Hash only canonical physical inputs, never labels or expected outcomes."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_jsonable).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
